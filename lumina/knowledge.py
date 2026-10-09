"""Read-only graph-file context traversal. No inference calls or neighbor lighting."""
import json
import re
from collections import deque
from pathlib import Path

STOP={'the','a','an','is','of','in','to','and','how','what','does','my','about','with','for'}
def words(value):return set(re.findall(r"[a-z0-9]+",str(value).lower()))-STOP

class KnowledgeGraph:
    def __init__(self,path,memory=None):self.path=Path(path);self.memory=memory
    def _memory_available(self):
        # UnavailableMemory exposes failure callables through __getattr__, so
        # hasattr(memory, 'repo') does not establish a working repository.
        return callable(getattr(getattr(self.memory,'repo',None),'rows',None))
    def source(self,requested='auto'):
        if requested not in {'auto','notes','continuity'}:raise ValueError('Unknown graph source.')
        if requested!='auto':return requested
        if self._memory_available() and self.memory.repo.rows("SELECT key FROM meta WHERE key LIKE 'bootstrap:latest:%' LIMIT 1"):
            return 'continuity'
        return 'notes'
    def read(self,source='auto',online=False):
        if self.source(source)=='continuity':
            if not self._memory_available():return {'nodes':[],'edges':[],'hyperedges':[],'unavailable':True,'source':'continuity'}
            from .continuity.graph import MemoryGraphProjection
            return MemoryGraphProjection(self.memory).read(online=online)
        if not self.path.is_file():return {'nodes':[],'edges':[],'hyperedges':[],'unavailable':True}
        if self.path.stat().st_size>20_000_000:raise ValueError('Graph file exceeds 20 MB.')
        data=json.loads(self.path.read_text('utf-8'))
        nodes=data.get('nodes',[]);ids={str(n['id']) for n in nodes}
        if len(ids)!=len(nodes):raise ValueError('Duplicate concept IDs.')
        edges=data.get('edges',data.get('links',[]))
        if any(str(e['source']) not in ids or str(e['target']) not in ids for e in edges):raise ValueError('Graph contains dangling edges.')
        return {**data,'nodes':nodes,'edges':edges,'hyperedges':data.get('hyperedges',[]),'source':'notes'}
    def query(self,question,limit=75):
        if not isinstance(question,str) or not question.strip():raise ValueError('A graph question is required.')
        if not isinstance(limit,int) or isinstance(limit,bool) or not 1<=limit<=75:raise ValueError('Graph context limit must be between 1 and 75.')
        data=self.read(online=True) if self.memory else self.read();nodes={str(n['id']):n for n in data['nodes']};tokens=words(question)
        def score(n):
            return len(tokens & words(' '.join(str(n.get(k,'')) for k in ('label','aliases','source_file','source_files','source_location'))))
        seeds=sorted((i for i,n in nodes.items() if score(n)),key=lambda i:(-score(nodes[i]),i))
        adjacency={i:set() for i in nodes}
        for e in data['edges']:
            a,b=str(e['source']),str(e['target']);adjacency[a].add(b);adjacency[b].add(a)
        for h in data['hyperedges']:
            members=sorted({str(i) for i in h.get('members',h.get('nodes',[]))}&nodes.keys())
            for i in members:adjacency[i].update(set(members)-{i})
        queue=deque(seeds);scheduled=set(seeds);seen=set();reached=[]
        while queue and len(reached)<limit:
            i=queue.popleft()
            if i in seen:continue
            seen.add(i);reached.append(nodes[i])
            neighbors=sorted(adjacency[i]-scheduled)
            scheduled.update(neighbors);queue.extend(neighbors)
        return {'ok':not data.get('unavailable',False),'question':question,'seed_ids':seeds,'nodes':reached,
                'edges':[e for e in data['edges'] if str(e['source']) in seen and str(e['target']) in seen],
                'hyperedges':[h for h in data['hyperedges'] if set(map(str,h.get('members',h.get('nodes',[])))) & seen],
                'truncated':bool(queue),'count':len(reached),'traversal':'breadth_first',
                'error':'Build the notes graph first.' if data.get('unavailable') else None}
