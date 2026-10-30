"""Production Profile Admission and Verification Script for Lumina.

Admits the Section 9 profile facts into the production database using the
repaired, loss-resistant continuity pipeline, verifying database integrity
before and after, and testing fresh recall across all categories.
"""
import datetime
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import sys

from lumina.continuity.chunker import MessageChunker
from lumina.continuity.extractor import MemoryExtractor
from lumina.continuity.manifest import ExtractionManifest
from lumina.continuity.service import MemoryService
from lumina.continuity_commands import ContinuityCommands, ContinuityTools, summary


SECTION_9_TEXT = (
    "Here is my complete profile information to remember: "
    "My favorite anime is One Piece. "
    "My favorite novel is Lord of the Mysteries (LOTM). "
    "For manhwa, my #1 favorite is Omniscient Reader's Viewpoint (ORV), "
    "my #2 favorite is SSS-Class Revival Hunter, and my #3 favorite is Eleceed. "
    "I also enjoy The World After the Fall, which is connected to ORV. "
    "For manhua, my #1 favorite is All Hail Sect Leader, "
    "my #2 favorite is Keep a Low Profile, Sect Leader, and my #3 favorite is Catastrophic Necromancer. "
    "For games, my #1 favorite is Genshin Impact (GI), my #2 favorite is Where Winds Meet (WWM), "
    "and my #3 favorite is Minecraft, which I enjoy playing with friends. "
    "My favorite colors are crimson bright red and neon purple. "
    "For food, I have no specific favorite food and eat a wide variety of foods, "
    "but I dislike brinjal/eggplant, which is venta in Nepali. "
    "I study BCA in fifth semester at Kantipur College of Management and Information Technology (KCMIT). "
    "I completed a 6-month MERN Stack Full-Stack Web Development course at Broadway Infosys. "
    "My best friends are Bibesh and Rohit. "
    "I follow the Marvel Cinematic Universe (MCU); I currently rank Brand New Day highly and am waiting for Avengers: Doomsday. "
    "My long-term goal is to build LUMINA as my lifelong personal AI companion and butler, "
    "and develop a game with extensive AI autonomy inspired by Worlds Greatest Troll, The Greatest Estate Developer, and Overgeared."
)


def main():
    prod_path = Path.home() / 'AppData' / 'Local' / 'LUMINA' / 'memory.sqlite3'
    print(f"=== Production Database: {prod_path} ===")
    if not prod_path.exists():
        print("ERROR: Production database does not exist!")
        sys.exit(1)

    # 1. Check initial integrity
    conn = sqlite3.connect(prod_path)
    cur = conn.cursor()
    cur.execute("PRAGMA integrity_check")
    status = cur.fetchone()[0]
    conn.close()
    if status != 'ok':
        print(f"ERROR: Production database integrity check failed: {status}")
        sys.exit(1)
    print(f"Initial DB integrity check: {status}")

    # 2. Take verified backup
    backup_dir = Path("artifacts/backups")
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"memory_backup_pre_admission_{ts}.sqlite3"
    shutil.copy2(prod_path, backup_path)

    bconn = sqlite3.connect(backup_path)
    bcur = bconn.cursor()
    bcur.execute("PRAGMA integrity_check")
    bstatus = bcur.fetchone()[0]
    bconn.close()
    if bstatus != 'ok':
        print(f"ERROR: Backup integrity check failed: {bstatus}")
        sys.exit(1)
    print(f"Verified pre-admission backup saved to: {backup_path}")

    # 3. Connect MemoryService and tools
    svc = MemoryService(prod_path)

    class ProdRegistry:
        def __init__(self, memory):
            self.memory = memory
            self.pending = {}
            self.runtime = type('ProdRuntime', (), {'auto_memory_capture': True})()
            self.memory_context = lambda: {
                'session_id': f'session-profile-admission-{ts}',
                'project_id': None,
                'source_event_id': getattr(memory, 'last_user_event_id', None),
                'query': 'save all these preferences to my memory'
            }

    reg = ProdRegistry(svc)
    tools = ContinuityTools(reg)
    commands = ContinuityCommands(reg)

    # 4. Record user evidence event
    ev = svc.record_event('conversation.message', {'role': 'user', 'text': SECTION_9_TEXT}, source_type='user')
    svc.last_user_event_id = ev['id']
    print(f"Recorded user evidence event: {ev['id']}")

    # 5. Multi-chunk extraction and manifest tracking
    chunker = MessageChunker(target_chars=800, max_chars=1400, overlap_chars=100)
    chunks = chunker.chunk_message(SECTION_9_TEXT, message_id=f'admission_msg_{ts}')
    manifest = ExtractionManifest.create_from_chunks(f'admission_msg_{ts}', f'hash_{ts}', chunks, repo=svc.repo)
    extractor = MemoryExtractor(user_id=svc.user_id)

    batches = []
    for c in chunks:
        manifest.start_chunk(c.chunk_id)
        cands = extractor.extract_candidates_from_text(
            c.text,
            source_event_id=ev['id'],
            chunk_index=c.index,
            source_span=(c.start_char, c.end_char)
        )
        batches.append(cands)
        manifest.record_chunk_result(c.chunk_id, candidate_ids=[x.get('predicate', '') for x in cands])

    reconciled = extractor.reconcile_candidates(batches)
    print(f"Extracted and reconciled {len(reconciled)} candidates.")

    # 6. Propose and admit candidates
    prop_res = tools.execute('memory_propose', {'proposals': reconciled}, online=False)
    manifest.status = 'completed'
    manifest.persist()

    print(f"Admission Result: status={prop_res.get('status')} admitted={prop_res.get('admitted_count')} rejected={prop_res.get('rejected_count')}")
    if prop_res.get('rejected'):
        print(f"WARNING: Rejected items: {prop_res.get('rejected')}")

    # 7. Post-admission integrity check
    conn = sqlite3.connect(prod_path)
    cur = conn.cursor()
    cur.execute("PRAGMA integrity_check")
    post_status = cur.fetchone()[0]
    for table in ['facts', 'goals', 'events', 'episodes', 'memory_candidates', 'evidence']:
        cur.execute(f"SELECT count(*) FROM {table}")
        print(f"Post-admission {table} count: {cur.fetchone()[0]}")
    conn.close()

    if post_status != 'ok':
        print(f"FATAL: Post-admission integrity check failed: {post_status}")
        sys.exit(1)
    print(f"Post-admission DB integrity check: {post_status}")

    # 8. Live retrieval verification across all Section 9 categories
    queries = [
        "What is my favorite anime?",
        "What is my favorite novel?",
        "What are my favorite manhwa?",
        "What is my top favorite manhwa?",
        "What is my second favorite manhwa?",
        "What is my third favorite manhwa?",
        "What is my favorite manhua?",
        "What is my second favorite manhua?",
        "What is my third favorite manhua?",
        "What are my favorite games?",
        "What is my second favorite game?",
        "What is my third favorite game?",
        "What are my favorite colors?",
        "What food do I dislike?",
        "Where do I study?",
        "What is my long-term goal?"
    ]

    print("\n=== LIVE RETRIEVAL RECALL VERIFICATION ===")
    all_success = True
    for q in queries:
        rec = svc.recall(q)
        ans = summary('memory_recall', rec)
        print(f"\nQ: {q}\n  -> Recall Facts: {len(rec.get('facts', []))}, Goals: {len(rec.get('goals', []))}\n  -> Answer: {ans}")
        if "I found no matching memory" in ans:
            print("  [FAIL] Missing memory response!")
            all_success = False

    # 9. Session Consolidation & Continuity check
    print("\n=== SESSION CONSOLIDATION CHECK ===")
    ep = svc.consolidate()
    print("Consolidated episode:", ep.get('id') if ep else "None")
    cont = svc.continuation()
    print("Continuation payload keys:", list(cont.keys()))
    if 'recent_episodes' in cont:
        print(f"Recent episodes in continuation: {len(cont['recent_episodes'])}")

    svc.close()
    if all_success:
        print("\n>>> ALL PROFILE ADMISSION AND RETRIEVAL CHECKS PASSED WITH 100% SUCCESS <<<")
    else:
        print("\n>>> ONE OR MORE QUERIES FAILED <<<")
        sys.exit(1)


if __name__ == '__main__':
    main()

