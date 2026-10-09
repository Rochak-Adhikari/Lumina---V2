"""Compatibility facade over the canonical continuity engine."""
from pathlib import Path
import os
import re
import secrets
import time
from .continuity.service import MemoryService
from .continuity.policy import text as checked_text, now

CATEGORIES = {'working', 'episodic', 'semantic', 'procedural', 'preference', 'project', 'journal'}


class MemoryStore(MemoryService):
    def __init__(self, path=None):
        if path in (None, ''):
            path = os.environ.get('LUMINA_MEMORY_PATH') or Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local')) / 'LUMINA' / 'memory.sqlite3'
        super().__init__(path)

    @staticmethod
    def _text(value):
        return checked_text(value)

    @staticmethod
    def _category(category):
        if category not in CATEGORIES:
            raise ValueError('That memory category is unavailable.')
        return category

    def remember(self, text, category='working', *, authorized=False):
        if authorized is not True:
            raise PermissionError('Saving memory requires your instruction.')
        text, category = self._text(text), self._category(category)
        privacy='sensitive' if category=='journal' else 'private'
        with self.repo.transaction():
            stamp=time.time()
            cur=self.db.execute('INSERT INTO memories(category,text,created,updated) VALUES(?,?,?,?)',(category,text,stamp,stamp))
            legacy_id=cur.lastrowid
            event=self.repo.get('events',self.last_user_event_id) if self.last_user_event_id else None
            if not event or event['source_type']!='user' or privacy=='sensitive':
                event=self.record_event('conversation.message',{'role':'user','text':text,'_privacy_class':privacy},source_type='user')
            # Only parse explicit preference syntax; arbitrary notes stay unparsed.
            preference=re.fullmatch(r'I prefer (.+?)[.!]?',text,re.I)
            predicate='prefers' if preference else 'saved_note:'+str(legacy_id)
            value=preference[1] if preference else text
            result=self.propose(dict(kind='fact',subject=self.user_id,predicate=predicate,object=value,
                source_event_id=event['id'],privacy_class=privacy,
                data={'cardinality':'multiple'} if preference else {}),authorized=True)
            if not result.get('ok'):
                # The legacy row must not claim success after failed admission.
                raise ValueError(result.get('error','Memory admission failed.'))
            self.db.execute('INSERT INTO legacy_memory_map(legacy_id,record_id) VALUES(?,?)',(legacy_id,result['record_id']))
            return {'ok':True,'id':legacy_id,'category':category,'record_id':result['record_id'],'decision':result['decision']}

    def search(self, query, *, include_journal=False, limit=20):
        query=self._text(query);limit=max(1,min(int(limit),50))
        clauses=['m.deleted IS NULL', 'm.text LIKE ?', "f.status IN ('active','disputed')", 'f.valid_until IS NULL']
        if not include_journal:clauses.append("m.category<>'journal' AND f.privacy_class<>'sensitive'")
        rows=self.repo.rows("SELECT m.id,m.category,m.text,m.created,m.updated FROM memories m JOIN legacy_memory_map l ON l.legacy_id=m.id JOIN facts f ON f.id=l.record_id WHERE "+' AND '.join(clauses)+' ORDER BY m.updated DESC LIMIT ?',(f'%{query}%',limit+1))
        return {'ok':True,'count':len(rows[:limit]),'total':len(rows[:limit]),'truncated':len(rows)>limit,'matches':rows[:limit]}

    def request_delete(self, memory_id):
        try:memory_id=int(memory_id)
        except (TypeError,ValueError):raise ValueError('That memory identifier is invalid.') from None
        rows=self.repo.rows('SELECT m.id,m.category,f.id record_id,f.version FROM memories m JOIN legacy_memory_map l ON l.legacy_id=m.id JOIN facts f ON f.id=l.record_id WHERE m.id=? AND m.deleted IS NULL',(memory_id,))
        if not rows:return {'ok':False,'error':'That memory is unavailable.'}
        token=secrets.token_urlsafe(24)
        self.pending[token]={**rows[0],'expires':time.monotonic()+60}
        return {'ok':False,'confirmation_required':True,'confirmation_id':token,'id':memory_id,'category':rows[0]['category'],
                'message':'Remove this saved note from current memory? History is retained; permanent erasure is a separate action.'}

    def confirm_delete(self, token, *, authorized=False):
        if authorized is not True:raise PermissionError('Deleting memory requires your instruction.')
        pending=self.pending.pop(token,None)
        if pending is None or time.monotonic()>pending['expires']:
            return {'ok':False,'error':'That confirmation is no longer valid.'}
        with self.repo.transaction():
            row=self.repo.get('facts',pending['record_id'])
            if not row or row['version']!=pending['version']:
                return {'ok':False,'error':'That memory changed; confirm again.'}
            result=self.forget(row['id'],authorized=True)
            if not result.get('ok'):return result
            stamp=time.time()
            self.db.execute('UPDATE memories SET deleted=?,updated=? WHERE id=?',(stamp,stamp,pending['id']))
        return {'ok':True,'id':pending['id'],'message':'The note was removed from current memory.'}

    def restore(self, memory_id, *, authorized=False):
        if authorized is not True:raise PermissionError('Restoring memory requires your instruction.')
        with self.repo.transaction():
            rows=self.repo.rows('SELECT l.record_id,m.* FROM legacy_memory_map l JOIN memories m ON m.id=l.legacy_id WHERE m.id=?',(int(memory_id),))
            if not rows:return {'ok':False,'error':'That saved note is unavailable.'}
            row=rows[0];previous=self.repo.get('facts',row['record_id'])
            if not previous or previous['status']!='invalidated':
                return {'ok':False,'error':'Only a removed saved note can be restored.'}
            event=self.record_event('conversation.message',{'role':'user','text':row['text'],'_privacy_class':previous['privacy_class']},source_type='user')
            # Restoration begins a new validity interval, preserving the deletion gap.
            result=self.propose(dict(kind='fact',subject=previous['subject_entity_id'],predicate=previous['predicate'],object=previous['object_value'],
                source_event_id=event['id'],privacy_class=previous['privacy_class']),authorized=True)
            if not result.get('ok'):return result
            self.db.execute('UPDATE legacy_memory_map SET record_id=? WHERE legacy_id=?',(result['record_id'],int(memory_id)))
            self.db.execute('UPDATE memories SET deleted=NULL,updated=? WHERE id=?',(time.time(),int(memory_id)))
        return {'ok':True,'id':int(memory_id)}


class UnavailableMemory:
    device_id=None
    last_user_event_id=None
    path=None
    def status(self):
        return {'ok':False,'status':'unavailable','error':'Memory storage is unavailable. No save was confirmed.'}
    def close(self):pass
    def __getattr__(self,name):
        if name.startswith('_'):raise AttributeError(name)
        return lambda *args,**kwargs:self.status()
