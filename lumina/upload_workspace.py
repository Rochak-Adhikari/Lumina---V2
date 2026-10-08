"""Persistent upload inventory. No migration, indexing database, or provider calls.

``root`` is the configured storage base; files live only in ``root / 'Uploads'``.
The caller must grant that base through the supplied resolver's existing policy.
"""
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
import stat


class UploadWorkspace:
    MAX_FILES = 200
    MAX_SCAN = 2000

    def __init__(self, root, resolver, file_processor):
        self.resolver = resolver
        self.file_processor = file_processor
        self.root = Path(os.path.abspath(Path(root) / 'Uploads'))

    def _directory(self):
        checked = self.resolver.path(str(self.root), must_exist=False)
        if checked != self.root:
            raise ValueError('Invalid upload directory.')
        checked.mkdir(parents=True, exist_ok=True)
        return self.resolver.path(str(checked))

    @staticmethod
    def _valid_name(name):
        return (isinstance(name, str) and 0 < len(name) <= 240
                and name == name.strip() and not name.startswith('.')
                and not name.endswith('.') and not re.search(r'[<>:"/\\|?*\x00-\x1f]', name)
                and not re.fullmatch(r'(?i)(CON|PRN|AUX|NUL|COM[0-9]|LPT[0-9])(?:\..*)?', name))

    def _entry(self, path):
        if not self._valid_name(path.name) or path.parent != self.root:
            raise ValueError('Invalid upload file.')
        checked = self.resolver.path(str(path))
        if checked != path or checked.parent != self.root:
            raise ValueError('Invalid upload file.')
        info = checked.stat(follow_symlinks=False)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError('Only ordinary upload files are available.')
        return {'id': hashlib.sha256(path.name.encode('utf-8')).hexdigest(),
                'name': path.name, 'path': str(path), 'bytes': info.st_size,
                'modified': datetime.fromtimestamp(info.st_mtime, timezone.utc).isoformat()}

    async def save(self, filename, data):
        if not self._valid_name(filename):
            return {'ok': False, 'status': 'invalid', 'error': 'The selected filename is invalid.'}
        try:
            directory = self._directory()
            self.resolver.path(str(directory / filename), must_exist=False)
            result = await self.file_processor.save_upload(directory, filename, data)
            if result.get('ok'):
                result.update(self._entry(directory / filename))
            return result
        except (OSError, ValueError):
            return {'ok': False, 'status': 'rejected', 'error': 'The file could not be stored in Uploads.'}

    def list_files(self, query=''):
        """Bounded, flat, metadata-only inventory. Hidden/protected files are omitted."""
        if not isinstance(query, str) or len(query) > 240:
            return {'ok': False, 'files': [], 'error': 'Use a search of at most 240 characters.'}
        files, truncated = [], False
        try:
            directory = self._directory()
            with os.scandir(directory) as entries:
                for count, item in enumerate(entries):
                    if count >= self.MAX_SCAN:
                        truncated = True
                        break
                    if query.casefold() not in item.name.casefold():
                        continue
                    try:
                        entry = self._entry(directory / item.name)
                    except (OSError, ValueError):
                        continue
                    if len(files) >= self.MAX_FILES:
                        truncated = True
                        break
                    files.append(entry)
            files.sort(key=lambda item: (item['name'].casefold(), item['name']))
            return {'ok': True, 'files': files, 'root': str(directory), 'truncated': truncated}
        except (OSError, ValueError):
            return {'ok': False, 'files': [], 'error': 'Upload workspace is unavailable.'}

    def resolve(self, selection):
        """Return an exact file Path by name, stable id or listed absolute path.

        No fuzzy matching or implicit latest-file fallback. Errors never echo paths.
        """
        if not isinstance(selection, str) or not selection or len(selection) > 2048:
            raise ValueError('Select an uploaded file by exact name, id or path.')
        directory = self._directory()
        candidate = Path(selection)
        if candidate.is_absolute():
            self._entry(candidate)
            return candidate
        if '/' in selection or '\\' in selection or ':' in selection or selection in {'.', '..'}:
            raise ValueError('Select a file from Uploads.')
        matches = []
        with os.scandir(directory) as entries:
            for count, item in enumerate(entries):
                if count >= self.MAX_SCAN:
                    raise ValueError('Too many uploads; select an exact listed path.')
                try:
                    entry = self._entry(directory / item.name)
                except (OSError, ValueError):
                    continue
                if selection in (entry['name'], entry['id']):
                    matches.append(Path(entry['path']))
        if len(matches) != 1:
            raise ValueError('Upload selection is missing or ambiguous; select an exact listed path.')
        return matches[0]
