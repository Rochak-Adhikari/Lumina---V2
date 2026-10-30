"""Daily Brain Dump tool integration and native Lumina command dispatch."""

import secrets
import time
from .tool_contract import ToolSpec
from .brain_dump import CATEGORIES, STATUSES


def _string(limit=4096, **extra):
    return {'type': 'string', 'maxLength': limit, **extra}


def _schema(properties=None, required=()):
    return {
        'type': 'object',
        'properties': properties or {},
        'required': list(required),
        'additionalProperties': False
    }


SCHEMAS = {
    'list_brain_dump_entries': _schema({
        'category': _string(20, enum=list(CATEGORIES)),
        'status': _string(20, enum=list(STATUSES)),
        'limit': {'type': 'integer', 'minimum': 1, 'maximum': 100},
        'offset': {'type': 'integer', 'minimum': 0}
    }),
    'search_brain_dump': _schema({
        'query': _string(240, minLength=1),
        'category': _string(20, enum=list(CATEGORIES)),
        'status': _string(20, enum=list(STATUSES)),
        'limit': {'type': 'integer', 'minimum': 1, 'maximum': 50}
    }, ('query',)),
    'create_brain_dump_entry': _schema({
        'text': _string(4096, minLength=1),
        'category': _string(20, enum=list(CATEGORIES))
    }, ('text',)),
    'update_brain_dump_entry': _schema({
        'id': _string(64, minLength=1),
        'text': _string(4096, minLength=1),
        'category': _string(20, enum=list(CATEGORIES))
    }, ('id',)),
    'complete_brain_dump_entry': _schema({
        'id': _string(64, minLength=1),
        'restore': {'type': 'boolean'}
    }, ('id',)),
    'archive_brain_dump_entry': _schema({
        'id': _string(64, minLength=1),
        'restore': {'type': 'boolean'}
    }, ('id',)),
    'delete_brain_dump_entry': _schema({
        'id': _string(64, minLength=1)
    }, ('id',)),
    'categorize_brain_dump_entries': _schema({
        'category': _string(20, enum=list(CATEGORIES)),
        'entry_ids': {'type': 'array', 'items': _string(64, minLength=1), 'maxItems': 50},
        'from_category': _string(20, enum=list(CATEGORIES))
    }, ('category',)),
}

DESCRIPTIONS = {
    'list_brain_dump_entries': (
        'List stored thoughts, tasks, ideas, and notes from the user Daily Brain Dump workspace. '
        'Supports pagination and filtering by category (inbox, task, idea, reminder, someday) '
        'or status (active, completed, archived). Returns stable entry IDs, text, category, and timestamps.'
    ),
    'search_brain_dump': (
        'Search entry content and text within the Daily Brain Dump workspace. '
        'Optionally filter by category or status without retrieving the whole dump.'
    ),
    'create_brain_dump_entry': (
        'Capture a new thought, task, idea, reminder note, or prospective item into the Daily Brain Dump. '
        'Defaults to inbox category when omitted or uncertain. Returns the created entry with its stable ID.'
    ),
    'update_brain_dump_entry': (
        'Edit the text content or category of an existing Brain Dump entry using its stable ID. '
        'Preserves user meaning and reports nonexistent IDs clearly.'
    ),
    'complete_brain_dump_entry': (
        'Mark an active Brain Dump entry as completed, or restore a completed entry back to active with restore=True.'
    ),
    'archive_brain_dump_entry': (
        'Archive a Brain Dump entry when finished or converted, or restore an archived entry back to active with restore=True.'
    ),
    'delete_brain_dump_entry': (
        'Permanently delete an entry from the Daily Brain Dump by ID. '
        'Destructive operation requiring explicit user confirmation before deletion occurs.'
    ),
    'categorize_brain_dump_entries': (
        'Classify one or more Brain Dump entries into a category (inbox, task, idea, reminder, someday). '
        'Accepts a list of explicit entry_ids or a from_category filter for batch reorganization.'
    ),
}

MUTATIONS = {
    'create_brain_dump_entry',
    'update_brain_dump_entry',
    'complete_brain_dump_entry',
    'archive_brain_dump_entry',
    'delete_brain_dump_entry',
    'categorize_brain_dump_entries'
}


class BrainDumpTools:
    """Dispatches Brain Dump model tools to the underlying BrainDumpService."""

    def __init__(self, service, registry):
        self.service = service
        self.registry = registry

    def execute(self, name, arguments=None):
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            return {'ok': False, 'status': 'invalid', 'error': 'Tool arguments must be an object.'}

        if name == 'list_brain_dump_entries':
            category = arguments.get('category')
            status = arguments.get('status', 'active')
            limit = arguments.get('limit', 50)
            offset = arguments.get('offset', 0)
            return self.service.execute('list', category=category, status=status, limit=limit, offset=offset)

        if name == 'search_brain_dump':
            query = arguments.get('query', '')
            if not query.strip():
                return {'ok': False, 'status': 'invalid', 'error': 'A non-empty query is required.'}
            category = arguments.get('category')
            status = arguments.get('status')
            limit = arguments.get('limit', 25)
            return self.service.execute('list', query=query, category=category, status=status, limit=limit)

        if name == 'create_brain_dump_entry':
            text = arguments.get('text', '')
            if not text.strip():
                return {'ok': False, 'status': 'invalid', 'error': 'Entry text must be non-empty.'}
            category = arguments.get('category') or 'inbox'
            return self.service.execute('create', text=text, category=category)

        if name == 'update_brain_dump_entry':
            entry_id = arguments.get('id')
            if not entry_id:
                return {'ok': False, 'status': 'invalid', 'error': 'An entry ID is required.'}
            text = arguments.get('text')
            category = arguments.get('category')
            if text is None and category is None:
                return {'ok': False, 'status': 'invalid', 'error': 'Provide text or category to update.'}
            return self.service.execute('update', id=entry_id, text=text, category=category)

        if name == 'complete_brain_dump_entry':
            entry_id = arguments.get('id')
            if not entry_id:
                return {'ok': False, 'status': 'invalid', 'error': 'An entry ID is required.'}
            restore = bool(arguments.get('restore', False))
            return self.service.execute('complete', id=entry_id, restore=restore)

        if name == 'archive_brain_dump_entry':
            entry_id = arguments.get('id')
            if not entry_id:
                return {'ok': False, 'status': 'invalid', 'error': 'An entry ID is required.'}
            restore = bool(arguments.get('restore', False))
            return self.service.execute('archive', id=entry_id, restore=restore)

        if name == 'delete_brain_dump_entry':
            entry_id = arguments.get('id')
            if not entry_id:
                return {'ok': False, 'status': 'invalid', 'error': 'An entry ID is required.'}

            # Lookup item text to provide clear confirmation details to user
            listed = self.service.execute('list')
            item_text = 'entry'
            if listed.get('ok'):
                for item in listed.get('items', []):
                    if item.get('id') == entry_id:
                        snippet = item.get('text', '')[:60]
                        item_text = f'"{snippet}"'
                        break

            token = secrets.token_urlsafe(24)
            self.registry.pending[token] = {
                'name': 'delete_brain_dump_entry',
                'arguments': {'id': entry_id},
                'expires': time.monotonic() + 60
            }
            return {
                'ok': False,
                'confirmation_required': True,
                'confirmation_id': token,
                'action': 'delete_brain_dump_entry',
                'target': entry_id,
                'message': f'Confirm permanent deletion of Brain Dump entry {item_text} ({entry_id})?'
            }

        if name == 'categorize_brain_dump_entries':
            category = arguments.get('category')
            if not category:
                return {'ok': False, 'status': 'invalid', 'error': 'A target category is required.'}
            entry_ids = arguments.get('entry_ids')
            from_category = arguments.get('from_category')
            if not entry_ids and not from_category:
                return {
                    'ok': False,
                    'status': 'invalid',
                    'error': 'Provide explicit entry_ids or a from_category filter.'
                }
            return self.service.execute('categorize', category=category, entry_ids=entry_ids, from_category=from_category)

        return {'ok': False, 'status': 'invalid', 'error': f'Unknown Brain Dump tool: {name}'}

    def confirm(self, pending):
        """Executes a confirmed destructive Brain Dump action."""
        args = pending.get('arguments', {})
        entry_id = args.get('id')
        if not entry_id:
            return {'ok': False, 'error': 'Missing entry ID in pending confirmation.'}
        return self.service.execute('delete', id=entry_id)


def create_specs(brain_dump_tools):
    """Builds the list of ToolSpec instances for registration in ToolRegistry."""
    specs = []
    for name, schema in SCHEMAS.items():
        is_destructive = name == 'delete_brain_dump_entry'
        is_mutation = name in MUTATIONS
        permission = 'L4' if is_destructive else ('L1' if is_mutation else 'L0')
        risk = 'destructive' if is_destructive else ('local action' if is_mutation else 'read-only')
        specs.append(ToolSpec(
            name=name,
            description=DESCRIPTIONS[name],
            input_schema=schema,
            output_schema={'type': 'object', 'properties': {'ok': {'type': 'boolean'}}, 'required': ['ok']},
            permission=permission,
            risk=risk,
            idempotent=not is_mutation,
            timeout=10
        ))
    return specs
