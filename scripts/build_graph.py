"""Build the notes knowledge graph without the external graphify package.

Reads notes/knowledge.json, validates source files exist, computes communities
using bounded greedy modularity (the same algorithm the continuity graph uses),
and writes graphify-out/graph.json.

No cloud calls, no external dependencies beyond the Python standard library.
"""
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
notes = ROOT / 'notes'
output = ROOT / 'graphify-out'


def _greedy_modularity(nodes, edges):
    """Bounded greedy modularity matching continuity/graph.py portable path."""
    adjacency = {n: set() for n in nodes}
    for source, target in edges:
        if source != target:
            adjacency[source].add(target)
            adjacency[target].add(source)

    groups = {node: {node} for node in sorted(adjacency)}
    volumes = {node: len(neighbors) for node, neighbors in adjacency.items()}
    between = {(a, b): 1 for a in adjacency for b in adjacency[a] if a < b}
    m = len(between)
    if m == 0:
        return {i: list(members) for i, (_, members) in enumerate(sorted(groups.items()))}

    improved = True
    while improved:
        improved = False
        for a in sorted(groups):
            best_partner, best_delta = None, 0
            for b in sorted(groups):
                if a >= b:
                    continue
                cross = sum(1 for x in groups[a] for y in groups[b] if (min(x, y), max(x, y)) in between)
                va = sum(volumes.get(x, 0) for x in groups[a])
                vb = sum(volumes.get(x, 0) for x in groups[b])
                delta = cross / m - va * vb / (2 * m * m) if m else 0
                if delta > best_delta:
                    best_partner, best_delta = b, delta
            if best_partner is not None:
                groups[a] = groups[a] | groups[best_partner]
                del groups[best_partner]
                improved = True
                break

    return {i: sorted(members) for i, members in enumerate(sorted(groups.values(), key=lambda s: sorted(s)))}


def build():
    """Build the knowledge graph from curated notes/knowledge.json."""
    extraction = json.loads((notes / 'knowledge.json').read_text('utf-8'))

    # Validate source files exist
    for n in extraction['nodes']:
        source = notes / n['source_file']
        if not source.is_file():
            raise ValueError(f'Missing source note: {n["source_file"]}')

    # Compute degree
    node_ids = {n['id'] for n in extraction['nodes']}
    degree = defaultdict(int)
    valid_edges = []
    for e in extraction['edges']:
        if e['source'] in node_ids and e['target'] in node_ids:
            degree[e['source']] += 1
            degree[e['target']] += 1
            valid_edges.append((e['source'], e['target']))

    # Compute communities
    communities = _greedy_modularity(list(node_ids), valid_edges)
    membership = {node: cid for cid, members in communities.items() for node in members}

    # Annotate nodes
    for n in extraction['nodes']:
        n['community'] = membership.get(n['id'], 0)
        n['degree'] = degree.get(n['id'], 0)
        n['file_type'] = 'concept'
        # Keep source_file relative for portability (knowledge.py resolves it)

    extraction['communities'] = communities
    extraction['metadata'] = {
        'source_root': str(notes),
        'extraction': 'Curated from explicit user statements; no inferred biography',
        'builder': 'self-contained build_graph (no external graphify)',
        'cloud_calls': 0,
        'nodes': len(extraction['nodes']),
        'edges': len(extraction['edges']),
        'hyperedges': len(extraction.get('hyperedges', []))
    }

    output.mkdir(exist_ok=True)
    (output / 'graph.json').write_text(json.dumps(extraction, indent=2), encoding='utf-8')

    report = f"""# Personal knowledge graph

Built from {len(set(n['source_file'] for n in extraction['nodes']))} source notes and curated knowledge.json.
Typed relations and hyperedges are retained. Communities are detected by bounded
greedy modularity (matching the continuity graph's portable algorithm).
No cloud extraction call was made.

## Statistics
- Nodes: {len(extraction['nodes'])}
- Edges: {len(extraction['edges'])}
- Hyperedges: {len(extraction.get('hyperedges', []))}
- Communities: {len(communities)}

Edit the notes and their curated knowledge.json facts together, then rerun
`scripts/build_graph.py`. This builder does not pretend arbitrary Markdown
changes are automatically semantically extracted.
"""
    (output / 'GRAPH_REPORT.md').write_text(report, encoding='utf-8')

    result = {
        'nodes': len(extraction['nodes']),
        'edges': len(extraction['edges']),
        'hyperedges': len(extraction.get('hyperedges', [])),
        'communities': len(communities)
    }
    print(json.dumps(result))
    return result


if __name__ == '__main__':
    build()
