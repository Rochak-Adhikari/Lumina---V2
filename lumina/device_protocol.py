"""Versioned device contract; no network, desktop or provider imports."""
import json
from urllib.parse import urlsplit

VERSION = 1
TOOLS = {'system_info': None, 'find_files': 'query', 'read_file': 'path',
         'list_directory': 'path', 'open_folder': 'path', 'create_directory': 'path',
         'open_app': 'name'}
TERMINAL = {'succeeded', 'failed', 'declined', 'unknown', 'cancelled', 'expired'}


def origin(value):
    if not isinstance(value, str):
        raise ValueError('Use the HTTPS origin of your Cloud Core.')
    p = urlsplit(value)
    if (p.scheme != 'https' or not p.hostname or p.username or p.password or
            p.path not in ('', '/') or p.query or p.fragment or len(value) > 300 or
            any(ord(c) <= 32 for c in value) or '\\' in value or p.port == 0):
        raise ValueError('Use an HTTPS origin without a path or credentials.')
    return value.rstrip('/')


def arguments(tool, args):
    if tool not in TOOLS or not isinstance(args, dict):
        raise ValueError('This device capability is not exposed.')
    key = TOOLS[tool]
    if set(args) != ({key} if key else set()):
        raise ValueError('Unexpected device arguments.')
    if key and (not isinstance(args[key], str) or not args[key].strip() or
                len(args[key]) > (240 if tool == 'find_files' else 1000) or
                any(ord(c) < 32 for c in args[key])):
        raise ValueError('Device argument is empty, invalid or too long.')
    return dict(args)


def signature_message(cloud_origin, device_id, nonce):
    return ('LUMINA-DEVICE-V1\n'+cloud_origin+'\n'+device_id+'\n'+nonce).encode('utf-8')


def digest(command):
    import hashlib
    return hashlib.sha256(json.dumps([command['id'], command['device_id'], command['tool'],
                                      command['args_json']], sort_keys=True).encode()).hexdigest()
