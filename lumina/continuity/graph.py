"""Disposable, evidence-backed view of canonical continuity, never a memory store.

Only fact subject/object links and record project_id membership become edges.
Registry entities retain their canonical IDs; small scalar values refer back to
their facts. Notes, lifecycle relationships and name-based links are not inferred.
"""
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json

from .policy import public_record

try:
    import networkx as nx
except ImportError:
    nx = None


_TABLES = {
    'entity': 'entities', 'fact': 'facts', 'goal': 'goals',
    'decision': 'decisions', 'open_loop': 'open_loops',
    'prediction': 'predictions', 'behavior_pattern': 'behavior_patterns',
}
_STATUSES = {
    'fact': {'active', 'disputed'}, 'goal': {'active', 'blocked'},
    'decision': {'active', 'needs_review', 'disputed'},
    'open_loop': {'open', 'blocked'}, 'prediction': {'pending'},
    'behavior_pattern': {'hypothesis'},
}


def _current(kind, row, instant):
    if kind == 'entity':
        return True
    if row.get('status') not in _STATUSES.get(kind, set()):
        return False
    if any(row.get(key) for key in ('superseded_at', 'completed_at', 'resolved_at')):
        return False
    try:
        for key, is_start in (('valid_from', True), ('valid_until', False),
                              ('horizon', False)):
            if row.get(key):
                value = datetime.fromisoformat(row[key].replace('Z', '+00:00'))
                if value.tzinfo is None or (value > instant if is_start else value <= instant):
                    return False
    except (ValueError, TypeError):
        return False
    return True


def _communities(nodes, edges):
    """Clustering is display metadata, never additional factual relationships."""
    adjacency = {node['id']: set() for node in nodes}
    for edge in edges:
        a, b = edge['source'], edge['target']
        if a != b:
            adjacency[a].add(b)
            adjacency[b].add(a)
    if nx is not None:
        graph = nx.Graph()
        graph.add_nodes_from(sorted(adjacency))
        graph.add_edges_from((a, b) for a in sorted(adjacency)
                             for b in sorted(adjacency[a]) if a < b)
        if graph.number_of_edges():
            groups = nx.community.greedy_modularity_communities(graph)
            algorithm = 'greedy_modularity'
        else:
            groups = nx.connected_components(graph)
            algorithm = 'connected_components'
        backend = 'networkx'
    else:
        # Bounded greedy modularity for the portable runtime, without an extra
        # dependency. Merge only when modularity strictly improves; deterministic
        # tie-breaking by canonical ID. Isolates retain their own community.
        groups={node:{node} for node in sorted(adjacency)}
        volumes={node:len(neighbors) for node,neighbors in adjacency.items()}
        between={(a,b):1 for a in adjacency for b in adjacency[a] if a<b}
        m=len(between)
        while between and m:
            gain,(a,b)=max((weight/m-volumes[a]*volumes[b]/(2*m*m),(a,b)) for (a,b),weight in between.items())
            if gain<=1e-12:break
            groups[a].update(groups.pop(b));volumes[a]+=volumes.pop(b)
            between.pop((a,b),None)
            for pair,weight in list(between.items()):
                if b in pair:
                    other=pair[1] if pair[0]==b else pair[0]
                    target=tuple(sorted((a,other)))
                    between[target]=between.get(target,0)+weight
                    del between[pair]
        groups=list(groups.values())
        algorithm, backend = ('greedy_modularity' if m else 'connected_components'), 'python'
    members = sorted((sorted(group) for group in groups), key=lambda group: group[0])
    communities = [{'id': str(i), 'members': group, 'size': len(group)}
                   for i, group in enumerate(members)]
    assignment = {member: group['id'] for group in communities for member in group['members']}
    for node in nodes:
        node['community'] = assignment[node['id']]
    return communities, {'algorithm': algorithm, 'backend': backend,
                         'deterministic': True, 'scope': 'returned_graph'}


class MemoryGraphProjection:
    MAX_NODES = 420  # Match the existing viewer's display bound.
    MAX_EDGES = 1600
    SCAN_LIMIT = 2000  # Per canonical record type; never claim an archive total.
    EVIDENCE_LIMIT = 100
    VALUE_LIMIT = 160

    def __init__(self, service):
        self.service = service
        self.repo = service.repo

    @contextmanager
    def _snapshot(self):
        # A deferred read snapshot also works inside an existing transaction.
        # Do not use current_state(), which writes a derived cache on reads.
        with self.repo.lock:
            self.repo.db.execute('SAVEPOINT continuity_graph_read')
            try:
                yield
            finally:
                self.repo.db.execute('RELEASE continuity_graph_read')

    def read(self, online=False):
        """Return a bounded current view, excluding sensitive or unsupported data.

        A revision hashes the visible canonical content in the scan, including
        record versions and provenance IDs, before display limits are applied.
        """
        with self._snapshot():
            return self._read(bool(online))

    def _read(self, online):
        instant = datetime.now(timezone.utc)
        scan_truncated = False
        evidence_truncated = False
        event_access = {}

        def provenance(kind, row):
            nonlocal evidence_truncated
            if not public_record(row, online=online):
                return None
            links = self.repo.rows(
                'SELECT * FROM evidence WHERE record_type=? AND record_id=? ORDER BY id LIMIT ?',
                (kind, row['id'], self.EVIDENCE_LIMIT + 1))
            if len(links) > self.EVIDENCE_LIMIT:
                evidence_truncated = True
                return None
            if not links:
                return None
            # Mixed-source derived records cannot launder a restricted source
            # by retaining just their less restrictive evidence links.
            for link in links:
                if not public_record(link, online=online):
                    return None
                event_id = link['event_id']
                if event_id not in event_access:
                    event = self.repo.get('events', event_id)
                    event_access[event_id] = bool(event) and self.service._event_accessible(event, online=online)
                if not event_access[event_id]:
                    return None
            return {'record_type': kind, 'record_id': row['id'], 'record_ids': [row['id']],
                    'historical_seed': any(link['source_type']=='bootstrap_seed' for link in links),
                    'requires_verification': any(link['source_type']=='bootstrap_seed' for link in links) and not row.get('confirmed_by_user'),
                    'record_versions': {row['id']: row['version']},
                    'evidence_ids': [link['id'] for link in links]}

        def records(kind):
            nonlocal scan_truncated
            clauses = ["privacy_class <> 'sensitive'"]
            params = []
            if online:
                clauses.extend(["privacy_class NOT IN ('device_local','cloud_blocked')",
                                "sync_policy <> 'cloud_blocked'"])
            if kind in _STATUSES:
                statuses = sorted(_STATUSES[kind])
                clauses.append('status IN (' + ','.join('?' for _ in statuses) + ')')
                params.extend(statuses)
            if kind == 'fact':
                # Filter archives/notes before the scan bound so they cannot
                # crowd current meaningful facts out of the candidate window.
                clauses.extend([
                    'julianday(valid_from) <= julianday(?)',
                    '(valid_until IS NULL OR julianday(valid_until) > julianday(?))',
                    "(object_entity_id IS NOT NULL OR (length(trim(object_value)) BETWEEN 1 AND ? "
                    "AND lower(predicate) NOT IN ('saved_note','legacy_note') "
                    "AND lower(predicate) NOT GLOB 'saved_note:*' "
                    "AND lower(predicate) NOT GLOB 'legacy_note:*'))",
                ])
                params.extend((instant.isoformat(), instant.isoformat(), self.VALUE_LIMIT))
            order = "CASE kind WHEN 'user' THEN 0 WHEN 'project' THEN 1 ELSE 2 END,id" if kind == 'entity' else 'id'
            rows = self.repo.rows(f'SELECT * FROM {_TABLES[kind]} WHERE '
                                  + ' AND '.join(clauses) + f' ORDER BY {order} LIMIT ?',
                                  (*params, self.SCAN_LIMIT + 1))
            scan_truncated |= len(rows) > self.SCAN_LIMIT
            return [row for row in rows[:self.SCAN_LIMIT] if _current(kind, row, instant)]

        nodes, edges, entities = {}, [], {}
        for row in records('entity'):
            proof = provenance('entity', row)
            if proof:
                entities[row['id']] = row
                nodes[row['id']] = dict(proof, id=row['id'], label=row['name'][:160], aliases=row['metadata_json'].get('aliases',[]),
                                        kind=row['kind'], assertion='entity', derived=False)

        def project_visible(row):
            project_id = row.get('project_id')
            return project_id is None or (project_id in entities and entities[project_id]['kind'] == 'project')

        groups = {}
        for row in records('fact'):
            if row['subject_entity_id'] not in entities or not project_visible(row):
                continue
            target = row.get('object_entity_id')
            value = row['object_value'].strip()
            if target is not None:
                if target not in entities:
                    continue
            elif (row['predicate'].casefold().split(':', 1)[0] in {'saved_note', 'legacy_note'}
                  or not value or len(value) > self.VALUE_LIMIT):
                continue
            proof = provenance('fact', row)
            if not proof:
                continue
            key = (row['subject_entity_id'], row['predicate'], target,
                   None if target else self.service._normal(value), row['status'], row.get('project_id'))
            if key in groups:
                previous = groups[key][1]
                previous['record_ids'].append(row['id'])
                previous['record_versions'].update(proof['record_versions'])
                previous['evidence_ids'] = sorted(set(previous['evidence_ids'] + proof['evidence_ids']))
            else:
                groups[key] = (row, proof)
        for row, proof in groups.values():
            assertion = 'disputed' if row['status'] == 'disputed' else 'fact'
            target = row.get('object_entity_id')
            shared = dict(proof, status=row['status'], assertion=assertion,
                          project_id=row.get('project_id'))
            if target is None:
                target = 'value:' + row['id']
                label = ('[Disputed] ' if assertion == 'disputed' else '') + row['object_value'].strip()
                nodes[target] = dict(shared, id=target, label=label, kind='value', derived=True)
            edges.append(dict(shared, id='fact:' + row['id'], source=row['subject_entity_id'],
                              target=target, relation=row['predicate'], kind='fact',
                              label=row['predicate'] + (' [disputed]' if assertion == 'disputed' else '')))

        for kind in ('goal', 'decision', 'open_loop', 'prediction', 'behavior_pattern'):
            for row in records(kind):
                if not project_visible(row):
                    continue
                proof = provenance(kind, row)
                if not proof:
                    continue
                hypothesis = kind in {'prediction', 'behavior_pattern'}
                assertion = 'hypothesis' if hypothesis else 'disputed' if row['status'] == 'disputed' else 'record'
                label = (row['subject'] + ': ' + row['chosen_option'] if kind == 'decision'
                         else row['prediction'] if kind == 'prediction'
                         else row['pattern'] if kind == 'behavior_pattern' else row['description'])
                label = ('[Hypothesis] ' if hypothesis else '[Disputed] ' if assertion == 'disputed' else '') + label[:160]
                shared = dict(proof, status=row['status'], assertion=assertion,
                              project_id=row.get('project_id'))
                nodes[row['id']] = dict(shared, id=row['id'], label=label, kind=kind, derived=False)
                if row.get('project_id'):
                    edges.append(dict(shared, id='project:' + row['id'], source=row['id'],
                                      target=row['project_id'], relation='belongs_to',
                                      label='belongs_to', kind='project_membership'))

        # Prefer canonical user/projects and connected nodes within the viewer's
        # bound. Output counts are exact; pre-limit counts cover only this scan.
        if self.repo.rows("SELECT key FROM meta WHERE key LIKE 'bootstrap:latest:%' LIMIT 1"):
            connected={edge[side] for edge in edges for side in ('source','target')}
            nodes={identity:node for identity,node in nodes.items() if node['record_type']!='entity'
                   or identity in connected or node['historical_seed'] or node['kind']=='user'}
        degree = defaultdict(int)
        for edge in edges:
            degree[edge['source']] += 1
            degree[edge['target']] += 1
        ordered = sorted(nodes.values(), key=lambda n: (
            0 if n['kind'] == 'user' else 1 if n['kind'] == 'project' else 2,
            -degree[n['id']], n['id']))
        kept_nodes = sorted(ordered[:self.MAX_NODES], key=lambda n: n['id'])
        kept_ids = {node['id'] for node in kept_nodes}
        kept_edges = sorted((e for e in edges if e['source'] in kept_ids and e['target'] in kept_ids),
                            key=lambda e: e['id'])[:self.MAX_EDGES]
        # Hash canonical content before display limits and community metadata.
        # Time itself is absent: expiry changes the hash only when visibility changes.
        revision = hashlib.sha256(json.dumps(
            [sorted(nodes.values(), key=lambda n: n['id']), sorted(edges, key=lambda e: e['id'])],
            sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
        communities, detection = _communities(kept_nodes, kept_edges)
        limited = len(kept_nodes) < len(nodes) or len(kept_edges) < len(edges)
        return {'nodes': kept_nodes, 'edges': kept_edges, 'hyperedges': [],
                'communities': communities, 'community_detection': detection,
                'source': 'continuity', 'revision': revision, 'revision_scope': 'visible_scanned_records',
                'unavailable': False, 'online': online,
                'counts': {'nodes': len(kept_nodes), 'edges': len(kept_edges), 'hyperedges': 0,
                           'communities': len(communities)},
                'limits': {'nodes': self.MAX_NODES, 'edges': self.MAX_EDGES,
                           'records_per_type': self.SCAN_LIMIT, 'evidence_per_record': self.EVIDENCE_LIMIT},
                'truncated': limited or scan_truncated or evidence_truncated,
                'scan_truncated': scan_truncated, 'evidence_truncated': evidence_truncated,
                'eligible_counts': {'nodes': len(nodes), 'edges': len(edges), 'scope': 'scanned_records'}}

    def consistency_check(self, data):
        """Validate a supplied projection against a fresh canonical read.

        Display-only additions (e.g. force-layout coordinates) are permitted.
        Missing items in a bounded/subset view are permitted; fabricated or stale
        items, altered provenance and repeated typed relations are not.
        """
        errors = []

        def error(code, identity=None):
            errors.append({'code': code, 'id': identity})

        with self._snapshot():
            expected = self._read(bool(data.get('online', False)))
            instant = datetime.now(timezone.utc)
            node_ids = {node.get('id') for node in data.get('nodes', [])}
            for collection in ('nodes', 'edges', 'hyperedges'):
                canonical = {item['id']: item for item in expected[collection]}
                seen, relations = set(), set()
                for item in data.get(collection, []):
                    identity = item.get('id')
                    if identity in seen:
                        error('duplicate_' + collection, identity)
                    seen.add(identity)
                    if collection == 'edges':
                        if item.get('source') not in node_ids or item.get('target') not in node_ids:
                            error('orphan_edge', identity)
                        relation = tuple(item.get(key) for key in
                                         ('source', 'target', 'relation', 'record_type', 'status', 'project_id'))
                        if relation in relations:
                            error('duplicate_relation', identity)
                        relations.add(relation)
                    if not item.get('evidence_ids'):
                        error('missing_evidence', identity)
                    record_ids = item.get('record_ids', [])
                    if not record_ids or item.get('record_id') not in record_ids:
                        error('missing_record', identity)
                    for record_id in record_ids:
                        kind, row = self.service._find(record_id)
                        if row is None:
                            error('unknown_record', record_id)
                        elif not _current(kind, row, instant):
                            error('noncurrent_record', record_id)
                    original = canonical.get(identity)
                    if original is None:
                        error('unsupported_' + collection, identity)
                        continue
                    if any(item.get(key) != original[key] for key in
                           ('record_type', 'record_id', 'record_ids', 'record_versions', 'evidence_ids')):
                        error('invalid_provenance', identity)
                    if any(item.get(key) != value for key, value in original.items() if key != 'community'):
                        error('canonical_mismatch', identity)
            if data.get('source') != 'continuity':
                error('invalid_source')
            if data.get('revision') != expected['revision']:
                error('stale_revision')
        return {'ok': not errors, 'errors': errors, 'revision': expected['revision']}
