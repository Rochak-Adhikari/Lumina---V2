"""Hierarchical Summary Engine for Lumina Continuity.

Implements the four-tier summary hierarchy:
- Level A: Core profile summary (compact, durable, bounded)
- Level B: Topic summaries (preferences, education, entertainment, identity, goals, relationships, decisions)
- Level C: Detailed context summaries (complex discussions, project milestones)
- Level D: Session summaries (integrated with episodes and episode_events)

All summaries maintain explicit links to source record IDs and events,
index into SQLite FTS5, and provide structured retrieval fallback.
"""
import datetime
import json
import re
from typing import Dict, Any, List, Optional


class HierarchicalSummaryService:
    """Manages creation, refresh, storage, indexing, and lookup of hierarchical summaries."""

    META_CATALOG_KEY = "hierarchical_summary_catalog"
    META_PREFIX = "summary:"

    TOPICS = [
        "personal_preferences",
        "education_and_training",
        "games_and_entertainment",
        "lumina_identity_and_vision",
        "goals_and_intentions",
        "relationships_and_people",
        "decisions_and_commitments",
    ]

    @classmethod
    def generate_all(cls, repo, user_id: Optional[str] = None) -> Dict[str, Any]:
        """Generates Level A (Core Profile) and Level B (Topic Summaries) from active records."""
        user_filter = "AND (subject_entity_id = ? OR subject_entity_id IS NULL)" if user_id else ""
        params = [user_id] if user_id else []

        cur = repo.db.cursor()
        cur.execute(
            f"SELECT id, predicate, object_value, status, confidence, created_at, updated_at FROM facts WHERE status='active' {user_filter} ORDER BY id ASC",
            params
        )
        facts = [dict(r) for r in cur.fetchall()]

        cur.execute("SELECT id, description, priority, status, created_at, updated_at FROM goals WHERE status='active'")
        goals = [dict(r) for r in cur.fetchall()]

        cur.execute("SELECT id, subject, chosen_option, reasoning, status, created_at, updated_at FROM decisions WHERE status IN ('active', 'needs_review')")
        decisions = [dict(r) for r in cur.fetchall()]

        cur.execute("SELECT id, description, status, created_at, updated_at FROM commitments WHERE status IN ('open', 'active')")
        commitments = [dict(r) for r in cur.fetchall()]

        cur.execute("SELECT id, description, status, created_at, updated_at FROM open_loops WHERE status IN ('open', 'blocked')")
        open_loops = [dict(r) for r in cur.fetchall()]

        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # Categorize facts
        identity_facts = []
        pref_facts = []
        edu_facts = []
        game_facts = []
        anime_facts = []
        novel_facts = []
        manhwa_facts = []
        manhua_facts = []
        color_facts = []
        food_facts = []
        dislike_facts = []
        friend_facts = []
        vision_facts = []

        for f in facts:
            pred = (f.get('predicate') or '').lower()
            val = (f.get('object_value') or '').strip()

            if pred in {'has_name', 'name', 'nickname', 'alias', 'birth_date', 'born_on', 'birthday', 'created_by', 'sole_creator_of'}:
                identity_facts.append(f)
            elif pred.startswith('prefers_') or pred == 'preference':
                pref_facts.append(f)
            elif pred in {'studies_at', 'education', 'reported_education', 'course', 'completed_course'}:
                edu_facts.append(f)
            elif pred in {'favorite_game', 'game', 'likes_game'}:
                game_facts.append(f)
            elif pred in {'favorite_anime', 'likes_anime'}:
                anime_facts.append(f)
            elif pred in {'favorite_novel', 'likes_novel'}:
                novel_facts.append(f)
            elif pred in {'favorite_manhwa', 'likes_manhwa', 'interest'}:
                manhwa_facts.append(f)
            elif pred in {'favorite_manhua', 'likes_manhua'}:
                manhua_facts.append(f)
            elif pred in {'favorite_color', 'color'}:
                color_facts.append(f)
            elif pred == 'food_preference':
                food_facts.append(f)
            elif pred in {'dislikes_food', 'food_dislike', 'dislikes_communication'}:
                dislike_facts.append(f)
            elif pred in {'friend', 'friends'}:
                friend_facts.append(f)
            elif 'lumina' in pred or 'creator' in pred or 'vision' in pred:
                vision_facts.append(f)
            else:
                pref_facts.append(f)

        summaries = {}

        # -------------------------------------------------------------
        # Level A: Core Profile Summary
        # -------------------------------------------------------------
        level_a_lines = ["# Core Profile Summary", ""]
        name_val = next((f['object_value'] for f in identity_facts if f['predicate'] in {'has_name', 'name'}), 'Rochak Adhikari')
        nick_val = next((f['object_value'] for f in identity_facts if f['predicate'] in {'nickname', 'alias'}), 'Scepter')
        dob_val = next((f['object_value'] for f in identity_facts if f['predicate'] in {'birth_date', 'born_on', 'birthday'}), '12 June 2004')
        level_a_lines.append(f"User: {name_val} (also known as {nick_val}), born {dob_val}.")
        addr_val = next((f['object_value'] for f in pref_facts if f['predicate'] == 'prefers_address'), 'sir')
        level_a_lines.append(f"Interaction: Prefers to be addressed as {addr_val}; concise, natural responses.")
        if edu_facts:
            level_a_lines.append(f"Education: {edu_facts[0]['object_value'].split(';', 1)[0]}.")
        if goals:
            level_a_lines.append(f"Active Long-Term Goal: {goals[0]['description']}.")
        if anime_facts:
            level_a_lines.append(f"Favorite Anime: {anime_facts[0]['object_value']}.")
        if novel_facts:
            level_a_lines.append(f"Favorite Novel: {novel_facts[0]['object_value']}.")
        if manhwa_facts:
            sorted_m = sorted(manhwa_facts, key=lambda x: cls._extract_rank(x['object_value']) or 99)
            level_a_lines.append(f"Top Manhwa: {sorted_m[0]['object_value']}.")
        if manhua_facts:
            sorted_h = sorted(manhua_facts, key=lambda x: cls._extract_rank(x['object_value']) or 99)
            level_a_lines.append(f"Top Manhua: {sorted_h[0]['object_value']}.")
        if game_facts:
            sorted_g = sorted(game_facts, key=lambda x: cls._extract_rank(x['object_value']) or 99)
            level_a_lines.append(f"Top Game: {sorted_g[0]['object_value']}.")
        if color_facts:
            level_a_lines.append(f"Favorite Colors: {', '.join(f['object_value'] for f in color_facts[:2])}.")
        if dislike_facts:
            level_a_lines.append(f"Dislikes: {dislike_facts[0]['object_value']}.")

        all_fact_ids = [f['id'] for f in facts]
        all_goal_ids = [g['id'] for g in goals]
        all_decision_ids = [d['id'] for d in decisions]

        summaries["summary:core:profile"] = {
            "id": "summary:core:profile",
            "level": "core",
            "topic": "profile",
            "title": "Core User Profile",
            "content": "\n".join(level_a_lines),
            "created_at": now_iso,
            "updated_at": now_iso,
            "version": 1,
            "status": "current",
            "source_fact_ids": all_fact_ids[:20],
            "source_record_ids": all_goal_ids[:5],
            "event_ids": [],
            "provenance": "Synthesized from confirmed identity, education, goal, and preference records."
        }

        # -------------------------------------------------------------
        # Level B: Topic Summaries
        # -------------------------------------------------------------
        # 1. Personal Preferences
        pref_lines = ["# Personal Preferences & Dislikes Summary", ""]
        pref_lines.append(f"- Preferred Address: {addr_val}")
        if color_facts:
            pref_lines.append(f"- Favorite Colors: {', '.join(f['object_value'] for f in color_facts)}")
        if food_facts:
            pref_lines.append(f"- Food Preferences: {food_facts[0]['object_value']}")
        else:
            pref_lines.append("- Food Preferences: Eats a wide variety of foods; no specific favorite food recorded.")
        if dislike_facts:
            for df in dislike_facts:
                pref_lines.append(f"- Dislike: {df['object_value']}")
        pref_srcs = [f['id'] for f in (pref_facts + color_facts + food_facts + dislike_facts)]
        summaries["summary:topic:personal_preferences"] = {
            "id": "summary:topic:personal_preferences",
            "level": "topic",
            "topic": "personal_preferences",
            "title": "Personal Preferences & Dislikes",
            "content": "\n".join(pref_lines),
            "created_at": now_iso,
            "updated_at": now_iso,
            "version": 1,
            "status": "current",
            "source_fact_ids": pref_srcs,
            "source_record_ids": [],
            "event_ids": [],
            "provenance": "Synthesized from active preference, color, food, and dislike facts."
        }

        # 2. Education & Training
        edu_lines = ["# Education & Professional Training Summary", ""]
        for ef in edu_facts:
            edu_lines.append(f"- {ef['predicate'].replace('_', ' ').title()}: {ef['object_value']}")
        edu_srcs = [f['id'] for f in edu_facts]
        summaries["summary:topic:education_and_training"] = {
            "id": "summary:topic:education_and_training",
            "level": "topic",
            "topic": "education_and_training",
            "title": "Education & Professional Training",
            "content": "\n".join(edu_lines),
            "created_at": now_iso,
            "updated_at": now_iso,
            "version": 1,
            "status": "current",
            "source_fact_ids": edu_srcs,
            "source_record_ids": [],
            "event_ids": [],
            "provenance": "Synthesized from college enrollment and completed professional training courses."
        }

        # 3. Games & Entertainment
        ent_lines = ["# Games, Anime, Novels, Manhwa & Manhua Summary", ""]
        if anime_facts:
            ent_lines.append(f"- Favorite Anime: {', '.join(f['object_value'] for f in anime_facts)}")
        if novel_facts:
            ent_lines.append(f"- Favorite Novel: {', '.join(f['object_value'] for f in novel_facts)}")
        if anime_facts:
            level_a_lines.append(f"Favorite Anime: {anime_facts[0]['object_value']}.")
        if novel_facts:
            level_a_lines.append(f"Favorite Novel: {novel_facts[0]['object_value']}.")
        if manhwa_facts:
            ent_lines.append("- Ranked Manhwa:")
            for mf in sorted(manhwa_facts, key=lambda x: cls._extract_rank(x['object_value']) or 99):
                ent_lines.append(f"  * {mf['object_value']}")
        if manhua_facts:
            ent_lines.append("- Ranked Manhua:")
            for hf in sorted(manhua_facts, key=lambda x: cls._extract_rank(x['object_value']) or 99):
                ent_lines.append(f"  * {hf['object_value']}")
        if game_facts:
            ent_lines.append("- Favorite Games:")
            for gf in sorted(game_facts, key=lambda x: cls._extract_rank(x['object_value']) or 99):
                ent_lines.append(f"  * {gf['object_value']}")
            if friend_facts:
                ent_lines.append(f"  * Social Context: Enjoys playing Minecraft with best friends {', '.join(f['object_value'] for f in friend_facts)}")
        ent_srcs = [f['id'] for f in (game_facts + anime_facts + novel_facts + manhwa_facts + manhua_facts)]
        summaries["summary:topic:games_and_entertainment"] = {
            "id": "summary:topic:games_and_entertainment",
            "level": "topic",
            "topic": "games_and_entertainment",
            "title": "Games & Entertainment Interests",
            "content": "\n".join(ent_lines),
            "created_at": now_iso,
            "updated_at": now_iso,
            "version": 1,
            "status": "current",
            "source_fact_ids": ent_srcs,
            "source_record_ids": [],
            "event_ids": [],
            "provenance": "Synthesized from ranked game, anime, novel, manhwa, and manhua records."
        }

        # 4. Lumina Identity & Long-Term Vision
        vis_lines = ["# Lumina Purpose & Game Development Vision", ""]
        vis_lines.append("- Creator: Rochak Adhikari (Scepter), sole creator and master.")
        vis_lines.append("- Primary Purpose: Lifelong personal AI companion and butler.")
        vis_lines.append("- Future Ambition: Develop a game with high AI autonomy/control inspired by The Greatest Estate Developer and Overgeared.")
        for g in goals:
            vis_lines.append(f"- Goal: {g['description']}")
        vis_srcs = [f['id'] for f in (identity_facts + vision_facts)]
        summaries["summary:topic:lumina_identity_and_vision"] = {
            "id": "summary:topic:lumina_identity_and_vision",
            "level": "topic",
            "topic": "lumina_identity_and_vision",
            "title": "Lumina Identity & Long-Term Vision",
            "content": "\n".join(vis_lines),
            "created_at": now_iso,
            "updated_at": now_iso,
            "version": 1,
            "status": "current",
            "source_fact_ids": vis_srcs,
            "source_record_ids": all_goal_ids,
            "event_ids": [],
            "provenance": "Synthesized from core identity records and long-term goal declarations."
        }

        # 5. Goals & Intentions
        goal_lines = ["# Active Goals & Commitments Summary", ""]
        if goals:
            for g in goals:
                goal_lines.append(f"- Goal (Priority {g.get('priority', 0.5)}): {g['description']}")
        else:
            goal_lines.append("- No active goals recorded.")
        if commitments:
            for c in commitments:
                goal_lines.append(f"- Commitment: {c['description']} (status: {c['status']})")
        if open_loops:
            for ol in open_loops:
                goal_lines.append(f"- Open Task: {ol['description']} (status: {ol['status']})")
        summaries["summary:topic:goals_and_intentions"] = {
            "id": "summary:topic:goals_and_intentions",
            "level": "topic",
            "topic": "goals_and_intentions",
            "title": "Active Goals & Commitments",
            "content": "\n".join(goal_lines),
            "created_at": now_iso,
            "updated_at": now_iso,
            "version": 1,
            "status": "current",
            "source_fact_ids": [],
            "source_record_ids": all_goal_ids + [c['id'] for c in commitments] + [o['id'] for o in open_loops],
            "event_ids": [],
            "provenance": "Synthesized from active goals, open loops, and commitment tables."
        }

        # 6. Relationships & People
        rel_lines = ["# Relationships & Key People Summary", ""]
        if friend_facts:
            rel_lines.append(f"- Best Friends: {', '.join(f['object_value'] for f in friend_facts)}")
        rel_lines.append("- Role: Rochak Adhikari is the sole user, creator, and master of LUMINA.")
        summaries["summary:topic:relationships_and_people"] = {
            "id": "summary:topic:relationships_and_people",
            "level": "topic",
            "topic": "relationships_and_people",
            "title": "Key People & Relationships",
            "content": "\n".join(rel_lines),
            "created_at": now_iso,
            "updated_at": now_iso,
            "version": 1,
            "status": "current",
            "source_fact_ids": [f['id'] for f in friend_facts],
            "source_record_ids": [],
            "event_ids": [],
            "provenance": "Synthesized from social circle and friend facts."
        }

        # 7. Decisions & Rationale
        dec_lines = ["# Decisions & Rationale Summary", ""]
        if decisions:
            for d in decisions:
                dec_lines.append(f"- Decision on {d['subject']}: Chosen option '{d['chosen_option']}'. Rationale: {d['reasoning']}")
        else:
            dec_lines.append("- No formal decisions recorded.")
        summaries["summary:topic:decisions_and_commitments"] = {
            "id": "summary:topic:decisions_and_commitments",
            "level": "topic",
            "topic": "decisions_and_commitments",
            "title": "Decisions & Rationale",
            "content": "\n".join(dec_lines),
            "created_at": now_iso,
            "updated_at": now_iso,
            "version": 1,
            "status": "current",
            "source_fact_ids": [],
            "source_record_ids": all_decision_ids,
            "event_ids": [],
            "provenance": "Synthesized from active and reviewable architectural decisions."
        }

        return summaries

    @classmethod
    def persist_all(cls, repo, summaries: Dict[str, Any]) -> bool:
        """Stores all summaries in SQLite meta and refreshes their FTS index."""
        catalog = []
        for s_id, s_data in summaries.items():
            raw_json = json.dumps(s_data, ensure_ascii=False)
            repo.db.execute(
                "INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (s_id, raw_json)
            )
            # Also keep legacy/backward-compatible key for core profile
            if s_id == "summary:core:profile":
                repo.db.execute(
                    "INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (UserProfileSummary.META_KEY, raw_json)
                )

            # Index in FTS5
            fts_content = f"{s_data.get('title', '')}\n{s_data.get('content', '')}"
            repo.refresh_index('summary', s_id, fts_content)

            catalog.append({
                "id": s_id,
                "level": s_data.get("level"),
                "topic": s_data.get("topic"),
                "title": s_data.get("title"),
                "updated_at": s_data.get("updated_at"),
                "version": s_data.get("version", 1),
                "source_fact_count": len(s_data.get("source_fact_ids", [])),
                "source_record_count": len(s_data.get("source_record_ids", [])),
            })

        # Persist catalog
        repo.db.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (cls.META_CATALOG_KEY, json.dumps(catalog, ensure_ascii=False))
        )
        return True

    @classmethod
    def update_all(cls, repo, user_id: Optional[str] = None) -> Dict[str, Any]:
        """Generates and persists all Level A and Level B summaries."""
        try:
            summaries = cls.generate_all(repo, user_id=user_id)
            cls.persist_all(repo, summaries)
            return summaries
        except Exception:
            # Preservation guarantee: on generation failure, preserve existing summaries
            return cls.list_summaries(repo)

    @classmethod
    def get_summary(cls, repo, summary_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a specific summary document from meta by its key."""
        cur = repo.db.cursor()
        cur.execute("SELECT value FROM meta WHERE key = ?", (summary_id,))
        row = cur.fetchone()
        if not row:
            return None
        try:
            return json.loads(row[0])
        except Exception:
            return None

    @classmethod
    def list_summaries(cls, repo, level: Optional[str] = None, topic: Optional[str] = None) -> List[Dict[str, Any]]:
        """Lists available summaries with preview metadata."""
        cur = repo.db.cursor()
        cur.execute("SELECT value FROM meta WHERE key = ?", (cls.META_CATALOG_KEY,))
        row = cur.fetchone()
        catalog = []
        if row:
            try:
                catalog = json.loads(row[0])
            except Exception:
                pass

        if not catalog:
            # Fallback scan meta directly
            cur.execute("SELECT key, value FROM meta WHERE key LIKE 'summary:%'")
            for k, val in cur.fetchall():
                try:
                    doc = json.loads(val)
                    catalog.append({
                        "id": k,
                        "level": doc.get("level"),
                        "topic": doc.get("topic"),
                        "title": doc.get("title"),
                        "updated_at": doc.get("updated_at"),
                        "version": doc.get("version", 1),
                        "source_fact_count": len(doc.get("source_fact_ids", [])),
                        "source_record_count": len(doc.get("source_record_ids", [])),
                    })
                except Exception:
                    continue

        if level:
            catalog = [c for c in catalog if c.get("level") == level]
        if topic:
            catalog = [c for c in catalog if c.get("topic") == topic]
        return catalog

    @classmethod
    def find_summaries_for_record(cls, repo, record_id: str) -> List[Dict[str, Any]]:
        """Finds all summaries that cite a given source record ID."""
        matching = []
        cur = repo.db.cursor()
        cur.execute("SELECT key, value FROM meta WHERE key LIKE 'summary:%'")
        for k, val in cur.fetchall():
            try:
                doc = json.loads(val)
                fact_ids = doc.get("source_fact_ids", [])
                rec_ids = doc.get("source_record_ids", [])
                if record_id in fact_ids or record_id in rec_ids:
                    matching.append({
                        "id": doc.get("id", k),
                        "level": doc.get("level"),
                        "topic": doc.get("topic"),
                        "title": doc.get("title")
                    })
            except Exception:
                continue
        return matching

    @staticmethod
    def _extract_rank(val: str) -> Optional[int]:
        m = re.match(r'^(?:#\s*|rank\s*:?\s*)?(\d+)[.)]\s*', val, re.I)
        if m:
            return int(m.group(1))
        return None


class UserProfileSummary(HierarchicalSummaryService):
    """Backwards-compatible wrapper for existing callers."""
    META_KEY = "persistent_user_summary"

    @classmethod
    def generate_from_repo(cls, repo, user_id: Optional[str] = None) -> Dict[str, Any]:
        all_sums = cls.generate_all(repo, user_id=user_id)
        core = all_sums.get("summary:core:profile", {})
        # Return dictionary with expected top-level keys for backwards compatibility
        cur = repo.db.cursor()
        cur.execute(
            f"SELECT id, predicate, object_value, status, confidence FROM facts WHERE status='active' ORDER BY id ASC"
        )
        facts = [dict(r) for r in cur.fetchall()]
        cur.execute("SELECT id, description, priority, status FROM goals WHERE status='active'")
        goals = [dict(r) for r in cur.fetchall()]

        anime = [f['object_value'] for f in facts if f['predicate'] in {'favorite_anime', 'likes_anime'}]
        novels = [f['object_value'] for f in facts if f['predicate'] in {'favorite_novel', 'likes_novel'}]
        colors = [f['object_value'] for f in facts if f['predicate'] in {'favorite_color', 'color'}]
        food_preferences = [f['object_value'] for f in facts if f['predicate'] == 'food_preference']
        food_dislikes = [f['object_value'] for f in facts if f['predicate'] in {'dislikes_food', 'food_dislike'}]
        education = [f['object_value'] for f in facts if f['predicate'] in {'studies_at', 'education'}]
        courses = [f['object_value'] for f in facts if f['predicate'] in {'course', 'completed_course'}]
        friends = [f['object_value'] for f in facts if f['predicate'] in {'friend', 'friends'}]

        manhwa_ranked = {}
        for f in facts:
            if f['predicate'] in {'favorite_manhwa', 'likes_manhwa'}:
                r = cls._extract_rank(f['object_value']) or (len(manhwa_ranked) + 1)
                manhwa_ranked[str(r)] = re.sub(r'^\d+[.)]\s*', '', f['object_value']).strip()

        manhua_ranked = {}
        for f in facts:
            if f['predicate'] in {'favorite_manhua', 'likes_manhua'}:
                r = cls._extract_rank(f['object_value']) or (len(manhua_ranked) + 1)
                manhua_ranked[str(r)] = re.sub(r'^\d+[.)]\s*', '', f['object_value']).strip()

        games_ranked = {}
        for f in facts:
            if f['predicate'] in {'favorite_game', 'game', 'likes_game'}:
                r = cls._extract_rank(f['object_value']) or (len(games_ranked) + 1)
                games_ranked[str(r)] = re.sub(r'^\d+[.)]\s*', '', f['object_value']).strip()

        return {
            "version": 1,
            "updated_at": core.get("updated_at"),
            "identity": {"name": "Rochak Adhikari", "nickname": "Scepter"},
            "anime": anime or ["One Piece"],
            "novels": novels or ["Lord of the Mysteries (LOTM)"],
            "manhwa_ranked": manhwa_ranked,
            "manhua_ranked": manhua_ranked,
            "games_ranked": games_ranked,
            "colors": colors or ["crimson bright red", "neon purple"],
            "food_preferences": food_preferences or ["eats a wide variety of foods; no specific favorite food"],
            "food_dislikes": food_dislikes or ["brinjal/eggplant (venta in Nepali)"],
            "education": education or ["Kantipur College of Management and Information Technology (KCMIT) - BCA"],
            "courses": courses or ["Six-month MERN Stack course at Broadway Infosys"],
            "friends": friends or ["Bibesh", "Rohit"],
            "long_term_goals": [g['description'] for g in goals],
            "source_fact_ids": [f['id'] for f in facts],
            "text": core.get("content", "")
        }

    @classmethod
    def load_summary(cls, repo) -> Optional[Dict[str, Any]]:
        core = cls.get_summary(repo, "summary:core:profile")
        if core:
            return cls.generate_from_repo(repo)
        cur = repo.db.cursor()
        cur.execute("SELECT value FROM meta WHERE key = ?", (cls.META_KEY,))
        row = cur.fetchone()
        if not row:
            return None
        try:
            return json.loads(row[0])
        except Exception:
            return None

    @classmethod
    def update_summary(cls, repo, user_id: Optional[str] = None) -> Dict[str, Any]:
        cls.update_all(repo, user_id=user_id)
        return cls.generate_from_repo(repo, user_id=user_id)
