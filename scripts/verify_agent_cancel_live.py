"""Cancel only an isolated, disposable native process, never a user's agent."""
import asyncio,json,os,sys,tempfile,ctypes
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from lumina.tmux_worker import TmuxWorker
from lumina.tasks import TaskManager

async def main():
    root=Path(tempfile.mkdtemp(prefix='lumina-cancel-check-'))
    os.environ['LOCALAPPDATA']=str(root)
    worker=TmuxWorker(root,'claude','C:/msys64')
    socket=str(root/'test.sock'); name='lumina-cancel-fixture'
    pidfile=root/'pid.txt'
    fixture=root/'fixture.py'
    fixture.write_text('import os,time,subprocess,sys,json\nfrom pathlib import Path\nchild=subprocess.Popen([sys.executable,"-c","import time;time.sleep(120)"])\nPath('+repr(str(pidfile))+').write_text(json.dumps([os.getpid(),child.pid]))\ntime.sleep(120)\n')
    import shlex
    command=shlex.quote(worker.path(sys.executable))+' '+shlex.quote(fixture.as_posix())
    output=await worker.command('-S',socket,'new-session','-d','-s',name,'-P','-F','#{pane_id}',command)
    worker.records['fixture']={'name':name,'socket':socket,'pane':output.strip(),'instruction':'Disposable process cancellation check','workspace':str(root)}
    worker.save();worker.restore('fixture')
    tasks=TaskManager({'claude':worker})
    process=None;child_process=None
    try:
        for _ in range(100):
            if pidfile.exists():break
            await asyncio.sleep(.1)
        assert pidfile.exists(),'Native process did not start'
        pid,child_pid=json.loads(pidfile.read_text())
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.OpenProcess.restype=ctypes.c_void_p
        kernel.WaitForSingleObject.argtypes=[ctypes.c_void_p,ctypes.c_uint32]
        kernel.CloseHandle.argtypes=[ctypes.c_void_p]
        process=kernel.OpenProcess(0x100000,False,pid)
        child_process=kernel.OpenProcess(0x100000,False,child_pid)
        assert process,'Cannot observe fixture process'
        assert child_process,'Cannot observe fixture child process'
        result=await tasks.cancel_task('fixture')
        assert result['status']=='CANCELLED',result
        stopped=await asyncio.to_thread(kernel.WaitForSingleObject,process,5000)==0
        assert stopped,'tmux disappeared but native worker process survived'
        child_stopped=await asyncio.to_thread(kernel.WaitForSingleObject,child_process,5000)==0
        assert child_stopped,'Worker child survived cancellation'
        assert result['status']=='CANCELLED',result
        assert (await tasks.remove_task('fixture'))['status']=='REMOVED'
        report={'native_process_stopped':stopped,'native_child_stopped':child_stopped,'session_cancelled':True,'inactive_record_removed':True,'isolated_registry':True}
        target=Path(__file__).resolve().parents[1]/'artifacts/agent-cancel-live.json'
        target.write_text(json.dumps(report,indent=2));print(json.dumps(report))
    finally:
        if process:kernel.CloseHandle(process)
        if child_process:kernel.CloseHandle(child_process)
        await tasks.close()

asyncio.run(main())
