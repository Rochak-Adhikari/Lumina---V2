"""Runs against a launched local-mode app; no cloud calls or real mic access."""
import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright, expect

OUT=Path(__file__).resolve().parents[1]/'artifacts'

async def main():
    OUT.mkdir(exist_ok=True)
    async with async_playwright() as p:
        browser=await p.chromium.launch(args=['--enable-unsafe-swiftshader'])
        page=await browser.new_page(viewport={'width':1440,'height':1000},device_scale_factor=1)
        errors=[]; remote=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('request',lambda r:remote.append(r.url) if not r.url.startswith(('http://127.0.0.1:8764','ws://127.0.0.1:8764','data:')) else None)
        response=await page.goto('http://127.0.0.1:8764')
        assert response.status==200
        await expect(page.locator('#runtime-health')).to_have_text('connected')
        await page.wait_for_selector('#orb canvas')
        await page.wait_for_selector('#graph canvas')
        await page.locator('#overview').click()
        await expect(page.locator('#graph')).to_have_attribute('data-settled','true',timeout=20000)
        await page.screenshot(path=str(OUT/'lumina-desktop.png'),full_page=True)
        await page.locator('#query').fill('config')
        await page.locator('#local-search button').click()
        await expect(page.locator('#search-view')).to_have_class('active')
        await expect(page.locator('#search-summary')).to_contain_text('1 direct matches')
        await expect(page.locator('#graph')).to_have_attribute('data-settled','true',timeout=20000)
        await page.screenshot(path=str(OUT/'lumina-search.png'),full_page=True)
        count=await page.locator('#results .result').count()
        assert count==1
        await page.locator('#refresh').click()
        await page.wait_for_timeout(500)
        assert '1 direct matches' in await page.locator('#search-summary').inner_text()
        await page.locator('#results .result').first.click()
        assert 'config.py' in await page.locator('#selection-name').inner_text()
        await page.locator('#close-selection').click()
        await page.locator('#message').fill('Hello LUMINA')
        await page.locator('.send').click()
        await expect(page.locator('#conversation')).to_contain_text('Online reasoning is not configured')
        await page.locator('#mic').click()
        assert 'Voice needs Gemini' in await page.locator('#notice').inner_text()
        await page.locator('#settings-open').click()
        assert await page.locator('#settings').is_visible()
        await page.locator('#settings-close').click()
        for name,width,height in [('narrow',390,844),('short',1280,600)]:
            await page.set_viewport_size({'width':width,'height':height})
            await page.wait_for_timeout(700)
            assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            box=await page.locator('#orb canvas').bounding_box()
            assert box['width']>100 and box['height']>100
            await page.screenshot(path=str(OUT/f'lumina-{name}.png'),full_page=True)
        assert not errors,errors
        assert not remote,remote
        report={'page_load':True,'orb_and_graph_canvases':True,'desktop_and_responsive_screenshots':True,
                'local_search_actual_repo_file':True,'direct_count':count,'refresh_preserved_search':True,
                'offline_text_and_voice_messages':True,'settings':True,'page_errors':errors,'external_requests':remote,
                'real_gemini':'not tested: credentials absent','physical_microphone_and_speaker':'not tested'}
        (OUT/'browser-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report,indent=2))
        await browser.close()

asyncio.run(main())
