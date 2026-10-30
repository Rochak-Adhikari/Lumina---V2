"""Session Continuity and Lifecycle Engine for Lumina Continuity.

Provides truthful, durable session tracking across conversation lifecycles:
- Real session boundaries (start, continue, finalize)
- Structured session summaries (Overview, Discussion, Decisions, Accomplishments, Unfinished Work, Memory Changes, Status)
- Graceful finalization and crash recovery for interrupted sessions
- Previous session recall strictly excluding the current active session
"""
import datetime
import json
import re
from typing import Dict, Any, List, Optional
from uuid import uuid4


class SessionContinuityService:
    """Manages conversation session continuity, finalization, recovery, and recall."""

    def __init__(self, service):
        self.s = service
        self.repo = service.repo

    def finalize_session(self, session_id: str, *, status: str = 'completed') -> Dict[str, Any]:
        """Finalizes a session, generating a durable, structured session summary."""
        if not session_id or not isinstance(session_id, str):
            raise ValueError("A valid session_id string is required.")

        clauses = ["session_id = ?", "event_type NOT LIKE 'memory.%'", "event_type <> 'entity.registered'"]
        events = self.repo.rows(
            f"SELECT * FROM events WHERE {' AND '.join(clauses)} ORDER BY timestamp ASC",
            (session_id,)
        )

        if not events:
            return {"ok": False, "error": f"No events recorded for session {session_id}."}

        started_at = events[0]['timestamp']
        ended_at = events[-1]['timestamp']
        project_id = events[0].get('project_id')
        privacy = events[0].get('privacy_class', 'private')

        # 1. Gather discussions and discoveries
        user_msgs = [
            e['payload_json'].get('text', '').strip()
            for e in events
            if e.get('event_type') == 'conversation.message' and e.get('payload_json', {}).get('role') == 'user'
            and e.get('payload_json', {}).get('text')
        ]
        tools_used = list(dict.fromkeys(
            e['payload_json'].get('tool')
            for e in events
            if e.get('event_type') in {'tool.started', 'tool.executed'} and e.get('payload_json', {}).get('tool')
        ))

        # 2. Gather decisions made during session
        decisions = self.repo.rows(
            "SELECT * FROM decisions WHERE made_at >= ? AND made_at <= ? ORDER BY made_at ASC",
            (started_at, ended_at)
        )

        # 3. Gather verified accomplishments (completed tasks)
        task_completed_events = [
            e['payload_json']
            for e in events
            if e.get('event_type') == 'task.completed' and isinstance(e.get('payload_json'), dict)
        ]
        accomplishments = []
        for tc in task_completed_events:
            desc = tc.get('description') or tc.get('task_id') or 'Task completed'
            accomplishments.append(desc)

        # 4. Gather unfinished work and open loops
        open_loops = self.repo.rows(
            "SELECT * FROM open_loops WHERE status IN ('open', 'blocked') ORDER BY updated_at DESC LIMIT 10"
        )
        unfinished_tasks = [
            ol.get('description')
            for ol in open_loops
            if ol.get('description')
        ]

        # 5. Gather memory changes
        memory_events = self.repo.rows(
            "SELECT * FROM events WHERE session_id = ? AND event_type LIKE 'memory.%' ORDER BY timestamp ASC",
            (session_id,)
        )
        memory_changes = []
        for me in memory_events:
            m_type = me.get('event_type', '').replace('memory.', '')
            payload = me.get('payload_json', {})
            rec_id = payload.get('record_id')
            memory_changes.append(f"{m_type.capitalize()} record {rec_id}" if rec_id else m_type.capitalize())

        # Formulate title
        first_topic = user_msgs[0][:40] if user_msgs else "General session"
        title = f"Session {started_at[:10]}: {first_topic}"

        # Build structured markdown summary
        summary_lines = [
            f"# Session Summary: {title}",
            "",
            "## Session Overview",
            f"- Session ID: {session_id}",
            f"- Started: {started_at}",
            f"- Ended: {ended_at}",
            f"- Status: {status}",
            f"- Total Events: {len(events)}",
            "",
            "## Discussion and Discoveries",
        ]
        if user_msgs:
            summary_lines.append(f"- Topics discussed: {'; '.join(user_msgs[:5])}.")
        else:
            summary_lines.append("- Topics discussed: None recorded.")

        if tools_used:
            summary_lines.append(f"- Tools and operations: {', '.join(tools_used[:6])}.")

        summary_lines.append("")
        summary_lines.append("## Decisions")
        if decisions:
            for d in decisions:
                summary_lines.append(f"- Decision on {d['subject']}: {d['chosen_option']}. Rationale: {d.get('reasoning', 'None recorded')}.")
        else:
            summary_lines.append("- None recorded.")

        summary_lines.append("")
        summary_lines.append("## Accomplishments")
        if accomplishments:
            for acc in accomplishments:
                summary_lines.append(f"- {acc}")
        else:
            summary_lines.append("- None recorded.")

        summary_lines.append("")
        summary_lines.append("## Unfinished Work")
        if unfinished_tasks:
            for unf in unfinished_tasks[:5]:
                summary_lines.append(f"- Open loop: {unf}")
        else:
            summary_lines.append("- None recorded.")

        summary_lines.append("")
        summary_lines.append("## Memory Changes")
        if memory_changes:
            summary_lines.append(f"- Changes: {', '.join(memory_changes[:6])}.")
        else:
            summary_lines.append("- None recorded.")

        full_summary = "\n".join(summary_lines)

        # Upsert episode
        outcome = "Accomplishments verified." if accomplishments else "Session concluded; no completed tasks."
        if status in {'interrupted', 'recovered'}:
            outcome = "Session interrupted; recovered from persisted events."

        with self.repo.transaction():
            # Check if episode for session already exists in meta or episodes
            key = f"episode:{session_id}"
            meta_row = self.repo.rows("SELECT value FROM meta WHERE key = ?", (key,))
            existing_ep = None
            if meta_row:
                existing_ep = self.repo.get('episodes', meta_row[0]['value'])

            if existing_ep:
                ep_id = existing_ep['id']
                row = self.repo.update('episodes', ep_id, dict(
                    title=title[:160],
                    summary=full_summary[:4000],
                    ended_at=ended_at,
                    status='consolidated' if status == 'completed' else status,
                    outcome=outcome
                ))
            else:
                ep_id = self.repo.insert('episodes', dict(
                    title=title[:160],
                    summary=full_summary[:4000],
                    started_at=started_at,
                    ended_at=ended_at,
                    project_id=project_id,
                    privacy_class=privacy,
                    status='consolidated' if status == 'completed' else status,
                    outcome=outcome
                ))
                self.repo.db.execute("INSERT OR REPLACE INTO meta VALUES(?, ?)", (key, ep_id))
                row = self.repo.get('episodes', ep_id)

            # Link unlinked events in episode_events
            for ev in events:
                try:
                    self.repo.insert('episode_events', {'episode_id': ep_id, 'event_id': ev['id']})
                except Exception:
                    pass

            # Index into FTS5
            self.s._index('episode', row)

        return {
            "ok": True,
            "session_id": session_id,
            "episode_id": ep_id,
            "title": title,
            "status": status,
            "accomplishments_count": len(accomplishments),
            "summary": full_summary
        }

    def recover_interrupted_sessions(self) -> List[Dict[str, Any]]:
        """Scans for unfinalized sessions and synthesizes truthful recovered summaries."""
        # Find distinct session_ids in events that lack a consolidated episode
        cur = self.repo.db.cursor()
        cur.execute("""
            SELECT DISTINCT session_id FROM events
            WHERE session_id IS NOT NULL
              AND session_id != ''
              AND NOT EXISTS (
                  SELECT 1 FROM episodes ep
                  JOIN meta m ON m.value = ep.id
                  WHERE m.key = 'episode:' || events.session_id
                    AND ep.status IN ('consolidated', 'recovered', 'completed')
              )
            ORDER BY timestamp DESC LIMIT 20
        """)
        rows = cur.fetchall()
        recovered = []
        for r in rows:
            sess_id = r[0]
            try:
                res = self.finalize_session(sess_id, status='recovered')
                if res.get('ok'):
                    recovered.append(res)
            except Exception:
                continue
        return recovered

    def get_previous_session(self, current_session_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Returns the latest finalized or recovered session before current_session_id."""
        clauses = []
        params = []
        if current_session_id:
            clauses.append("id NOT IN (SELECT value FROM meta WHERE key = ?)")
            params.append(f"episode:{current_session_id}")
            clauses.append("id != ?")
            params.append(current_session_id)

        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = f"SELECT * FROM episodes{where} ORDER BY ended_at DESC, started_at DESC LIMIT 1"
        rows = self.repo.rows(sql, tuple(params))
        if not rows:
            return None

        ep = rows[0]
        summary_text = ep.get('summary', '')

        # Extract structured parts from summary_text
        discoveries_match = re.search(r'## Discussion and Discoveries\s*\n(.*?)(?=\n##|\Z)', summary_text, re.DOTALL)
        decisions_match = re.search(r'## Decisions\s*\n(.*?)(?=\n##|\Z)', summary_text, re.DOTALL)
        accomplishments_match = re.search(r'## Accomplishments\s*\n(.*?)(?=\n##|\Z)', summary_text, re.DOTALL)
        unfinished_match = re.search(r'## Unfinished Work\s*\n(.*?)(?=\n##|\Z)', summary_text, re.DOTALL)

        return {
            "id": ep['id'],
            "title": ep.get('title'),
            "summary": summary_text,
            "started_at": ep.get('started_at'),
            "ended_at": ep.get('ended_at'),
            "status": ep.get('status'),
            "outcome": ep.get('outcome'),
            "discoveries": discoveries_match.group(1).strip() if discoveries_match else "",
            "decisions": decisions_match.group(1).strip() if decisions_match else "",
            "accomplishments": accomplishments_match.group(1).strip() if accomplishments_match else "None recorded.",
            "unfinished_work": unfinished_match.group(1).strip() if unfinished_match else "None recorded."
        }

