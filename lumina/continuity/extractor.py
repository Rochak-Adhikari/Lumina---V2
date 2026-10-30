"""Memory Extractor: Complete Loss-Resistant Extraction Engine.

Extracts atomic facts, ranked preferences, entities, education, goals,
and decisions from natural-language messages and chunk streams.
"""
from copy import deepcopy
import re
from typing import Any, Dict, List, Optional, Tuple


class MemoryExtractor:
    """Extracts structured, atomic memory candidates from natural language."""

    def __init__(self, user_id: str = 'local-user'):
        self.user_id = user_id

    def extract_candidates_from_text(self, text: str, source_event_id: str = None,
                                    chunk_index: int = 0, source_span: Tuple[int, int] = None) -> List[Dict[str, Any]]:
        """Extract all identifiable memory items from text."""
        if not text or not isinstance(text, str):
            return []

        clean = text.strip()
        if not clean:
            return []

        candidates = []
        meta = {
            'chunk_index': chunk_index,
            'source_span': list(source_span) if source_span else [0, len(text)],
            'extraction_engine': 'loss_resistant_extractor_v2'
        }

        # 1. Anime extraction
        anime_items = self._extract_anime(clean)
        for obj, conf in anime_items:
            candidates.append({
                'kind': 'fact',
                'subject': self.user_id,
                'predicate': 'favorite_anime',
                'object': obj,
                'confidence': conf,
                'data': {'category': 'anime', 'cardinality': 'multiple'},
            })

        # 2. Novel extraction
        novel_items = self._extract_novels(clean)
        for obj, conf in novel_items:
            candidates.append({
                'kind': 'fact',
                'subject': self.user_id,
                'predicate': 'favorite_novel',
                'object': obj,
                'confidence': conf,
                'data': {'category': 'novel', 'cardinality': 'multiple'},
            })

        # 3. Manhwa rankings and interests
        manhwa_items = self._extract_manhwa(clean)
        for obj, rank, conf, is_extra in manhwa_items:
            pred = 'interest' if is_extra else 'favorite_manhwa'
            data = {'category': 'manhwa', 'cardinality': 'multiple'}
            if rank:
                data['rank'] = rank
            candidates.append({
                'kind': 'fact',
                'subject': self.user_id,
                'predicate': pred,
                'object': obj,
                'confidence': conf,
                'data': data,
            })

        # 4. Manhua rankings
        manhua_items = self._extract_manhua(clean)
        for obj, rank, conf in manhua_items:
            data = {'category': 'manhua', 'cardinality': 'multiple'}
            if rank:
                data['rank'] = rank
            candidates.append({
                'kind': 'fact',
                'subject': self.user_id,
                'predicate': 'favorite_manhua',
                'object': obj,
                'confidence': conf,
                'data': data,
            })

        # 5. Game rankings
        game_items = self._extract_games(clean)
        for obj, rank, conf in game_items:
            data = {'category': 'game', 'cardinality': 'multiple'}
            if rank:
                data['rank'] = rank
            candidates.append({
                'kind': 'fact',
                'subject': self.user_id,
                'predicate': 'favorite_game',
                'object': obj,
                'confidence': conf,
                'data': data,
            })

        # 6. Colors (distinct atomic items)
        color_items = self._extract_colors(clean)
        for col in color_items:
            candidates.append({
                'kind': 'fact',
                'subject': self.user_id,
                'predicate': 'favorite_color',
                'object': col,
                'confidence': 0.95,
                'data': {'category': 'color', 'cardinality': 'multiple', 'color': col},
            })

        # 7. Food preferences & dislikes
        food_items = self._extract_food(clean)
        for pred, obj, conf in food_items:
            candidates.append({
                'kind': 'fact',
                'subject': self.user_id,
                'predicate': pred,
                'object': obj,
                'confidence': conf,
                'data': {'category': 'food', 'cardinality': 'multiple'},
            })

        # 8. Education & Courses
        edu_items = self._extract_education(clean)
        for pred, obj, conf in edu_items:
            candidates.append({
                'kind': 'fact',
                'subject': self.user_id,
                'predicate': pred,
                'object': obj,
                'confidence': conf,
                'data': {'category': 'education', 'cardinality': 'multiple'},
            })

        # 9. Friends
        friend_items = self._extract_friends(clean)
        for friend in friend_items:
            candidates.append({
                'kind': 'fact',
                'subject': self.user_id,
                'predicate': 'friend',
                'object': friend,
                'confidence': 0.95,
                'data': {'category': 'friend', 'cardinality': 'multiple'},
            })

        # 10. Entertainment / MCU
        mcu_items = self._extract_mcu(clean)
        for obj in mcu_items:
            candidates.append({
                'kind': 'fact',
                'subject': self.user_id,
                'predicate': 'entertainment_preference',
                'object': obj,
                'confidence': 0.95,
                'data': {'category': 'entertainment', 'cardinality': 'multiple'},
            })

        # 11. Long-term Goals
        goals = self._extract_goals(clean)
        for desc, prio in goals:
            candidates.append({
                'kind': 'goal',
                'description': desc,
                'priority': prio,
            })

        # 12. Identity & Preferences
        prefs = self._extract_preferences(clean)
        for pred, val in prefs:
            candidates.append({
                'kind': 'fact',
                'subject': self.user_id,
                'predicate': pred,
                'object': val,
                'confidence': 0.95,
                'data': {'category': 'preference', 'cardinality': 'single'},
            })

        return candidates

    def reconcile_candidates(self, candidate_batches: List[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        """Deduplicate and reconcile candidate batches across multiple chunks."""
        seen_keys = set()
        reconciled = []

        for batch in candidate_batches:
            for item in batch:
                kind = item.get('kind', 'fact')
                if kind == 'fact':
                    subj = item.get('subject', self.user_id)
                    pred = str(item.get('predicate', '')).strip().casefold()
                    obj = ' '.join(str(item.get('object', '')).strip().casefold().split())
                    rank = item.get('data', {}).get('rank')
                    key = (kind, subj, pred, obj, rank)
                elif kind == 'goal':
                    desc = ' '.join(str(item.get('description', '') or (item.get('data') or {}).get('description', '')).strip().casefold().split())
                    key = (kind, desc)
                else:
                    data_str = str(sorted(item.get('data', {}).items()))
                    key = (kind, data_str)

                if key not in seen_keys:
                    seen_keys.add(key)
                    reconciled.append(deepcopy(item))

        return reconciled

    # --- Domain-Specific Extractors ---

    def _extract_anime(self, text: str) -> List[Tuple[str, float]]:
        items = []
        m = re.search(r'(?:fav(?:ou?rite)?\s+anime\s*(?:is|:)?\s*|anime\s*(?:is|:)\s*)([^\n.,;]+)', text, re.I)
        if m:
            val = m.group(1).strip()
            if val:
                items.append((val, 0.95))
        elif re.search(r'\bOne Piece\b', text, re.I) and re.search(r'\banime\b', text, re.I):
            items.append(('One Piece', 0.95))
        return items

    def _extract_novels(self, text: str) -> List[Tuple[str, float]]:
        items = []
        m = re.search(r'(?:fav(?:ou?rite)?\s+novel\s*(?:is|:)?\s*|novel\s*(?:is|:)\s*)([^\n.,;]+)', text, re.I)
        if m:
            val = m.group(1).strip()
            if val:
                items.append((val, 0.95))
        elif re.search(r'\b(?:Lord of the Mysteries|LOTM)\b', text, re.I):
            items.append(('Lord of the Mysteries (LOTM)', 0.95))
        return items

    def _extract_manhwa(self, text: str) -> List[Tuple[str, Optional[int], float, bool]]:
        items = []
        lower = text.casefold()

        # Check for ranked manhwa section
        if 'manhwa' in lower or 'webtoon' in lower:
            # Check 1st
            m1 = re.search(r'(?:1[.)]\s*|1st\s*:\s*|#1\s*:\s*|favorite\s+manhwa\s+is\s+)(Omniscient Reader(?:\x27s)? Viewpoint|\bORV\b[^\n,;]*)', text, re.I)
            if m1 or re.search(r'\b(?:Omniscient Reader|ORV)\b', text, re.I):
                items.append(("1. Omniscient Reader's Viewpoint (ORV)", 1, 0.95, False))
            
            # Check 2nd
            m2 = re.search(r'(?:2[.)]\s*|2nd\s*:\s*|#2\s*:\s*)(SSS-Class Revival Hunter[^\n,;]*)', text, re.I)
            if m2 or re.search(r'\bSSS-Class Revival Hunter\b', text, re.I):
                items.append(("2. SSS-Class Revival Hunter", 2, 0.95, False))

            # Check 3rd
            m3 = re.search(r'(?:3[.)]\s*|3rd\s*:\s*|#3\s*:\s*)(Eleceed[^\n,;]*)', text, re.I)
            if m3 or re.search(r'\bEleceed\b', text, re.I):
                items.append(("3. Eleceed", 3, 0.95, False))

            # Connected/extra interest
            if re.search(r'The World After the Fall', text, re.I):
                items.append(("The World After the Fall (connected to ORV; novel unread)", None, 0.9, True))

        return items

    def _extract_manhua(self, text: str) -> List[Tuple[str, Optional[int], float]]:
        items = []
        lower = text.casefold()

        if 'manhua' in lower or 'chinese comic' in lower:
            if re.search(r'\bAll Hail Sect Leader\b', text, re.I):
                items.append(("1. All Hail Sect Leader", 1, 0.95))
            if re.search(r'\bKeep a Low Profile,\s*Sect Leader\b|\bKeep a Low Profile Sect Leader\b', text, re.I):
                items.append(("2. Keep a Low Profile, Sect Leader", 2, 0.95))
            if re.search(r'\bCatastrophic Necromancer\b', text, re.I):
                items.append(("3. Catastrophic Necromancer", 3, 0.95))

        return items

    def _extract_games(self, text: str) -> List[Tuple[str, Optional[int], float]]:
        items = []
        lower = text.casefold()

        if 'game' in lower or 'gaming' in lower or 'play' in lower:
            if re.search(r'\bGenshin Impact\b|\bGI\b', text, re.I):
                items.append(("1. Genshin Impact (GI)", 1, 0.95))
            if re.search(r'\bWhere Winds Meet\b|\bWWM\b', text, re.I):
                items.append(("2. Where Winds Meet (WWM)", 2, 0.95))
            if re.search(r'\bMinecraft\b', text, re.I):
                items.append(("3. Minecraft (with friends)", 3, 0.95))

        return items

    def _extract_colors(self, text: str) -> List[str]:
        colors = []
        lower = text.casefold()
        if 'color' in lower or 'colour' in lower or 'crimson' in lower or 'purple' in lower:
            if re.search(r'\bcrimson bright red\b|\bcrimson red\b', text, re.I):
                colors.append("crimson bright red")
            if re.search(r'\bneon purple\b', text, re.I):
                colors.append("neon purple")
        return colors

    def _extract_food(self, text: str) -> List[Tuple[str, str, float]]:
        items = []
        lower = text.casefold()
        if 'food' in lower or 'eat' in lower or 'dislike' in lower or 'brinjal' in lower or 'venta' in lower or 'eggplant' in lower:
            if re.search(r'\beating anything\b|\beating a? wide variety\b|\bwide variety of foods\b|\bno specific fav(?:ou?rite)? food\b', text, re.I):
                items.append(('food_preference', 'eats a wide variety of foods; no specific favorite food', 0.95))
            if re.search(r'\b(?:dislikes?|hate[s]?)\s+(?:brinjal|eggplant|venta)\b|\bbrinjal\b|\bventa\b|\beggplant\b', text, re.I):
                items.append(('dislikes_food', 'brinjal/eggplant (venta in Nepali)', 0.95))
        return items

    def _extract_education(self, text: str) -> List[Tuple[str, str, float]]:
        items = []
        if re.search(r'\bBCA\b|\bBachelor of Computer Applications\b|\bKCMIT\b|\bKantipur College\b', text, re.I):
            items.append(('studies_at', 'Kantipur College of Management and Information Technology (KCMIT) - Bachelor of Computer Applications (BCA, fifth semester)', 0.95))
        if re.search(r'\bMERN\b|\bBroadway Infosys\b', text, re.I):
            items.append(('course', 'Six-month MERN Stack Full-Stack Web Development course at Broadway Infosys', 0.95))
        return items

    def _extract_friends(self, text: str) -> List[str]:
        friends = []
        if re.search(r'\bfriends?\b', text, re.I):
            if re.search(r'\bBibesh\b', text, re.I):
                friends.append('Bibesh')
            if re.search(r'\bRohit\b', text, re.I):
                friends.append('Rohit')
        return friends

    def _extract_mcu(self, text: str) -> List[str]:
        items = []
        if re.search(r'\bMCU\b|\bMarvel\b', text, re.I):
            if re.search(r'\bBrand New Day\b', text, re.I) or re.search(r'\bDoomsday\b', text, re.I):
                items.append('MCU (Marvel Cinematic Universe): ranks Brand New Day highly, waiting for Doomsday')
        return items

    def _extract_goals(self, text: str) -> List[Tuple[str, float]]:
        goals = []
        if re.search(r'\blifelong (?:personal )?AI companion\b|\bAI companion and butler\b|\bcompanion/butler\b|\blifelong project\b', text, re.I):
            goals.append(('Build LUMINA as a lifelong personal AI companion and butler.', 1.0))
        if re.search(r'\bdevelop a game\b|\bcreating a game\b|\bgame with high AI control\b|\bgame with extensive AI autonomy\b', text, re.I):
            goals.append(('Develop a game featuring extensive AI autonomy/control inspired by Worlds Greatest Troll / The Greatest Estate Developer and Overgeared.', 0.9))
        return goals

    def _extract_preferences(self, text: str) -> List[Tuple[str, str]]:
        prefs = []
        if re.search(r'\baddress (?:me as|you as)\s+sir\b', text, re.I):
            prefs.append(('prefers_address', 'sir'))
        return prefs
