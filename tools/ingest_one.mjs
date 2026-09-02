#!/usr/bin/env node
// Ingest ONE uploaded workbook into an existing stockwise.db, then re-run
// matching (pending rows only), derived tables, and calc. Used by the live
// upload path (stockwise/ingest.py shells out to this).
//
//   node --experimental-sqlite tools/ingest_one.mjs <module> <file.xlsx> [--name "PPB - RI.xlsx"]
//
// Prints a single JSON line as its last line of stdout.

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { openDb, createDb } from './lib/db.mjs';
import { ingestMaster } from './lib/ingest_master.mjs';
import { ingestProcurement } from './lib/ingest_procurement.mjs';
import { ingestNpbg } from './lib/ingest_consumption.mjs';
import {
  ingestBorrowLend, ingestStpp, ingestTires, ingestMaintenance,
  ingestManufacturing, ingestUsedReturns,
} from './lib/ingest_tracking.mjs';
import { runMatching, runDerived, runCalc } from './lib/postprocess.mjs';

const ROOT = path.resolve(fileURLToPath(new URL('..', import.meta.url)));
const DB_PATH = process.env.STOCKWISE_DB || path.join(ROOT, 'stockwise.db');
const SCHEMA = path.join(ROOT, 'db', 'schema.sql');

const argv = process.argv.slice(2);
const module = argv[0];
const file = argv[1];
const nameIdx = argv.indexOf('--name');
const displayName = nameIdx >= 0 ? argv[nameIdx + 1] : path.basename(file || '');

const HANDLERS = {
  master: ingestMaster,
  procurement: ingestProcurement,
  npbg: ingestNpbg,
  borrow_lend: ingestBorrowLend,
  stpp: ingestStpp,
  tire: ingestTires,
  asset_maint: ingestMaintenance,
  manufacturing: ingestManufacturing,
  used_returns: ingestUsedReturns,
};

function out(obj) { process.stdout.write('\n' + JSON.stringify(obj) + '\n'); }

if (!module || !file || !HANDLERS[module]) {
  out({ ok: false, error: `usage: ingest_one.mjs <${Object.keys(HANDLERS).join('|')}> <file.xlsx>` });
  process.exit(1);
}
if (!fs.existsSync(file)) { out({ ok: false, error: `file not found: ${file}` }); process.exit(1); }

const db = fs.existsSync(DB_PATH) ? openDb(DB_PATH) : createDb(DB_PATH, SCHEMA);
db.exec("PRAGMA foreign_keys = ON");

try {
  const t0 = Date.now();
  // rename the physical temp file so lineage shows the real workbook name
  const named = path.join(path.dirname(file), displayName.replace(/[\\/:*?"<>|]/g, '_'));
  let target = file;
  if (named !== file && !fs.existsSync(named)) { fs.copyFileSync(file, named); target = named; }

  const before = tableCounts(db);
  HANDLERS[module](db, target);
  const match = runMatching(db, { onlyPending: true });
  runDerived(db);
  const calc = runCalc(db);
  const after = tableCounts(db);

  if (target !== file) fs.rmSync(target, { force: true });

  const delta = {};
  for (const k of Object.keys(after)) if (after[k] !== (before[k] || 0)) delta[k] = after[k] - (before[k] || 0);
  const batches = db.prepare(
    `SELECT module, total_rows, inserted, duplicate, need_review FROM upload_batches
     WHERE id > (SELECT COALESCE(MAX(id),0) FROM upload_batches) - ? ORDER BY id`,
  ).all(20);
  const lastBatches = db.prepare(
    `SELECT module, total_rows total, inserted, duplicate, need_review FROM upload_batches ORDER BY id DESC LIMIT ?`,
  ).all(module === 'master' ? 2 : 4);

  const totalInserted = lastBatches.reduce((a, b) => a + (b.inserted || 0), 0);
  const totalDup = lastBatches.reduce((a, b) => a + (b.duplicate || 0), 0);
  const totalRows = lastBatches.reduce((a, b) => a + (b.total || 0), 0);
  const matchedNew = Object.values(match).reduce((a, s) => a + (s.MATCHED || 0), 0);
  const needReview = db.prepare(
    `SELECT COUNT(DISTINCT source_table||source_row_id) c FROM matching_reviews WHERE decision='PENDING'`,
  ).get().c;

  out({
    ok: true,
    module, file: displayName, seconds: +((Date.now() - t0) / 1000).toFixed(1),
    summary: {
      total: totalRows, inserted: totalInserted, duplicate: totalDup,
      matched: matchedNew, need_review: needReview,
      calc_run: calc.runId, row_delta: delta, batches: lastBatches,
    },
  });
} catch (e) {
  out({ ok: false, error: String(e && e.stack || e) });
  process.exit(1);
} finally {
  db.close();
}

function tableCounts(db) {
  const names = db.prepare(`SELECT name FROM sqlite_master WHERE type='table'`).all().map((r) => r.name);
  const o = {};
  for (const n of names) { try { o[n] = db.prepare(`SELECT COUNT(*) c FROM ${n}`).get().c; } catch {} }
  return o;
}
