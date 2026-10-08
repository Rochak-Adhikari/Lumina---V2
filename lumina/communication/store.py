import json
import sqlite3


class Inbox:
    def __init__(self,path):
        path.parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(path)
        self.db.execute('CREATE TABLE IF NOT EXISTS messages(provider TEXT,id TEXT,destination TEXT,body TEXT,PRIMARY KEY(provider,id))')
        self.db.execute('CREATE TABLE IF NOT EXISTS cursors(provider TEXT PRIMARY KEY,value INTEGER)')
    def offset(self,provider):
        row=self.db.execute('SELECT value FROM cursors WHERE provider=?',(provider,)).fetchone()
        return row[0] if row else 0
    def save(self,provider,messages,offset=None):
        with self.db:
            for m in messages:self.db.execute('INSERT OR REPLACE INTO messages VALUES(?,?,?,?)',(provider,str(m['id']),str(m['destination']),json.dumps(m)))
            if offset is not None:self.db.execute('INSERT OR REPLACE INTO cursors VALUES(?,?)',(provider,offset))
            self.db.execute('DELETE FROM messages WHERE provider=? AND rowid NOT IN (SELECT rowid FROM messages WHERE provider=? ORDER BY rowid DESC LIMIT 500)',(provider,provider))
    def read(self,provider,destination='',query=''):
        rows=self.db.execute('SELECT body FROM messages WHERE provider=? ORDER BY rowid DESC LIMIT 500',(provider,)).fetchall()
        return [m for (body,) in rows if (m:=json.loads(body)) and (not destination or str(m['destination'])==destination) and query.casefold() in m.get('content','').casefold()][:50]
    def get(self,provider,message_id):
        row=self.db.execute('SELECT body FROM messages WHERE provider=? AND id=?',(provider,message_id)).fetchone()
        return json.loads(row[0]) if row else None
    def close(self):self.db.close()
