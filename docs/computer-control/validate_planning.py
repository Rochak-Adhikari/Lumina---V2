"""Planning consistency/preservation inspection only; no application imports."""
from pathlib import Path
import hashlib
import json
import re
import subprocess
import os
import sys
from datetime import datetime

D = Path(__file__).resolve().parent
ROOT = D.parents[1]
checks = {}
register = (D/'ROADMAP.md').read_text(encoding='utf-8')
rows = [[c.strip() for c in line.split('|')[1:-1]] for line in register.splitlines() if re.match(r'^\| P\d+\.\d+\s*\|', line)]
ids = [r[0] for r in rows]
checks['unique_milestone_ids'] = len(ids) == len(set(ids))
deps = {r[0]: [] if r[3] == '—' else r[3].split(',') for r in rows}
checks['all_dependencies_exist'] = all(x in ids for ds in deps.values() for x in ds)
active, done = set(), set()
def visit(x):
    if x in active: raise ValueError('dependency cycle: '+x)
    if x in done: return
    active.add(x)
    for y in deps[x]: visit(y)
    active.remove(x)
    done.add(x)
try:
    for x in ids: visit(x)
    checks['acyclic_dependencies'] = True
except (ValueError, KeyError): checks['acyclic_dependencies'] = False
checks['explicit_exits_effort_status'] = all(len(r)==9 and r[4] and r[5] and r[8] for r in rows)
checks['exactly_eight_phases'] = {r[1] for r in rows} == set(map(str, range(8)))
checks['phase_specs_and_handoffs'] = all((D/f'phases/PHASE-{i:02d}.md').is_file() and
    'Reusable Astra handoff prompt' in (D/f'phases/PHASE-{i:02d}.md').read_text(encoding='utf-8') for i in range(8))
checks['twenty_fields_per_phase'] = all(all(re.search(rf'(?m)^{j}\. ', (D/f'phases/PHASE-{i:02d}.md').read_text(encoding='utf-8')) for j in range(1,21)) for i in range(8))
matrix = (D/'ACCEPTANCE_TEST_MATRIX.md').read_text(encoding='utf-8')
checks['all_completion_classes_mapped'] = all(re.search(rf'(?m)^\| {x} — ', matrix) for x in 'ABCDEFGHIJ')
contracts = (D/'CONTRACTS.md').read_text(encoding='utf-8')
contract_ids = re.findall(r'(?m)^\| (C\d\d) \|', contracts)
checks['thirty_unique_contract_ids'] = len(contract_ids)==len(set(contract_ids))==30
checks['status_next_milestone_matches_graph'] = (deps.get('P1.1')==['P0.1'] and
    'P1.1' in (D/'STATUS.md').read_text(encoding='utf-8') and
    next(r for r in rows if r[0]=='P0.1')[4]=='STATIC_COMPLETE' and
    next(r for r in rows if r[0]=='P1.1')[4]=='AWAITING_PLAN_APPROVAL')
broken = []
planning_md = [p for p in D.rglob('*.md') if not p.name.startswith('LUMINA_')]
for p in planning_md:
    for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)',p.read_text(encoding='utf-8')):
        if '://' not in target and not target.startswith('#') and not (p.parent/target.split('#')[0]).exists():
            broken.append([str(p.relative_to(D)), target])
checks['local_links_resolve'] = not broken
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
record=json.loads((D/'PLANNING_PRESERVATION.json').read_text(encoding='utf-8'))
initial=record['initial']
final_hashes={p:sha(ROOT/p) if (ROOT/p).is_file() else None for p in initial['sources']}
drift=[p for p,h in initial['sources'].items() if final_hashes[p]!=h]
originals={p:sha(D/p) for p in initial['originals']}
checks['selected_sources_unchanged']=not drift
checks['original_plans_unchanged']=originals==initial['originals']
git={}
for k,args in {'root':['rev-parse','--show-toplevel'],'branch':['branch','--show-current'],'head':['rev-parse','HEAD'],'status':['status','--short','--untracked-files=all'],'diff':['diff','--stat']}.items():
    p=subprocess.run(['git',*args],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',env={**os.environ,'GIT_OPTIONAL_LOCKS':'0'})
    git[k]={'exit':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
checks['branch_head_unchanged']=all(git[k]['stdout']==initial['git'][k]['stdout'] for k in ('root','branch','head'))
before=set(initial['git']['status']['stdout'].splitlines());after=set(git['status']['stdout'].splitlines())
added=sorted(after-before);removed=sorted(before-after)
checks['no_initial_status_entry_removed']=not removed
checks['new_status_entries_planning_only']=all('docs/computer-control/' in x.replace('\\','/') for x in added)
checks['tracked_diff_summary_unchanged']=git['diff']['stdout']==initial['git']['diff']['stdout']
remaining=[r for r in rows if r[1]!='0']
efforts=[tuple(map(int,r[5].split('–'))) for r in remaining]
totals=[sum(x[i] for x in efforts) for i in (0,1)]
checks['schedule_matches_register']=totals==[30,54]
record['final']={'time':datetime.now().astimezone().isoformat(),'git':git,'sources':final_hashes,'originals':originals,
                 'source_drift':drift,'new_status_entries':added,'removed_status_entries':removed}
(D/'PLANNING_PRESERVATION.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
result={'time':record['final']['time'],'checks':checks,'all_checks_pass':all(checks.values()),
        'milestone_ids':ids,'remaining_active_days':totals,'broken_links':broken,'source_drift':drift,
        'note':'Document/static preservation validation only. No app tests, native control or inference executed.'}
(D/'PLAN_VALIDATION.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result))
sys.exit(0 if result['all_checks_pass'] else 1)
