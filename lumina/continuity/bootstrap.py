"""Reviewed, hash-bound seed imports into the existing canonical repository.

The manifest is a private staging artifact, not another memory database. It must
be reviewed when the source changes. No model, network call or shell is invoked.
"""
import hashlib
import json
from pathlib import Path
import re

from .policy import document, now, text

VERSION = 1


def digest(value):
    return hashlib.sha256(value if isinstance(value, bytes) else json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def sections(source):
    matches = list(re.finditer(r'^# (\d+)\. .+$', source, re.M))
    return {int(m[1]): source[m.start():matches[i+1].start() if i+1<len(matches) else len(source)]
            for i,m in enumerate(matches)}


def load_plan(seed, manifest):
    seed, manifest = Path(seed).resolve(), Path(manifest).resolve()
    if seed.stat().st_size > 2_000_000 or manifest.stat().st_size > 2_000_000:
        raise ValueError('Seed or reviewed plan exceeds 2 MB.')
    raw = seed.read_bytes()
    plan = json.loads(manifest.read_text('utf-8'))
    if plan.get('version') != VERSION or plan.get('seed_sha256') != digest(raw):
        raise ValueError('The seed changed or the plan version is unsupported. Review a new plan before importing.')
    source = raw.decode('utf-8-sig').replace('\r\n','\n')
    parts = sections(source)
    if not parts or not isinstance(plan.get('records'), list) or not isinstance(plan.get('entities'), list):
        raise ValueError('A sectioned source and structured reviewed plan are required.')
    if len(plan['records']) > 500 or len(plan['entities']) > 150:
        raise ValueError('Reviewed seed exceeds the import bound.')
    if not re.fullmatch(r'[a-z0-9_-]{1,80}', plan.get('source_key','')):
        raise ValueError('Invalid stable source key.')
    covered = plan.get('sections', [])
    if len(covered)!=len(parts) or {r['section'] for r in covered} != set(parts):
        raise ValueError('Every source section needs an explicit coverage disposition.')
    for group in ('entities','records'):
        keys=set()
        for item in plan[group]:
            document(item)
            if not re.fullmatch(r'[a-z0-9_-]{1,100}',item.get('key','')) or item['key'] in keys:
                raise ValueError('Duplicate or invalid seed item identity.')
            keys.add(item['key'])
            quote=text(item.get('quote'), 'source quote').replace('\r\n','\n')
            if quote not in parts.get(item.get('section'), ''):
                raise ValueError('A reviewed quotation is not present in its source section: '+item['key'])
    keys={i['key'] for i in plan['entities']}
    for item in plan['records']:
        if item.get('kind') not in {'fact','goal','decision','open_loop','event','behavior_pattern'}:
            raise ValueError('Unsupported seed record kind.')
        if item.get('temporal') not in {'historical','current','aspiration','unverified'}:
            raise ValueError('Each record needs explicit temporal classification.')
        for field in ('subject','object_entity','project'):
            if item.get(field) and item[field] not in keys:
                raise ValueError('Unknown reviewed entity reference.')
    return seed, plan, {str(k):digest(v.encode()) for k,v in parts.items()}


class SeedImporter:
    def __init__(self, service):
        self.s=service
        self.repo=service.repo

    def _get(self, key, default=None):
        rows=self.repo.rows('SELECT value FROM meta WHERE key=?',(key,))
        return json.loads(rows[0]['value']) if rows else default

    def _put(self,key,value):
        self.repo.db.execute('INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)',(key,json.dumps(value,ensure_ascii=False)))

    def run(self, seed, manifest, *, workspace, workspace_aliases=(), authorized=False):
        if authorized is not True:
            raise ValueError('Seed ingestion requires explicit local authorization.')
        seed,plan,section_hashes=load_plan(seed,manifest)
        source=plan['source_key']; fingerprint=plan['seed_sha256']; plan_hash=digest(plan)
        key='bootstrap:latest:'+source
        with self.repo.transaction():
            previous=self._get(key,{})
            if previous.get('seed_hash')==fingerprint:
                if previous.get('plan_hash')!=plan_hash:
                    raise ValueError('This source version already has a different reviewed plan; create a reviewed source revision.')
                return {**previous,'already_imported':True,'mutations':0}
            report={'source_key':source,'seed_hash':fingerprint,'plan_hash':plan_hash,'importer_version':VERSION,
                'source_path':str(seed),'imported_at':now(),'proposed':len(plan['records']),
                'admitted':0,'deduplicated':0,'requires_review':0,'rejected':0,'entities_created':0,
                'counts':{},'items':[],'sections':plan['sections'],'section_hashes':section_hashes}
            old_sections=previous.get('section_hashes',{})
            report['section_changes']={
                'new':sorted(set(section_hashes)-set(old_sections)),
                'removed':sorted(set(old_sections)-set(section_hashes)),
                'changed':sorted(k for k in section_hashes if k in old_sections and section_hashes[k]!=old_sections[k]),
                'unchanged':sorted(k for k in section_hashes if old_sections.get(k)==section_hashes[k])}
            entities={}
            known=self.repo.rows('SELECT * FROM entities')
            if len(known)>10000:raise ValueError('Entity registry needs scoped review before this import.')
            workspace=str(Path(workspace).resolve())
            if not Path(workspace).is_dir():raise ValueError('The assigned workspace does not exist.')
            workspace_key='workspace-project:'+workspace.casefold()
            for item in plan['entities']:
                stable='bootstrap:entity:'+source+':'+item['key']
                old=self._get(stable)
                matches=[]
                if old:
                    matches=[r for r in known if r['id']==old['id']]
                    if not matches:raise ValueError('A previously imported entity was removed; review instead of resurrecting it.')
                elif item['key']=='user':
                    matches=[r for r in known if r['id']==self.s.user_id]
                else:
                    names={v.casefold() for v in [item['name'],*item.get('aliases',[])]}
                    matches=[r for r in known if r['kind']==item['kind'] and
                        (r['name'].casefold() in names or names & {a.casefold() for a in r['metadata_json'].get('aliases',[])})]
                    if item['key']==plan.get('workspace_entity'):
                        scoped=[r for r in known if r['canonical_key']==workspace_key]
                        if scoped and matches and scoped[0]['id'] not in {r['id'] for r in matches}:
                            raise ValueError('Workspace and named project have different identities; resolve explicitly before import.')
                        matches=scoped or matches
                if len(matches)>1:raise ValueError('Ambiguous entity identity; review '+item['key'])
                row=matches[0] if matches else self.s.entity(item['kind'],item['name'],
                    workspace_key if item['key']==plan.get('workspace_entity') else stable, {'aliases':item.get('aliases',[])})
                if not matches:report['entities_created']+=1;known.append(row)
                metadata=dict(row['metadata_json'])
                metadata['aliases']=sorted(set(metadata.get('aliases',[])+item.get('aliases',[])+[item['name']]))
                changes={'metadata_json':metadata}
                if row['name']=='User' or (row['canonical_key']==workspace_key and row['name']==Path(workspace).name):
                    changes['name']=item['name']
                if changes.get('name') or metadata!=row['metadata_json']:self.repo.update('entities',row['id'],changes)
                event=self._event(seed,plan,item,'entity')
                self.s._evidence('entity',row['id'],event,.7,False,'reviewed_seed')
                self._put(stable,{'id':row['id']})
                entities[item['key']]=row['id']
            project=entities.get(plan.get('workspace_entity'))
            if project:
                for path in [workspace,*workspace_aliases]:
                    path=str(Path(path).resolve())
                    if not Path(path).is_dir():raise ValueError('Workspace alias does not exist.')
                    self.repo.db.execute('INSERT OR REPLACE INTO meta VALUES(?,?)',('workspace_alias:'+path.casefold(),project))
            prior_items={i['key'] for i in previous.get('items',[])}
            report['removed_items_retained']=sorted(prior_items-{i['key'] for i in plan['records']})
            for item in plan['records']:
                ledger='bootstrap:item:'+source+':'+item['key']; old=self._get(ledger)
                content=digest({k:v for k,v in item.items() if k not in {'quote','section'}})
                outcome={'key':item['key'],'section':item['section']}
                if old and old['content_hash']==content:
                    report['deduplicated']+=1
                    report['items'].append({**outcome,**old,'decision':'unchanged'})
                    continue
                if old:
                    _,record=self.s._find(old['record_id'])
                    if item['kind']!='fact' or not record or record['version']!=old['record_version'] or record.get('confirmed_by_user') or record.get('status') in {'superseded','invalidated','expired','resolved','completed','cancelled'}:
                        report['requires_review']+=1
                        report['items'].append({**outcome,'decision':'review','reason':'Existing memory was corrected, removed, or resolved; seed cannot override it.'})
                        continue
                event=self._event(seed,plan,item,'record')
                result=self.s.admission.bootstrap_record(item,event,entities,authorized=True)
                if not result.get('ok'):
                    # All-or-nothing: do not leave an apparently complete partial bootstrap.
                    raise ValueError('Admission rejected seed item '+item['key']+': '+result.get('error','validation failed'))
                identity=result['record_id'];kind=result['kind'];record=self.s._find(identity)[1]
                state={'content_hash':content,'record_id':identity,'record_version':record['version'],'kind':kind,'seed_hash':fingerprint}
                self._put(ledger,state)
                report['items'].append({**outcome,**state,'decision':result['decision']})
                report['counts'][kind]=report['counts'].get(kind,0)+1
                if result['decision'] in {'duplicate','reinforce'}:report['deduplicated']+=1
                else:report['admitted']+=1
                if result['decision']=='contradict':report['requires_review']+=1
            # Persist audit metadata, never the complete seed or manifest.
            self._put(key,report)
            self._put('bootstrap:import:'+source+':'+fingerprint,report)
            self.s.record_event('memory.bootstrap.imported',{k:report[k] for k in
                ('source_key','seed_hash','plan_hash','importer_version','proposed','admitted','deduplicated','rejected','requires_review')},
                source_type='bootstrap_seed',source_id=source+':'+fingerprint)
            return report

    def _event(self,seed,plan,item,category):
        return self.s.record_event('seed.'+category,dict(source_path=str(seed),seed_hash=plan['seed_sha256'],
            importer_version=VERSION,section=item['section'],quote=item['quote'],item_key=item['key'],
            temporal=item.get('temporal','historical'),source_occurred_at=None,
            authority='historical_user_context',requires_verification=True),source_type='bootstrap_seed',
            source_id=plan['source_key']+':'+category+':'+item['key']+':'+plan['seed_sha256'])
