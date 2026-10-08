"""Bounded acceptance checks. No private frames, credentials or window titles saved."""
import asyncio
import io
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from PIL import Image
from lumina.screen_sharing import ScreenSharing
from lumina.browser_control import BrowserController
from lumina.desktop import PathResolver, WorkspaceManager
from lumina.computer_settings import ComputerSettings
from lumina.web_search import WebSearch
from lumina.youtube import YouTube


async def main():
    report={'module_root':str(Path(__import__('lumina').__file__).resolve().parent)}
    events=[]
    async def no_model():raise AssertionError('Local capture must not initialize a model')
    connection=SimpleNamespace(rt=SimpleNamespace(session_log=SimpleNamespace(write=lambda *a,**kw:events.append(kw))),live=None,sharing=False,ensure_live=no_model)
    share=ScreenSharing(connection)
    try:
        sources=await share.capture.sources()
        monitors=sources.get('monitors',[])
        report['screen_sources']={'ok':sources.get('ok'),'monitors':len(monitors)}
        if monitors:
            started=await share.start({'capture':'windows','mode':'local','target':'monitor','source':monitors[0]['id']})
            result=await share.accept(started['share_id'])
            report['screen_capture']={k:result.get(k) for k in ('ok','mode','frame_count','code')}
            if result.get('ok'):
                with Image.open(io.BytesIO(share.frame)) as image:report['screen_capture']['dimensions']=image.size
            await share.stop()
            report['screen_cleanup']=share.frame is None and share.capture.last_frame is None and not connection.sharing
    finally:await share.close()
    with tempfile.TemporaryDirectory(prefix='lumina-browser-repair-') as folder:
        root=Path(folder)
        browser=BrowserController(PathResolver(WorkspaceManager(root)))
        try:
            started=await browser.execute('start')
            report['browser']={k:started.get(k) for k in ('ok','status','code')}
            if started.get('ok'):
                tabs=await browser.execute('list_tabs')
                inspected=await browser.execute('inspect',tab_id=tabs['tabs'][0]['tab_id'])
                report['browser']['inspected']=inspected.get('ok')
        finally:
            closed=await browser.close()
            report['browser_closed']=closed.get('ok')
    settings=ComputerSettings()
    inventory=await settings.execute('list_targets',kind='audio')
    report['audio']={'ok':inventory.get('ok'),'endpoints':len(inventory.get('targets',[]))}
    search=await WebSearch().search('Windows WebView2 documentation',limit=3)
    report['free_search']={k:search.get(k) for k in ('ok','provider','count','code')}
    report['free_search']['links']=[r['url'] for r in search.get('results',[])]
    metadata=await YouTube().execute('metadata',url='https://www.youtube.com/watch?v=jNQXAC9IVRw')
    report['youtube']={k:metadata.get(k) for k in ('ok','status','code','source')}
    print(json.dumps(report,indent=2))


if __name__=='__main__':asyncio.run(main())
