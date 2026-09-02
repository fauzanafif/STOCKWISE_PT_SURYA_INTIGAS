// NPBG — inventory consumption / outgoing  (2. NPBG.xlsx)
import { openWorkbook, sheetRows, detectHeader, mapColumns, rowGetter, baseName } from './sheet.mjs';
import { cleanText, cleanKey, descNorm, parseNum, parseDateISO, rowHash } from './textnorm.mjs';
import { insert, insertOrIgnore, newBatch, finishBatch, note, mtimeOf } from './db.mjs';

const NPBG_MAP = {
  tgl_npbg: ['tgl npbg'], no_npbg: ['no npbg'], tipe: ['tipe npbg'], klasifikasi: ['klasifikasi'],
  pelanggan: ['pelanggan'], nama_proyek: ['nama proyek'], no_seri_nopol: ['no seri / nopol', 'no seri/nopol', 'no seri'],
  deskripsi: ['deskripsi barang'], qty: ['kuantitas'], satuan: ['satuan'],
  peminta: ['peminta'], dikeluarkan_oleh: ['dikeluarkan oleh'], divisi: ['divisi'], keterangan: ['keterangan'],
};
const SKIP = new Set(['export list_klasifikasi', 'dropdown list']);

export function ingestNpbg(db, file) {
  const wb = openWorkbook(file);
  const fname = baseName(file);
  const mtime = mtimeOf(file);
  const batchId = newBatch(db, { filename: fname, module: 'npbg', source_mtime: mtime });
  note(db, batchId, 'file', `sheet dilewati: ${wb.SheetNames.filter((s) => SKIP.has(s.toLowerCase())).join(', ') || 'none'}`);

  const rows = sheetRows(wb, 'NPBG');
  const { headerIndex, header, dataRows } = detectHeader(rows, ['no npbg', 'deskripsi barang']);
  const { colIndex, missing } = mapColumns(header, NPBG_MAP);
  const get = rowGetter(colIndex);
  for (const m of missing) insert(db, 'import_errors', { upload_batch_id: batchId, sheet: 'NPBG', rule: 'MISSING_COLUMN', column: m, severity: 'WARNING', message: m });

  let inserted = 0, dup = 0, nokey = 0, negQty = 0, ln = 0, lastKey = null;
  db.exec('BEGIN');
  for (let i = 0; i < dataRows.length; i++) {
    const r = dataRows[i];
    const no_npbg = cleanKey(get(r, 'no_npbg'));
    const deskripsi = cleanText(get(r, 'deskripsi'));
    if (!no_npbg && !deskripsi) continue;
    if (!no_npbg) { nokey++; continue; }
    if (no_npbg !== lastKey) { ln = 0; lastKey = no_npbg; }
    ln++;
    const qty = parseNum(get(r, 'qty'));
    if (qty !== null && qty < 0) negQty++;
    const v = {
      no_npbg, line_no: ln, tgl_npbg: parseDateISO(get(r, 'tgl_npbg')),
      tipe: cleanText(get(r, 'tipe')), klasifikasi: cleanText(get(r, 'klasifikasi')),
      pelanggan: cleanText(get(r, 'pelanggan')), nama_proyek: cleanText(get(r, 'nama_proyek')),
      no_seri_nopol: cleanText(get(r, 'no_seri_nopol')),
      deskripsi, deskripsi_norm: descNorm(deskripsi),
      qty, satuan_raw: cleanText(get(r, 'satuan')),
      peminta: cleanText(get(r, 'peminta')), dikeluarkan_oleh: cleanText(get(r, 'dikeluarkan_oleh')),
      divisi: cleanText(get(r, 'divisi')), keterangan: cleanText(get(r, 'keterangan')),
    };
    v.row_hash = rowHash(['npbg', no_npbg, v.deskripsi_norm, qty, v.tgl_npbg, ln]);
    v.source_file = fname; v.source_sheet = 'NPBG'; v.source_row = headerIndex + 2 + i; v.upload_batch_id = batchId;
    const res = insertOrIgnore(db, 'npbg_lines', v);
    if (res.inserted) inserted++; else dup++;
  }
  db.exec('COMMIT');
  if (nokey) note(db, batchId, 'sheet', `${nokey} baris tanpa No NPBG dilewati`);
  if (negQty) note(db, batchId, 'column', `${negQty} baris Kuantitas negatif (dipertahankan)`);
  finishBatch(db, batchId, { total: dataRows.length, inserted, duplicate: dup, status: 'OK' });
  return { inserted, duplicate: dup };
}
