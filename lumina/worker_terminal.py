"""Owned Windows ConPTY adapter with bounded polling and explicit cleanup."""
import asyncio
import socket
import time


class PtyStream:
    def __init__(self, owner): self.owner=owner
    async def read(self,size):
        while True:
            try:
                chunk=await asyncio.to_thread(self.owner.pty.read,size)
                if chunk:return chunk.encode('utf-8')
            except socket.timeout:
                if self.owner.returncode is not None:return b''
            except (EOFError,OSError):return b''
            if self.owner.closed:return b''
            await asyncio.sleep(.02)


class EmptyStream:
    async def read(self,size):return b''


class WindowsTerminal:
    def __init__(self,pty):
        self.pty=pty;self.pid=pty.pid;self.closed=False
        pty.fileobj.settimeout(.2)
        self.stdout=PtyStream(self);self.stderr=EmptyStream()
    @classmethod
    async def spawn(cls,argv,cwd,env):
        from winpty import PtyProcess
        pty=await asyncio.to_thread(PtyProcess.spawn,argv,cwd=cwd,env=env,dimensions=(40,32767),backend=0)
        return cls(pty)
    @property
    def returncode(self):
        return None if self.pty.pty.isalive() else self.pty.exitstatus
    async def wait(self):
        while self.returncode is None:await asyncio.sleep(.05)
        return self.returncode
    async def close(self):
        if self.closed:return
        self.closed=True
        # pywinpty marks closed on process exit before closing its sockets.
        self.pty.closed=False
        await asyncio.to_thread(self.pty.close,True)
