"""Explicit, real Claude acceptance probe. Uses the user's configured CLI auth."""
import asyncio
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from lumina.workers import ClaudeCodeWorker

async def main():
    worker=ClaudeCodeWorker(Path.cwd(),'claude.ps1',90)
    try:
        result=await worker.run('acceptance','Use the workspace read tool to read requirements.txt. Report the number of dependencies. Do not modify any files.')
        print(result.summary)
    except Exception as exc:print(type(exc).__name__,str(exc))
    finally:
        state=worker.manager.list_workers()[0]
        print({k:state[k] for k in ('status','transport','exit_code','error')})
        print(state['output'][-6000:])

if __name__=='__main__':asyncio.run(main())
