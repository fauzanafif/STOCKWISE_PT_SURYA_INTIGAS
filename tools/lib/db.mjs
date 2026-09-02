import { DatabaseSync } from 'node:sqlite';
import fs from 'node:fs';
import path from 'node:path';

export function createDb(dbPath, schemaPath) {
  for (const f of [dbPath, dbPath + '-wal', dbPath + '-shm']) {
    if (fs.existsSync(f)) fs.rmSync(f);
  }
  const db = new DatabaseSync(dbPath);
  db.exec(fs.readFileSync(schemaPath, 'utf8'));
  return db;
}

export function openDb(dbPath) {
  return new DatabaseSync(dbPath);
}

// Prepared-statement cache — node:sqlite recompiles on every .prepare(), which
// is the single biggest perf sink in a bulk ingest. Key on the exact SQL text.
const _stmt = new WeakMap();
function prep(db, sql) {
  let m = _stmt.get(db);
  if (!m) { m = new Map(); _stmt.set(db, m); }
  let s = m.get(sql);
  if (!s) { s = db.prepare(sql); m.set(sql, s); }
  return s;
}

/** insert one row from an object; returns lastInsertRowid */
export function insert(db, table, obj) {
  const keys = Object.keys(obj);
  const sql = `INSERT INTO ${table} (${keys.map(q).join(',')}) VALUES (${keys.map(() => '?').join(',')})`;
  const info = prep(db, sql).run(...keys.map((k) => norm(obj[k])));
  return info.lastInsertRowid;
}

/** insert, ignoring UNIQUE conflicts; returns {inserted: bool} */
export function insertOrIgnore(db, table, obj) {
  const keys = Object.keys(obj);
  const sql = `INSERT OR IGNORE INTO ${table} (${keys.map(q).join(',')}) VALUES (${keys.map(() => '?').join(',')})`;
  const info = prep(db, sql).run(...keys.map((k) => norm(obj[k])));
  return { inserted: info.changes > 0, id: info.lastInsertRowid };
}

const q = (k) => `"${k}"`;
function norm(v) {
  if (v === undefined || v === null) return null;
  if (typeof v === 'boolean') return v ? 1 : 0;
  if (v instanceof Date) return v.toISOString();
  return v;
}

export function newBatch(db, { filename, module, source_mtime, notes = null }) {
  // one row per processing event — re-uploading the same file monthly is expected;
  // row-level dedup happens via row_hash, not here.
  const batch_uid = `${module}:${filename}:${source_mtime || ''}:${Date.now()}:${Math.random().toString(36).slice(2, 7)}`;
  const id = insert(db, 'upload_batches', { batch_uid, filename, module, source_mtime, notes });
  return id;
}

export function finishBatch(db, id, stats) {
  db.prepare(`UPDATE upload_batches SET total_rows=?, inserted=?, updated=?, duplicate=?, invalid=?, need_review=?, status=? WHERE id=?`)
    .run(stats.total || 0, stats.inserted || 0, stats.updated || 0, stats.duplicate || 0, stats.invalid || 0, stats.need_review || 0, stats.status || 'OK', id);
}

export function note(db, batchId, scope, message) {
  insert(db, 'import_notes', { upload_batch_id: batchId, scope, message });
}

export function mtimeOf(file) {
  try { return fs.statSync(file).mtime.toISOString(); } catch { return null; }
}
