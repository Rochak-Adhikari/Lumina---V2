"""Pure P2.2 runner gates. No Windows calls, Runtime, secrets or launch on import."""
import hashlib
import json
from pathlib import Path
import time
import sys

SCOPE = 'p22-two-owned-windows-ordinary-focus-v2'
DIAGNOSTIC_SCOPE = 'p22-two-owned-windows-one-move-diagnostic-v1'
DIAGNOSTIC_MANDATE = '87861e43-2a05-4a50-af93-ebb401cf9206'


def runtime_hashes():
    """Code-only dedicated Python/stdlib/dependency inventory; no user data.

    OS libraries remain platform prerequisites, not supplied application code.
    Base-environment site-packages are excluded (venv forbids their import).
    """
    base=Path(sys.base_prefix).resolve()
    prefix=Path(sys.prefix).resolve()
    paths={Path(sys.executable).resolve()}
    for directory in (base,base/'DLLs'):
        paths.update(p for p in directory.glob('*') if p.is_file() and p.suffix.lower() in ('.exe','.dll','.pyd','.zip'))
    library=base/'Lib'
    paths.update(p for p in library.glob('*.py') if p.is_file())
    directories=[p for p in library.iterdir() if p.is_dir() and p.name not in ('site-packages','__pycache__')]
    directories.append(prefix/'Lib'/'site-packages')
    for directory in directories:
        paths.update(p for p in directory.rglob('*') if p.is_file() and
                     p.suffix.lower() in ('.py','.pyd','.dll','.pth'))
    return {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}
REQUIRED = frozenset({
    'lumina/practice_input.py', 'lumina/runtime.py', 'lumina/server.py',
    'lumina/computer_control.py', 'lumina/computer_action.py',
    'lumina/control_authority.py', 'lumina/computer_geometry.py',
    'lumina/owned_windows.py', 'lumina/windows_input.py',
    'lumina/observations.py', 'lumina/screen_capture_worker.py',
    'tests/test_practice_input_native.py', 'tests/test_server.py',
    'scripts/p22_acceptance.py', 'docs/computer-control/DECISION_LOG.md',
})


def load_authorization(path, root, *, now=None):
    """Validate the fixed local owner record; never mint/extend authorization.

    Hashes detect source drift, not malicious same-user replacement. The human
    mandate remains the authority; a JSON file or environment flag alone is not.
    """
    path=Path(path).resolve(); root=Path(root).resolve()
    value=json.loads(path.read_text(encoding='utf-8'))
    diagnostic=type(value) is dict and value.get('scope')==DIAGNOSTIC_SCOPE
    fields={
        'version','scope','run_id','issued_at','expires_at','session_seconds',
        'admissions','windows','owner_mandate','hashes','runner_sha256'}
    if diagnostic:fields|={'interpreter','interpreter_sha256','python_version','environment_hashes','runtime_hashes'}
    if type(value) is not dict or set(value)!=fields:
        raise PermissionError('invalid_authorization_record')
    if (type(value['version']) is not int or value['version']!=1 or value['scope'] not in (SCOPE,DIAGNOSTIC_SCOPE) or
        type(value['session_seconds']) is not int or value['session_seconds']!=900 or
        type(value['admissions']) is not int or value['admissions']!=100 or
        type(value['windows']) is not int or value['windows']!=2 or
        value['owner_mandate']!=(DIAGNOSTIC_MANDATE if diagnostic else 'd75a64c8-8c8b-4ea8-b07d-5085343eb7fa')):
        raise PermissionError('scope_mismatch')
    import math
    issued,expires=value['issued_at'],value['expires_at']
    current=time.time() if now is None else now
    if (any(type(x) not in (float,int) or not math.isfinite(x) for x in (issued,expires)) or
        not 0 < expires-issued <= 86400 or not issued <= current < expires or
        type(value['run_id']) is not str or len(value['run_id'])!=32 or
        any(c not in '0123456789abcdef' for c in value['run_id'])):
        raise PermissionError('authorization_expired_or_invalid')
    hashes=value['hashes']
    if type(hashes) is not dict or not REQUIRED <= hashes.keys():
        raise PermissionError('missing_source_pins')
    if diagnostic:
        # Pin the complete local Python source set, not only currently loaded
        # modules. Newly added source also invalidates an authorized freeze.
        sources={p.relative_to(root).as_posix() for folder in ('lumina','tests','scripts')
                 for p in (root/folder).rglob('*.py') if '__pycache__' not in p.parts}
        if not sources <= hashes.keys():raise PermissionError('incomplete_source_inventory')
        interpreter=Path(sys.executable).resolve()
        if (value['interpreter']!=str(interpreter) or value['python_version']!=sys.version or
                value['interpreter_sha256']!=hashlib.sha256(interpreter.read_bytes()).hexdigest()):
            raise PermissionError('interpreter_drift')
        if value['runtime_hashes']!=runtime_hashes():raise PermissionError('runtime_dependency_drift')
        env=value['environment_hashes']
        if type(env) is not dict or 'pytest.ini' not in env or '.venv/pyvenv.cfg' not in env:
            raise PermissionError('missing_environment_pins')
        for relative,expected in env.items():
            target=(root/relative).resolve()
            if (not target.is_relative_to(root) or relative not in ('pytest.ini','.venv/pyvenv.cfg','requirements.txt') or
                    not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest()!=expected):
                raise PermissionError('environment_drift')
    for relative,expected in hashes.items():
        target=(root/relative).resolve()
        if (not target.is_relative_to(root) or not relative.startswith(('lumina/','tests/','scripts/','docs/')) or
            not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest()!=expected):
            raise PermissionError('source_drift: '+relative)
    runner=path.parent/'validate_native.py'
    if hashlib.sha256(runner.read_bytes()).hexdigest()!=value['runner_sha256']:
        raise PermissionError('runner_drift')
    return value


def preflight_and_claim(path, root, context_check, *, check_only=False, expected_scope=None):
    """No claim on failed context. Repeat source/expiry check after OS queries."""
    path=Path(path)
    if (path.parent/'consumed.json').exists() or (path.parent/'native-observations.json').exists():
        raise PermissionError('session_consumed')
    initial=load_authorization(path,root)
    if expected_scope is not None and initial['scope']!=expected_scope:
        raise PermissionError('scope_mismatch')
    context=context_check()
    if (type(context) is not dict or context.get('desktops_match') is not True or
        context.get('elevated') is not False or not context.get('thread_desktop') or
        context.get('thread_desktop')!=context.get('input_desktop')):
        raise PermissionError('interactive_context_unavailable')
    record=load_authorization(path,root)
    if expected_scope is not None and record['scope']!=expected_scope:
        raise PermissionError('scope_mismatch')
    if not check_only:consume(path.parent/'consumed.json',record)
    return record,context


def consume(path, record):
    """Exclusive one-use claim AFTER child-process context and hash preflight.

    Never delete this file, even if the write, startup or subsequent test fails.
    Two competing runners cannot both win. No implied settlement on exit.
    """
    with Path(path).open('x',encoding='utf-8') as file:
        json.dump({'run_id':record['run_id'],'consumed_at':time.time(),
                   'scope':record['scope'],'state':'consumed_before_target_creation'},file)
        file.flush()
        import os
        os.fsync(file.fileno())
