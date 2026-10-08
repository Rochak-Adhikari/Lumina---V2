"""Build curated note facts with graphify communities, preserving typed edges/hyperedges.
Run with the Python interpreter that has graphify installed. No cloud calls.
"""
import json
from pathlib import Path
from graphify.build import build_from_json
from graphify.cluster import cluster
from graphify.detect import detect

ROOT=Path(__file__).resolve().parent.parent
notes=ROOT/'notes'
output=ROOT/'graphify-out'
output.mkdir(exist_ok=True)
detection=detect(notes)
extraction=json.loads((notes/'knowledge.json').read_text('utf-8'))
for n in extraction['nodes']:
    if not (notes/n['source_file']).is_file():raise ValueError('Missing source note')
graph=build_from_json(extraction,root=notes)
communities=cluster(graph)
membership={str(node):cid for cid,members in communities.items() for node in members}
# Preserve original concept IDs and n-ary relations rather than flattening export.
for n in extraction['nodes']:
    n['community']=membership.get(n['id'],0)
    n['degree']=graph.degree(n['id']) if n['id'] in graph else 0
    n['source_file']=str(notes/n['source_file'])
extraction['communities']=communities
extraction['metadata']={'source_root':str(notes),'extraction':'Curated from explicit user statements; no inferred biography','builder':'graphify build_from_json + cluster','cloud_calls':0,'token_usage':'Host extraction usage not separately available'}
(output/'graph.json').write_text(json.dumps(extraction,indent=2),encoding='utf-8')
(output/'GRAPH_REPORT.md').write_text('# Personal knowledge graph\n\nBuilt from three source notes and curated knowledge.json. Typed relations and the project-charter hyperedge are retained. Communities are detected by graphify. No cloud extraction call was made; host extraction token usage is not separately available.\n\nAge 23 is a user-stated claim, not a computed age. The supplied date of birth implies age 22 on 5 October 2026. Confirmation remains pending.\n\nEdit the notes and their curated knowledge.json facts together, then rerun scripts/build_notes_graph.py. This builder does not pretend arbitrary Markdown changes are automatically semantically extracted.\n',encoding='utf-8')
print(json.dumps({'nodes':len(extraction['nodes']),'edges':len(extraction['edges']),'hyperedges':len(extraction['hyperedges']),'communities':len(communities)}))
