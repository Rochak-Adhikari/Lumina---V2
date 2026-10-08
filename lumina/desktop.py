"""Structured desktop operations. Desktop roots never grant worker access."""
from dataclasses import dataclass, field
from pathlib import Path
from difflib import SequenceMatcher
import hashlib
import json
import os
import re
import shutil
import string
import subprocess
import time

from .filesystem import IGNORED
from .local_operations import SECRET_NAMES, LocalOperations


class DesktopError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


@dataclass
class WorkspaceManager:
    active_workspace: Path
    roots: list = field(default_factory=list)
    active_directory: Path = None
    last_opened_path: Path = None
    last_selected_file: Path = None
    active_worker_workspace: Path = None

    def __post_init__(self):
        self.active_workspace = Path(self.active_workspace).resolve()
        self.active_directory = self.active_workspace
        self.roots = list(dict.fromkeys([self.active_workspace, *(Path(p).resolve() for p in self.roots)]))

    def locations(self):
        home = Path.home()
        return {name.lower(): home / name for name in ('Desktop', 'Documents', 'Downloads', 'Pictures', 'Videos', 'Music')} | {'home': home, 'appdata': Path(os.environ.get('APPDATA', home))}


class PathResolver:
    def __init__(self, workspace):
        self.workspace = workspace

    def path(self, value, must_exist=True):
        if not isinstance(value, str) or not value.strip() or len(value) > 2048:
            raise DesktopError('INVALID_OPERATION', 'A bounded path is required.')
        value = value.strip().strip('"')
        aliases = {'my project': self.workspace.active_workspace, 'the lumina project': self.workspace.active_workspace,
                   'lumina project': self.workspace.active_workspace, 'the current project': self.workspace.active_workspace,
                   'current project': self.workspace.active_workspace, 'the folder i just opened': self.workspace.last_opened_path,
                   'the current claude workspace': self.workspace.active_worker_workspace,
                   'the folder where claude is working': self.workspace.active_worker_workspace}
        aliases.update(self.workspace.locations())
        aliases.update({'my ' + k: v for k, v in self.workspace.locations().items()})
        value = aliases.get(value.casefold(), value)
        if value is None:
            raise DesktopError('PATH_NOT_FOUND', 'That location has not been selected.')
        expanded = os.path.expandvars(os.path.expanduser(str(value)))
        if expanded.startswith(('\\\\', '//')) or '\x00' in expanded:
            raise DesktopError('PERMISSION_DENIED', 'Network and device paths are not permitted.')
        candidate = Path(expanded)
        if candidate.drive and not candidate.is_absolute():
            raise DesktopError('INVALID_OPERATION', 'Use a complete absolute path.')
        if not candidate.is_absolute():
            candidate = self.workspace.active_directory / candidate
        candidate = Path(os.path.abspath(candidate))
        if any(':' in p or p.casefold() in SECRET_NAMES or p.startswith('.') for p in candidate.parts[1:]):
            raise DesktopError('PERMISSION_DENIED', 'Protected or hidden paths are not permitted.')
        for cursor in (candidate, *candidate.parents):
            if cursor.is_symlink() or getattr(cursor, 'is_junction', lambda: False)():
                raise DesktopError('PERMISSION_DENIED', 'Links and junctions cannot be traversed.')
        resolved = candidate.resolve()
        if not any(resolved.is_relative_to(root) for root in self.workspace.roots):
            raise DesktopError('PERMISSION_DENIED', 'That location is outside the configured desktop roots.')
        if must_exist and not resolved.exists():
            raise DesktopError('PATH_NOT_FOUND', 'That path does not exist.')
        return resolved

    def resolve_path(self, path):
        try:target = self.path(path)
        except DesktopError as exc:
            if exc.code!='PATH_NOT_FOUND':raise
            search=FileSearchService(self)
            containing=path.casefold().startswith('the folder containing ')
            query=path[len('the folder containing '):] if containing else path
            files=search.search_files(query=query)['results']
            folders=[] if containing else search.search_directories(query=query)['results']
            hits=files+folders
            exact=[h for h in hits if not h['partial']]
            hits=exact or hits
            if not hits:raise
            if len(hits)>1:return {'ok':False,'status':'ambiguous','code':'AMBIGUOUS_PATH','error':'Several paths match. Choose a specific path.','results':hits[:20]}
            target=Path(hits[0]['path']).parent if containing else Path(hits[0]['path'])
            return {'ok':True,'status':'search_result','path':str(target),'partial':hits[0]['partial'],'type':'directory' if target.is_dir() else 'file'}
        return {'ok': True, 'status': 'resolved', 'path': str(target), 'type': 'directory' if target.is_dir() else 'file'}


class FileSearchService:
    def __init__(self, resolver):
        self.resolver = resolver
        self.cache = {}

    def invalidate(self):
        self.cache.clear()

    def search(self, query='', root=None, file_type=None, max_results=50, recursive=True, directories=False):
        base = self.resolver.path(root or str(self.resolver.workspace.active_workspace))
        if not base.is_dir() or base == Path(base.anchor):
            raise DesktopError('INVALID_OPERATION', 'Choose a directory below the drive root.')
        key = (str(base), recursive)
        cached = self.cache.get(key)
        if not cached or time.monotonic() - cached[0] > 15:
            entries, incomplete = [], False
            deadline = time.monotonic() + 5
            def onerror(error):
                nonlocal incomplete
                incomplete = True
            for parent, folders, files in os.walk(base, followlinks=False, onerror=onerror):
                folders[:] = [n for n in folders if n not in IGNORED and not n.startswith('.') and not (Path(parent)/n).is_symlink() and not getattr(Path(parent)/n, 'is_junction', lambda:False)()]
                for name in [*folders, *files]:
                    if name.startswith('.') or name.casefold() in SECRET_NAMES:
                        continue
                    p = Path(parent)/name
                    if p.is_symlink() or getattr(p, 'is_junction', lambda:False)(): continue
                    entries.append((p, name in folders))
                    if len(entries) >= 20000 or time.monotonic() > deadline:
                        incomplete = True
                        break
                if incomplete or not recursive: break
            cached = (time.monotonic(), entries, incomplete)
            self.cache[key] = cached
        needle = query.casefold().strip()
        extension = ('.' + file_type.lstrip('.').lower()) if file_type else None
        hits = []
        for p, is_dir in cached[1]:
            if is_dir != directories or (extension and p.suffix.lower() != extension): continue
            score = 1 if not needle or needle == p.name.casefold() else .9 if needle in p.name.casefold() else .8 if needle in str(p.relative_to(base)).casefold() else SequenceMatcher(None, needle, p.name.casefold()).ratio() * .7
            if score < .6: continue
            hits.append({'path': str(p), 'filename': p.name, 'type': 'directory' if is_dir else 'file', 'score': score, 'partial': score < 1})
        hits.sort(key=lambda h: (-h['score'], h['path']))
        limit = max(1, min(int(max_results), 100))
        return {'ok': True, 'count': len(hits), 'results': hits[:limit], 'truncated': len(hits)>limit, 'scan_incomplete': cached[2]}

    def search_files(self, **kwargs):
        return self.search(**kwargs)

    def search_directories(self, **kwargs):
        return self.search(directories=True, **kwargs)


class DirectorySearchService(FileSearchService):
    pass


class FilesystemManager:
    def __init__(self, resolver, search):
        self.resolver, self.search = resolver, search

    def inspect_path(self, path):
        p = self.resolver.path(path, must_exist=False)
        if not p.exists(): return {'ok': True, 'exists': False, 'path': str(p)}
        s = p.stat()
        return {'ok': True, 'exists': True, 'path': str(p), 'type': 'directory' if p.is_dir() else 'file', 'size': s.st_size, 'created': s.st_ctime, 'modified': s.st_mtime, 'extension': p.suffix}

    def fingerprint(self,path):
        p=self.resolver.path(path)
        digest=hashlib.sha256()
        items=[p]
        if p.is_dir():
            for parent,folders,files in os.walk(p,followlinks=False):
                for name in sorted([*folders,*files]):
                    items.append(self.resolver.path(str(Path(parent)/name)))
                    if len(items)>20000:raise DesktopError('INVALID_OPERATION','The operation is too large for one confirmation.')
        for item in sorted(items):
            st=item.stat();digest.update(str((str(item),st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns)).encode())
        return digest.hexdigest()

    def list_directory(self, path):
        p = self.resolver.path(path)
        if not p.is_dir(): raise DesktopError('INVALID_OPERATION', 'Choose a directory.')
        entries = []
        for child in p.iterdir():
            if child.name.startswith('.') or child.name.casefold() in SECRET_NAMES: continue
            entries.append({'name': child.name, 'path': str(child), 'type': 'link' if child.is_symlink() or getattr(child, 'is_junction', lambda:False)() else 'directory' if child.is_dir() else 'file'})
            if len(entries) == 101: break
        return {'ok': True, 'entries': entries[:100], 'truncated': len(entries)>100}

    def create_directory(self, path):
        p = self.resolver.path(path, False)
        if p.exists(): raise DesktopError('DIRECTORY_ALREADY_EXISTS', 'That location already exists.')
        p.mkdir(parents=True)
        self.search.invalidate()
        return {'ok': True, 'path': str(p), 'message': f'Created {p.name}, sir.'}

    def transfer(self, source, destination, move=False):
        src, dst = self.resolver.path(source), self.resolver.path(destination, False)
        if src in self.resolver.workspace.roots or dst.is_relative_to(src):
            raise DesktopError('INVALID_OPERATION', 'Workspace roots and nested destinations cannot be moved or copied.')
        if dst.exists(): raise DesktopError('FILE_ALREADY_EXISTS', 'The destination already exists; nothing was overwritten.')
        if not dst.parent.is_dir(): raise DesktopError('PATH_NOT_FOUND', 'The destination folder does not exist.')
        # Validate every child before recursive operations, including link/secret boundaries.
        if src.is_dir():
            count = 0
            for parent, folders, files in os.walk(src, followlinks=False):
                for name in [*folders, *files]:
                    self.resolver.path(str(Path(parent)/name))
                    count += 1
                    if count > 20000: raise DesktopError('INVALID_OPERATION', 'This folder is too large for one operation.')
        if move:
            if src.stat().st_dev == dst.parent.stat().st_dev: src.rename(dst)
            else: shutil.move(str(src),str(dst))
        elif src.is_dir(): shutil.copytree(src, dst)
        else:
            with src.open('rb') as inp, dst.open('xb') as out: shutil.copyfileobj(inp, out)
        self.search.invalidate()
        return {'ok': True, 'path': str(dst), 'message': f'{"Moved" if move else "Copied"} {src.name}, sir.'}

    def copy_path(self, source, destination): return self.transfer(source, destination)
    def move_path(self, source, destination): return self.transfer(source, destination, True)
    def rename_path(self, source, destination): return self.transfer(source, destination, True)

    def delete_path(self, path):
        p = self.resolver.path(path)
        if p in self.resolver.workspace.roots: raise DesktopError('PERMISSION_DENIED', 'A configured root cannot be deleted.')
        self.fingerprint(str(p))
        if os.name != 'nt': raise DesktopError('INVALID_OPERATION', 'Recycle Bin deletion requires Windows.')
        import ctypes
        from ctypes import wintypes
        class SHFILEOPSTRUCT(ctypes.Structure):
            _fields_ = [('hwnd', wintypes.HWND), ('wFunc', wintypes.UINT), ('pFrom', wintypes.LPCWSTR), ('pTo', wintypes.LPCWSTR), ('fFlags', wintypes.WORD), ('fAnyOperationsAborted', wintypes.BOOL), ('hNameMappings', ctypes.c_void_p), ('lpszProgressTitle', wintypes.LPCWSTR)]
        op = SHFILEOPSTRUCT(None, 3, str(p)+'\0\0', None, 0x40|0x10|0x4|0x400, False, None, None)
        code = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
        if code or op.fAnyOperationsAborted: raise DesktopError('INVALID_OPERATION', 'Windows did not confirm deletion.')
        self.search.invalidate()
        return {'ok': True, 'message': 'Moved the selected item and its contents to the Recycle Bin, sir.'}


class ProcessManager:
    def __init__(self): self.owned = {}
    def register(self, process, kind, target):
        self.owned[str(process.pid)] = (process, kind, str(target))
        return process.pid
    def list_processes(self):
        return {'ok': True, 'processes': [{'id': pid, 'kind': kind, 'target': target, 'running': p.poll() is None} for pid,(p,kind,target) in self.owned.items()]}
    def terminate_process(self, process_id):
        entry = self.owned.get(str(process_id))
        if not entry: raise DesktopError('PERMISSION_DENIED', 'Only a LUMINA-owned process can be stopped.')
        process = entry[0]
        if process.poll() is None: process.terminate()
        return {'ok': True, 'message': 'Termination was requested.'}


class ApplicationManager:
    def __init__(self, processes):
        self.processes, self.applications, self.discovered = processes, {}, 0

    def _add(self, name, path, source, arguments=None, **metadata):
        identity = hashlib.sha256((str(path).casefold()+str(arguments)).encode()).hexdigest()[:16]
        self.applications[identity] = {'application_id': identity, 'display_name': name, 'executable_path': str(path), 'launch_command': str(path), 'arguments': arguments or [], 'source': source, 'publisher': None, 'install_location': str(Path(path).parent), 'icon': None, 'installed_at': None, 'aliases': list({name.casefold(), Path(path).stem.casefold()}), 'last_discovered': time.time(), **metadata}
        if Path(path).stem.lower()=='code':self.applications[identity]['aliases'].extend(['visual studio code','vs code','vscode'])

    def discover_applications(self):
        if not self.discovered or time.time()-self.discovered>300: self.refresh_application_index()
        return {'ok': True, 'count': len(self.applications), 'applications': list(self.applications.values())[:100]}

    def refresh_application_index(self):
        self.applications.clear()
        for directory in dict.fromkeys(os.environ.get('PATH','').split(os.pathsep)):
            if not directory: continue
            try:
                for p in Path(directory).iterdir():
                    if p.suffix.lower() in {'.exe', '.com'} and p.is_file(): self._add(p.stem, p, 'PATH')
            except OSError: pass
        if os.name == 'nt':
            import winreg
            for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                for flags in (winreg.KEY_READ | winreg.KEY_WOW64_64KEY, winreg.KEY_READ | winreg.KEY_WOW64_32KEY):
                    try:
                        with winreg.OpenKey(hive, r'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths', 0, flags) as key:
                            for i in range(winreg.QueryInfoKey(key)[0]):
                                name = winreg.EnumKey(key, i)
                                try:
                                    with winreg.OpenKey(key,name) as app:
                                        path = Path(os.path.expandvars(winreg.QueryValue(app, None).strip('"')))
                                        if path.is_file(): self._add(path.stem, path, 'App Paths')
                                except OSError: pass
                    except OSError: pass
            for env in ('APPDATA','PROGRAMDATA'):
                start = Path(os.environ.get(env, ''))/'Microsoft/Windows/Start Menu/Programs'
                if start.is_dir():
                    for p in start.rglob('*.lnk'): self._add(p.stem, p, 'Start Menu')
            self._discover_start_apps()
        self.discovered=time.time()
        return {'ok': True, 'count': len(self.applications)}

    def _discover_start_apps(self):
        """Windows-native app list (includes packaged/Store apps). Launched by AppID via shell:AppsFolder."""
        powershell = str(Path(os.environ.get('SystemRoot', r'C:\Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe')
        try:
            result = subprocess.run([powershell, '-NoProfile', '-Command', 'Get-StartApps | ConvertTo-Json -Compress'],
                capture_output=True, text=True, timeout=20, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            entries = json.loads(result.stdout or '[]')
        except (OSError, ValueError, subprocess.SubprocessError):
            return
        if isinstance(entries, dict): entries = [entries]
        for entry in entries:
            name, app_id = entry.get('Name'), entry.get('AppID')
            if not name or not app_id: continue
            identity = hashlib.sha256(('startapp:'+str(app_id).casefold()).encode()).hexdigest()[:16]
            if identity in self.applications: continue
            self.applications[identity] = {'application_id': identity, 'display_name': name,
                'executable_path': str(app_id), 'launch_command': 'shell:AppsFolder\\'+str(app_id), 'arguments': [],
                'source': 'Start Apps', 'publisher': None, 'install_location': None, 'icon': None,
                'installed_at': None, 'aliases': list({name.casefold()}), 'last_discovered': time.time(), 'packaged': True}

    def find_application(self, query):
        self.discover_applications()
        needle=query.casefold().strip()
        aliases={'vs code':'visual studio code','vscode':'visual studio code','explorer':'explorer','command prompt':'cmd'}
        needle=aliases.get(needle,needle)
        values=list(self.applications.values())
        exact=[a for a in values if needle in a['aliases']]
        hits=exact or [a for a in values if needle in a['display_name'].casefold()]
        if needle=='browser': hits=[a for a in values if any(n in a['aliases'] for n in ('chrome','msedge','firefox','brave','opera'))]
        # Prefer executables over shortcuts of the same product.
        def product(app):
            return 'visual studio code' if 'visual studio code' in app['aliases'] else app['display_name'].casefold()
        hits=list({product(a):a for a in sorted(hits,key=lambda a:Path(a['executable_path']).suffix.lower()=='.exe')}.values())
        if not hits: return {'ok':False,'code':'APPLICATION_NOT_FOUND','error':'No matching application was discovered.'}
        return {'ok':len(hits)==1,'code':'RESOLVED' if len(hits)==1 else 'AMBIGUOUS_APPLICATION','error': None if len(hits)==1 else 'Several applications match; choose one.', 'applications':hits[:20]}

    def launch_application(self, application_id, path=None):
        self.discover_applications()
        app=self.applications.get(application_id)
        if not app: raise DesktopError('APPLICATION_NOT_FOUND','That application is not indexed.')
        target=app['executable_path']
        if re.search(r'(?i)\b(?:claude|codex|gemini|tmux|wt|windowsterminal|mintty)\b',str(target)+' '+app.get('display_name','')):
            raise DesktopError('INVALID_OPERATION','Start agents only through the supervised spawn/task tool.')
        if app.get('packaged'):
            if path: raise DesktopError('INVALID_OPERATION','Opening a path requires a discovered executable, not a packaged app.')
            os.startfile(app['launch_command'])
            return {'ok':True,'pid':None,'message':f"Opened {app['display_name']}, sir."}
        if not path and Path(target).suffix.lower()=='.exe' and Path(target).name.casefold() in self.running_process_names():
            return {'ok':True,'already_running':True,'message':f"{app['display_name']} is already running, sir."}
        if Path(target).suffix.lower()=='.lnk':
            if path: raise DesktopError('INVALID_OPERATION','Opening a path requires a discovered executable, not a shortcut.')
            os.startfile(target)
            pid=None
        else:
            process=subprocess.Popen([target,*app['arguments'],*([path] if path else [])],shell=False)
            pid=self.processes.register(process,'application',target)
        return {'ok':True,'pid':pid,'message':f"Opened {app['display_name']}, sir."}

    @staticmethod
    def running_process_names():
        return LocalOperations.running_process_names() if os.name=='nt' else set()


class ExplorerManager:
    def __init__(self, resolver): self.resolver=resolver
    def open_folder(self,path):
        p=self.resolver.path(path)
        if not p.is_dir(): raise DesktopError('INVALID_OPERATION','Choose a folder.')
        os.startfile(str(p));self.resolver.workspace.last_opened_path=p
        return {'ok':True,'message':f'Opened {p.name}, sir.'}
    def reveal_in_explorer(self,path):
        p=self.resolver.path(path)
        subprocess.Popen(['explorer.exe', '/select,',str(p)],shell=False)
        self.resolver.workspace.last_selected_file=p
        return {'ok':True,'message':'The item is selected in Explorer, sir.'}


class TerminalManager:
    def __init__(self,resolver,processes): self.resolver,self.processes=resolver,processes
    def open_terminal(self,path):
        p=self.resolver.path(path)
        if not p.is_dir(): raise DesktopError('INVALID_OPERATION','Choose a folder.')
        executable=Path(os.environ.get('SystemRoot',r'C:\Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
        process=subprocess.Popen([str(executable),'-NoProfile'],cwd=p,creationflags=subprocess.CREATE_NEW_CONSOLE)
        self.processes.register(process,'terminal',p)
        return {'ok':True,'message':'PowerShell is open in that folder, sir.'}


class DesktopServices:
    def __init__(self,root,roots=()):
        self.workspace=WorkspaceManager(root,list(roots))
        self.resolver=PathResolver(self.workspace)
        self.search=FileSearchService(self.resolver)
        self.files=FilesystemManager(self.resolver,self.search)
        self.processes=ProcessManager()
        self.apps=ApplicationManager(self.processes)
        self.explorer=ExplorerManager(self.resolver)
        self.terminal=TerminalManager(self.resolver,self.processes)

    def open_app(self,app):
        result=self.apps.find_application(app)
        return self.apps.launch_application(result['applications'][0]['application_id']) if result['ok'] else result

    def open_with(self,path,application):
        p=self.resolver.path(path)
        result=self.apps.find_application(application)
        return self.apps.launch_application(result['applications'][0]['application_id'],str(p)) if result['ok'] else result

    def desktop_locations(self):
        return {'ok':True,'roots':[str(p) for p in self.workspace.roots],'known_directories':{k:str(v) for k,v in self.workspace.locations().items()},'drives':[f'{c}:\\' for c in string.ascii_uppercase if Path(f'{c}:\\').exists()] if os.name=='nt' else ['/']}

    def execute(self,name,arguments):
        try:
            for owner in (self,self.resolver,self.search,self.files,self.apps,self.explorer,self.terminal,self.processes):
                method=getattr(owner,name,None)
                if method and name!='execute': return method(**arguments)
            raise DesktopError('INVALID_OPERATION','Unknown desktop operation.')
        except DesktopError as exc: return {'ok':False,'code':exc.code,'error':str(exc)}
        except PermissionError: return {'ok':False,'code':'PERMISSION_DENIED','error':'Windows denied access to that item.'}
        except OSError: return {'ok':False,'code':'INVALID_OPERATION','error':'Windows could not complete that operation.'}
