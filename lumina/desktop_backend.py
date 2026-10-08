"""Owned desktop server: EOF or shutdown on private stdin triggers aiohttp cleanup."""
import asyncio
import json
import os
import sys
from pathlib import Path
from aiohttp import web
from .config import Config
from .server import create_app

def configuration():
    bundled_browser=Path(sys.executable).resolve().parent.parent/'playwright-browsers'
    if bundled_browser.is_dir():
        os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH',str(bundled_browser))
    c=Config.load()
    return c

async def serve():
    c=configuration()
    runner=web.AppRunner(create_app(c),access_log=None)
    await runner.setup()
    try:
        await web.TCPSite(runner,c.host,c.port).start()
        await asyncio.to_thread(sys.stdin.readline)
    finally:
        await runner.cleanup()

if __name__=='__main__':
    if '--describe' in sys.argv:
        c=configuration()
        print(json.dumps({'host':c.host,'port':c.port}))
    else:
        asyncio.run(serve())
