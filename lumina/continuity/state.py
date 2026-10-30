"""Rebuildable projections, bounded episodes and conservative hypotheses."""
from collections import Counter
import copy
from datetime import datetime, timedelta, timezone
dt_timezone = timezone
import json
import re
from .models import contains_secret
from .policy import now, public_record, timestamp as normalize_time
from .retrieval import bounded_pack


def _parse_iso(ts):
    if not ts or not isinstance(ts, str):
        return None
    try:
        return datetime.fromisoformat(ts.replace('Z', '+00:00'))
    except Exception:
        return None


def _resolve_default_timezone(service=None):
    if service is not None:
        tz_cand = getattr(service, 'timezone', None)
        if tz_cand:
            return tz_cand
        rt = getattr(service, 'rt', None)
        if rt is not None:
            tz_cand = getattr(rt, 'timezone', None)
            if tz_cand:
                return tz_cand
            tools = getattr(rt, 'tools', None)
            if tools is not None:
                reminders = getattr(tools, 'reminders', None)
                if reminders is not None and getattr(reminders, 'timezone', None):
                    return reminders.timezone
    import os
    env_tz = os.environ.get('LUMINA_TIMEZONE') or os.environ.get('TZ')
    if env_tz:
        return env_tz
    return 'UTC'


def _parse_timezone(tz_val, default='UTC'):
    if tz_val is None or tz_val == '':
        tz_val = default
    if tz_val == 'UTC' or tz_val == 'Z':
        return dt_timezone.utc, 'UTC'
    if isinstance(tz_val, dt_timezone):
        return tz_val, str(tz_val)
    if hasattr(tz_val, 'key'):
        offset_str = datetime.now(tz_val).strftime('%z')
        offset_fmt = f"{offset_str[:3]}:{offset_str[3:]}" if len(offset_str) == 5 else str(tz_val)
        return tz_val, offset_fmt
    if isinstance(tz_val, (int, float)):
        if abs(tz_val) <= 14:
            delta = timedelta(hours=tz_val)
        else:
            delta = timedelta(minutes=tz_val)
        tz = dt_timezone(delta)
        return tz, str(tz)
    if isinstance(tz_val, str):
        s = tz_val.strip()
        if s in ('UTC', 'Z', '+00:00', '-00:00'):
            return dt_timezone.utc, 'UTC'
        m = re.match(r'^([+-])(\d{1,2}):?(\d{2})?$', s)
        if m:
            sign = -1 if m.group(1) == '-' else 1
            hours = int(m.group(2))
            minutes = int(m.group(3) or 0)
            if 0 <= hours <= 23 and 0 <= minutes <= 59:
                delta = timedelta(minutes=sign * (hours * 60 + minutes))
                tz = dt_timezone(delta)
                return tz, s
        try:
            import zoneinfo
            zi = zoneinfo.ZoneInfo(s)
            offset_str = datetime.now(zi).strftime('%z')
            offset_fmt = f"{offset_str[:3]}:{offset_str[3:]}" if len(offset_str) == 5 else s
            return zi, offset_fmt
        except Exception:
            pass
    raise ValueError(f"Invalid timezone_offset: {tz_val}")


def _generate_deterministic_summary(period_label, metrics, categories, decisions, open_loops, is_empty, goals=None):
    if is_empty:
        return f"No relevant activity recorded for {period_label}."
    lines = [f"Deterministic reflection for {period_label}:"]

    evt_count = metrics['total_events']
    sess_count = metrics['sessions_count']
    sess_str = f" across {sess_count} session(s)" if sess_count > 0 else ""
    lines.append(f"- Activity: {evt_count} event(s) recorded{sess_str}.")

    user_msg_count = metrics['user_messages_count']
    if user_msg_count > 0:
        lines.append(f"- User messages: {user_msg_count} message(s) observed.")

    tasks_completed = metrics['tasks_completed_count']
    tasks_active = metrics['tasks_active_count']
    if tasks_completed > 0 or tasks_active > 0:
        lines.append(f"- Tasks: {tasks_completed} completed, {tasks_active} active/in-progress.")

    files = categories['files']
    if files:
        sample_str = ", ".join(files[:3])
        if len(files) > 3:
            sample_str += f" and {len(files) - 3} more"
        lines.append(f"- Files touched ({len(files)}): {sample_str}.")

    tools = categories['tool_executions']
    if tools:
        lines.append(f"- Tool executions: {len(tools)} call(s) recorded.")

    dec_count = len(decisions)
    if dec_count > 0:
        lines.append(f"- Decisions: {dec_count} relevant decision(s) recorded/active.")

    c_counts = metrics.get('candidate_counts', {})
    if c_counts.get('total', 0) > 0:
        lines.append(
            f"- Memory candidates: {c_counts.get('total', 0)} total "
            f"({c_counts.get('pending', 0)} pending, {c_counts.get('admitted', 0)} admitted, "
            f"{c_counts.get('deferred', 0)} deferred, {c_counts.get('rejected', 0)} rejected)."
        )

    open_count = len(open_loops)
    if open_count > 0:
        lines.append(f"- Open loops: {open_count} unresolved loop(s) remaining.")
    else:
        lines.append("- Open loops: No unresolved open loops.")

    if goals:
        lines.append(f"- Active goals: {len(goals)} active goal(s) recorded.")

    return "\n".join(lines)


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
                counts_summary='; '.join(str(r['n'])+' '+r['event_type'] for r in totals)
                user_msgs=[e.get('payload_json',{}).get('text','') for e in group if e.get('event_type')=='conversation.message' and e.get('payload_json',{}).get('role')=='user']
                tools_used=list(dict.fromkeys(e.get('payload_json',{}).get('tool') for e in group if e.get('event_type')=='tool.started' and e.get('payload_json',{}).get('tool')))
                summary_parts=[f"Session {session} on {group[0]['timestamp'][:10]}."]
                if user_msgs:
                    topics='; '.join(m.strip()[:80] for m in user_msgs[:3] if m.strip())
                    if topics:
                        summary_parts.append(f"Topics and inquiries: {topics}.")
                if tools_used:
                    summary_parts.append(f"Operations executed: {', '.join(tools_used[:5])}.")
                summary_parts.append(f"Event summary: {counts_summary}.")
                full_summary=' '.join(summary_parts)
                title=(f"Session {group[0]['timestamp'][:10]}: {user_msgs[0].strip()[:40]}" if user_msgs and user_msgs[0].strip() else 'Work session')
                row=self.s.repo.update('episodes',identity,dict(title=title[:160],summary=full_summary[:4000],ended_at=group[-1]['timestamp'],status='consolidated',outcome='Session consolidated with recorded topics and operations.'))
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
        prev_sess = None
        if hasattr(self.s, 'session_continuity'):
            try:
                prev_sess = self.s.session_continuity.get_previous_session()
            except Exception:
                pass
        result={'ok':True,'project':project,'workspace':state['current_workspace'],'active_task':state['active_task'],
                'open_loops':state['open_loops'][:limit],'goals':state['active_goals'][:limit],
                'decisions':state['recent_decisions'][:limit], 'episode':state['recent_episode'],
                'previous_session': prev_sess,
                'constraints': [c for d in state['recent_decisions'] for c in d['constraints_json']][:limit],
                'files':files,'agent_sessions':state['agent_sessions'][:limit],
                'blockers':state['blocked_items'][:limit],
                'uncertainties':['Task and agent state is last observed, not proof a process is still running.'],
                'state':{k:state[k] for k in ('current_device','last_activity')},'truncated':False}
        if not result['open_loops'] and not result['active_task'] and not result['goals']:
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

    def daily_reflection(self, date=None, *, since=None, until=None, timezone_offset=None, timezone=None, project_id=None, online=False):
        """Produce a deterministic, local-only reflection for an explicit period.
        
        Strictly read-only; no external model calls, no state mutations, no background tasks.
        """
        data_quality_notes = []

        # 1. Resolve time boundaries
        tz_arg = timezone if timezone is not None else timezone_offset
        default_tz = _resolve_default_timezone(self.s)
        tz, tz_name = _parse_timezone(tz_arg, default=default_tz)

        if date is not None:
            if not isinstance(date, str) or not re.match(r'^\d{4}-\d{2}-\d{2}$', date.strip()):
                raise ValueError(f"Invalid date format: {date}. Expected YYYY-MM-DD.")
            date_clean = date.strip()
            try:
                dt_parsed = datetime.strptime(date_clean, '%Y-%m-%d')
            except ValueError:
                raise ValueError(f"Invalid calendar date: {date}.")

            dt_start = datetime(dt_parsed.year, dt_parsed.month, dt_parsed.day, 0, 0, 0, 0, tzinfo=tz)
            dt_end = datetime(dt_parsed.year, dt_parsed.month, dt_parsed.day, 23, 59, 59, 999999, tzinfo=tz)
            since_val = dt_start.astimezone(dt_timezone.utc).isoformat(timespec='microseconds')
            until_val = dt_end.astimezone(dt_timezone.utc).isoformat(timespec='microseconds')
            target_date = date_clean
        elif since is not None or until is not None:
            if since is None or until is None:
                raise ValueError("Both 'since' and 'until' must be provided when specifying an interval.")
            since_val = normalize_time(since)
            until_val = normalize_time(until)
            if since_val > until_val:
                raise ValueError("since must be earlier than or equal to until.")
            target_date = since_val[:10]
        else:
            now_local = datetime.now(tz)
            target_date = now_local.strftime('%Y-%m-%d')
            dt_start = datetime(now_local.year, now_local.month, now_local.day, 0, 0, 0, 0, tzinfo=tz)
            dt_end = datetime(now_local.year, now_local.month, now_local.day, 23, 59, 59, 999999, tzinfo=tz)
            since_val = dt_start.astimezone(dt_timezone.utc).isoformat(timespec='microseconds')
            until_val = dt_end.astimezone(dt_timezone.utc).isoformat(timespec='microseconds')

        period = {
            'date': target_date,
            'since': since_val,
            'until': until_val,
            'timezone': tz_name
        }

        # 2. Check for malformed timestamps in repository
        malformed_ts_rows = self.s.repo.rows(
            "SELECT count(*) AS count FROM events WHERE timestamp IS NULL OR julianday(timestamp) IS NULL"
        )
        malformed_ts_count = malformed_ts_rows[0]['count'] if malformed_ts_rows else 0
        if malformed_ts_count > 0:
            data_quality_notes.append(
                f"{malformed_ts_count} event(s) in repository have invalid or missing timestamps."
            )

        # 3. Query events within bounded interval
        clauses = [
            "julianday(timestamp) >= julianday(?)",
            "julianday(timestamp) <= julianday(?)",
            "event_type <> 'entity.registered'"
        ]
        params = [since_val, until_val]
        if project_id:
            clauses.append("project_id = ?")
            params.append(project_id)

        sql = f"SELECT * FROM events WHERE {' AND '.join(clauses)} ORDER BY timestamp ASC, id ASC"
        raw_events = self.s.repo.rows(sql, tuple(params))

        # Deduplicate events by canonical id
        seen_event_ids = set()
        deduped_events = []
        for ev in raw_events:
            if ev['id'] not in seen_event_ids:
                seen_event_ids.add(ev['id'])
                deduped_events.append(ev)

        # 4. Privacy and secret screening
        secret_events_count = 0
        omitted_private_events = 0
        visible_events = []

        for ev in deduped_events:
            payload = ev.get('payload_json') or {}
            if contains_secret(payload):
                secret_events_count += 1
                ev = dict(ev)
                ev['payload_json'] = {'_redacted': 'Secret detected in payload'}

            if online:
                if ev.get('privacy_class') != 'public' or not public_record(ev, online=True):
                    omitted_private_events += 1
                    continue
            visible_events.append(ev)

        if secret_events_count > 0:
            data_quality_notes.append(
                f"Secrets detected and sanitized in {secret_events_count} event payload(s)."
            )
        if online and omitted_private_events > 0:
            data_quality_notes.append(
                f"{omitted_private_events} non-public event(s) omitted due to external transmission privacy policy."
            )

        # 5. Group events into categories
        user_messages = []
        tasks_by_id = {}
        files_touched = {}
        tool_executions = []
        lifecycle_events = []
        other_events = []
        sessions = set()

        for ev in visible_events:
            if ev.get('session_id'):
                sessions.add(ev['session_id'])

            ev_type = ev.get('event_type') or 'unknown'
            payload = ev.get('payload_json') or {}

            if ev_type == 'conversation.message' and (ev.get('source_type') == 'user' or payload.get('role') == 'user'):
                text_content = str(payload.get('text', '')).strip()
                user_messages.append({
                    'id': ev['id'],
                    'timestamp': ev.get('timestamp'),
                    'text': text_content[:500],
                    'session_id': ev.get('session_id'),
                    'privacy_class': ev.get('privacy_class', 'private')
                })
            elif ev_type.startswith('task.'):
                task_id = payload.get('task_id') or ev.get('source_id') or ev['id']
                task_entry = tasks_by_id.setdefault(task_id, {
                    'task_id': task_id,
                    'title': payload.get('title') or payload.get('description') or '',
                    'events': [],
                    'latest_status': 'UNKNOWN',
                    'completed': False,
                    'privacy_class': ev.get('privacy_class', 'private')
                })
                status = payload.get('status') or ev_type.split('.', 1)[1].upper()
                task_entry['events'].append({
                    'event_id': ev['id'],
                    'event_type': ev_type,
                    'timestamp': ev.get('timestamp'),
                    'status': status
                })
                task_entry['latest_status'] = status
                if status in {'COMPLETED', 'completed'} or ev_type == 'task.completed':
                    task_entry['completed'] = True
                if not task_entry['title'] and (payload.get('title') or payload.get('description')):
                    task_entry['title'] = payload.get('title') or payload.get('description')
            elif ev_type.startswith('file.'):
                path = payload.get('path')
                if path:
                    files_touched.setdefault(path, []).append({
                        'operation': ev_type,
                        'timestamp': ev.get('timestamp')
                    })
            elif ev_type in ('tool.executed', 'tool.execution') or ev.get('source_type') == 'tool':
                tool_name = payload.get('tool') or payload.get('name') or ev_type
                tool_executions.append({
                    'id': ev['id'],
                    'tool': tool_name,
                    'timestamp': ev.get('timestamp'),
                    'privacy_class': ev.get('privacy_class', 'private')
                })
            elif ev_type.startswith(('memory.', 'goal.', 'prediction.', 'open_loop.')):
                lifecycle_events.append({
                    'id': ev['id'],
                    'event_type': ev_type,
                    'timestamp': ev.get('timestamp'),
                    'privacy_class': ev.get('privacy_class', 'private')
                })
            else:
                other_events.append({
                    'id': ev['id'],
                    'event_type': ev_type,
                    'timestamp': ev.get('timestamp'),
                    'source_type': ev.get('source_type', 'unknown'),
                    'privacy_class': ev.get('privacy_class', 'private')
                })

        if tasks_by_id:
            data_quality_notes.append(
                "Task statuses reflect the latest recorded observation, not verified live process execution."
            )

        # 6. Query relevant decisions
        decisions_clauses = [
            "(julianday(made_at) >= julianday(?) AND julianday(made_at) <= julianday(?)) OR status IN ('active', 'needs_review')"
        ]
        decisions_params = [since_val, until_val]
        if project_id:
            decisions_clauses.append("(project_id = ? OR project_id IS NULL)")
            decisions_params.append(project_id)

        decisions_sql = f"SELECT * FROM decisions WHERE {' AND '.join(decisions_clauses)} ORDER BY made_at ASC, id ASC"
        decision_rows = self.s.repo.rows(decisions_sql, tuple(decisions_params))

        seen_decision_ids = set()
        decisions = []
        for d in decision_rows:
            if d['id'] in seen_decision_ids:
                continue
            seen_decision_ids.add(d['id'])
            if online and (d.get('privacy_class') != 'public' or not public_record(d, online=True)):
                continue
            decisions.append({
                'id': d['id'],
                'subject': d.get('subject', ''),
                'chosen_option': d.get('chosen_option', ''),
                'reasoning': d.get('reasoning', ''),
                'status': d.get('status', 'active'),
                'made_at': d.get('made_at'),
                'privacy_class': d.get('privacy_class', 'private')
            })

        # 7. Query open loops (unresolved)
        loops_clauses = ["status IN ('open', 'blocked')"]
        loops_params = []
        if project_id:
            loops_clauses.append("(project_id = ? OR project_id IS NULL)")
            loops_params.append(project_id)

        loops_sql = f"SELECT * FROM open_loops WHERE {' AND '.join(loops_clauses)} ORDER BY created_at ASC, id ASC"
        loop_rows = self.s.repo.rows(loops_sql, tuple(loops_params))

        seen_loop_ids = set()
        open_loops = []
        for l in loop_rows:
            if l['id'] in seen_loop_ids:
                continue
            seen_loop_ids.add(l['id'])
            if online and (l.get('privacy_class') != 'public' or not public_record(l, online=True)):
                continue
            open_loops.append({
                'id': l['id'],
                'description': l.get('description', ''),
                'status': l.get('status', 'open'),
                'next_action': l.get('next_action'),
                'blocked_by': l.get('blocked_by_json') or [],
                'task_id': l.get('task_id'),
                'privacy_class': l.get('privacy_class', 'private')
            })

        if open_loops and any(not l.get('next_action') for l in open_loops):
            data_quality_notes.append("One or more unresolved open loops do not have a defined next action.")

        # 7b. Query active goals
        goals_clauses = ["status IN ('active', 'open', 'pending')"]
        goals_params = []
        if project_id:
            goals_clauses.append("(project_id = ? OR project_id IS NULL)")
            goals_params.append(project_id)
        where_goals = ' AND '.join(goals_clauses)
        goals_sql = f"SELECT * FROM goals WHERE {where_goals} ORDER BY created_at ASC, id ASC"
        goal_rows = self.s.repo.rows(goals_sql, tuple(goals_params))
        seen_goal_ids = set()
        active_goals = []
        for g in goal_rows:
            if g['id'] in seen_goal_ids:
                continue
            seen_goal_ids.add(g['id'])
            if online and (g.get('privacy_class') != 'public' or not public_record(g, online=True)):
                continue
            active_goals.append({
                'id': g['id'],
                'description': g.get('description', ''),
                'status': g.get('status', 'active'),
                'priority': g.get('priority', 0.5),
                'deadline': g.get('deadline'),
                'privacy_class': g.get('privacy_class', 'private'),
                'created_at': g.get('created_at'),
            })

        # 8. Query memory candidate counts
        candidate_counts = {
            'pending': 0,
            'deferred': 0,
            'admitted': 0,
            'rejected': 0,
            'total': 0
        }
        cand_rows = self.s.repo.rows(
            "SELECT status, count(*) AS count FROM memory_candidates "
            "WHERE julianday(created_at) >= julianday(?) AND julianday(created_at) <= julianday(?) "
            "GROUP BY status",
            (since_val, until_val)
        )
        for cr in cand_rows:
            st = str(cr.get('status', '')).lower()
            cnt = cr.get('count', 0)
            if st in candidate_counts:
                candidate_counts[st] += cnt
                candidate_counts['total'] += cnt
            else:
                candidate_counts['total'] += cnt

        # 9. Determine empty day
        dt_since = _parse_iso(since_val)
        dt_until = _parse_iso(until_val)
        decisions_made_in_period = []
        for d in decisions:
            dt_made = _parse_iso(d.get('made_at'))
            if dt_made and dt_since and dt_until and (dt_since <= dt_made <= dt_until):
                decisions_made_in_period.append(d)

        is_empty = (len(visible_events) == 0 and candidate_counts['total'] == 0 and len(decisions_made_in_period) == 0)
        if is_empty:
            data_quality_notes.append(f"No recorded activity found for date {period['date']}.")

        # 10. Metrics & Categories
        metrics = {
            'total_events': len(visible_events),
            'user_messages_count': len(user_messages),
            'sessions_count': len(sessions),
            'tasks_active_count': len([t for t in tasks_by_id.values() if not t['completed']]),
            'tasks_completed_count': len([t for t in tasks_by_id.values() if t['completed']]),
            'files_touched_count': len(files_touched),
            'tool_executions_count': len(tool_executions),
            'decisions_count': len(decisions),
            'open_loops_count': len(open_loops),
            'candidate_counts': candidate_counts,
        }

        categories = {
            'user_messages': user_messages,
            'tasks': sorted(list(tasks_by_id.values()), key=lambda x: str(x['task_id'])),
            'files': sorted(list(files_touched.keys())),
            'tool_executions': tool_executions,
            'lifecycle_events': lifecycle_events,
            'other_events': other_events,
        }

        # 11. Deterministic summary text
        metrics['goals_count'] = len(active_goals)
        summary_text = _generate_deterministic_summary(
            period['date'], metrics, categories, decisions, open_loops, is_empty, goals=active_goals
        )

        return {
            'ok': True,
            'period': period,
            'is_empty': is_empty,
            'summary': summary_text,
            'metrics': metrics,
            'categories': categories,
            'decisions': decisions,
            'open_loops': open_loops,
            'goals': active_goals,
            'candidate_counts': candidate_counts,
            'data_quality_notes': data_quality_notes,
        }

