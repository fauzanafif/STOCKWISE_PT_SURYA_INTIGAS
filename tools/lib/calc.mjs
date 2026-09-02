// Calculation engine — one place, mirrored by stockwise/calc.py.
// Produces one calc_results row per master item for a new calc_run.
// See AUDIT/00_decisions.md [A-3][A-4][A-5].

export const LEAD_TIME_HIGH_THRESHOLD_DAYS = 14;   // [A-5] PENDING business confirmation

const FINAL_PPB_STATUS = new Set(['completed', 'close', 'error']);

export function runCalc(db, { threshold = LEAD_TIME_HIGH_THRESHOLD_DAYS } = {}) {
  const runId = db.prepare(`INSERT INTO calc_runs (lead_time_threshold, notes) VALUES (?, ?)`)
    .run(threshold, 'auto').lastInsertRowid;

  // resolve safety stock onto master items: prefer matcher-resolved link, else exact deskripsi_norm
  db.exec(`
    UPDATE safety_stock_params
       SET master_item_id = (SELECT m.id FROM master_items m WHERE m.deskripsi_norm = safety_stock_params.item_desc_norm LIMIT 1)
     WHERE master_item_id IS NULL;
    UPDATE monthly_consumption
       SET master_item_id = (SELECT m.id FROM master_items m WHERE m.deskripsi_norm = monthly_consumption.item_desc_norm LIMIT 1)
     WHERE master_item_id IS NULL;
  `);

  const items = db.prepare(`
    SELECT m.id,
           s.sisa_stok_num  AS sisa,
           s.sisa_stok_known AS sisa_known,
           ssp.safety_stock AS ss,
           ssp.lead_time_days AS lt,
           ssp.avg_12_bln   AS avg12
    FROM master_items m
    LEFT JOIN inventory_snapshots s ON s.master_item_id = m.id
    LEFT JOIN safety_stock_params ssp ON ssp.master_item_id = m.id
  `).all();

  // per-item incoming (outstanding procurement) — approximation, see [A-17]
  const incomingRows = db.prepare(`
    SELECT p.master_item_id AS id,
           SUM(CASE WHEN LOWER(COALESCE(p.status,'')) NOT IN ('completed','close','error') THEN COALESCE(p.qty,0) ELSE 0 END) AS ppb_open,
           (SELECT COALESCE(SUM(r.qty),0) FROM ri_lines r
             WHERE r.master_item_id = p.master_item_id AND r.no_ppb IS NOT NULL) AS ri_recv
    FROM ppb_lines p
    WHERE p.master_item_id IS NOT NULL
    GROUP BY p.master_item_id
  `).all();
  const incoming = new Map(incomingRows.map((r) => [r.id, Math.max((r.ppb_open || 0) - (r.ri_recv || 0), 0)]));

  const npbgUsage = new Map(db.prepare(`
    SELECT master_item_id AS id, SUM(COALESCE(qty,0)) AS total, COUNT(DISTINCT substr(tgl_npbg,1,7)) AS months
    FROM npbg_lines WHERE master_item_id IS NOT NULL AND tgl_npbg IS NOT NULL
    GROUP BY master_item_id
  `).all().map((r) => [r.id, r.months ? r.total / r.months : null]));

  // pass 1: compute raw fields, collect unsafe defisit distribution
  const rows = [];
  const unsafeDef = [];
  for (const it of items) {
    const sisaKnown = it.sisa_known === 1 && it.sisa !== null;
    const ssKnown = it.ss !== null && it.ss !== undefined;
    const sisa = sisaKnown ? it.sisa : null;
    const ss = ssKnown ? it.ss : null;
    let selisih = null, defisit = null, status;

    if (!sisaKnown) status = 'UNKNOWN';
    else if (sisa === 0 && (!ssKnown || ss === 0)) status = 'BEP';
    else if (!ssKnown) status = 'NO_SAFETY_STOCK';
    else {
      selisih = sisa - ss;
      defisit = Math.max(ss - sisa, 0);
      if (sisa === 0 && ss > 0) status = 'OUT_OF_STOCK';
      else if (sisa < ss) status = 'TIDAK_AMAN';
      else status = 'AMAN';
    }
    const unsafe = status === 'TIDAK_AMAN' || status === 'OUT_OF_STOCK';
    if (unsafe && defisit !== null) unsafeDef.push(defisit);

    const inc = incoming.get(it.id) ?? null;
    const projected = sisaKnown ? sisa + (inc || 0) : null;
    const avgUse = it.avg12 ?? npbgUsage.get(it.id) ?? null;

    rows.push({ it, sisa, sisaKnown, ss, ssKnown, selisih, defisit, status, unsafe, inc, projected, avgUse });
  }

  const median = pctl(unsafeDef, 0.5);
  const p75 = pctl(unsafeDef, 0.75);

  const ins = db.prepare(`
    INSERT INTO calc_results
      (master_item_id, calc_run_id, sisa_stok, sisa_stok_known, safety_stock, safety_stock_known,
       lead_time_days, selisih, defisit, stock_status, is_critical, priority_score, priority_level,
       rekomendasi, incoming_qty, projected_stock, avg_monthly_usage)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
  `);

  db.exec('BEGIN');
  for (const r of rows) {
    const lt = r.it.lt ?? null;
    let score = 0, level = 'LOW';
    if (r.unsafe) {
      score = (r.defisit || 0) * 2.0 + (lt || 0) * 1.0;
      const high = (r.defisit !== null && median !== null && r.defisit >= median) || (lt !== null && lt >= threshold);
      level = high ? 'HIGH' : 'MEDIUM';
    }
    const critical = r.unsafe && ((r.defisit !== null && p75 !== null && r.defisit >= p75) || level === 'HIGH') ? 1 : 0;
    const rek = recommend(r.status, lt, threshold, r.ssKnown, r.sisaKnown);
    ins.run(
      r.it.id, runId, r.sisa, r.sisaKnown ? 1 : 0, r.ss, r.ssKnown ? 1 : 0,
      lt, r.selisih, r.defisit, r.status, critical, round(score), level,
      rek, r.inc, r.projected, r.avgUse !== null ? round(r.avgUse) : null,
    );
  }
  db.exec('COMMIT');

  return { runId, items: rows.length, median, p75, threshold };
}

function recommend(status, lt, threshold, ssKnown, sisaKnown) {
  if (!sisaKnown) return 'Sisa stok belum terdata — input dulu di Master Inventory.';
  if (!ssKnown) return 'Safety stock belum tersedia untuk barang ini — belum bisa dinilai aman/tidak.';
  switch (status) {
    case 'BEP': return 'Sisa & Safety Stock sama-sama 0 — cek apakah barang non-aktif atau data belum diisi.';
    case 'OUT_OF_STOCK': return 'STOK HABIS. Segera adakan pembelian — cek status PPB/PO.';
    case 'TIDAK_AMAN': return (lt !== null && lt >= threshold) ? 'Prioritas tinggi untuk procurement (lead time panjang).' : 'Segera lakukan replenishment.';
    case 'AMAN': return 'Stok aman, tidak perlu replenishment segera.';
    default: return '-';
  }
}

function pctl(arr, p) {
  if (!arr.length) return null;
  const s = [...arr].sort((a, b) => a - b);
  const idx = (s.length - 1) * p;
  const lo = Math.floor(idx), hi = Math.ceil(idx);
  return lo === hi ? s[lo] : s[lo] + (s[hi] - s[lo]) * (idx - lo);
}
const round = (n) => (n === null || n === undefined ? null : Math.round(n * 100) / 100);
