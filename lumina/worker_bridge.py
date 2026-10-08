"""Private stdio MCP bridge supplying bounded workspace file tools only."""
import json
from pathlib import Path
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lumina.desktop import DesktopServices


class WorkspaceBridge:
    def __init__(self, root):
        self.desktop = DesktopServices(Path(root))

    def call(self, name, args):
        if name == 'search': return self.desktop.search.search_files(query=args['query'])
        path = self.desktop.resolver.path(args['path'], must_exist=name!='write')
        if name == 'read':
            if not path.is_file(): raise ValueError('Choose a file.')
            with path.open('rb') as stream: data=stream.read(65537)
            if b'\0' in data: raise ValueError('Binary files cannot be read.')
            return {'path':str(path),'text':data[:65536].decode('utf-8',errors='replace'),'truncated':len(data)>65536}
        if name == 'write':
            text=args['text']
            if len(text)>65536: raise ValueError('Content is too large.')
            with path.open('x',encoding='utf-8') as stream: stream.write(text)
            self.desktop.search.invalidate()
            return {'path':str(path),'changed':True}
        if name == 'edit':
            if path.stat().st_size>65536: raise ValueError('File is too large.')
            original=path.read_text('utf-8');old,new=args['old'],args['new']
            if not old or original.count(old)!=1 or len(new)>65536: raise ValueError('The exact edit must match once.')
            path.write_text(original.replace(old,new,1),'utf-8')
            return {'path':str(path),'changed':True}
        raise ValueError('Unsupported workspace tool.')


def main():
    bridge=WorkspaceBridge(sys.argv[1]);definitions=[]
    for name,params in [('search',['query']),('read',['path']),('write',['path','text']),('edit',['path','old','new'])]:
        definitions.append({'name':name,'description':f'{name.title()} inside the selected workspace only. Hidden files and links are denied.', 'inputSchema':{'type':'object','properties':{p:{'type':'string','maxLength':65536} for p in params},'required':params,'additionalProperties':False}})
    for line in sys.stdin:
        try:
            req=json.loads(line)
            if 'id' not in req: continue
            method=req.get('method')
            if method=='initialize': result={'protocolVersion':'2024-11-05','capabilities':{'tools':{}},'serverInfo':{'name':'lumina-workspace','version':'1.0'}}
            elif method=='tools/list': result={'tools':definitions}
            elif method=='tools/call':
                params=req['params']
                try:
                    value=bridge.call(params['name'],params.get('arguments',{}))
                    result={'content':[{'type':'text','text':json.dumps(value)}]}
                except (ValueError,OSError,KeyError,TypeError): result={'content':[{'type':'text','text':'Workspace operation denied or unavailable.'}],'isError':True}
            elif method=='ping': result={}
            else:
                print(json.dumps({'jsonrpc':'2.0','id':req['id'],'error':{'code':-32601,'message':'Unknown method'}}),flush=True);continue
            print(json.dumps({'jsonrpc':'2.0','id':req['id'],'result':result}),flush=True)
        except (ValueError,TypeError,KeyError): continue


if __name__=='__main__': main()
