// Matching + derived tables + calc — shared by build_stockwise_db.mjs and ingest_one.mjs.
import { buildMasterIndex, resolve } from './match.mjs';
import { runCalc } from './calc.mjs';

const MATCH_TARGETS = [
  ['ppb_lines', 'deskripsi'], ['ppb_changes', 'deskripsi'], ['ri_lines', 'deskripsi'],
  ['npbg_lines', 'deskripsi'], ['borrow_lend', 'deskripsi'], ['stpp', 'deskripsi'],
  ['tire_transactions', 'deskripsi_ban_baru'], ['manufacturing', 'hasil_produk'],
  ['used_returns', 'deskripsi'],
];

/** Re-match only rows that were never matched or are still pending manual review.
 *  Rows a human ACCEPTed (matching_reviews.decision='ACCEPT') are left alone. */
export function runMatching(db, { onlyPending = false } = {}) {
  const masters = db.prepare(`SELECT id, kode_barang, deskripsi, deskripsi_norm, deskripsi_core FROM master_items`).all();
  const idx = buildMasterIndex(masters);
  const cache = new Map();
  const doResolve = (d) => { if (!cache.has(d)) cache.set(d, resolve(idx, d)); return cache.get(d); };
  const accepted = new Set(
    db.prepare(`SELECT source_table||'#'||source_row_id k FROM matching_reviews WHERE decision IN ('ACCEPT','NEW_ITEM')`)
      .all().map((r) => r.k),
  );

  const stats = {};
  for (const [table, col] of MATCH_TARGETS) {
    const filter = onlyPending ? `AND (match_status IS NULL OR match_status <> 'MATCHED')` : '';
    const rows = db.prepare(`SELECT id, ${col} AS d FROM ${table} WHERE ${col} IS NOT NULL ${filter}`).all();
    const upd = db.prepare(`UPDATE ${table} SET master_item_id = ?, match_status = ? WHERE id = ?`);
    const rev = db.prepare(`INSERT OR IGNORE INTO matching_reviews
      (source_table, source_row_id, source_desc, source_desc_norm, candidate_item_id, candidate_desc, confidence, method, decision)
      VALUES (?,?,?,?,?,?,?,?, 'PENDING')`);
    const s = { MATCHED: 0, POSSIBLE_MATCH: 0, NEED_REVIEW: 0, NEW_ITEM: 0 };
    db.exec('BEGIN');
    for (const row of rows) {
      if (accepted.has(`${table}#${row.id}`)) continue;
      const res = doResolve(row.d);
      upd.run(res.master_item_id, res.status, row.id);
      s[res.status] = (s[res.status] || 0) + 1;
      if (res.status !== 'MATCHED') {
        // only rows with real candidates go to the review queue; a NEW_ITEM with
        // no candidate is already flagged via the row's match_status.
        for (const c of res.candidates.slice(0, 5))
          if (c.id) rev.run(table, row.id, row.d, null, c.id, c.desc, c.confidence, c.method);
      }
    }
    db.exec('COMMIT');
    stats[table] = s;
  }
  return stats;
}

export function runDerived(db) {
  db.exec(`DELETE FROM po_derived;`);
  db.exec(`
    INSERT INTO po_derived (no_po, vendor, first_ri_date, last_ri_date, ri_count, total_qty)
    SELECT no_po, MAX(vendor), MIN(tgl_ri), MAX(tgl_ri), COUNT(*), SUM(COALESCE(qty,0))
    FROM ri_lines WHERE no_po IS NOT NULL GROUP BY no_po;
  `);
  const vi = db.prepare(`INSERT OR IGNORE INTO vehicles (nopol, first_seen, last_seen) VALUES (?,?,?)`);
  const vset = new Map();
  for (const [tbl, col, dcol] of [
    ['tire_transactions', 'nopol', 'tgl_npbg'], ['tire_bpn_snapshots', 'nopol', 'tanggal_cut_off'],
    ['tire_deliver_receive', 'nopol', 'tgl_npbg'], ['asset_maintenance', 'nopol', 'tgl_laporan'],
    ['npbg_lines', 'no_seri_nopol', 'tgl_npbg'],
  ]) {
    for (const r of db.prepare(`SELECT ${col} AS n, ${dcol} AS d FROM ${tbl} WHERE ${col} IS NOT NULL`).all()) {
      const n = String(r.n).trim();
      if (!/\b[A-Z]{1,2}\s?\d{2,4}\b/i.test(n)) continue;
      const cur = vset.get(n) || { first: r.d, last: r.d };
      if (r.d && (!cur.first || r.d < cur.first)) cur.first = r.d;
      if (r.d && (!cur.last || r.d > cur.last)) cur.last = r.d;
      vset.set(n, cur);
    }
  }
  db.exec('BEGIN');
  for (const [n, v] of vset) vi.run(n, v.first || null, v.last || null);
  db.exec('COMMIT');
  return { po: db.prepare('SELECT COUNT(*) c FROM po_derived').get().c, vehicles: vset.size };
}

export { runCalc };
