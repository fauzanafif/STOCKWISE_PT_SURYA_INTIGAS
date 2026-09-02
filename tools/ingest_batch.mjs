#!/usr/bin/env node
// Ingest MANY workbooks in one shot: auto-detect each file's module, ingest in the
// right order (master first), then run matching + derived + calc ONCE at the end.
//
//   node --experimental-sqlite tools/ingest_batch.mjs <file1.xlsx> <file2.xlsx> ...
//   node --experimental-sqlite tools/ingest_batch.mjs --dir DATAFIX
//
// Each --name pair (repeatable) overrides the display name of the Nth positional file:
//   ... file1 file2 --names "1. PPB - RI.xlsx" "2. NPBG.xlsx"
//
// Prints one JSON line last.

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { openDb, createDb } from './lib/db.mjs';
import { detectModule, MODULE_ORDER } from './lib/detect_module.mjs';
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

const HANDLERS = {
  master: ingestMaster, procurement: ingestProcurement, npbg: ingestNpbg,
  borrow_lend: ingestBorrowLend, stpp: ingestStpp, tire: ingestTires,
  asset_maint: ingestMaintenance, manufacturing: ingestManufacturing, used_returns: ingestUsedReturns,
};

const out = (o) => process.stdout.write('\n' + JSON.stringify(o) + '\n');

// ── parse args ──
const argv = process.argv.slice(2);
let files = [];
const names = [];
for (let i = 0; i < argv.length; i++) {
  const a = argv[i];
  if (a === '--dir') {
    const d = argv[++i];
    files.push(...fs.readdirSync(d).filter((f) => /\.xlsx?$/i.test(f)).map((f) => path.join(d, f)));
  } else if (a === '--names') {
    while (i + 1 < argv.length && !argv[i + 1].startsWith('--')) names.push(argv[++i]);
  } else {
    files.push(a);
  }
}
files = files.filter((f) => fs.existsSync(f));
if (!files.length) { out({ ok: false, error: 'no files' }); process.exit(1); }

// ── detect + rename to real workbook name for lineage ──
const plan = [];
const tmpCopies = [];
files.forEach((f, idx) => {
  const display = names[idx] || path.basename(f);
  const { module, confidence } = detectModule(f);
  let target = f;
  const wanted = path.join(path.dirname(f), display.replace(/[\\/:*?"<>|]/g, '_'));
  if (wanted !== f && !fs.existsSync(wanted)) { fs.copyFileSync(f, wanted); target = wanted; tmpCopies.push(wanted); }
  plan.push({ file: target, display, module, confidence });
});

const known = plan.filter((p) => p.module && HANDLERS[p.module]);
const unknown = plan.filter((p) => !p.module || !HANDLERS[p.module]);
known.sort((a, b) => MODULE_ORDER.indexOf(a.module) - MODULE_ORDER.indexOf(b.module));

const db = fs.existsSync(DB_PATH) ? openDb(DB_PATH) : createDb(DB_PATH, SCHEMA);
db.exec('PRAGMA foreign_keys = ON');

const t0 = Date.now();
const results = [];
try {
  const maxBatchBefore = db.prepare('SELECT COALESCE(MAX(id),0) m FROM upload_batches').get().m;
  for (const p of known) {
    const s = Date.now();
    try {
      HANDLERS[p.module](db, p.file);
      results.push({ file: p.display, module: p.module, confidence: p.confidence, ok: true, seconds: +((Date.now() - s) / 1000).toFixed(1) });
    } catch (e) {
      results.push({ file: p.display, module: p.module, ok: false, error: String(e && e.message || e) });
    }
  }
  const match = runMatching(db, { onlyPending: true });
  runDerived(db);
  const calc = runCalc(db);

  for (const f of tmpCopies) { try { fs.rmSync(f, { force: true }); } catch {} }

  const myBatches = db.prepare(
    'SELECT module, total_rows total, inserted, duplicate FROM upload_batches WHERE id > ? ORDER BY id',
  ).all(maxBatchBefore);
  const pending = db.prepare(
    "SELECT COUNT(DISTINCT source_table||source_row_id) c FROM matching_reviews WHERE decision='PENDING' AND candidate_item_id IS NOT NULL",
  ).get().c;
  const ssConf = db.prepare("SELECT COUNT(*) c FROM safety_stock_params WHERE dq_flag='SS_CONFLICT'").get().c;

  out({
    ok: results.every((r) => r.ok),
    seconds: +((Date.now() - t0) / 1000).toFixed(1),
    files: results,
    unknown: unknown.map((u) => u.display),
    summary: {
      inserted: myBatches.reduce((a, b) => a + (b.inserted || 0), 0),
      duplicate: myBatches.reduce((a, b) => a + (b.duplicate || 0), 0),
      matched_new: Object.values(match).reduce((a, s) => a + (s.MATCHED || 0), 0),
      need_review: pending,
      ss_conflicts: ssConf,
      calc_run: calc.runId,
      batches: myBatches,
    },
  });
} catch (e) {
  out({ ok: false, error: String(e && e.stack || e) });
  process.exit(1);
} finally {
  db.close();
}
