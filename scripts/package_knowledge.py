"""Opt-in personal graph packaging; no model calls or invented graph nodes."""
import json,shutil,sys
from pathlib import Path


def package_knowledge(source,app):
    source=Path(source).resolve();app=Path(app).resolve()
    graph=source/'graphify-out/graph.json'
    if not graph.is_file():raise ValueError('Personal graph is missing; build it before packaging.')
    if (app/'notes').exists() or (app/'graphify-out').exists():
        raise ValueError('Refusing to overwrite packaged knowledge.')
    data=json.loads(graph.read_text(encoding='utf-8'))
    notes=(source/'notes').resolve(strict=True)
    files=[]
    for item in notes.rglob('*'):
        if item.is_symlink() or item.is_junction():raise ValueError('Knowledge links are not packaged.')
        if item.is_file():
            if item.suffix not in {'.md','.txt','.json'}:continue
            if item.stat().st_size>20_000_000:raise ValueError('Knowledge file is oversized.')
            files.append(item)
    if len(files)>1000 or sum(p.stat().st_size for p in files)>50_000_000:raise ValueError('Knowledge package exceeds limits.')
    def relative(path):
        p=Path(path)
        if not p.is_absolute():p=source/p
        p=p.resolve(strict=True)
        if not p.is_relative_to(notes) or p not in files:raise ValueError('Graph source is outside packaged notes.')
        return p.relative_to(source).as_posix()
    for node in data.get('nodes',[]):
        if node.get('source_file'):node['source_file']=relative(node['source_file'])
        if node.get('source_files'):node['source_files']=[relative(p) for p in node['source_files']]
    data.setdefault('metadata',{})['source_root']='notes'
    for item in files:
        target=app/item.relative_to(source);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(item,target)
    destination=app/'graphify-out';destination.mkdir(parents=True)
    (destination/'graph.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
    return {'nodes':len(data.get('nodes',[])),'hyperedges':len(data.get('hyperedges',[])),'note_files':len(files)}

if __name__=='__main__':print(json.dumps(package_knowledge(sys.argv[1],sys.argv[2])))
