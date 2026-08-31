#!/usr/bin/env python3
from __future__ import annotations
import json, sqlite3, hashlib, os, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
RUNS=ROOT/'evidence'/'fault_injection'/'runs'
OUT=ROOT/'evidence'/'fault_injection'
DB=OUT/'frontier_relational_smoke.sqlite3'
if DB.exists(): DB.unlink()

sources=['ctg','medrxiv','pubmed']
rows_by_table={}
for src in sources:
    wh=RUNS/src/'warehouse'
    for p in wh.glob('*.jsonl'):
        table=p.stem
        for line in p.read_text(encoding='utf-8').splitlines():
            if line.strip(): rows_by_table.setdefault(table,[]).append(json.loads(line))

pk={
 'ingestion_run':['run_id'],'run_artifact':['artifact_id'],'source_record':['source_record_key'],
 'source_observation':['run_id','source_record_key'],'canonical_record':['canonical_record_key'],
 'quarantine_record':['quarantine_id'],'ctg_study_record':['canonical_record_key'],
 'ctg_study_snapshot':['run_id','canonical_record_key'],'ctg_phase':['canonical_record_key','phase'],
 'ctg_condition':['canonical_record_key','ordinal'],'ctg_keyword':['canonical_record_key','ordinal'],
 'ctg_sponsor':['canonical_record_key','role','ordinal'],'ctg_arm':['canonical_record_key','ordinal'],
 'ctg_intervention':['canonical_record_key','ordinal'],'ctg_outcome':['canonical_record_key','outcome_type','ordinal'],
 'ctg_location':['canonical_record_key','ordinal'],'ctg_contact':['canonical_record_key','contact_type','ordinal'],
 'ctg_reference':['canonical_record_key','reference_type','ordinal'],'ctg_available_ipd':['canonical_record_key','ordinal'],
 'pubmed_record':['canonical_record_key'],'pubmed_snapshot':['run_id','canonical_record_key'],
 'pubmed_author':['canonical_record_key','ordinal'],'pubmed_mesh_heading':['canonical_record_key','ordinal'],
 'preprint_record':['canonical_record_key'],'preprint_snapshot':['run_id','canonical_record_key'],
 'drug_source_record':['source_record_key'],'drug_entity':['drug_entity_key'],'drug_alias':['drug_entity_key','alias','source'],
 'drug_linkage_evidence':['linkage_evidence_key'],
}
# Only create tables actually emitted in this smoke run.
all_tables=sorted(rows_by_table)
cols_by_table={t:sorted({k for r in rows_by_table[t] for k in r}) for t in all_tables}

def sql_type(values):
    scalar=[v for v in values if v is not None and not isinstance(v,(dict,list))]
    if scalar and all(isinstance(v,bool) for v in scalar): return 'INTEGER'
    if scalar and all(isinstance(v,int) and not isinstance(v,bool) for v in scalar): return 'INTEGER'
    if scalar and all(isinstance(v,(int,float)) and not isinstance(v,bool) for v in scalar): return 'REAL'
    return 'TEXT'

def q(name): return '"'+name.replace('"','""')+'"'

def enc(v):
    if isinstance(v,(dict,list)): return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False)
    if isinstance(v,bool): return 1 if v else 0
    return v

conn=sqlite3.connect(DB)
conn.execute('PRAGMA foreign_keys=ON')
conn.execute('PRAGMA journal_mode=WAL')

# Create tables first.
for t in all_tables:
    cols=cols_by_table[t]
    defs=[]
    for c in cols:
        vals=[r.get(c) for r in rows_by_table[t]]
        defs.append(f'{q(c)} {sql_type(vals)}')
    pks=[c for c in pk.get(t,[]) if c in cols]
    if pks: defs.append('PRIMARY KEY ('+', '.join(q(c) for c in pks)+')')
    conn.execute(f'CREATE TABLE {q(t)} ('+', '.join(defs)+')')

# Add FK enforcement through triggers because SQLite cannot ALTER TABLE ADD CONSTRAINT after creation.
# This still executes on every insert and catches missing parent lineage.
fks=[]
for t in all_tables:
    cols=set(cols_by_table[t])
    if t!='ingestion_run' and 'run_id' in cols and 'ingestion_run' in all_tables:
        fks.append((t,'run_id','ingestion_run','run_id'))
    if t!='source_record' and 'source_record_key' in cols and 'source_record' in all_tables:
        fks.append((t,'source_record_key','source_record','source_record_key'))
    if t!='canonical_record' and 'canonical_record_key' in cols and 'canonical_record' in all_tables:
        fks.append((t,'canonical_record_key','canonical_record','canonical_record_key'))
for i,(child,cc,parent,pc) in enumerate(fks):
    conn.execute(f'''CREATE TRIGGER fk_{i}_{child}_{cc} BEFORE INSERT ON {q(child)}
    WHEN NEW.{q(cc)} IS NOT NULL AND NOT EXISTS (SELECT 1 FROM {q(parent)} WHERE {q(pc)}=NEW.{q(cc)})
    BEGIN SELECT RAISE(ABORT, 'missing parent {parent}.{pc}'); END;''')

# Dependency order.
priority=['ingestion_run','run_artifact','source_record','source_observation','canonical_record']
ordered=[t for t in priority if t in all_tables]+[t for t in all_tables if t not in priority]
inserted={}
try:
    conn.execute('BEGIN')
    for t in ordered:
        cols=cols_by_table[t]; placeholders=','.join('?' for _ in cols)
        sql=f'INSERT INTO {q(t)} ('+', '.join(q(c) for c in cols)+f') VALUES ({placeholders})'
        for r in rows_by_table[t]: conn.execute(sql,[enc(r.get(c)) for c in cols])
        inserted[t]=len(rows_by_table[t])
    conn.commit()
except Exception:
    conn.rollback(); raise

# Verify counts and FK trigger list.
for t,n in inserted.items():
    actual=conn.execute(f'SELECT COUNT(*) FROM {q(t)}').fetchone()[0]
    if actual!=n: raise RuntimeError(f'{t} count mismatch {actual}!={n}')

# Deliberately prove FK enforcement by trying an invalid canonical record child.
if 'ctg_phase' in all_tables:
    cols=cols_by_table['ctg_phase']; fake={c:None for c in cols}; fake['canonical_record_key']='missing-parent'; fake['phase']='PHASE3'
    try:
        conn.execute('BEGIN')
        sql='INSERT INTO ctg_phase ('+', '.join(q(c) for c in cols)+') VALUES ('+','.join('?' for _ in cols)+')'
        conn.execute(sql,[enc(fake.get(c)) for c in cols]); conn.commit(); fk_enforced=False
    except sqlite3.IntegrityError:
        conn.rollback(); fk_enforced=True
else: fk_enforced=False
if not fk_enforced: raise RuntimeError('relational FK enforcement proof failed')

conn.execute('PRAGMA wal_checkpoint(FULL)')
conn.close()
h=hashlib.sha256(DB.read_bytes()).hexdigest()
report={
 'evidence_schema_version':'frontier-relational-smoke-1.0','status':'PASS','engine':'sqlite3',
 'target_database_certification':False,'note':'Executable transactional relational smoke test only; does not certify PostgreSQL or BigQuery.',
 'database_path':str(DB.relative_to(ROOT)),'database_sha256':h,'tables_loaded':len(inserted),
 'rows_loaded':sum(inserted.values()),'rows_by_table':inserted,'foreign_key_negative_test':'PASS',
}
(OUT/'RELATIONAL_SMOKE.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n',encoding='utf-8')
(OUT/'RELATIONAL_SMOKE.txt').write_text(f"RELATIONAL SMOKE: PASS\nENGINE: sqlite3\nTABLES: {len(inserted)}\nROWS: {sum(inserted.values())}\nFK NEGATIVE TEST: PASS\nTARGET POSTGRES/BIGQUERY CERTIFICATION: FALSE\nDB SHA256: {h}\n",encoding='utf-8')
print((OUT/'RELATIONAL_SMOKE.txt').read_text())
