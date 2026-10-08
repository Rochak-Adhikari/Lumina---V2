"""Display-only console: never starts Claude or accepts commands for it."""
import json
from pathlib import Path
import sys
import time


def main():
    directory=Path(sys.argv[1]);worker_id=sys.argv[2]
    if sys.platform=='win32':
        import ctypes
        ctypes.windll.kernel32.SetConsoleTitleW('LUMINA Claude worker '+worker_id[:8])
    print('LUMINA / CLAUDE CODE\nWorker '+worker_id+'\nLive output from the supervised worker.\n',flush=True)
    path=directory/'session.log';offset=0;identity=None
    while True:
        try:
            stat=path.stat()
            if identity!=stat.st_ino or stat.st_size<offset:offset=0;identity=stat.st_ino
            with path.open('r',encoding='utf-8') as stream:
                stream.seek(offset)
                for line in stream:
                    try:event=json.loads(line)
                    except ValueError:continue
                    if event['type']=='worker.output':print(event.get('text',''),end='',flush=True)
                    else:print('\n['+event['type']+']',flush=True)
                offset=stream.tell()
            metadata=json.loads((directory/'metadata.json').read_text('utf-8'))
            if metadata.get('status') in {'COMPLETED','FAILED','CANCELLED','TERMINATED'}:
                print('\n'+metadata['status']+' — '+(metadata.get('summary') or metadata.get('error') or ''),flush=True)
                print('Session log: '+str(path),flush=True)
                input('Press Enter to close this display. ')
                return
        except (FileNotFoundError,json.JSONDecodeError):pass
        time.sleep(.2)


if __name__=='__main__':main()
