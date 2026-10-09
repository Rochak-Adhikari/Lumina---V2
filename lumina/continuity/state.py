"""Rebuildable projections, bounded episodes and conservative hypotheses."""
from collections import Counter
from datetime import datetime, timedelta, timezone
import json
from .policy import now, public_record
from .retrieval import bounded_pack


class ContinuityProjection:
    def __init__(self, service):
        self.s=service

    def consolidate(self, session_id=None, limit=200):
        limit=max(1,min(int(limit),1000))
        # Only unlinked source events; lifecycle events do not create episodes.
        clauses=["e.event_type NOT LIKE 'memory.%'", "e.event_type<>'entity.registered'", 'e.session_id IS NOT NULL',
                 'NOT EXISTS(SELECT 1 FROM episode_events l WHERE l.event_id=e.id)']
        values=[]
        if session_id:
            clauses.append('e.session_id=?');values.append(session_id)
        events=self.s.repo.rows('SELECT e.* FROM events e WHERE '+' AND '.join(clauses)+' ORDER BY e.timestamp LIMIT ?',(*values,limit+1))
        groups={}
        for event in events[:limit]:
            groups.setdefault((event['session_id'],event.get('project_id'),event['privacy_class']),[]).append(event)
        ids=[]
        with self.s.repo.transaction():
            for (session,project,privacy),group in groups.items():
                key='episode:'+json.dumps([session,project,privacy])
                existing=self.s.repo.rows('SELECT value FROM meta WHERE key=?',(key,))
                episode=self.s.repo.get('episodes',existing[0]['value']) if existing else None
                if not episode:
                    identity=self.s.repo.insert('episodes',dict(title='Work session',started_at=group[0]['timestamp'],project_id=project,privacy_class=privacy))
                    self.s.db.execute('INSERT OR REPLACE INTO meta VALUES(?,?)',(key,identity))
                else:identity=episode['id']
                for event in group:
                    self.s.repo.insert('episode_events',{'episode_id':identity,'event_id':event['id']})
                    self.s._evidence('episode',identity,event,.9,False,'deterministic_session_group')
                totals=self.s.repo.rows('SELECT e.event_type,count(*) n FROM events e JOIN episode_events l ON l.event_id=e.id WHERE l.episode_id=? GROUP BY e.event_type',(identity,))
                summary='; '.join(str(r['n'])+' '+r['event_type'] for r in totals)
                row=self.s.repo.update('episodes',identity,dict(summary=summary[:4000],ended_at=group[-1]['timestamp'],status='consolidated',outcome='Observed events grouped; no inferred outcome.'))
                self.s._index('episode',row);ids.append(identity)
            self.s.metrics['consolidations']+=1
        return {'ok':True,'episodes':ids,'processed_events':min(len(events),limit),'truncated':len(events)>limit}

    def current_state(self, project_id=None, *, online=False):
        self.s._project(project_id)
        filter_sql=' AND project_id=?' if project_id else ''
        params=(project_id,) if project_id else ()
        workspace=self.s.repo.rows("SELECT * FROM events WHERE event_type='workspace.changed'"+filter_sql+' ORDER BY timestamp DESC,id DESC LIMIT 20',params)
        workspace=next((e for e in workspace if public_record(e,online=online)),None)
        project_id=project_id or (workspace.get('project_id') if workspace else None)
        project=self.s.repo.get('entities',project_id) if project_id else None
        # An unknown project must not merge unfinished tasks across every project.
        scope='project_id=?' if project_id else 'project_id IS NULL'
        params=(project_id,) if project_id else ()
        def records(table,statuses):
            rows=self.s.repo.rows(f'SELECT * FROM {table} WHERE {scope} AND status IN ({",".join("?" for _ in statuses)}) ORDER BY updated_at DESC LIMIT 30',(*params,*statuses))
            return [r for r in rows if public_record(r,online=online)]
        loops=records('open_loops',['open','blocked'])
        goals=records('goals',['active','blocked'])
        decisions=records('decisions',['active','needs_review'])
        events=self.s.repo.rows(f"SELECT * FROM events WHERE {scope} AND event_type LIKE 'task.%' ORDER BY timestamp DESC,id DESC LIMIT 200",params)
        tasks={}
        for event in events:
            if not public_record(event,online=online):continue
            payload=event['payload_json']
            task_id=payload.get('task_id')
            if task_id and task_id not in tasks:
                tasks[task_id]={**payload,'observed_at':event['timestamp'],'event_id':event['id'],'observation':'last observed; recheck before execution'}
        unfinished=[t for t in tasks.values() if t.get('status') not in {'COMPLETED','CANCELLED','REMOVED'}]
        episodes=self.s.repo.rows(f'SELECT * FROM episodes WHERE {scope} ORDER BY ended_at DESC LIMIT 10',params)
        episode=next((e for e in episodes if public_record(e,online=online)),None)
        activity=self.s.repo.rows(f'SELECT timestamp FROM events WHERE {scope} ORDER BY timestamp DESC LIMIT 1',params)
        beliefs=self.s.repo.rows("SELECT * FROM facts WHERE status IN ('active','disputed') AND valid_until IS NULL AND julianday(valid_from)<=julianday('now') "
            "AND (project_id IS ? OR (project_id IS NULL AND subject_entity_id=?)) "
            "AND predicate NOT LIKE 'legacy_note:%' AND predicate NOT LIKE 'saved_note:%' "
            "ORDER BY valid_from DESC LIMIT 40",(project_id,self.s.user_id))
        beliefs=[{k:r[k] for k in ('id','subject_entity_id','predicate','object_value','status','confidence','confirmed_by_user','source_type','valid_from')}
                 for r in beliefs if public_record(r,online=online) and any(
                     self.s._event_accessible(self.s.repo.get('events',e['event_id']),online=online)
                     for e in self.s.repo.rows('SELECT event_id FROM evidence WHERE record_id=? LIMIT 20',(r['id'],)))][:20]
        for belief in beliefs:belief['object_value']=belief['object_value'][:512]
        state={'ok':True,'active_project':project,'active_task':unfinished[0] if unfinished else None,
               'current_device':self.s.device_id,'current_workspace':workspace['payload_json'].get('workspace') if workspace else None,
               'recent_episode':episode,'open_loops':loops,'active_goals':goals,'recent_decisions':decisions,
               'blocked_items':[r for r in loops+goals if r['status']=='blocked'],
               'last_activity':activity[0]['timestamp'] if activity else None,'agent_sessions':unfinished[:20],
               'current_beliefs':beliefs}
        if not online:
            with self.s.repo.transaction():
                key='state:'+(project_id or 'global')
                old=self.s.repo.get('current_state',key)
                if old:self.s.repo.update('current_state',key,{'data_json':state})
                else:self.s.repo.insert('current_state',{'id':key,'data_json':state})
        return state

    def continuation(self, project_id=None,limit=20,budget=12000,online=False):
        limit=max(1,min(int(limit),30))
        state=self.current_state(project_id,online=online)
        project=state['active_project']
        project_id=project['id'] if project else None
        scope='project_id=?' if project_id else 'project_id IS NULL'
        params=(project_id,) if project_id else ()
        events=self.s.repo.rows(f"SELECT * FROM events WHERE {scope} AND event_type LIKE 'file.%' ORDER BY timestamp DESC LIMIT 30",params)
        files=list(dict.fromkeys(e['payload_json']['path'] for e in events if e['payload_json'].get('path') and public_record(e,online=online)))[:limit]
        # Keep the projection compact; never duplicate long lists inside state.
        result={'ok':True,'project':project,'workspace':state['current_workspace'],'active_task':state['active_task'],
                'open_loops':state['open_loops'][:limit],'goals':state['active_goals'][:limit],
                'decisions':state['recent_decisions'][:limit], 'episode':state['recent_episode'],
                'constraints': [c for d in state['recent_decisions'] for c in d['constraints_json']][:limit],
                'files':files,'agent_sessions':state['agent_sessions'][:limit],
                'blockers':state['blocked_items'][:limit],
                'uncertainties':['Task and agent state is last observed, not proof a process is still running.'],
                'state':{k:state[k] for k in ('current_device','last_activity')},'truncated':False}
        if not result['open_loops'] and not result['active_task']:
            result['uncertainties'].append('No unfinished work is supported by the recorded evidence.')
        return bounded_pack(result,budget,['open_loops','goals','decisions','constraints','files','agent_sessions','blockers'])

    def predict(self, project_id=None):
        state=self.current_state(project_id)
        predictions=[]
        with self.s.repo.transaction():
            for loop in state['open_loops'][:5]:
                evidence=self.s.repo.rows('SELECT event_id FROM evidence WHERE record_id=? ORDER BY observed_at DESC LIMIT 5',(loop['id'],))
                if not evidence:continue
                phrase='Unfinished work may be revisited: '+loop['description']
                existing=self.s.repo.rows("SELECT * FROM predictions WHERE prediction=? AND status='pending' LIMIT 1",(phrase,))
                if existing:
                    predictions.append(existing[0]);continue
                identity=self.s.repo.insert('predictions',dict(prediction=phrase,confidence=.55,status='pending',
                    horizon=(datetime.now(timezone.utc)+timedelta(days=7)).isoformat(),evidence_ids_json=[e['event_id'] for e in evidence],
                    project_id=loop.get('project_id'),privacy_class=loop['privacy_class']))
                for ev in evidence:self.s._evidence('prediction',identity,self.s.repo.get('events',ev['event_id']),.55,False,'rule_unfinished_work')
                row=self.s.repo.get('predictions',identity);self.s._index('prediction',row);predictions.append(row)
        return {'ok':True,'predictions':predictions,'interpretation':'Hypotheses only. No action was started.'}

    def evaluate_prediction(self, identity,outcome,authorized=False):
        if not authorized or outcome not in {'correct','incorrect','unresolved'}:
            return {'ok':False,'error':'Explicit, supported prediction feedback is required.'}
        with self.s.repo.transaction():
            row=self.s.repo.get('predictions',identity)
            if not row:return {'ok':False,'error':'Prediction unavailable.'}
            self.s.repo.update('predictions',identity,{'outcome':outcome,'status':'evaluated' if outcome!='unresolved' else 'pending'})
            event=self.s.record_event('prediction.evaluated',{'prediction_id':identity,'outcome':outcome},source_type='user',project_id=row.get('project_id'))
            self.s._evidence('prediction',identity,event,.99,True,'user_feedback')
        return {'ok':True,'outcome':outcome}

    def observe_patterns(self,project_id=None,limit=200):
        self.s._project(project_id)
        scope=' AND project_id=?' if project_id else ''
        rows=self.s.repo.rows("SELECT * FROM events WHERE event_type IN ('task.completed','workspace.changed') AND session_id IS NOT NULL"+scope+' ORDER BY timestamp DESC LIMIT ?',(*( [project_id] if project_id else []),max(1,min(int(limit),1000))))
        groups={}
        for event in rows:
            groups.setdefault((event['event_type'],event['project_id']),{}).setdefault(event['session_id'],event)
        patterns=[]
        with self.s.repo.transaction():
            for (kind,project),sessions in groups.items():
                if len(sessions)<3:continue
                events=list(sessions.values())
                phrase=kind+' was observed across distinct work sessions.'
                existing=self.s.repo.rows('SELECT * FROM behavior_patterns WHERE pattern=? AND project_id IS ?',(phrase,project))
                data=dict(pattern=phrase,confidence=min(.75,.4+.03*len(events)),status='hypothesis',evidence_count=len(events),
                          supporting_events_json=[e['id'] for e in events],last_observed=max(e['timestamp'] for e in events),project_id=project)
                identity=existing[0]['id'] if existing else self.s.repo.insert('behavior_patterns',data)
                if existing:self.s.repo.update('behavior_patterns',identity,data)
                for event in events:self.s._evidence('behavior_pattern',identity,event,data['confidence'],False,'distinct_session_count')
                row=self.s.repo.get('behavior_patterns',identity);self.s._index('behavior_pattern',row);patterns.append(row)
        return {'ok':True,'patterns':patterns,'interpretation':'Operational observations, not personality facts.'}
