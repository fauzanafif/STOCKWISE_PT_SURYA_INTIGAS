// Master items + inventory snapshot + safety-stock params + monthly consumption (DATA.xlsx)
import { openWorkbook, sheetRows, detectHeader, mapColumns, rowGetter, baseName } from './sheet.mjs';
import { cleanText, cleanKey, descNorm, descCore, parseStockNum, parseNum, parseBool } from './textnorm.mjs';
import { insert, insertOrIgnore, newBatch, finishBatch, note, mtimeOf } from './db.mjs';

const MASTER_SHEET_CANDIDATES = ['database utama', 'data', 'master inventory', 'master'];
const SKIP_SHEETS = new Set(['cetak', 'sheet2', 'sheet6']);

const MASTER_MAP = {
  kode_barang:      ['kode barang', 'kode'],
  kategori_induk:   ['kategori induk'],
  kategori_anak_1:  ['kategori anak 1'],
  kategori_anak_2:  ['kategori anak 2'],
  kategori_anak_3:  ['kategori anak 3'],
  deskripsi:        ['deskripsi barang', 'deskripsi'],
  uom:              ['uom', 'satuan'],
  perlu_blueprint:  ['perlu blueprint'],
  nama_alias:       ['nama alias', 'alias'],
  letak_gudang:     ['letak gudang'],
  letak_rak:        ['letak rak'],
  blueprint_img_ref:['blueprint img'],
  blueprint_pdf_ref:['blueprint detail pdf'],
  blueprint_3d_ref: ['blueprint 3d'],
  sisa_stok:        ['sisa stok'],
  lead_time:        ['lead time'],
  sqrt_lt:          ['√lt'],
  safety_stock:     ['safety stock'],
  min_pr:           ['min pr'],
};

const SS_MONTHS = ['Agt', 'Sept', 'Okt', 'Nov', 'Des', 'Jan', 'Feb', 'Mar', 'April', 'Mei', 'Juni', 'Juli'];
// Agt 2025 .. Juli 2026 (per sheet header "NPBG (Agt 2025-Juli 2026)")
const SS_MONTH_YM = {
  Agt: '2025-08', Sept: '2025-09', Okt: '2025-10', Nov: '2025-11', Des: '2025-12',
  Jan: '2026-01', Feb: '2026-02', Mar: '2026-03', April: '2026-04', Mei: '2026-05', Juni: '2026-06', Juli: '2026-07',
};

export function ingestMaster(db, file) {
  const wb = openWorkbook(file);
  const fname = baseName(file);
  const mtime = mtimeOf(file);
  const batchId = newBatch(db, { filename: fname, module: 'master', source_mtime: mtime });

  // ── pick master sheet ──
  const lower = wb.SheetNames.map((s) => s.toLowerCase());
  let sheetName = wb.SheetNames.find((s, i) => MASTER_SHEET_CANDIDATES.includes(lower[i]));
  if (!sheetName) {
    for (const s of wb.SheetNames) {
      if (SKIP_SHEETS.has(s.toLowerCase()) || s.toLowerCase().startsWith('safety stock') || s.toLowerCase() === 'dropdown list') continue;
      const { header } = detectHeader(sheetRows(wb, s), ['kode barang', 'deskripsi']);
      if (header.some((h) => /kode barang/i.test(h)) && header.some((h) => /deskripsi/i.test(h))) { sheetName = s; break; }
    }
  }
  if (!sheetName) throw new Error('master sheet not found in ' + fname);
  note(db, batchId, 'file', `master sheet = "${sheetName}"; sheets skipped: ${wb.SheetNames.filter(s => SKIP_SHEETS.has(s.toLowerCase())).join(', ') || 'none'}`);

  const rows = sheetRows(wb, sheetName);
  const { headerIndex, header, dataRows } = detectHeader(rows, ['kode barang', 'deskripsi barang']);
  const { colIndex, missing } = mapColumns(header, MASTER_MAP);
  const get = rowGetter(colIndex);
  const snapDate = (() => {
    const h = header[colIndex.sisa_stok] || '';
    const m = h.match(/(\d{1,2})[\/\-.](\d{1,2})[\/\-.](\d{2,4})/);
    if (!m) return null;
    let [, d, mo, y] = m; if (y.length === 2) y = '20' + y;
    return `${y}-${String(mo).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
  })();

  for (const req of ['kode_barang', 'deskripsi'])
    if (missing.includes(req)) insert(db, 'import_errors', { upload_batch_id: batchId, sheet: sheetName, rule: 'MISSING_COLUMN', column: req, severity: 'INVALID', message: `column for ${req} not found` });

  // duplicate / blank kode detection
  const kodeCount = new Map();
  dataRows.forEach((r) => { const k = cleanKey(get(r, 'kode_barang')); if (k) kodeCount.set(k, (kodeCount.get(k) || 0) + 1); });
  const descCount = new Map();
  dataRows.forEach((r) => { const d = descNorm(get(r, 'deskripsi')); if (d) descCount.set(d, (descCount.get(d) || 0) + 1); });

  let seq = 0, inserted = 0, snaps = 0;
  const aliasDropped = [];
  db.exec('BEGIN');
  for (let i = 0; i < dataRows.length; i++) {
    const r = dataRows[i];
    const deskripsi = cleanText(get(r, 'deskripsi'));
    const kode = cleanKey(get(r, 'kode_barang'));
    if (!deskripsi && !kode) continue;
    seq++;
    const id = 'ITEM-' + String(seq).padStart(6, '0');
    const dn = descNorm(deskripsi);
    const flags = [];
    if (!kode) flags.push('KODE_MISSING');
    if (kode && kodeCount.get(kode) > 1) flags.push('KODE_DUPLICATE');
    if (dn && descCount.get(dn) > 5) flags.push('DESC_MASS_DUPLICATE');

    const alias = cleanText(get(r, 'nama_alias'));
    if (alias && !/^(ya|tidak)$/i.test(alias)) {
      insert(db, 'item_aliases', { master_item_id: id, alias, alias_norm: descNorm(alias), source: 'master.Nama Alias' });
    } else if (alias) aliasDropped.push(alias);

    insert(db, 'master_items', {
      id, kode_barang: kode,
      kategori_induk: cleanText(get(r, 'kategori_induk')),
      kategori_anak_1: cleanText(get(r, 'kategori_anak_1')),
      kategori_anak_2: cleanText(get(r, 'kategori_anak_2')),
      kategori_anak_3: cleanText(get(r, 'kategori_anak_3')),
      deskripsi: deskripsi || '(tanpa deskripsi)',
      deskripsi_norm: dn || '(TANPA DESKRIPSI)',
      deskripsi_core: descCore(deskripsi) || dn,
      uom: cleanText(get(r, 'uom')),
      perlu_blueprint: parseBool(get(r, 'perlu_blueprint')),
      letak_gudang: cleanText(get(r, 'letak_gudang')),
      letak_rak: cleanText(get(r, 'letak_rak')),
      blueprint_img_ref: cleanText(get(r, 'blueprint_img_ref')),
      blueprint_pdf_ref: cleanText(get(r, 'blueprint_pdf_ref')),
      blueprint_3d_ref: cleanText(get(r, 'blueprint_3d_ref')),
      dq_flags: flags.join(',') || null,
      source_file: fname, source_sheet: sheetName, source_row: headerIndex + 2 + i,
      upload_batch_id: batchId,
    });
    inserted++;

    const rawStock = get(r, 'sisa_stok');
    const num = parseStockNum(rawStock);
    const known = num !== null ? 1 : 0;
    if (rawStock !== null || num !== null) {
      insert(db, 'inventory_snapshots', {
        master_item_id: id, snapshot_date: snapDate,
        sisa_stok_raw: rawStock === null ? null : String(rawStock),
        sisa_stok_num: num, sisa_stok_known: known,
        source_file: fname, source_sheet: sheetName, source_row: headerIndex + 2 + i, upload_batch_id: batchId,
      });
      snaps++;
    }
  }
  db.exec('COMMIT');
  if (aliasDropped.length) note(db, batchId, 'column', `Nama Alias: ${aliasDropped.length} nilai di-drop (isinya "Ya"/"Tidak", bukan alias)`);
  finishBatch(db, batchId, { total: dataRows.length, inserted, status: 'OK' });

  // ── safety stock sheets ──
  ingestSafetyStock(db, wb, file, fname, mtime);

  return { sheetName, items: inserted, snapshots: snaps };
}

function ingestSafetyStock(db, wb, file, fname, mtime) {
  const sheets = wb.SheetNames.filter((s) => s.toLowerCase().startsWith('safety stock'));
  const batchId = newBatch(db, { filename: fname, module: 'safety_stock', source_mtime: mtime });
  let rowsSeen = 0, kept = 0, conflicts = 0, monthly = 0;
  const best = new Map();       // desc_norm -> {rec, score}
  const monthAgg = new Map();   // `${desc_norm}|${month}` -> {qty, sheet}

  for (const sheet of sheets) {
    const raw = sheetRows(wb, sheet);
    // header: row0 has group labels, row1 has month labels. Data from row2.
    const r0 = (raw[0] || []).map((c) => (c === null ? '' : String(c).trim()));
    const col = {
      desc: 1,
      lt: r0.findIndex((x) => x.toUpperCase() === 'LT'),
      slt: r0.findIndex((x) => x === '√LT'),
      ss: r0.findIndex((x) => x.toUpperCase() === 'SS'),
      minpr: r0.findIndex((x) => x.replace(/\s+/g, '').toUpperCase() === 'MINPR'),
    };
    // month columns are indices 2..13 in observed layout; map by header row1
    const r1 = (raw[1] || []).map((c) => (c === null ? '' : String(c).trim()));
    const monthCols = {};
    SS_MONTHS.forEach((m) => { const i = r1.findIndex((x) => x.toLowerCase() === m.toLowerCase()); if (i >= 0) monthCols[m] = i; });
    const avgCols = { '1_bln': r1.findIndex(x => /^1\s*bln/i.test(x)), '3_bln': r1.findIndex(x => /^3\s*bln/i.test(x)), '6_bln': r1.findIndex(x => /^6\s*bln/i.test(x)), '12_bln': r1.findIndex(x => /^12\s*bln/i.test(x)) };

    const data = raw.slice(2);
    for (let i = 0; i < data.length; i++) {
      const r = data[i];
      const desc = cleanText(r[col.desc]);
      if (!desc) continue;
      rowsSeen++;
      const dn = descNorm(desc);
      const rec = {
        item_description: desc, item_desc_norm: dn,
        lead_time_days: col.lt >= 0 ? parseNum(r[col.lt]) : null,
        sqrt_lt: col.slt >= 0 ? parseNum(r[col.slt]) : null,
        safety_stock: col.ss >= 0 ? parseNum(r[col.ss]) : null,
        min_pr: col.minpr >= 0 ? parseNum(r[col.minpr]) : null,
        avg_1_bln: avgCols['1_bln'] >= 0 ? parseNum(r[avgCols['1_bln']]) : null,
        avg_3_bln: avgCols['3_bln'] >= 0 ? parseNum(r[avgCols['3_bln']]) : null,
        avg_6_bln: avgCols['6_bln'] >= 0 ? parseNum(r[avgCols['6_bln']]) : null,
        avg_12_bln: avgCols['12_bln'] >= 0 ? parseNum(r[avgCols['12_bln']]) : null,
        source_sheet: sheet, source_file: fname, source_row: i + 3, upload_batch_id: batchId,
      };
      const score = (rec.avg_12_bln != null ? 4 : 0) + (rec.safety_stock != null ? 2 : 0) + (rec.lead_time_days != null ? 1 : 0);
      const prev = best.get(dn);
      if (!prev) best.set(dn, { rec, score });
      else {
        const differ = prev.rec.safety_stock !== rec.safety_stock || prev.rec.lead_time_days !== rec.lead_time_days;
        if (differ) { conflicts++; prev.rec.dq_flag = 'SS_CONFLICT'; }
        if (score > prev.score) best.set(dn, { rec: { ...rec, dq_flag: 'SS_CONFLICT' }, score });
      }
      // monthly consumption: one row per (desc, month) — first non-null wins
      for (const [m, ci] of Object.entries(monthCols)) {
        const q = parseNum(r[ci]);
        if (q === null) continue;
        const key = dn + '|' + m;
        if (!monthAgg.has(key)) monthAgg.set(key, { qty: q, sheet });
      }
    }
  }
  db.exec('BEGIN');
  for (const { rec } of best.values()) {
    try { insert(db, 'safety_stock_params', rec); kept++; } catch { /* dup desc_norm */ }
  }
  for (const [key, v] of monthAgg) {
    const [dn, m] = key.split('|');
    insert(db, 'monthly_consumption', {
      item_desc_norm: dn, period_month: m, period_ym: SS_MONTH_YM[m] || null,
      qty: v.qty, source_sheet: v.sheet, upload_batch_id: batchId,
    });
    monthly++;
  }
  db.exec('COMMIT');
  note(db, batchId, 'file', `${sheets.length} sheet SAFETY STOCK diproses; ${kept} deskripsi unik disimpan; ${conflicts} konflik nilai antar-sheet (dq_flag=SS_CONFLICT); ${monthly} baris monthly_consumption`);
  finishBatch(db, batchId, { total: rowsSeen, inserted: kept, need_review: conflicts, status: 'OK' });
}
