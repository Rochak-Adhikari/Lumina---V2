"""The admission boundary: a model supplies a proposal, never authority."""
class MemoryAdmissionService:
    def __init__(self, service):
        self.service = service

    def propose(self, proposal, *, authorized=False):
        return self.service._propose(proposal, authorized=authorized)

    def admit(self, candidate_id, *, authorized=False):
        return self.service._admit(candidate_id, authorized=authorized)

    def bootstrap_record(self, item, event, entities, *, authorized=False):
        """Local reviewed-import boundary; deliberately not exposed as a model tool.

        Import time is acquisition time. The seed supplies no occurrence date.
        Historical episodes and single-source hypotheses cannot become facts.
        """
        from .policy import document, text, score
        if authorized is not True or event.get('source_type') != 'bootstrap_seed':
            raise ValueError('Seed admission requires explicit local import authority.')
        s = self.service
        item = document(item)
        kind = item['kind']
        confidence = min(.75, score(item.get('confidence', .65)))
        project = entities.get(item.get('project'))
        s._project(project)
        with s.repo.transaction():
            if kind == 'event' or (kind == 'goal' and item['temporal'] == 'historical'):
                summary = text(item.get('data', {}).get('summary') or item.get('object'), maximum=4000)
                identity = s.repo.insert('episodes', dict(title='Historical seed: '+item['key'].replace('_',' '),
                    summary=summary, status='closed', project_id=project,
                    outcome='Historical report; occurrence date unknown. Timestamps represent import, not occurrence.',
                    importance=score(item.get('importance', .5))))
                actual_kind = 'episode'
            elif kind == 'behavior_pattern':
                identity = s.repo.insert('behavior_patterns', dict(pattern=text(item['data']['pattern'], maximum=4000),
                    confidence=min(.5, confidence), status='hypothesis', evidence_count=1,
                    supporting_events_json=[event['id']], project_id=project))
                actual_kind = kind
            else:
                data = dict(item.get('data', {}))
                if kind == 'fact':
                    data = {'cardinality': item.get('cardinality', 'single')}
                elif kind == 'goal':
                    data.pop('next_action', None)
                    data.setdefault('priority', score(item.get('importance', .5)))
                proposal = dict(kind=kind, source_event_id=event['id'], confidence=confidence,
                    importance=score(item.get('importance', .5)), project_id=project, data=data,
                    reason='Reviewed historical seed; not a live observation or an instruction.',
                    model_metadata={'temporal':item['temporal'], 'source_occurred_at':None})
                if kind == 'fact':
                    proposal.update(subject=entities[item['subject']], predicate=item['predicate'], object=item['object'],
                                    object_entity_id=entities.get(item.get('object_entity')))
                result = s.propose(proposal, authorized=True)
                if result.get('ok') and kind == 'decision' and item['temporal'] == 'historical' and result['decision'] == 'create':
                    s.repo.update('decisions', result['record_id'], {'status':'needs_review'})
                return {**result, 'kind':kind}
            s._evidence(actual_kind, identity, event, confidence, False, 'reviewed_seed')
            s._index(actual_kind, s.repo.get({'episode':'episodes','behavior_pattern':'behavior_patterns'}[actual_kind], identity))
            return {'ok':True, 'record_id':identity, 'kind':actual_kind, 'decision':'create'}
