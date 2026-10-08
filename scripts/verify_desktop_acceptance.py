"""Opt-in acceptance against a running server; opens VS Code and creates test123."""
import asyncio
import json
from pathlib import Path
from aiohttp import ClientSession
from playwright.async_api import async_playwright,expect


async def main():
    url='http://127.0.0.1:8764'
    report={}
    async with ClientSession() as client:
        config=await (await client.get(url+'/api/config')).json()
        headers={'X-Lumina-Token':config['token']}
        async with client.ws_connect(url+'/ws?token='+config['token']) as ws:
            async def command(text,tool):
                await ws.send_json({'type':'text','text':text,'voice':False})
                observed=False
                async with asyncio.timeout(20):
                    while True:
                        event=await ws.receive_json()
                        if event['type']=='state':
                            data=event['data']
                            if data.get('current_tool')==tool:observed=True
                            if observed and data['state']=='IDLE' and data.get('last_tool_result'):
                                return data['last_tool_result']
            for key,text,tool in [
                ('resolve','Find my Lumina project.','resolve_path'),
                ('editor','Open the Lumina project in VS Code.','open_with'),
                ('create','Create a folder called test123 inside the Lumina project.','create_directory'),
                ('python_files','Find every Python file inside the Lumina project.','search_files')]:
                result=await command(text,tool)
                report[key]={k:v for k,v in result.items() if k not in {'results','graph'}}
        async with async_playwright() as p:
            browser=await p.chromium.launch(args=['--enable-unsafe-swiftshader'])
            page=await browser.new_page(viewport={'width':1440,'height':1000})
            await page.goto(url);await expect(page.locator('#runtime-health')).to_have_text('connected')
            await page.locator('#workers-open').click()
            started=await (await client.post(url+'/api/tasks',headers=headers,json={'action':'start','worker':'claude-code','message':'Inspect the audio system and report what is wrong. Do not modify files.'})).json()
            async with asyncio.timeout(30):
                while True:
                    workers=(await (await client.get(url+'/api/workers')).json())['workers']
                    session=next((w for w in workers if w['task_id']==started['task_id']),None)
                    if session and session['status'] in {'COMPLETED','FAILED','CANCELLED'}:break
                    await asyncio.sleep(.2)
            report['real_claude']={k:session[k] for k in ('worker_id','status','transport','exit_code','error')}
            await expect(page.locator('#worker-select option[value="'+session['worker_id']+'"]')).to_have_count(1)
            await page.locator('#worker-select').select_option(session['worker_id'])
            await expect(page.locator('#worker-meta')).to_contain_text(session['status'])
            await page.screenshot(path='artifacts/desktop-live-acceptance.png',full_page=True)
            await browser.close()
    print(json.dumps(report,indent=2))


if __name__=='__main__':asyncio.run(main())
