"""Daily Brain Dump: quick-capture thought entries with categories.

Persistence follows the same locked-JSON pattern as ReminderService.
Items are independent entries until the user explicitly converts one
into an existing Lumina task or reminder.  No parallel task store.
"""

import json
import os
import time
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

CATEGORIES = ('inbox', 'task', 'idea', 'reminder', 'someday')
STATUSES = ('active', 'completed', 'archived')


def _result(ok, status, error=None, **fields):
    return {'ok': ok, 'status': status, 'error': error, **fields}


class BrainDumpService:
    """Use execute(action, **kwargs) for all operations.

    create:   text, category (optional, default inbox)
    list:     category (optional filter), status (optional filter), query (optional search)
    update:   id, text and/or category
    complete: id
    archive:  id
    delete:   id
    restore:  id  (un-complete / un-archive back to active)
    convert_to_task:     id  (marks item converted, returns task-ready payload)
    convert_to_reminder: id, due_at, timezone (optional)
    """

    def __init__(self, path, *, resolver, on_change=None):
        self.resolver = resolver
        self.path = Path(resolver.path(str(path), must_exist=False))
        self.on_change = on_change

    def _path(self, path):
        return Path(self.resolver.path(str(path), must_exist=False))

    @contextmanager
    def _locked(self):
        target = self._path(self.path)
        target.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self._path(str(target) + '.lock')
        with open(lock_path, 'a+b') as handle:
            handle.seek(0, os.SEEK_END)
            if not handle.tell():
                handle.write(b'0')
                handle.flush()
            handle.seek(0)
            try:
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise BlockingIOError('Brain Dump authority is busy') from exc
            try:
                yield
            finally:
                handle.seek(0)
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _save(self, items):
        target = self._path(self.path)
        temporary = self._path(str(target) + '.' + str(uuid4()) + '.tmp')
        try:
            with open(temporary, 'x', encoding='utf-8') as handle:
                json.dump({'version': 1, 'items': items}, handle, ensure_ascii=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        finally:
            if temporary.exists():
                temporary.unlink(missing_ok=True)

    def _load(self):
        target = self._path(self.path)
        if not target.exists():
            return []
        try:
            data = json.loads(target.read_text(encoding='utf-8'))
            if not isinstance(data, dict) or data.get('version') != 1:
                raise ValueError('Unsupported state')
            items = data['items']
            if not isinstance(items, list):
                raise ValueError('Invalid items')
            for item in items:
                if not isinstance(item, dict):
                    raise ValueError('Invalid item')
                if item.get('category') not in CATEGORIES:
                    raise ValueError('Invalid category')
                if item.get('status') not in STATUSES:
                    raise ValueError('Invalid status')
        except (ValueError, KeyError, TypeError, UnicodeError):
            quarantine = self._path(str(target) + '.corrupt.' + str(uuid4()))
            os.replace(target, quarantine)
            raise ValueError('Corrupt brain dump state quarantined at ' + str(quarantine))
        return items

    @staticmethod
    def _text(value):
        if not isinstance(value, str) or not value.strip() or len(value) > 4096:
            raise ValueError('Text must contain 1-4096 characters')
        return value.strip()

    @staticmethod
    def _category(value):
        if value not in CATEGORIES:
            raise ValueError(f'Category must be one of: {", ".join(CATEGORIES)}')
        return value

    def _find(self, items, item_id):
        if not isinstance(item_id, str) or not item_id:
            raise ValueError('A valid item ID is required')
        for item in items:
            if item['id'] == item_id:
                return item
        raise ValueError('That brain dump item is unavailable')

    def execute(self, action, **args):
        try:
            with self._locked():
                items = self._load()
                now = time.time()
                now_iso = _iso(now)

                if action == 'list':
                    res = self._list(items, **args)
                elif action == 'create':
                    res = self._create(items, now, now_iso, **args)
                elif action == 'update':
                    res = self._update(items, now_iso, **args)
                elif action == 'complete':
                    if args.get('restore'):
                        res = self._set_status(items, now_iso, args.get('id'), 'active')
                    else:
                        res = self._set_status(items, now_iso, args.get('id'), 'completed')
                elif action == 'archive':
                    if args.get('restore'):
                        res = self._set_status(items, now_iso, args.get('id'), 'active')
                    else:
                        res = self._set_status(items, now_iso, args.get('id'), 'archived')
                elif action == 'restore':
                    res = self._set_status(items, now_iso, args.get('id'), 'active')
                elif action == 'delete':
                    res = self._delete(items, args.get('id'))
                elif action == 'categorize':
                    res = self._categorize(items, now_iso, **args)
                elif action == 'convert_to_task':
                    res = self._convert_to_task(items, now_iso, args.get('id'))
                elif action == 'convert_to_reminder':
                    res = self._convert_to_reminder(items, now_iso, **args)
                else:
                    raise ValueError(f'Unknown action: {action}')

                if res.get('ok') and self.on_change:
                    try:
                        self.on_change({'type': 'brain_dump_change', 'action': action, 'result': res,
                                        'item': res.get('item'), 'id': res.get('id') or args.get('id')})
                    except Exception:
                        pass
                return res

        except BlockingIOError:
            return _result(False, 'busy', 'Brain Dump is busy with another operation')
        except ValueError as exc:
            return _result(False, 'error', str(exc))

    def _list(self, items, **filters):
        results = [i for i in items if i.get('status') != 'deleted']
        category = filters.get('category')
        if category:
            self._category(category)
            results = [i for i in results if i['category'] == category]
        status = filters.get('status')
        if status:
            if status not in STATUSES:
                raise ValueError('Invalid status filter')
            results = [i for i in results if i['status'] == status]
        query = filters.get('query', '').strip().lower()
        if query:
            results = [i for i in results if query in i['text'].lower()]
        # Sort: active first, then by updated descending
        status_order = {'active': 0, 'completed': 1, 'archived': 2}
        results.sort(key=lambda i: (status_order.get(i['status'], 9), -i.get('updated_at_ts', 0)))
        total_count = len(results)
        offset = int(filters.get('offset', 0) or 0)
        limit = filters.get('limit')
        if limit is not None:
            limit = int(limit)
            results = results[offset:offset+limit]
        return _result(True, 'listed', items=deepcopy(results), count=len(results),
                       total_count=total_count, offset=offset)

    def _create(self, items, now, now_iso, **args):
        text = self._text(args.get('text', ''))
        category = self._category(args.get('category', 'inbox'))
        item = {
            'id': uuid4().hex,
            'text': text,
            'category': category,
            'status': 'active',
            'created_at': now_iso,
            'updated_at': now_iso,
            'created_at_ts': now,
            'updated_at_ts': now,
            'converted': None,
        }
        items.append(item)
        self._save(items)
        return _result(True, 'created', item=deepcopy(item))

    def _update(self, items, now_iso, **args):
        item = self._find(items, args.get('id'))
        if item['status'] != 'active':
            raise ValueError('Only active items can be edited')
        changed = False
        if 'text' in args and args['text'] is not None:
            item['text'] = self._text(args['text'])
            changed = True
        if 'category' in args and args['category'] is not None:
            item['category'] = self._category(args['category'])
            changed = True
        if not changed:
            raise ValueError('Provide text or category to update')
        item['updated_at'] = now_iso
        item['updated_at_ts'] = time.time()
        self._save(items)
        return _result(True, 'updated', item=deepcopy(item))

    def _set_status(self, items, now_iso, item_id, new_status):
        item = self._find(items, item_id)
        item['status'] = new_status
        item['updated_at'] = now_iso
        item['updated_at_ts'] = time.time()
        self._save(items)
        return _result(True, new_status, item=deepcopy(item))

    def _delete(self, items, item_id):
        item = self._find(items, item_id)
        items.remove(item)
        self._save(items)
        return _result(True, 'deleted', id=item_id)

    def _categorize(self, items, now_iso, **args):
        category = self._category(args.get('category'))
        entry_ids = args.get('entry_ids')
        if entry_ids is None and 'id' in args:
            entry_ids = [args['id']]
        from_category = args.get('from_category')
        if not entry_ids and not from_category:
            raise ValueError('Provide entry_ids or from_category to categorize entries')

        updated_ids = []
        skipped_ids = []
        now_ts = time.time()

        if entry_ids:
            if isinstance(entry_ids, str):
                entry_ids = [entry_ids]
            id_set = set(entry_ids)
            for item in items:
                if item['id'] in id_set:
                    if item['status'] == 'active':
                        item['category'] = category
                        item['updated_at'] = now_iso
                        item['updated_at_ts'] = now_ts
                        updated_ids.append(item['id'])
                    else:
                        skipped_ids.append(item['id'])
            found_ids = set(updated_ids) | set(skipped_ids)
            for eid in entry_ids:
                if eid not in found_ids:
                    skipped_ids.append(eid)
        elif from_category:
            self._category(from_category)
            for item in items:
                if item['status'] == 'active' and item['category'] == from_category:
                    item['category'] = category
                    item['updated_at'] = now_iso
                    item['updated_at_ts'] = now_ts
                    updated_ids.append(item['id'])

        self._save(items)
        return _result(True, 'categorized', category=category, updated_count=len(updated_ids),
                       updated_ids=updated_ids, skipped_ids=skipped_ids)

    def _convert_to_task(self, items, now_iso, item_id):
        item = self._find(items, item_id)
        if item['status'] != 'active':
            raise ValueError('Only active items can be converted')
        item['converted'] = {'type': 'task', 'at': now_iso}
        item['status'] = 'archived'
        item['updated_at'] = now_iso
        item['updated_at_ts'] = time.time()
        self._save(items)
        return _result(True, 'converted', conversion='task', item=deepcopy(item),
                       task_payload={'text': item['text'], 'source': 'brain_dump', 'source_id': item['id']})

    def _convert_to_reminder(self, items, now_iso, **args):
        item_id = args.get('id')
        item = self._find(items, item_id)
        if item['status'] != 'active':
            raise ValueError('Only active items can be converted')
        due_at = args.get('due_at')
        if not due_at:
            raise ValueError('due_at is required for reminder conversion')
        item['converted'] = {'type': 'reminder', 'at': now_iso, 'due_at': due_at}
        item['status'] = 'archived'
        item['updated_at'] = now_iso
        item['updated_at_ts'] = time.time()
        self._save(items)
        return _result(True, 'converted', conversion='reminder', item=deepcopy(item),
                       reminder_payload={'message': item['text'], 'due_at': due_at,
                                         'timezone': args.get('timezone', 'Asia/Kathmandu')})


def _iso(ts):
    """UTC ISO timestamp from epoch seconds."""
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
