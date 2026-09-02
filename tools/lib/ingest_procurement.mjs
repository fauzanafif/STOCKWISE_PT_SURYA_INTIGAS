// PPB / RI / PPB Perubahan  (1. PPB - RI.xlsx)
import { openWorkbook, sheetRows, detectHeader, mapColumns, rowGetter, baseName } from './sheet.mjs';
import { cleanText, cleanKey, descNorm, parseNum, parseDateISO, rowHash } from './textnorm.mjs';
import { insert, insertOrIgnore, newBatch, finishBatch, note, mtimeOf } from './db.mjs';

const PPB_MAP = {
  tgl_ppb: ['tgl ppb'], no_ppb: ['no ppb'], deskripsi: ['deskripsi barang'],
  qty: ['kuantitas'], satuan: ['satuan'], peminta: ['peminta'], divisi: ['divisi'],
  keterangan: ['keterangan'], status: ['status'],
  cnt_ri: ['cntri'], sum_ri: ['sumri'], cnt_amend: ['cntamend'], cnt_close: ['cntclose'],
};
const RI_MAP = {
  tgl_ri: ['tgl ri'], no_ri: ['no ri'], deskripsi: ['deskripsi barang'], qty: ['kuantitas'],
  satuan: ['satuan'], no_ppb: ['no ppb'], no_po: ['no po'], vendor: ['vendor'],
  no_surat_jalan: ['no surat jalan'], pemeriksa: ['pemeriksa'], keterangan: ['keterangan'],
};
const CHG_MAP = {
  tgl_perubahan: ['tgl perubahan'], no_ppb: ['no ppb'], deskripsi: ['deskripsi barang'],
  qty: ['kuantitas'], satuan: ['satuan'], peminta: ['peminta'], divisi: ['divisi'],
  tipe_perubahan: ['tipe perubahan'], keterangan: ['keterangan'],
};

export function ingestProcurement(db, file) {
  const wb = openWorkbook(file);
  const fname = baseName(file);
  const mtime = mtimeOf(file);
  const out = {};

  out.ppb = ingestSheet(db, wb, fname, mtime, 'ppb', 'PPB', ['no ppb', 'deskripsi barang'], PPB_MAP, (get, r, ln) => ({
    no_ppb: cleanKey(get(r, 'no_ppb')), line_no: ln, tgl_ppb: parseDateISO(get(r, 'tgl_ppb')),
    deskripsi: cleanText(get(r, 'deskripsi')), deskripsi_norm: descNorm(get(r, 'deskripsi')),
    qty: parseNum(get(r, 'qty')), satuan_raw: cleanText(get(r, 'satuan')),
    peminta: cleanText(get(r, 'peminta')), divisi: cleanText(get(r, 'divisi')),
    status: cleanText(get(r, 'status')), keterangan: cleanText(get(r, 'keterangan')),
    cnt_ri: parseNum(get(r, 'cnt_ri')), sum_ri: parseNum(get(r, 'sum_ri')),
    cnt_amend: parseNum(get(r, 'cnt_amend')), cnt_close: parseNum(get(r, 'cnt_close')),
  }), (v) => [v.no_ppb, v.deskripsi_norm, v.qty, v.tgl_ppb]);

  out.ri = ingestSheet(db, wb, fname, mtime, 'ri', 'RI', ['no ri', 'deskripsi barang'], RI_MAP, (get, r, ln) => ({
    no_ri: cleanKey(get(r, 'no_ri')), line_no: ln, tgl_ri: parseDateISO(get(r, 'tgl_ri')),
    deskripsi: cleanText(get(r, 'deskripsi')), deskripsi_norm: descNorm(get(r, 'deskripsi')),
    qty: parseNum(get(r, 'qty')), satuan_raw: cleanText(get(r, 'satuan')),
    no_ppb: cleanKey(get(r, 'no_ppb')), no_po: cleanKey(get(r, 'no_po')),
    vendor: cleanText(get(r, 'vendor')), no_surat_jalan: cleanText(get(r, 'no_surat_jalan')),
    pemeriksa: cleanText(get(r, 'pemeriksa')), keterangan: cleanText(get(r, 'keterangan')),
  }), (v) => [v.no_ri, v.deskripsi_norm, v.qty, v.no_po, v.tgl_ri]);

  out.ppb_changes = ingestSheet(db, wb, fname, mtime, 'ppb', 'PPB Perubahan', ['no ppb', 'tipe perubahan'], CHG_MAP, (get, r) => ({
    no_ppb: cleanKey(get(r, 'no_ppb')), tgl_perubahan: parseDateISO(get(r, 'tgl_perubahan')),
    deskripsi: cleanText(get(r, 'deskripsi')), deskripsi_norm: descNorm(get(r, 'deskripsi')),
    qty: parseNum(get(r, 'qty')), satuan_raw: cleanText(get(r, 'satuan')),
    peminta: cleanText(get(r, 'peminta')), divisi: cleanText(get(r, 'divisi')),
    tipe_perubahan: cleanText(get(r, 'tipe_perubahan')), keterangan: cleanText(get(r, 'keterangan')),
  }), (v) => [v.no_ppb, v.tgl_perubahan, v.deskripsi_norm, v.qty, v.tipe_perubahan], 'ppb_changes');

  return out;
}

/** generic line-sheet ingest with row_hash dedup */
export function ingestSheet(db, wb, fname, mtime, module, sheetName, signature, colMap, build, hashParts, table = null) {
  table = table || (sheetName === 'PPB' ? 'ppb_lines' : sheetName === 'RI' ? 'ri_lines' : module + '_lines');
  const batchId = newBatch(db, { filename: fname, module: `${module}:${sheetName}`, source_mtime: mtime });
  const rows = sheetRows(wb, sheetName);
  if (!rows.length) { note(db, batchId, 'sheet', `sheet "${sheetName}" kosong (0 baris)`); finishBatch(db, batchId, { status: 'OK' }); return { inserted: 0, duplicate: 0, total: 0 }; }
  const { headerIndex, header, dataRows } = detectHeader(rows, signature);
  const { colIndex, missing } = mapColumns(header, colMap);
  const get = rowGetter(colIndex);
  for (const m of missing) insert(db, 'import_errors', { upload_batch_id: batchId, sheet: sheetName, rule: 'MISSING_COLUMN', column: m, severity: 'WARNING', message: `${m} not found` });

  const keyField = Object.keys(colMap).find((k) => /^no_/.test(k)) || 'no_ppb';
  let inserted = 0, dup = 0, nokey = 0, ln = 0, lastKey = null;
  db.exec('BEGIN');
  for (let i = 0; i < dataRows.length; i++) {
    const r = dataRows[i];
    const v = build(get, r, null);
    const keyVal = v[keyField];
    if (!keyVal && !v.deskripsi) continue;
    if (!keyVal) { nokey++; continue; }
    if (keyVal !== lastKey) { ln = 0; lastKey = keyVal; }
    ln++;
    if ('line_no' in v) v.line_no = ln;
    const rh = rowHash([module, ...hashParts(v)]);
    const row = {
      ...v, row_hash: rh,
      source_file: fname, source_sheet: sheetName, source_row: headerIndex + 2 + i, upload_batch_id: batchId,
    };
    // ppb_changes has no line_no col
    const res = insertOrIgnore(db, table, row);
    if (res.inserted) inserted++; else dup++;
  }
  db.exec('COMMIT');
  if (nokey) note(db, batchId, 'sheet', `${nokey} baris dilewati (nomor dokumen kosong)`);
  finishBatch(db, batchId, { total: dataRows.length, inserted, duplicate: dup, status: 'OK' });
  return { inserted, duplicate: dup, total: dataRows.length, sheet: sheetName };
}
