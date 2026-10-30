"""Private two-message transport for one authority-bound fixture toggle.

No registry entry, arbitrary helper/command, or independent approval store.
Only the existing adapter's live, one-shot action can deliver a commit grant.
"""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import re
import time

# Deliberately not a configuration option. The native proxy failed validation
# and can synthesize keyboard input during focus acquisition. Fake tests alone
# may substitute both this gate and _spawn; the helper independently denies.
NATIVE_TOGGLE_READY=False


async def _spawn():
    executable=Path(os.environ.get('SystemRoot',r'C:\Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
    return await asyncio.create_subprocess_exec(str(executable),'-NoLogo','-NoProfile','-NonInteractive','-Mta',
        '-ExecutionPolicy','RemoteSigned','-File',str(Path(__file__).with_name('fixture_toggle_helper.ps1')),
        stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,
        limit=8192,creationflags=0x08000000)


async def execute(adapter,authorization):
    if authorization is None:raise PermissionError('toggle_authority_required')
    action,lease,observation,cancelled=authorization
    if action.operation!='toggle_external_fixture':raise PermissionError('toggle_operation_required')
    session_token=adapter.observations._session_token
    def observe():
        nonlocal authorization,observation
        adapter.authority.validate(lease)
        current=adapter.observations.latest()
        if (adapter._active.get(action.action_id) is not authorization or cancelled.is_set() or
                adapter.observations._session_token is not session_token or current is None or
                current.session_id!=action.session_id or current.sequence<observation.sequence or
                current.sequence<action.observation_sequence):
            raise PermissionError('toggle_observation_unavailable')
        # A newer frame is fresh evidence, never a revival of the old handle.
        # Keep the approved action/lease/target intact; revalidate the target next.
        observation=current
        authorization=(action,lease,current,cancelled)
        adapter._active[action.action_id]=authorization
    observe()
    def check(submit=False):
        with adapter._native() as (target,value,_,__):
            adapter._admit_effect(authorization,target,None,submit=submit)
            return value
    # Unauthorized direct transport calls fail before even launching a client.
    before=await adapter._work(check)
    r=adapter.registration
    request=dict(version=1,operation=action.operation,pid=r.pid,window=r.window,target=r.toggle,decoy=r.toggle_decoy,
        label=r.toggle_label,nonce=r.nonce,birth=str(adapter.birth),control_id=action.target.control_id,before=before,
        action_id=action.action_id,scope=lease.digest,deadline=int(time.time()*1000)+5000)
    payload=json.dumps(request,sort_keys=True,separators=(',',':')).encode('ascii')
    request_hash=hashlib.sha256(payload).hexdigest()
    spawn=asyncio.create_task(_spawn());adapter.managed_jobs.add(spawn);adapter.authority.track(spawn)
    process=None
    async def response():
        line=await process.stdout.readline()
        if len(line)>4096:raise ValueError('toggle_response_too_large')
        value=json.loads(line)
        if not isinstance(value,dict) or value.get('request')!=request_hash:
            raise ValueError('toggle_response_mismatch')
        return value
    try:
        async with asyncio.timeout(4.5):  # Within the existing controller's five-second dispatch bound.
            process=await asyncio.shield(spawn)
            observe()
            await adapter._work(check)  # Revoke/stop may race process creation.
            process.stdin.write(payload+b'\n');await process.stdin.drain()
            ready=await response()
            if (set(ready)!={'stage','request','challenge','thread','apartment'} or ready['stage']!='ready' or
                    ready['apartment']!='MTA' or type(ready['thread']) is not int or
                    not isinstance(ready['challenge'],str) or not re.fullmatch('[0-9a-f]{32}',ready['challenge'])):
                raise ValueError('toggle_prepare_rejected')
            observe()
            await adapter._work(lambda:check(True))
            # No yield between the final authority check and pipe write.
            adapter.authority.validate(lease)
            if cancelled.is_set() or observation._revoked.is_set():raise PermissionError('toggle_cancelled_or_frame_replaced')
            grant=dict(commit=ready['challenge'],request=request_hash,expires=int(time.time()*1000)+500)
            process.stdin.write(json.dumps(grant,separators=(',',':')).encode()+b'\n')
            await process.stdin.drain();process.stdin.close()
            admitted=await response()
            if (set(admitted)!={'stage','request','thread'} or admitted['stage']!='admitted' or
                    admitted['thread']!=ready['thread']):
                raise ValueError('toggle_grant_not_admitted')
            result=await response()
            if (set(result)!={'stage','request','thread'} or result['stage']!='returned' or
                    result['thread']!=ready['thread'] or await process.wait()!=0):
                raise ValueError('toggle_outcome_unverified')
            # A returned UIA call is not a verified postcondition. The adapter
            # and controller perform independent native readback after this.
    finally:
        async def reap():
            child=process if process is not None else await asyncio.shield(spawn)
            if child.returncode is None:
                try:child.kill()
                except ProcessLookupError:pass
                await child.wait()
        cleanup=asyncio.create_task(reap());adapter.managed_jobs.add(cleanup);adapter.authority.track(cleanup)
        def finished(task):
            # A failed reap leaves an unresolved ownership record in this set.
            if not task.cancelled() and task.exception() is None:
                adapter.managed_jobs.discard(task);adapter.managed_jobs.discard(spawn)
        cleanup.add_done_callback(finished)
        try:await asyncio.wait_for(asyncio.shield(cleanup),.25)
        except (TimeoutError,asyncio.CancelledError):pass
