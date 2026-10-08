"""Provider-neutral camera capability; Windows device ownership lives in the helper."""
import asyncio
import json
import os
from pathlib import Path
import time
import uuid


class CameraCapture:
    def __init__(self, helper=None, spool=None):
        self.last_frame = None
        root=Path(__file__).resolve().parent.parent
        self.helper=Path(helper) if helper else next((p for p in (
            root.parent/'camera'/'LUMINA.Camera.exe',
            root/'dist'/'LUMINA-Portable'/'camera'/'LUMINA.Camera.exe',
        ) if p.is_file()), root/'camera'/'LUMINA.Camera.exe')
        self.spool=Path(spool) if spool else Path(os.environ.get('LOCALAPPDATA',Path.home()/'AppData'/'Local'))/'LUMINA'/'camera'

    async def capture_camera_frame(self):
        self.last_frame = None
        if not self.helper.is_file():
            return {'ok':False,'error':'Windows camera helper is not installed.'}
        self.spool.mkdir(parents=True,exist_ok=True)
        # Expired protocol artifacts from a crashed engine/helper are disposable.
        for path in self.spool.iterdir():
            prefix, _, suffix=path.name.partition('.')
            if len(prefix)==32 and all(c in '0123456789abcdef' for c in prefix) and suffix in {
                'request.json','response.json','jpg','request.tmp','response.json.tmp','jpg.tmp'}:
                try:
                    if not path.is_symlink() and path.is_file() and time.time()-path.stat().st_mtime>60:
                        path.unlink()
                except OSError:
                    pass
        request_id=uuid.uuid4().hex
        request=self.spool/(request_id+'.request.json')
        response=self.spool/(request_id+'.response.json')
        image=self.spool/(request_id+'.jpg')
        temporary=request.with_suffix('.tmp')
        temporary.write_text(json.dumps({'id':request_id,'expires':time.time()+20}),encoding='utf-8')
        temporary.replace(request)
        process=None
        try:
            process=await asyncio.create_subprocess_exec(str(self.helper),request_id,
                cwd=str(self.helper.parent),creationflags=0x08000000 if os.name=='nt' else 0,
                stdin=asyncio.subprocess.DEVNULL,stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.DEVNULL)
            async with asyncio.timeout(22):
                await process.wait()
            if not response.is_file():return {'ok':False,'error':'Camera helper exited without a capture result.'}
            if response.stat().st_size>32768:raise ValueError('Camera response exceeds its size limit.')
            result=json.loads(response.read_text('utf-8'))
            if result.get('id')!=request_id:raise ValueError('Camera response does not match the request.')
            if not result.get('ok'):return result
            if image.is_symlink() or not image.is_file() or not 4<=image.stat().st_size<=16*1024*1024:
                raise ValueError('Camera did not return a bounded JPEG.')
            jpeg=image.read_bytes()
            if not jpeg.startswith(b'\xff\xd8') or not jpeg.endswith(b'\xff\xd9'):raise ValueError('Camera returned an invalid JPEG.')
            self.last_frame = jpeg
            return {**result,'mime_type':'image/jpeg','byte_count':len(jpeg),
                    'message':'Captured locally. Image bytes are available to the runtime; no image has been sent to an online provider.'}
        except (OSError,ValueError,TimeoutError):
            return {'ok':False,'error':'Camera capture failed or timed out. Other LUMINA capabilities remain available.'}
        finally:
            if process and process.returncode is None:
                process.kill()
                await process.wait()
            # These are this request's disposable captures, never user documents.
            for path in (request,response,image,temporary,image.with_suffix('.jpg.tmp'),response.with_suffix('.json.tmp')):
                try:path.unlink(missing_ok=True)
                except OSError:pass
