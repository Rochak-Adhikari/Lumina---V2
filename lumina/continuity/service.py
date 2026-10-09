"""Canonical local continuity APIs. Providers see evidence, never SQL or authority."""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import time
from uuid import uuid4

from .admission import MemoryAdmissionService
from .policy import document, now, timestamp, text, score, PRIVACY, public_record
from .repository import Repository

TABLES = {'fact': 'facts', 'decision': 'decisions', 'goal': 'goals',
          'commitment': 'commitments', 'open_loop': 'open_loops', 'episode': 'episodes',
          'prediction': 'predictions', 'behavior_pattern': 'behavior_patterns',
          'relationship': 'relationships', 'entity': 'entities', 'event': 'events'}
MUTABLE_KINDS = {'fact', 'decision', 'goal', 'commitment', 'open_loop'}
PROPOSAL_KEYS = {'kind', 'type', 'subject', 'predicate', 'object', 'source_event_id',
                 'confidence', 'stability', 'importance', 'reason', 'project_id',
                 'privacy_class', 'data', 'supersedes', 'model_metadata', 'object_entity_id'}
STATE_STATUSES = {'active', 'open', 'blocked', 'pending', 'needs_review', 'disputed'}


class MemoryService:
    def __init__(self, path=':memory:'):
        self.repo = Repository(path)
        self.db = self.repo.db  # Legacy callers only; not exposed as a model tool.
        self.path = Path(path)
        self.pending = {}
        self.last_user_event_id = None
        self.metrics = {'retrievals': 0, 'retrieval_ms': 0.0, 'context_bytes': 0, 'consolidations': 0}
        self.admission = MemoryAdmissionService(self)
        with self.repo.transaction():
            stored = self.repo.rows('SELECT value FROM meta WHERE key=?', ('device_id',))
            self.device_id = stored[0]['value'] if stored else str(uuid4())
            if not stored:
                self.db.execute('INSERT INTO meta(key,value) VALUES(?,?)', ('device_id', self.device_id))
        self.user_id = self.entity('user', 'User', 'local-user')['id']
        self._closed = False

    def status(self):
        with self.repo.transaction():
            counts = {kind: self.repo.rows(f'SELECT count(*) AS n FROM {table}')[0]['n'] for kind, table in TABLES.items()}
            rejected = self.repo.rows("SELECT count(*) AS n FROM memory_candidates WHERE decision='reject'")[0]['n']
            contradictions = self.repo.rows("SELECT count(*) AS n FROM relationships WHERE relationship_type='CONTRADICTS'")[0]['n']
            corrections = self.repo.rows("SELECT count(*) AS n FROM events WHERE event_type='memory.corrected'")[0]['n']
            outcomes=self.repo.rows("SELECT outcome,count(*) n FROM predictions WHERE outcome IN ('correct','incorrect') GROUP BY outcome")
            tested=sum(r['n'] for r in outcomes)
            correct=sum(r['n'] for r in outcomes if r['outcome']=='correct')
        return {'ok': True, 'status': 'ready', 'schema_version': self.repo.schema_version,
                'counts': counts, 'rejected_proposals': rejected, 'contradictions': contradictions,
                'corrections': corrections, 'metrics': dict(self.metrics),
                'prediction_evaluations':tested,'prediction_accuracy':correct/tested if tested else None,
                'retrieval': 'sqlite_fts5_structured', 'embeddings': 'not_configured', 'cloud_sync': 'not_implemented'}

    def record_event(self, event_type, payload, *, source_type='runtime', source_id=None,
                     session_id=None, device_id=None, project_id=None, importance=.5, timestamp=None):
        event_type = text(event_type, 'event type', 100)
        if not re.fullmatch(r'[a-z][a-z0-9_.-]{0,99}', event_type):
            raise ValueError('Invalid event type.')
        payload = document(payload)
        source_type = text(source_type, 'source type', 60)
        source_id = text(source_id or str(uuid4()), 'source ID', 256)
        from .policy import timestamp as normalize_time
        observed = normalize_time(timestamp)
        for value in (session_id, device_id, project_id):
            if value is not None:
                text(value, 'scope ID', 256)
        self._project(project_id)
        with self.repo.transaction():
            existing = self.repo.rows('SELECT * FROM events WHERE source_type=? AND source_id=? AND event_type=? LIMIT 1',
                                      (source_type, source_id, event_type))
            if existing:
                return existing[0]
            privacy = payload.pop('_privacy_class', 'private') if isinstance(payload, dict) else 'private'
            if privacy not in PRIVACY:
                raise ValueError('Invalid privacy class.')
            identity = self.repo.insert('events', dict(event_type=event_type, timestamp=observed,
                session_id=session_id, device_id=device_id or self.device_id, project_id=project_id,
                source_type=source_type, source_id=source_id, payload_json=payload,
                importance=score(importance, 'importance'), privacy_class=privacy))
            return self.repo.get('events', identity)

    def entity(self, kind, name, canonical_key=None, metadata=None):
        kind, name = text(kind, 'entity kind', 60), text(name, 'entity name', 512)
        if kind not in {'user','person','project','device','application','file','technology','organization','goal','decision','task','workspace'}:
            raise ValueError('Unsupported entity kind.')
        metadata = document(metadata or {})
        # Names are labels, not identities. Unkeyed entities always get a new ID.
        key = text(canonical_key or str(uuid4()), 'entity key', 2048)
        with self.repo.transaction():
            rows = self.repo.rows('SELECT * FROM entities WHERE canonical_key=?', (key,))
            if rows:
                if rows[0]['kind'] != kind:
                    raise ValueError('That stable identity belongs to a different entity kind.')
                return rows[0]
            identity = self.repo.insert('entities', dict(kind=kind, name=name, canonical_key=key, metadata_json=metadata))
            event = self.record_event('entity.registered', {'entity_id': identity, 'kind': kind}, source_id=identity)
            self._evidence('entity', identity, event, .99, False, 'registry')
            return self.repo.get('entities', identity)

    def _project(self, project_id):
        if project_id is not None:
            row = self.repo.get('entities', project_id)
            if not row or row['kind'] != 'project':
                raise ValueError('Use an existing project identity.')

    def _find(self, identity):
        text(identity, 'record ID', 256)
        for kind, table in TABLES.items():
            row = self.repo.get(table, identity)
            if row:
                return kind, row
        return None, None

    def _event_accessible(self,event,online=False):
        if not public_record(event,online=online):return False
        # A private source is not made public by referencing it from a generated
        # episode or by requesting the timeline instead of the sensitive fact.
        for link in self.repo.rows('SELECT record_id FROM evidence WHERE event_id=? LIMIT 101',(event['id'],)):
            _,record=self._find(link['record_id'])
            if record and not public_record(record,online=online):return False
        candidates=self.repo.rows('SELECT privacy_class,sync_policy FROM memory_candidates WHERE source_event_id=? LIMIT 101',(event['id'],))
        return all(public_record(c,online=online) for c in candidates)

    def _evidence(self, kind, identity, event, confidence, confirmed, method, model_metadata=None):
        fingerprint = hashlib.sha256((event['source_type']+'\0'+event['source_id']).encode()).hexdigest()
        old = self.repo.rows('SELECT id FROM evidence WHERE record_type=? AND record_id=? AND source_fingerprint=?',
                             (kind, identity, fingerprint))
        if old:
            return False
        self.repo.insert('evidence', dict(record_type=kind, record_id=identity, event_id=event['id'],
            source_type=event['source_type'], source_id=event['source_id'], observed_at=event['timestamp'],
            extraction_method=method, confidence=confidence, confirmed_by_user=int(confirmed),
            model_metadata_json=model_metadata or {}, source_fingerprint=fingerprint,
            privacy_class=event.get('privacy_class', 'private')))
        return True

    def _index(self, kind, row):
        keys = {'fact': ('predicate','object_value'), 'decision': ('subject','chosen_option','reasoning','alternatives_json'),
                'goal': ('description',), 'commitment': ('description',), 'open_loop': ('description','next_action'),
                'episode': ('title','summary','outcome'), 'prediction': ('prediction',), 'behavior_pattern': ('pattern',)}
        content = ' '.join(str(row.get(key, '')) for key in keys.get(kind, ())).replace('_',' ')
        if kind == 'fact':
            entity = self.repo.get('entities', row['subject_entity_id'])
            content = (entity['name'] if entity else '') + ' ' + content
        if content.strip():
            self.repo.refresh_index(kind, row['id'], content)

    def propose(self, proposal, *, authorized=False):
        return self.admission.propose(proposal, authorized=authorized)

    def admit(self, candidate_id, *, authorized=False):
        return self.admission.admit(candidate_id, authorized=authorized)

    def _validate_proposal(self, proposal):
        if is_dataclass(proposal):
            proposal = asdict(proposal)
        if not isinstance(proposal, dict) or set(proposal) - PROPOSAL_KEYS:
            raise ValueError('The proposal has unsupported fields; model output cannot declare authority.')
        p = document(proposal)
        p['kind'] = p.get('kind', p.get('type', 'fact'))
        if p['kind'] not in MUTABLE_KINDS:
            raise ValueError('Unsupported memory proposal kind.')
        event = self.repo.get('events', p.get('source_event_id', ''))
        if not event or event['source_type'] not in {'user', 'runtime', 'tool', 'legacy', 'model', 'bootstrap_seed'}:
            raise ValueError('The proposal requires an existing source event.')
        if event['event_type'].startswith('memory.') and event['event_type'] != 'memory.confirmed':
            raise ValueError('A memory lifecycle event is not independent evidence.')
        p['confidence'] = score(p.get('confidence', .7))
        p['stability'] = score(p.get('stability', .5), 'stability')
        p['importance'] = score(p.get('importance', .5), 'importance')
        p['reason'] = text(p.get('reason', 'proposal'), 'reason', 1024)
        p['data'] = p.get('data', {})
        if not isinstance(p['data'], dict):
            raise ValueError('Proposal data must be an object.')
        privacy = p.get('privacy_class', event.get('privacy_class', 'private'))
        if privacy not in PRIVACY:
            raise ValueError('Invalid privacy class.')
        if event.get('privacy_class') in {'sensitive','device_local','cloud_blocked'}:
            privacy = event['privacy_class']
        p['privacy_class'] = privacy
        self._project(p.get('project_id'))
        if p['kind'] == 'fact':
            p['subject'] = p.get('subject', self.user_id)
            if p['subject'] == 'user':
                p['subject'] = self.user_id
            if not self.repo.get('entities', p['subject']):
                raise ValueError('Use a known subject entity ID, not a guessed name.')
            p['predicate'] = text(p.get('predicate'), 'predicate', 160).casefold()
            p['object'] = text(p.get('object'), 'object', 12000)
            if p.get('object_entity_id') and not self.repo.get('entities', p['object_entity_id']):
                raise ValueError('Use a known object entity ID.')
            if p['object'].casefold().strip('.!? ') in {'hello','hi','hey','haha','thanks','ok','okay','yes','no'}:
                raise ValueError('That is transient conversation, not durable knowledge.')
            if set(p['data']) - {'cardinality'} or p['data'].get('cardinality', 'single') not in {'single','multiple'}:
                raise ValueError('Invalid fact comparison policy.')
        else:
            self._domain_values(p)
        return p, event

    def _propose(self, proposal, *, authorized=False):
        try:
            with self.repo.transaction():
                p, event = self._validate_proposal(proposal)
                candidate = self.repo.insert('memory_candidates', dict(proposal_json=p, status='pending', decision='pending',
                    reason='Awaiting admission', source_event_id=event['id'], privacy_class=p['privacy_class']))
                if not authorized:
                    return {'ok': True, 'decision': 'pending', 'status': 'candidate', 'candidate_id': candidate,
                            'confirmation_required': True, 'message': 'Proposed memory is not yet canonical.'}
                return self._apply(candidate, p, event, confirmed=event['source_type'] == 'user')
        except (ValueError, TypeError, KeyError) as exc:
            # Do not persist malformed/secret input even in a rejected candidate.
            reason = str(exc) if isinstance(exc, ValueError) else 'Malformed memory proposal.'
            with self.repo.transaction():
                candidate = self.repo.insert('memory_candidates', dict(proposal_json={}, status='rejected', decision='reject', reason=reason))
            return {'ok': False, 'decision': 'reject', 'candidate_id': candidate, 'error': reason}

    def _admit(self, candidate_id, *, authorized=False):
        if authorized is not True:
            return {'ok': False, 'error': 'Admission requires explicit user confirmation.'}
        with self.repo.transaction():
            item = self.repo.get('memory_candidates', candidate_id)
            if not item or item['status'] != 'pending':
                return {'ok': False, 'error': 'That pending candidate is unavailable.'}
            p, source = self._validate_proposal(item['proposal_json'])
            # Approval is new historical evidence, never a rewritten source event.
            event = self.record_event('memory.confirmed', {'candidate_id': candidate_id, 'source_event_id': source['id']},
                                      source_type='user', project_id=p.get('project_id'))
            result = self._apply(candidate_id, p, event, confirmed=True)
            if result.get('record_id'):
                self._evidence(p['kind'], result['record_id'], source, min(p['confidence'], .8), False,
                               'model_proposal' if p.get('model_metadata') else 'proposal', p.get('model_metadata'))
            return result

    def _apply(self, candidate_id, p, event, *, confirmed):
        if not confirmed and (p['confidence'] < .55 or p['privacy_class'] == 'sensitive' or p.get('supersedes')):
            self.repo.update('memory_candidates', candidate_id, dict(status='rejected', decision='reject', reason='Insufficient authority or evidence.'))
            return {'ok': False, 'decision': 'reject', 'candidate_id': candidate_id, 'error': 'Explicit confirmation is required for this belief.'}
        kind = p['kind']
        confidence = max(.95, p['confidence']) if confirmed else min(.75, p['confidence'])
        if kind != 'fact':
            values = self._domain_values(p)
            values.update(project_id=p.get('project_id'), privacy_class=p['privacy_class'])
            # Compare meaningful fields, excluding lifecycle timestamps. Matching
            # labels alone never merge decisions with different reasoning.
            compare={k:v for k,v in values.items() if k not in {'made_at','status'}}
            current=self.repo.rows(f'SELECT * FROM {TABLES[kind]} WHERE project_id IS ? ORDER BY updated_at DESC LIMIT 200',(p.get('project_id'),))
            equivalent=next((r for r in current if all(r.get(k)==v for k,v in compare.items()) and r.get('status') in STATE_STATUSES),None)
            identity=equivalent['id'] if equivalent else self.repo.insert(TABLES[kind], values)
            independent=self._evidence(kind, identity, event, confidence, confirmed, 'explicit_user_statement' if confirmed else 'proposal', p.get('model_metadata'))
            decision='create' if not equivalent else 'reinforce' if independent else 'duplicate'
        else:
            current = self.repo.rows("SELECT * FROM facts WHERE subject_entity_id=? AND predicate=? AND valid_until IS NULL AND status IN ('active','disputed') ORDER BY valid_from DESC",
                                     (p['subject'], p['predicate']))
            if p.get('project_id') is not None:
                current = [r for r in current if r.get('project_id') == p['project_id']]
            else:
                current = [r for r in current if r.get('project_id') is None]
            equivalent = next((r for r in current if self._normal(r['object_value']) == self._normal(p['object']) and r.get('object_entity_id')==p.get('object_entity_id')), None)
            if equivalent and not p.get('supersedes'):
                identity = equivalent['id']
                independent = self._evidence(kind, identity, event, confidence, confirmed,
                                             'explicit_user_statement' if confirmed else 'proposal', p.get('model_metadata'))
                decision = 'reinforce' if independent else 'duplicate'
                if independent:
                    self.repo.update('facts', identity, dict(confidence=min(.99, max(equivalent['confidence'], confidence) + .01),
                        confirmed_by_user=int(bool(equivalent['confirmed_by_user']) or confirmed),
                        last_confirmed_at=max(equivalent.get('last_confirmed_at') or equivalent['valid_from'], event['timestamp'])))
            else:
                decision = 'create'
                status = 'active'
                if p.get('supersedes'):
                    old = self.repo.get('facts', p['supersedes'])
                    if not confirmed or not old or old['subject_entity_id'] != p['subject'] or old['predicate'] != p['predicate'] or old.get('project_id') != p.get('project_id'):
                        raise ValueError('Supersession requires the exact existing fact and user authority.')
                    if old['valid_until'] is not None or event['timestamp'] < old['valid_from']:
                        raise ValueError('The fact changed or the correction predates it; inspect it again.')
                    for previous in current:
                        if previous['valid_from'] > event['timestamp']:
                            raise ValueError('A correction cannot predate a current belief.')
                        self.repo.update('facts', previous['id'], dict(valid_until=event['timestamp'], status='superseded'))
                        self._review_assumptions(previous['id'], event)
                    decision = 'supersede'
                elif current and p['data'].get('cardinality', 'single') != 'multiple':
                    decision, status = 'contradict', 'disputed'
                identity = self.repo.insert('facts', dict(subject_entity_id=p['subject'], predicate=p['predicate'],
                    object_value=p['object'], object_entity_id=p.get('object_entity_id'), confidence=confidence, stability=p['stability'], importance=p['importance'],
                    valid_from=event['timestamp'], status=status, source_type=event['source_type'],
                    confirmed_by_user=int(confirmed), last_confirmed_at=event['timestamp'],
                    project_id=p.get('project_id'), privacy_class=p['privacy_class']))
                self._evidence(kind, identity, event, confidence, confirmed,
                               'explicit_user_statement' if confirmed else 'proposal', p.get('model_metadata'))
                for previous in current:
                    if decision in {'contradict', 'supersede'}:
                        self._relationship(identity, 'CONTRADICTS' if decision == 'contradict' else 'SUPERSEDES', previous['id'], event, p.get('project_id'))
        self.repo.update('memory_candidates', candidate_id, dict(status='admitted', decision=decision, reason=decision, record_id=identity))
        self._index(kind, self.repo.get(TABLES[kind], identity))
        if decision != 'duplicate':
            lifecycle = {'create':'created', 'reinforce':'reinforced', 'contradict':'contradicted', 'supersede':'superseded'}[decision]
            self.record_event('memory.'+lifecycle, {'record_id': identity, 'kind': kind, 'candidate_id': candidate_id}, project_id=p.get('project_id'))
        return {'ok': True, 'decision': decision, 'candidate_id': candidate_id, 'record_id': identity,
                'uncertainty': 'Conflicting evidence remains unresolved.' if decision == 'contradict' else None}

    @staticmethod
    def _normal(value):
        return ' '.join(value.casefold().split())

    def _domain_values(self, p):
        kind, data = p['kind'], p['data']
        allowed = {'decision': {'subject','chosen_option','alternatives','reasoning','constraints','assumptions','expected_outcome'},
                   'goal': {'description','priority','deadline','parent_goal_id'},
                   'commitment': {'description','owner_entity_id','due_at'},
                   'open_loop': {'description','blocked_by','next_action','task_id'}}[kind]
        if set(data) - allowed:
            raise ValueError('Unsupported fields for this memory kind.')
        if kind == 'decision':
            result = {k: text(data.get(k, ''), k, 4000, empty=k in {'reasoning','expected_outcome'})
                      for k in ('subject','chosen_option','reasoning','expected_outcome')}
            for key in ('alternatives','constraints','assumptions'):
                value = data.get(key, [])
                if not isinstance(value, list) or len(value) > 30:
                    raise ValueError('Decision context must be a bounded list.')
                result[key+'_json'] = value
            for assumption in data.get('assumptions', []):
                if isinstance(assumption, dict) and assumption.get('fact_id') and not self.repo.get('facts', assumption['fact_id']):
                    raise ValueError('An assumption refers to an unknown fact.')
            return dict(result, status='active', made_at=now(), importance=p.get('importance', .5))
        result = {'description': text(data.get('description'), 'description', 4000), 'status': 'open' if kind == 'open_loop' else 'active'}
        if kind == 'goal':
            result['priority'] = score(data.get('priority', .5), 'priority')
            result['deadline'] = timestamp(data['deadline']) if data.get('deadline') else None
            if data.get('parent_goal_id') and not self.repo.get('goals', data['parent_goal_id']):
                raise ValueError('Unknown parent goal.')
            result['parent_goal_id'] = data.get('parent_goal_id')
        elif kind == 'commitment':
            owner = data.get('owner_entity_id', self.user_id)
            if not self.repo.get('entities', owner):
                raise ValueError('Unknown commitment owner.')
            result.update(owner_entity_id=owner, due_at=timestamp(data['due_at']) if data.get('due_at') else None,
                          confidence=p.get('confidence', .7))
        else:
            blocked = data.get('blocked_by', [])
            if not isinstance(blocked, list) or len(blocked) > 30 or any(not self._find(i)[1] for i in blocked):
                raise ValueError('Blocked items must reference existing records.')
            result.update(blocked_by_json=blocked, next_action=text(data.get('next_action',''), empty=True, maximum=2000), task_id=data.get('task_id'))
            if blocked:
                result['status'] = 'blocked'
        return result

    def _relationship(self, source, relation, target, event, project_id=None):
        if not self._find(source)[1] or not self._find(target)[1]:
            raise ValueError('A relationship must reference existing records.')
        old = self.repo.rows('SELECT * FROM relationships WHERE source_entity=? AND relationship_type=? AND target_entity=? AND valid_until IS NULL', (source, relation, target))
        if old:
            return old[0]
        identity = self.repo.insert('relationships', dict(source_entity=source, relationship_type=relation,
            target_entity=target, confidence=.99, valid_from=event['timestamp'], source_event=event['id'], project_id=project_id))
        self._evidence('relationship', identity, event, .99, False, 'explicit_relationship')
        return self.repo.get('relationships', identity)

    def relate(self, source, relationship_type, target, *, source_event_id, authorized=False, project_id=None):
        if not authorized:
            return {'ok': False, 'error': 'Relationship admission requires authority.'}
        allowed = {'BELONGS_TO','SUPPORTS','BLOCKS','DEPENDS_ON','RELATES_TO','HOSTS'}
        if relationship_type not in allowed:
            raise ValueError('Unsupported relationship type.')
        event = self.repo.get('events', source_event_id)
        if not event:
            raise ValueError('Relationship evidence is required.')
        with self.repo.transaction():
            return {'ok': True, 'record': self._relationship(source, relationship_type, target, event, project_id)}

    def _review_assumptions(self, fact_id, event):
        for row in self.repo.rows("SELECT * FROM decisions WHERE status='active' LIMIT 1000"):
            assumptions = row.get('assumptions_json') or []
            if any(isinstance(a, dict) and a.get('fact_id') == fact_id for a in assumptions):
                self.repo.update('decisions', row['id'], {'status': 'needs_review'})
                self._evidence('decision', row['id'], event, .99, False, 'assumption_changed')

    def correct(self, fact_id, new_value, *, authorized=False, source_event_id=None):
        if authorized is not True:
            return {'ok': False, 'confirmation_required': True, 'error': 'Confirm the exact correction first.'}
        with self.repo.transaction():
            old = self.repo.get('facts', fact_id)
            if not old:
                return {'ok': False, 'error': 'That fact is unavailable.'}
            event = self.repo.get('events', source_event_id) if source_event_id else None
            if event and event['source_type'] != 'user':
                return {'ok': False, 'error': 'A correction requires user evidence.'}
            if source_event_id and not event:
                return {'ok': False, 'error': 'The correction source is unavailable.'}
            if not event:
                event = self.record_event('conversation.message', {'role':'user', 'text':text(new_value)}, source_type='user', project_id=old.get('project_id'))
            result = self.propose(dict(kind='fact', subject=old['subject_entity_id'], predicate=old['predicate'], object=new_value,
                source_event_id=event['id'], supersedes=fact_id, stability=old['stability'], importance=old['importance'],
                project_id=old.get('project_id'), privacy_class=old['privacy_class']), authorized=True)
            if result.get('ok'):
                self.record_event('memory.corrected', {'old_id':fact_id, 'new_id':result['record_id']}, project_id=old.get('project_id'))
            return result

    def supersede(self, fact_id, new_value, **kwargs):
        return self.correct(fact_id, new_value, **kwargs)

    def resolve(self, identity, status='resolved', *, authorized=False):
        if authorized is not True:
            return {'ok':False, 'confirmation_required':True, 'error':'Confirm this status change first.'}
        kind, row = self._find(identity)
        valid = {'goal': {'active','blocked','completed','cancelled'}, 'commitment': {'active','fulfilled','cancelled'},
                 'open_loop': {'open','blocked','resolved','cancelled'}, 'decision': {'active','needs_review','completed','invalidated','superseded'}}
        if kind not in valid or status not in valid[kind]:
            return {'ok':False, 'error':'Invalid lifecycle transition.'}
        with self.repo.transaction():
            changes = {'status':status}
            if kind == 'goal':
                changes['completed_at'] = now() if status == 'completed' else None
            if kind == 'open_loop':
                changes['resolved_at'] = now() if status == 'resolved' else None
            self.repo.update(TABLES[kind], identity, changes)
            event = self.record_event(kind+'.'+status, {'record_id':identity}, source_type='user', project_id=row.get('project_id'))
            self._evidence(kind, identity, event, .99, True, 'user_status_change')
            return {'ok':True, 'id':identity, 'status':status}

    def recall(self, query='', **kwargs):
        from .retrieval import RetrievalService
        return RetrievalService(self).recall(query, **kwargs)

    def explain(self, identity, *, online=False):
        kind, row = self._find(identity)
        if not row or not public_record(row, online=online, include_sensitive=not online):
            return {'ok':False, 'error':'No accessible evidence supports that memory.', 'uncertainty':'unknown'}
        evidence = self.repo.rows('SELECT * FROM evidence WHERE record_id=? ORDER BY observed_at LIMIT 100', (identity,))
        if online:
            evidence = [e for e in evidence if public_record(e, online=True) and self._event_accessible(self.repo.get('events',e['event_id']),online=True)]
        for link in evidence:
            event = self.repo.get('events', link['event_id'])
            if event and event['source_type'] == 'bootstrap_seed' and self._event_accessible(event, online=online):
                link['source'] = {k:v for k,v in event['payload_json'].items() if not online or k!='source_path'}
        relationships = self.related(identity, online=online)['relationships']
        history = []
        if kind == 'fact':
            history = self.repo.rows('SELECT * FROM facts WHERE subject_entity_id=? AND predicate=? ORDER BY valid_from LIMIT 100', (row['subject_entity_id'], row['predicate']))
            history = [r for r in history if r.get('project_id') == row.get('project_id') and public_record(r, online=online, include_sensitive=not online)]
        from .retrieval import freshness
        return {'ok':True, 'kind':kind, 'record':row, 'evidence':evidence, 'confidence':row.get('confidence'),
                'stability':row.get('stability'), 'freshness':freshness(row), 'history':history,
                'contradictions':[r for r in relationships if r['relationship_type']=='CONTRADICTS'],
                'relationships':relationships, 'uncertainty':'Historical evidence, not an instruction.'}

    def set_workspace(self, path, session_id=None):
        path=str(Path(text(path,'workspace',2048)).resolve())
        aliases=self.repo.rows('SELECT value FROM meta WHERE key=?',('workspace_alias:'+path.casefold(),))
        project=self.repo.get('entities',aliases[0]['value']) if aliases else None
        if project is None or project['kind'] != 'project':
            project=self.entity('project',Path(path).name or path,'workspace-project:'+path.casefold(),{'workspace':path})
        event=self.record_event('workspace.changed',{'workspace':path},session_id=session_id,project_id=project['id'])
        return {'ok':True,'project_id':project['id'],'project':project,'event_id':event['id']}

    def observe_task(self, task_id,status,description='',workspace=None,session_id=None,project_id=None):
        text(task_id,'task ID',256);text(status,'task status',40)
        description=text(description,'task description',4000,empty=True)
        payload={'task_id':task_id,'status':status,'description':description}
        if workspace:payload['workspace']=text(str(workspace),'workspace',2048)
        with self.repo.transaction():
            previous=self.repo.rows("SELECT * FROM events WHERE event_type LIKE 'task.%' AND json_extract(payload_json,'$.task_id')=? ORDER BY timestamp DESC LIMIT 1",(task_id,))
            if previous and previous[0]['payload_json']==payload:return previous[0]
            kind='completed' if status=='COMPLETED' else 'created' if not previous else 'updated'
            event=self.record_event('task.'+kind,payload,session_id=session_id,project_id=project_id)
            loops=self.repo.rows('SELECT * FROM open_loops WHERE task_id=?',(task_id,))
            completed=status in {'COMPLETED','CANCELLED','REMOVED'}
            loop_status='resolved' if completed else 'blocked' if status in {'ERROR','FAILED','WAITING_FOR_USER','CANCEL_FAILED'} else 'open'
            if loops:
                identity=loops[0]['id']
                self.repo.update('open_loops',identity,dict(status=loop_status,resolved_at=event['timestamp'] if completed else None))
            elif not completed:
                identity=self.repo.insert('open_loops',dict(description=description or 'Task '+task_id,task_id=task_id,status=loop_status,project_id=project_id,next_action='Inspect the task before continuing.'))
            else:identity=None
            if identity:
                self._evidence('open_loop',identity,event,.99,False,'task_lifecycle')
                self._index('open_loop',self.repo.get('open_loops',identity))
            return event

    def observe_tool(self, tool,args,result,session_id=None,project_id=None,call_id=None):
        """No raw arguments, transcripts, file contents, screenshots or secrets."""
        payload={'tool':text(tool,'tool',100),'ok':result.get('ok') is True,
                 'awaiting_confirmation':bool(result.get('confirmation_required'))}
        if isinstance(result.get('status'),str):payload['status']=result['status'][:80]
        succeeded=payload['ok'] and not payload['awaiting_confirmation']
        with self.repo.transaction():
            event=self.record_event('tool.executed',payload,source_type='tool',source_id=call_id,session_id=session_id,project_id=project_id)
            if succeeded:
                kinds={'open_file':'file.opened','create_directory':'file.created','copy_path':'file.created','move_path':'file.modified',
                       'rename_path':'file.modified','open_app':'application.opened','launch_application':'application.opened',
                       'terminate_process':'application.closed','delete_path':'file.deleted'}
                if tool in kinds:
                    details={k:v for k,v in result.items() if k in {'path','output_path','application_id','pid'} and isinstance(v,(str,int))}
                    self.record_event(kinds[tool],details,source_type='tool',session_id=session_id,project_id=project_id)
            return event

    def consolidate(self,session_id=None,limit=200):
        from .state import ContinuityProjection
        return ContinuityProjection(self).consolidate(session_id,limit)

    def current_state(self,project_id=None,**kwargs):
        from .state import ContinuityProjection
        return ContinuityProjection(self).current_state(project_id,**kwargs)

    def continuation(self,project_id=None,**kwargs):
        from .state import ContinuityProjection
        return ContinuityProjection(self).continuation(project_id,**kwargs)

    def predict(self,project_id=None):
        from .state import ContinuityProjection
        return ContinuityProjection(self).predict(project_id)

    def evaluate_prediction(self,identity,outcome,*,authorized=False):
        from .state import ContinuityProjection
        return ContinuityProjection(self).evaluate_prediction(identity,outcome,authorized)

    def observe_patterns(self,project_id=None,limit=200):
        from .state import ContinuityProjection
        return ContinuityProjection(self).observe_patterns(project_id,limit)

    def open_loops(self,project_id=None):
        return {'ok':True,'items':self.current_state(project_id)['open_loops']}

    def forget_plan(self,identity):
        kind,row=self._find(identity)
        if kind not in MUTABLE_KINDS|{'episode','prediction','behavior_pattern'}:
            return {'ok':False,'error':'Only memory records can be forgotten through this operation.'}
        records={identity};events=set();candidates=set()
        # A local interactive review must not scan an unlimited event archive.
        total=sum(self.repo.rows('SELECT count(*) AS n FROM '+table)[0]['n']
                  for table in ('evidence','events','relationships','memory_candidates'))
        if total>10000:
            return {'ok':False,'error':'This archive requires an explicit offline privacy review before hard deletion. Invalidation remains available.'}
        # Follow provenance to dependent derived records. Explicit scope is shown
        # before confirmation: sharing evidence can widen the necessary erasure.
        for _ in range(20):
            before=(len(records),len(events),len(candidates))
            for evidence in self.repo.rows('SELECT record_id,event_id FROM evidence'):
                if evidence['record_id'] in records and evidence['event_id']:events.add(evidence['event_id'])
                if evidence['event_id'] in events:
                    k,r=self._find(evidence['record_id'])
                    if k and k!='entity':records.add(r['id'])
            for rel in self.repo.rows('SELECT id,source_entity,target_entity,source_event FROM relationships'):
                if rel['source_entity'] in records or rel['target_entity'] in records or rel['source_event'] in events:
                    records.add(rel['id'])
            for candidate in self.repo.rows('SELECT id,record_id,source_event_id,proposal_json FROM memory_candidates'):
                if candidate['record_id'] in records or candidate['source_event_id'] in events or candidate['proposal_json'].get('supersedes') in records:
                    candidates.add(candidate['id'])
            for event in self.repo.rows('SELECT id,payload_json FROM events'):
                def references(value):
                    if isinstance(value,str):return value in records|events|candidates
                    if isinstance(value,dict):return any(references(v) for v in value.values())
                    if isinstance(value,list):return any(references(v) for v in value)
                    return False
                if references(event['payload_json']):events.add(event['id'])
            if len(records)+len(events)+len(candidates)>1000:
                return {'ok':False,'error':'Deletion scope exceeds the interactive limit; use an explicit offline privacy review.'}
            if before==(len(records),len(events),len(candidates)):break
        else:return {'ok':False,'error':'Deletion scope requires an offline privacy review.'}
        scope={'records':sorted(records),'events':sorted(events),'candidates':sorted(candidates)}
        revisions={i:self._find(i)[1]['version'] for i in records if self._find(i)[1]}
        revisions.update({i:self.repo.get('memory_candidates',i)['version'] for i in candidates})
        return {'ok':True,**scope,'affected_count':sum(map(len,scope.values())),
                'scope_id':hashlib.sha256(json.dumps([scope,revisions],sort_keys=True).encode()).hexdigest(),
                'notice':'Deletes the record, its source evidence and dependent memories from the active database. Existing offline backups and older session logs are separate copies and are not erased.'}

    def forget(self,identity,mode='invalidate',*,authorized=False,scope_id=None):
        if authorized is not True:
            return {'ok':False,'confirmation_required':True,'error':'Exact deletion or invalidation must be confirmed.'}
        if mode=='delete':mode='hard_delete'
        if mode not in {'invalidate','expire','hard_delete'}:
            return {'ok':False,'error':'Unsupported forgetting mode.'}
        with self.repo.transaction():
            kind,row=self._find(identity)
            if not row:return {'ok':False,'error':'Memory unavailable.'}
            if mode!='hard_delete':
                if kind!='fact':return self.resolve(identity,'cancelled',authorized=True)
                event=self.record_event('memory.'+('expired' if mode=='expire' else 'invalidated'),{'record_id':identity},source_type='user',project_id=row.get('project_id'))
                self.repo.update('facts',identity,dict(valid_until=event['timestamp'],status='expired' if mode=='expire' else 'invalidated'))
                self._review_assumptions(identity,event)
                return {'ok':True,'id':identity,'mode':mode}
            plan=self.forget_plan(identity)
            if not plan.get('ok'):return plan
            if scope_id and plan['scope_id']!=scope_id:
                return {'ok':False,'error':'The deletion scope changed; confirm the new scope.'}
            records=set(plan['records']);events=set(plan['events'])
            # Remove dependent links before source events (foreign keys remain on).
            for i in records:
                self.db.execute('DELETE FROM evidence WHERE record_id=?',(i,))
                legacy=self.repo.rows('SELECT legacy_id FROM legacy_memory_map WHERE record_id=?',(i,))
                self.db.execute('DELETE FROM legacy_memory_map WHERE record_id=?',(i,))
                for old in legacy:self.db.execute('DELETE FROM memories WHERE id=?',(old['legacy_id'],))
                self.db.execute('DELETE FROM episode_events WHERE episode_id=?',(i,))
            for i in events:
                self.db.execute('DELETE FROM evidence WHERE event_id=?',(i,))
                self.db.execute('DELETE FROM episode_events WHERE event_id=?',(i,))
                self.db.execute('DELETE FROM memory_candidates WHERE source_event_id=?',(i,))
            for i in plan['candidates']:self.db.execute('DELETE FROM memory_candidates WHERE id=?',(i,))
            for i in records:
                k,r=self._find(i)
                if k:
                    if k=='goal':self.db.execute('UPDATE goals SET parent_goal_id=NULL WHERE parent_goal_id=?',(i,))
                    self.db.execute(f'DELETE FROM {TABLES[k]} WHERE id=?',(i,))
            for i in events:self.db.execute('DELETE FROM events WHERE id=?',(i,))
            self.db.execute('DELETE FROM current_state')
            self.record_event('memory.deleted',{'records_removed':len(records),'source_events_removed':len(events)},source_type='user')
            return {'ok':True,'mode':mode,'removed':len(records),'notice':plan['notice']}

    def explain_decision(self, identity, **kwargs):
        result = self.explain(identity, **kwargs)
        if result.get('kind') != 'decision':
            return {'ok':False, 'error':'That decision is unavailable.'}
        return result

    def related(self, identity, limit=20, *, online=False):
        limit = max(1, min(int(limit), 75))
        rows = self.repo.rows('SELECT * FROM relationships WHERE (source_entity=? OR target_entity=?) AND valid_until IS NULL ORDER BY created_at DESC LIMIT ?', (identity, identity, limit))
        valid = []
        for row in rows:
            if all((target := self._find(i)[1]) and public_record(target, online=online, include_sensitive=not online)
                   for i in (row['source_entity'], row['target_entity'])):
                valid.append(row)
        return {'ok':True, 'relationships':valid, 'truncated':len(rows)==limit}

    def affected_by(self, identity, limit=30):
        limit = max(1, min(int(limit), 75))
        reached, queue, edges = {identity}, [identity], []
        while queue and len(reached) <= limit:
            current = queue.pop(0)
            for edge in self.related(current, 75)['relationships']:
                if edge['relationship_type'] not in {'DEPENDS_ON','SUPPORTS','BLOCKS','BELONGS_TO'}:
                    continue
                target = edge['source_entity'] if edge['target_entity']==current else edge['target_entity']
                if target not in reached and len(reached)<limit:
                    reached.add(target); queue.append(target)
                if edge not in edges:
                    edges.append(edge)
        return {'ok':True, 'record_ids':sorted(reached-{identity}), 'relationships':edges[:150],
                'interpretation':'direct recorded relationships only; no inferred impact', 'truncated':bool(queue)}

    def timeline(self, project_id=None, limit=30, *, since=None, until=None, online=False):
        self._project(project_id)
        limit = max(1, min(int(limit), 100))
        clauses, values = [], []
        for key, value, op in [('project_id',project_id,'='), ('timestamp',timestamp(since) if since else None,'>='), ('timestamp',timestamp(until) if until else None,'<=')]:
            if value is not None:
                clauses.append(key+op+'?'); values.append(value)
        if online:
            clauses.append("privacy_class NOT IN ('sensitive','device_local','cloud_blocked') AND sync_policy<>'cloud_blocked'")
        where = ' WHERE '+' AND '.join(clauses) if clauses else ''
        rows = self.repo.rows('SELECT * FROM events'+where+' ORDER BY timestamp DESC,id DESC LIMIT ?', (*values, limit*3+1))
        visible=[r for r in rows if self._event_accessible(r,online=online)]
        return {'ok':True, 'events':visible[:limit], 'truncated':len(visible)>limit or len(rows)>limit*3, 'evidence_only':True}

    def maintenance(self, *, force=False):
        """Called by the existing runtime scheduler, never an independent daemon."""
        previous=getattr(self,'_maintenance_at',0)
        if not force and time.monotonic()-previous<300:
            return {'ok':True,'status':'not_due'}
        self._maintenance_at=time.monotonic()
        result=self.consolidate(limit=200)
        patterns=self.observe_patterns(limit=200)
        return {'ok':True,'status':'completed','consolidation':result,'patterns_updated':len(patterns['patterns'])}

    def close(self):
        if not self._closed:
            self.repo.close()
            self._closed=True
