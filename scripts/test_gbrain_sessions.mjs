import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { DatabaseSync } from 'node:sqlite';
import { zstdCompressSync } from 'node:zlib';
import { createHash } from 'node:crypto';
import { checkpoint, recordsForStore, makePages, writePages, renderEvent, coldRows } from './gbrain_sessions_export.mjs';

function fixture() {
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'gbrain-future-test-'));
  const file=path.join(root,'agent.sqlite');
  const db=new DatabaseSync(file);
  db.exec(`CREATE TABLE session_windows(session_id TEXT PRIMARY KEY,session_key TEXT,created_at INTEGER,session_scope TEXT);
    CREATE TABLE transcript_events(session_id TEXT,seq INTEGER,event_json TEXT,event_zstd BLOB,event_utf8_bytes INTEGER,created_at INTEGER);
    CREATE TABLE transcript_event_identities(event_id TEXT);
    CREATE TABLE session_transcript_cold_archives(session_id TEXT,generation TEXT,archive_name TEXT,archive_sha256 TEXT,event_count INTEGER,raw_bytes INTEGER,archive_bytes INTEGER,last_seq INTEGER,archived_at INTEGER,storage TEXT,archive_blob BLOB);
    INSERT INTO session_windows VALUES('existing','agent:main:existing',1000,'conversation');`);
  const add=(session,id,seq,text,created,compressed=false)=>{
    const event={type:'message',id,timestamp:new Date(created).toISOString(),message:{role:'user',content:text}};
    const json=JSON.stringify(event);
    db.prepare('INSERT INTO transcript_events VALUES(?,?,?,?,?,?)').run(session,seq,compressed?null:json,
      compressed?zstdCompressSync(Buffer.from(json)):null,compressed?Buffer.byteLength(json):null,created);
    db.prepare('INSERT INTO transcript_event_identities VALUES(?)').run(id);
  };
  return {root,file,db,add,close:()=>{db.close();fs.rmSync(root,{recursive:true,force:true});}};
}

test('checkpoint excludes old messages but includes future turns in existing and new sessions',()=>{
  const f=fixture();
  try {
    f.add('existing','old',1,'OLD PRIVATE TEXT',1000);
    const boundary=checkpoint({main:f.file},()=>2000);
    assert(!JSON.stringify(boundary).includes('OLD PRIVATE TEXT'));
    f.add('existing','future',2,'future on existing session',3000,true);
    f.db.exec("INSERT INTO session_windows VALUES('new','agent:main:new',3000,'conversation')");
    f.add('new','new-id',1,'new session',3000);
    f.add('new','old',2,'copied pre-checkpoint message',4000);
    const before=f.db.prepare('SELECT count(*) AS n FROM transcript_events').get().n;
    const records=recordsForStore(f.file,'main',boundary).records;
    assert.deepEqual(records.map(r=>r.id),['future','new-id']);
    assert.equal(f.db.prepare('SELECT count(*) AS n FROM transcript_events').get().n,before);
  } finally {f.close();}
});

test('long Unicode messages survive page splitting and the supplied redactor runs before writes',()=>{
  const f=fixture();
  try {
    const boundary=checkpoint({main:f.file},()=>2000);
    const body='A'.repeat(23999)+'🌍'+'B'.repeat(55000)+' credentials: fake-secret-value tail-end';
    f.add('existing','long',1,body,3000,true);
    const records=recordsForStore(f.file,'main',boundary).records;
    const pages=makePages(records,'main',boundary,text=>text.replaceAll('fake-secret-value','[REDACTED]'));
    const all=Object.values(pages).join('');
    assert(Object.keys(pages).length>1);
    assert(all.includes('🌍')); assert(all.includes('tail-end'));
    assert.equal((all.match(/B/g)||[]).length,55000);
    assert(!all.includes('fake-secret-value'));
    writePages(f.root,'main',pages);
    assert.equal(fs.statSync(path.join(f.root,'sources/main',Object.keys(pages)[0])).mode & 0o777,0o600);
    assert.equal(writePages(f.root,'main',pages),0);
    writePages(f.root,'main',{});
    assert(!fs.readdirSync(path.join(f.root,'sources/main')).some(x=>x.endsWith('.md')));
  } finally {f.close();}
});

test('editing and deleting native records changes the derived archive',()=>{
  const f=fixture();
  try {
    const boundary=checkpoint({main:f.file},()=>2000);
    f.add('existing','future',1,'initial wording',3000);
    const record=JSON.parse(f.db.prepare('SELECT event_json FROM transcript_events').get().event_json);
    record.message.content='corrected wording';
    f.db.prepare('UPDATE transcript_events SET event_json=?').run(JSON.stringify(record));
    assert.equal(recordsForStore(f.file,'main',boundary).records[0].text,'corrected wording');
    f.db.exec('DELETE FROM transcript_events; DELETE FROM session_windows');
    assert.deepEqual(recordsForStore(f.file,'main',boundary).records,[]);
  } finally {f.close();}
});

test('cold SQLite archives are verified and decoded without restoring or changing OpenClaw',()=>{
  const event=JSON.stringify({type:'message',id:'cold-id',message:{role:'user',content:'cold future text'}});
  const records=[{kind:'header',version:1,sessionId:'cold',generation:'gen'},
    {kind:'event',row:{seq:1,event_json:event,created_at:3000}}];
  const bytes=zstdCompressSync(Buffer.from(records.map(x=>JSON.stringify(x)).join('\n')));
  const archive={storage:'sqlite',archive_blob:bytes,archive_name:'a'.repeat(64)+'.jsonl.zst',
    archive_bytes:bytes.length,archive_sha256:createHash('sha256').update(bytes).digest('hex'),
    session_id:'cold',generation:'gen',event_count:1,last_seq:1};
  assert.equal(coldRows('/unused/agent/db.sqlite',archive)[0].event_json,event);
  assert.throws(()=>coldRows('/unused/agent/db.sqlite',{...archive,archive_sha256:'wrong'}));
});

test('tool evidence is retained; memory echoes and hidden reasoning are not recursively archived',()=>{
  assert.equal(renderEvent({type:'message',message:{role:'assistant',channel:'analysis',content:'private reasoning'}}),null);
  assert.equal(renderEvent({type:'message',message:{role:'assistant',content:[
    {type:'thinking',thinking:'private reasoning'},{type:'text',text:'visible reply'}]}}).text,'visible reply');
  assert(!renderEvent({type:'message',message:{role:'toolResult',toolName:'gbrain_history_main__search',
    content:[{type:'text',text:'duplicate memory contents'}]}}).text.includes('duplicate memory contents'));
  assert.equal(renderEvent({type:'message',message:{role:'toolResult',toolName:'exec',
    content:[{type:'text',text:'test output'}]}}).text,'test output');
});

test('export refuses symlink destinations without overwriting other files',()=>{
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'gbrain-link-test-'));
  try {
    const outside=path.join(root,'outside'); fs.mkdirSync(outside);
    fs.mkdirSync(path.join(root,'sources'));
    fs.symlinkSync(outside,path.join(root,'sources/main'));
    assert.throws(()=>writePages(root,'main',{'example.md':'must not write'}));
    assert.deepEqual(fs.readdirSync(outside),[]);
  } finally {fs.rmSync(root,{recursive:true,force:true});}
});
