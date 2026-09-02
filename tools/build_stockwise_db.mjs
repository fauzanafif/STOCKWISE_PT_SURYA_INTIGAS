#!/usr/bin/env node
// Bootstrap / verification tool: build stockwise.db from every workbook in DATAFIX/,
// run the matcher + calc engine, and write AUDIT/03_ingest_report.md.
//
//   node --experimental-sqlite tools/build_stockwise_db.mjs [--datafix DIR] [--out FILE]
//
// This is the reference implementation of the ingest contract. stockwise/ (Python)
// mirrors it for the live app; both write the identical schema (db/schema.sql).

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createDb } from './lib/db.mjs';
import { ingestMaster } from './lib/ingest_master.mjs';
import { ingestProcurement } from './lib/ingest_procurement.mjs';
import { ingestNpbg } from './lib/ingest_consumption.mjs';
import {
  ingestBorrowLend, ingestStpp, ingestTires, ingestMaintenance,
  ingestManufacturing, ingestUsedReturns,
} from './lib/ingest_tracking.mjs';
import { runMatching, runDerived, runCalc } from './lib/postprocess.mjs';

const ROOT = path.resolve(fileURLToPath(new URL('..', import.meta.url)));
const argv = process.argv.slice(2);
const args = {};
for (let i = 0; i < argv.length; i++) if (argv[i].startsWith('--')) args[argv[i].slice(2)] = argv[i + 1];
const DATAFIX = path.resolve(args.datafix || path.join(ROOT, 'DATAFIX'));
const OUT = path.resolve(args.out || path.join(ROOT, 'stockwise.db'));
const SCHEMA = path.join(ROOT, 'db', 'schema.sql');

const F = (name) => {
  const p = path.join(DATAFIX, name);
  if (!fs.existsSync(p)) throw new Error(`missing file: ${p}`);
  return p;
};

const t0 = Date.now();
console.log(`DATAFIX = ${DATAFIX}\nOUT     = ${OUT}\n`);
const db = createDb(OUT, SCHEMA);

const summary = {};
step('master', () => (summary.master = ingestMaster(db, F('DATA.xlsx'))));
step('procurement', () => (summary.proc = ingestProcurement(db, F('1. PPB - RI.xlsx'))));
step('npbg', () => (summary.npbg = ingestNpbg(db, F('2. NPBG.xlsx'))));
step('borrow/lend', () => (summary.bl = ingestBorrowLend(db, F('3. Tracking Borrow & Lend.xlsx'))));
step('stpp', () => (summary.stpp = ingestStpp(db, F('4. Tracking STPP.xlsx'))));
step('tires', () => (summary.tire = ingestTires(db, F('5. Tracking Ban Luar.xlsx'))));
step('maintenance', () => (summary.maint = ingestMaintenance(db, F('6. Tracking Maintenance Assets.xlsx'))));
step('manufacturing', () => (summary.mfg = ingestManufacturing(db, F('7. Tracking Manufaktur & Assembly.xlsx'))));
step('used returns', () => (summary.ur = ingestUsedReturns(db, F('8. Tracking Pengembalian Bekas.xlsx'))));

// ── matching ──
step('matching', () => {
  const masters = db.prepare(`SELECT id, kode_barang, deskripsi, deskripsi_norm, deskripsi_core FROM master_items`).all();
  const idx = buildMasterIndex(masters);
  const cache = new Map();
  const doResolve = (desc) => {
    if (cache.has(desc)) return cache.get(desc);
    const r = resolve(idx, desc);
    cache.set(desc, r);
    return r;
  };
  const targets = [
    ['ppb_lines', 'deskripsi'], ['ppb_changes', 'deskripsi'], ['ri_lines', 'deskripsi'],
    ['npbg_lines', 'deskripsi'], ['borrow_lend', 'deskripsi'], ['stpp', 'deskripsi'],
    ['tire_transactions', 'deskripsi_ban_baru'], ['manufacturing', 'hasil_produk'],
    ['used_returns', 'deskripsi'],
  ];
  const stats = {};
  for (const [table, col] of targets) {
    const rows = db.prepare(`SELECT id, ${col} AS d FROM ${table} WHERE ${col} IS NOT NULL`).all();
    const upd = db.prepare(`UPDATE ${table} SET master_item_id = ?, match_status = ? WHERE id = ?`);
    const rev = db.prepare(`INSERT OR IGNORE INTO matching_reviews
      (source_table, source_row_id, source_desc, source_desc_norm, candidate_item_id, candidate_desc, confidence, method, decision)
      VALUES (?,?,?,?,?,?,?,?, 'PENDING')`);
    const s = { MATCHED: 0, POSSIBLE_MATCH: 0, NEED_REVIEW: 0, NEW_ITEM: 0 };
    db.exec('BEGIN');
    for (const row of rows) {
      const res = doResolve(row.d);
      upd.run(res.master_item_id, res.status, row.id);
      s[res.status] = (s[res.status] || 0) + 1;
      if (res.status !== 'MATCHED') {
        for (const c of res.candidates.slice(0, 5)) {
          rev.run(table, row.id, row.d, null, c.id, c.desc, c.confidence, c.method);
        }
        if (!res.candidates.length) rev.run(table, row.id, row.d, null, null, null, 0, res.method || 'NONE');
      }
    }
    db.exec('COMMIT');
    stats[table] = s;
  }
  summary.matching = stats;
});

// ── derived: po_derived, vehicles ──
step('derived', () => {
  db.exec(`
    INSERT INTO po_derived (no_po, vendor, first_ri_date, last_ri_date, ri_count, total_qty)
    SELECT no_po, MAX(vendor), MIN(tgl_ri), MAX(tgl_ri), COUNT(*), SUM(COALESCE(qty,0))
    FROM ri_lines WHERE no_po IS NOT NULL GROUP BY no_po;
  `);
  const vset = new Map();
  for (const [tbl, col, dcol] of [
    ['tire_transactions', 'nopol', 'tgl_npbg'], ['tire_bpn_snapshots', 'nopol', 'tanggal_cut_off'],
    ['tire_deliver_receive', 'nopol', 'tgl_npbg'], ['asset_maintenance', 'nopol', 'tgl_laporan'],
    ['npbg_lines', 'no_seri_nopol', 'tgl_npbg'],
  ]) {
    for (const r of db.prepare(`SELECT ${col} AS n, ${dcol} AS d FROM ${tbl} WHERE ${col} IS NOT NULL`).all()) {
      const n = String(r.n).trim();
      if (!/\b[A-Z]{1,2}\s?\d{2,4}\b/i.test(n)) continue; // looks like a plate
      const cur = vset.get(n) || { first: r.d, last: r.d };
      if (r.d && (!cur.first || r.d < cur.first)) cur.first = r.d;
      if (r.d && (!cur.last || r.d > cur.last)) cur.last = r.d;
      vset.set(n, cur);
    }
  }
  const vi = db.prepare(`INSERT OR IGNORE INTO vehicles (nopol, first_seen, last_seen) VALUES (?,?,?)`);
  db.exec('BEGIN');
  for (const [n, v] of vset) vi.run(n, v.first || null, v.last || null);
  db.exec('COMMIT');
  summary.vehicles = vset.size;
});

step('calc', () => (summary.calc = runCalc(db)));

writeReport();
db.close();
console.log(`\n✓ done in ${((Date.now() - t0) / 1000).toFixed(1)}s → ${OUT}`);

// ────────────────────────────────────────────────────────────────
function step(name, fn) {
  const s = Date.now();
  process.stdout.write(`• ${name} … `);
  try { fn(); console.log(`ok (${((Date.now() - s) / 1000).toFixed(1)}s)`); }
  catch (e) { console.log('FAILED'); console.error(e); process.exitCode = 1; throw e; }
}

function count(sql) { return db.prepare(sql).get().c; }

function writeReport() {
  const L = [];
  const p = (s = '') => L.push(s);
  p(`# STOCKWISE — Laporan Ingest (${new Date().toISOString().slice(0, 16).replace('T', ' ')})`);
  p();
  p(`Dibuat oleh \`tools/build_stockwise_db.mjs\` dari \`DATAFIX/\`. Sumber kebenaran = Excel; \`stockwise.db\` = layer normalized.`);
  p();

  p(`## Ringkасан tabel`);
  p();
  p(`| Tabel | Baris |`);
  p(`|---|--:|`);
  for (const t of ['master_items', 'item_aliases', 'inventory_snapshots', 'safety_stock_params', 'monthly_consumption',
    'ppb_lines', 'ppb_changes', 'ri_lines', 'po_derived', 'npbg_lines', 'borrow_lend', 'stpp',
    'tire_transactions', 'tire_bpn_snapshots', 'tire_deliver_receive', 'asset_maintenance', 'manufacturing',
    'used_returns', 'vehicles', 'matching_reviews', 'calc_results']) {
    p(`| ${t} | ${count(`SELECT COUNT(*) c FROM ${t}`).toLocaleString('id')} |`);
  }
  p();

  p(`## Batch upload`);
  p();
  p(`| Modul | File | Total | Insert | Duplikat | Need review | Status |`);
  p(`|---|---|--:|--:|--:|--:|---|`);
  for (const b of db.prepare(`SELECT module, filename, total_rows, inserted, duplicate, need_review, status FROM upload_batches ORDER BY id`).all()) {
    p(`| ${b.module} | ${b.filename} | ${b.total_rows} | ${b.inserted} | ${b.duplicate} | ${b.need_review} | ${b.status} |`);
  }
  p();

  p(`## Hasil matching (barang transaksi → master)`);
  p();
  p(`| Tabel | MATCHED | POSSIBLE_MATCH | NEED_REVIEW | NEW_ITEM | % matched |`);
  p(`|---|--:|--:|--:|--:|--:|`);
  for (const [t, s] of Object.entries(summary.matching || {})) {
    const tot = s.MATCHED + s.POSSIBLE_MATCH + s.NEED_REVIEW + s.NEW_ITEM;
    p(`| ${t} | ${s.MATCHED} | ${s.POSSIBLE_MATCH} | ${s.NEED_REVIEW} | ${s.NEW_ITEM} | ${tot ? (100 * s.MATCHED / tot).toFixed(0) : 0}% |`);
  }
  p();
  p(`Antrian review (\`matching_reviews.decision = 'PENDING'\`): **${count(`SELECT COUNT(DISTINCT source_table||source_row_id) c FROM matching_reviews WHERE decision='PENDING'`).toLocaleString('id')}** baris transaksi menunggu keputusan manual. Fuzzy tidak pernah auto-match (RULE 8).`);
  p();

  p(`## Kondisi stok (calc run #${summary.calc?.runId}, threshold lead time = ${summary.calc?.threshold} hari [A-5])`);
  p();
  p(`| stock_status | Jumlah item |`);
  p(`|---|--:|`);
  for (const r of db.prepare(`SELECT stock_status s, COUNT(*) c FROM v_inventory GROUP BY stock_status ORDER BY c DESC`).all()) {
    p(`| ${r.s || '(null)'} | ${r.c.toLocaleString('id')} |`);
  }
  p();
  const crit = count(`SELECT COUNT(*) c FROM v_inventory WHERE is_critical = 1`);
  const ssKnown = count(`SELECT COUNT(*) c FROM v_inventory WHERE safety_stock_known = 1`);
  const aman = count(`SELECT COUNT(*) c FROM v_inventory WHERE stock_status = 'AMAN'`);
  p(`- Item CRITICAL: **${crit}**`);
  p(`- Item dengan Safety Stock diketahui: **${ssKnown.toLocaleString('id')}** dari ${count(`SELECT COUNT(*) c FROM master_items`).toLocaleString('id')}`);
  p(`- Skor Kesehatan [A-4] = AMAN / (item ber-SS) = ${ssKnown ? (100 * aman / ssKnown).toFixed(1) : 0}%  *(berdasarkan ${ssKnown.toLocaleString('id')} item)*`);
  p(`- median defisit item TIDAK_AMAN/OUT_OF_STOCK = ${fmt(summary.calc?.median)} · P75 = ${fmt(summary.calc?.p75)}`);
  p();

  p(`## Data quality flags`);
  p();
  for (const r of db.prepare(`SELECT dq_flags f, COUNT(*) c FROM master_items WHERE dq_flags IS NOT NULL GROUP BY dq_flags`).all())
    p(`- master \`${r.f}\`: ${r.c}`);
  p(`- safety_stock_params SS_CONFLICT: ${count(`SELECT COUNT(*) c FROM safety_stock_params WHERE dq_flag='SS_CONFLICT'`)}`);
  p(`- used_returns qty negatif: ${count(`SELECT COUNT(*) c FROM used_returns WHERE qty < 0`)}`);
  p(`- import_errors: ${count(`SELECT COUNT(*) c FROM import_errors`)} (lihat tabel \`import_errors\`)`);
  p();
  p(`## Catatan ingest`);
  p();
  for (const n of db.prepare(`SELECT b.module, i.scope, i.message FROM import_notes i JOIN upload_batches b ON b.id=i.upload_batch_id ORDER BY i.id`).all())
    p(`- **${n.module}** (${n.scope}): ${n.message}`);
  p();

  fs.writeFileSync(path.join(ROOT, 'AUDIT', '03_ingest_report.md'), L.join('\n'));
  console.log('  → AUDIT/03_ingest_report.md');
}
const fmt = (n) => (n === null || n === undefined ? 'n/a' : Math.round(n * 100) / 100);
