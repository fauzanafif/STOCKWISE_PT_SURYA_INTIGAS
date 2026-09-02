// Tracking modules: borrow/lend, STPP, tires, asset maintenance, manufacturing, used returns.
import { openWorkbook, sheetRows, detectHeader, mapColumns, rowGetter, baseName } from './sheet.mjs';
import { cleanText, cleanKey, descNorm, parseNum, parseDateISO, rowHash } from './textnorm.mjs';
import { insert, insertOrIgnore, newBatch, finishBatch, note, mtimeOf } from './db.mjs';

const raw = (v) => (v === null || v === undefined || v === '' ? null : String(v).trim());

function runSheet(db, wb, fname, mtime, module, sheet, signature, colMap, table, build, hashParts) {
  const batchId = newBatch(db, { filename: fname, module: `${module}:${sheet}`, source_mtime: mtime });
  const rows = sheetRows(wb, sheet);
  if (!rows.length) { note(db, batchId, 'sheet', `sheet "${sheet}" kosong (0 baris)`); finishBatch(db, batchId, { status: 'OK' }); return { inserted: 0, duplicate: 0, total: 0, sheet }; }
  const { headerIndex, header, dataRows } = detectHeader(rows, signature);
  const { colIndex, missing } = mapColumns(header, colMap);
  const get = rowGetter(colIndex);
  for (const m of missing) insert(db, 'import_errors', { upload_batch_id: batchId, sheet, rule: 'MISSING_COLUMN', column: m, severity: 'WARNING', message: m });
  let inserted = 0, dup = 0, empty = 0, seq = 0;
  db.exec('BEGIN');
  for (let i = 0; i < dataRows.length; i++) {
    const r = dataRows[i];
    seq++;
    const built = build(get, r, seq, header, colIndex);
    if (built === null) { empty++; continue; }
    const list = Array.isArray(built) ? built : [built];
    for (const v of list) {
      const srcRow = headerIndex + 2 + i;
      v.row_hash = rowHash([module, ...hashParts(v, srcRow)]);
      v.source_file = fname; v.source_sheet = sheet; v.source_row = srcRow; v.upload_batch_id = batchId;
      const res = insertOrIgnore(db, table, v);
      if (res.inserted) inserted++; else dup++;
    }
  }
  db.exec('COMMIT');
  if (empty) note(db, batchId, 'sheet', `${empty} baris kosong dilewati`);
  finishBatch(db, batchId, { total: dataRows.length, inserted, duplicate: dup, status: 'OK' });
  return { inserted, duplicate: dup, total: dataRows.length, sheet };
}

// ─────────────────────────── Borrow & Lend ───────────────────────────
export function ingestBorrowLend(db, file) {
  const wb = openWorkbook(file), fname = baseName(file), mtime = mtimeOf(file);
  const lend = runSheet(db, wb, fname, mtime, 'borrow_lend', 'Lend', ['deskripsi barang', 'tgl pinjam'], {
    seq_no: ['no'], tgl_pinjam: ['tgl pinjam'], deskripsi: ['deskripsi barang'], qty: ['kuantitas'],
    satuan: ['satuan'], pihak: ['peminta'], keperluan: ['keperluan'], est_hari: ['est. pinjam', 'est pinjam'],
    ref_keluar: ['tanda keluar'], status: ['status'], ref_kembali: ['tanda kembali'],
    tgl_kembali: ['tgl kembali'], keterangan: ['keterangan kembali'],
  }, 'borrow_lend', (get, r, seq) => {
    const deskripsi = cleanText(get(r, 'deskripsi'));
    if (!deskripsi) return null;
    return {
      arah: 'LEND', seq_no: parseNum(get(r, 'seq_no')) ?? seq, tgl_pinjam: parseDateISO(get(r, 'tgl_pinjam')),
      deskripsi, deskripsi_norm: descNorm(deskripsi), qty: parseNum(get(r, 'qty')),
      satuan_raw: cleanText(get(r, 'satuan')), pihak: cleanText(get(r, 'pihak')),
      keperluan: cleanText(get(r, 'keperluan')), est_hari: parseNum(get(r, 'est_hari')),
      ref_keluar: cleanKey(get(r, 'ref_keluar')), status: cleanText(get(r, 'status')),
      ref_kembali: cleanKey(get(r, 'ref_kembali')), tgl_kembali: parseDateISO(get(r, 'tgl_kembali')),
      keterangan: cleanText(get(r, 'keterangan')),
    };
  }, (v) => ['LEND', v.tgl_pinjam, v.deskripsi_norm, v.qty, v.pihak, v.ref_keluar, v.seq_no]);

  const borrow = runSheet(db, wb, fname, mtime, 'borrow_lend', 'Borrow', ['deskripsi barang', 'vendor'], {
    seq_no: ['no'], tgl_pinjam: ['tgl pinjam'], deskripsi: ['deskripsi barang'], qty: ['kuantitas'],
    satuan: ['satuan'], pihak: ['vendor'], keterangan: ['keterangan'], ref_kembali: ['tanda terima'],
    status: ['status'], ref_keluar: ['tanda keluar'], keterangan_kembali: ['keterangan barang kembali'],
  }, 'borrow_lend', (get, r, seq) => {
    const deskripsi = cleanText(get(r, 'deskripsi'));
    if (!deskripsi) return null;
    return {
      arah: 'BORROW', seq_no: parseNum(get(r, 'seq_no')) ?? seq, tgl_pinjam: parseDateISO(get(r, 'tgl_pinjam')),
      deskripsi, deskripsi_norm: descNorm(deskripsi), qty: parseNum(get(r, 'qty')),
      satuan_raw: cleanText(get(r, 'satuan')), pihak: cleanText(get(r, 'pihak')),
      keperluan: null, est_hari: null, ref_keluar: cleanKey(get(r, 'ref_keluar')),
      status: cleanText(get(r, 'status')), ref_kembali: cleanKey(get(r, 'ref_kembali')),
      tgl_kembali: null,
      keterangan: [cleanText(get(r, 'keterangan')), cleanText(get(r, 'keterangan_kembali'))].filter(Boolean).join(' | ') || null,
    };
  }, (v) => ['BORROW', v.tgl_pinjam, v.deskripsi_norm, v.qty, v.pihak, v.ref_kembali, v.seq_no]);

  return { lend, borrow };
}

// ─────────────────────────── STPP ───────────────────────────
export function ingestStpp(db, file) {
  const wb = openWorkbook(file), fname = baseName(file), mtime = mtimeOf(file);
  const stpp = runSheet(db, wb, fname, mtime, 'stpp', 'STPP', ['no seri', 'deskripsi barang'], {
    no_seri: ['no seri'], deskripsi: ['deskripsi barang'], qty: ['kuantitas'], satuan: ['satuan'],
    peminta: ['peminta'], penempatan: ['penempatan'], tgl_npbg: ['tgl npbg'], ref_npbg: ['no. npbg', 'no npbg'],
    item_no: ['item no'], status: ['status'], tgl_ri: ['tgl ri'], ref_kembali: ['tanda kembali'],
    bukti_keluar_ref: ['bukti keluar'], bukti_terima_ref: ['bukti terima'],
    nama_file_ref: ['nama file(.#ext)', 'nama file (.#ext)'], nama_file2_ref: ['nama file(.#ext2)', 'nama file (.#ext2)'],
    keterangan: ['keterangan kembali'],
  }, 'stpp', (get, r, seq) => {
    const deskripsi = cleanText(get(r, 'deskripsi'));
    const no_seri = cleanKey(get(r, 'no_seri'));
    if (!deskripsi && !no_seri) return null;
    return {
      no_seri, seq_no: seq, deskripsi, deskripsi_norm: descNorm(deskripsi),
      qty: parseNum(get(r, 'qty')), satuan_raw: cleanText(get(r, 'satuan')),
      peminta: cleanText(get(r, 'peminta')), penempatan: cleanText(get(r, 'penempatan')),
      tgl_npbg: parseDateISO(get(r, 'tgl_npbg')), ref_npbg: cleanKey(get(r, 'ref_npbg')),
      item_no: parseNum(get(r, 'item_no')), status: cleanText(get(r, 'status')),
      tgl_ri: parseDateISO(get(r, 'tgl_ri')), ref_kembali: cleanKey(get(r, 'ref_kembali')),
      keterangan: cleanText(get(r, 'keterangan')),
      bukti_keluar_ref: raw(get(r, 'bukti_keluar_ref')), bukti_terima_ref: raw(get(r, 'bukti_terima_ref')),
      nama_file_ref: raw(get(r, 'nama_file_ref')), nama_file2_ref: raw(get(r, 'nama_file2_ref')),
    };
  }, (v) => [v.no_seri, v.deskripsi_norm, v.ref_npbg, v.item_no, v.seq_no]);

  // "Maintenance" sheet is present but empty — ingest to record structure/notes
  runSheet(db, wb, fname, mtime, 'stpp', 'Maintenance', ['no seri', 'deskripsi barang'], {
    no_seri: ['no seri'], deskripsi: ['deskripsi barang'], qty: ['kuantitas'], satuan: ['satuan'],
    peminta: ['peminta'], tgl_npbg: ['tgl npbg'], ref_npbg: ['no npbg'], keterangan: ['keterangan'],
  }, 'stpp', (get, r, seq) => {
    const deskripsi = cleanText(get(r, 'deskripsi'));
    if (!deskripsi) return null;
    return {
      no_seri: cleanKey(get(r, 'no_seri')), seq_no: seq, deskripsi, deskripsi_norm: descNorm(deskripsi),
      qty: parseNum(get(r, 'qty')), satuan_raw: cleanText(get(r, 'satuan')), peminta: cleanText(get(r, 'peminta')),
      penempatan: null, tgl_npbg: parseDateISO(get(r, 'tgl_npbg')), ref_npbg: cleanKey(get(r, 'ref_npbg')),
      item_no: null, status: 'MAINTENANCE', tgl_ri: null, ref_kembali: null, keterangan: cleanText(get(r, 'keterangan')),
      bukti_keluar_ref: null, bukti_terima_ref: null, nama_file_ref: null, nama_file2_ref: null,
    };
  }, (v) => [v.no_seri, v.deskripsi_norm, v.ref_npbg, 'MAINT', v.seq_no]);

  return { stpp };
}

// ─────────────────────────── Tires ───────────────────────────
export function ingestTires(db, file) {
  const wb = openWorkbook(file), fname = baseName(file), mtime = mtimeOf(file);

  const main = runSheet(db, wb, fname, mtime, 'tire', 'Ban Luar', ['nopol', 'deskripsi ban baru'], {
    nopol: ['nopol'], tgl_npbg: ['tgl npbg'], ref_npbg: ['no npbg'],
    deskripsi_ban_baru: ['deskripsi ban baru'], no_seri_baru: ['no seri baru'],
    ban_pos: ['ban'], pergantian: ['pergantian'], keterangan_keluar: ['keterangan keluar'],
    status: ['status'], tgl_ri: ['tgl ri'], ref_ri: ['no. ri', 'no ri'],
    deskripsi_ban_lama: ['deskripsi ban lama'], no_seri_lama: ['no seri lama'],
    keterangan_kembali: ['keterangan kembali'],
    foto_out_ref: ['foto ban (out-old)2', 'foto ban (out'], foto_in_ref: ['foto ban (in)'],
  }, 'tire_transactions', (get, r) => {
    const d = cleanText(get(r, 'deskripsi_ban_baru'));
    const nopol = cleanText(get(r, 'nopol'));
    if (!d && !nopol) return null;
    return {
      nopol, tgl_npbg: parseDateISO(get(r, 'tgl_npbg')), ref_npbg: raw(get(r, 'ref_npbg')),
      deskripsi_ban_baru: d, deskripsi_ban_baru_norm: descNorm(d), no_seri_baru: cleanText(get(r, 'no_seri_baru')),
      deskripsi_ban_lama: cleanText(get(r, 'deskripsi_ban_lama')), no_seri_lama: cleanText(get(r, 'no_seri_lama')),
      ban_pos: parseNum(get(r, 'ban_pos')), pergantian: parseNum(get(r, 'pergantian')),
      keterangan_keluar: cleanText(get(r, 'keterangan_keluar')), status: cleanText(get(r, 'status')),
      tgl_ri: parseDateISO(get(r, 'tgl_ri')), ref_ri: cleanKey(get(r, 'ref_ri')),
      keterangan_kembali: cleanText(get(r, 'keterangan_kembali')),
      foto_out_ref: raw(get(r, 'foto_out_ref')), foto_in_ref: raw(get(r, 'foto_in_ref')),
    };
  }, (v) => [v.nopol, v.ref_npbg, v.no_seri_baru, v.deskripsi_ban_baru_norm, v.tgl_npbg]);

  const bpn = runSheet(db, wb, fname, mtime, 'tire_bpn', 'Ban Luar BPN', ['nopol', 'deskripsi ban'], {
    seq_no: ['no'], tanggal_cut_off: ['tanggal cut off'], nopol: ['nopol'],
    deskripsi_ban: ['deskripsi ban'], no_seri: ['no seri'], foto_ref: ['foto'], keterangan: ['keterangan'],
  }, 'tire_bpn_snapshots', (get, r, seq) => {
    const d = cleanText(get(r, 'deskripsi_ban'));
    if (!d) return null;
    return {
      seq_no: parseNum(get(r, 'seq_no')) ?? seq, tanggal_cut_off: parseDateISO(get(r, 'tanggal_cut_off')),
      nopol: cleanText(get(r, 'nopol')), deskripsi_ban: d, no_seri: cleanText(get(r, 'no_seri')),
      foto_ref: raw(get(r, 'foto_ref')), keterangan: cleanText(get(r, 'keterangan')),
    };
  }, (v) => [v.seq_no, v.nopol, v.no_seri, v.deskripsi_ban]);

  // Deliver & Receive — duplicate column names, handle positionally
  const dr = ingestDeliverReceive(db, wb, fname, mtime);

  return { main, bpn, dr };
}

function ingestDeliverReceive(db, wb, fname, mtime) {
  const sheet = 'Deliver & Receive Ban SIG-BPN';
  const batchId = newBatch(db, { filename: fname, module: `tire_dr:${sheet}`, source_mtime: mtime });
  const rows = sheetRows(wb, sheet);
  if (!rows.length) { note(db, batchId, 'sheet', 'kosong'); finishBatch(db, batchId, { status: 'OK' }); return { inserted: 0 }; }
  const { headerIndex, header, dataRows } = detectHeader(rows, ['nopol', 'no npbg']);
  const up = header.map((h) => h.replace(/\s+/g, ' ').trim().toUpperCase());
  const idx = (name, from = 0) => { for (let i = from; i < up.length; i++) if (up[i].includes(name)) return i; return -1; };
  const cNo = idx('NO'), cNopol = idx('NOPOL'), cTglN = idx('TGL NPBG'), cNoN = idx('NO NPBG');
  const cDescOut = idx('DESKRIPSI'), cSeriOut = idx('BAN BARU') >= 0 ? idx('BAN BARU') : idx('NO SERI');
  const cFotoOut = idx('FOTO BAN'), cKetOut = idx('KET');
  const cTglR = idx('TGL RI'), cNoR = idx('NO RI');
  const cDescIn = idx('DESKRIPSI', cNoR + 1), cSeriIn = idx('BAN BEKAS') >= 0 ? idx('BAN BEKAS') : idx('NO SERI', cNoR + 1);
  const cFotoIn = idx('FOTO BAN', cNoR + 1), cKetIn = idx('KET', cNoR + 1);
  let inserted = 0, dup = 0;
  db.exec('BEGIN');
  for (let i = 0; i < dataRows.length; i++) {
    const r = dataRows[i];
    const nopol = cleanText(r[cNopol]);
    if (!nopol) continue;
    const v = {
      seq_no: parseNum(r[cNo]) ?? (i + 1), nopol,
      tgl_npbg: parseDateISO(r[cTglN]), ref_npbg: raw(r[cNoN]),
      deskripsi_out: cleanText(r[cDescOut]), no_seri_out: cleanText(r[cSeriOut]),
      foto_out_ref: raw(r[cFotoOut]), ket_out: cleanText(r[cKetOut]),
      tgl_ri: parseDateISO(r[cTglR]), ref_ri: cleanKey(r[cNoR]),
      deskripsi_in: cDescIn >= 0 ? cleanText(r[cDescIn]) : null, no_seri_in: cSeriIn >= 0 ? cleanText(r[cSeriIn]) : null,
      foto_in_ref: cFotoIn >= 0 ? raw(r[cFotoIn]) : null, ket_in: cKetIn >= 0 ? cleanText(r[cKetIn]) : null,
    };
    v.row_hash = rowHash(['tire_dr', v.nopol, v.ref_npbg, v.no_seri_out, v.no_seri_in, v.seq_no]);
    v.source_file = fname; v.source_sheet = sheet; v.source_row = headerIndex + 2 + i; v.upload_batch_id = batchId;
    const res = insertOrIgnore(db, 'tire_deliver_receive', v);
    if (res.inserted) inserted++; else dup++;
  }
  db.exec('COMMIT');
  finishBatch(db, batchId, { total: dataRows.length, inserted, duplicate: dup, status: 'OK' });
  return { inserted, duplicate: dup, sheet };
}

// ─────────────────────────── Asset maintenance ───────────────────────────
export function ingestMaintenance(db, file) {
  const wb = openWorkbook(file), fname = baseName(file), mtime = mtimeOf(file);
  const r = runSheet(db, wb, fname, mtime, 'asset_maint', 'Maintenance Kendaraan', ['no. spk', 'nopol'], {
    tgl_laporan: ['tgl laporan'], no_spk: ['no. spk', 'no spk'], sub_spk: ['sub spk'], nopol: ['nopol'],
    keterangan_awal: ['keterangan awal'], bengkel: ['bengkel'], status: ['status hasil pengerjaan'],
    ref_npbg: ['no. npbg', 'no npbg'], tgl_selesai: ['tgl selesai'], keterangan_akhir: ['keterangan akhir'],
    foto_sebelum_ref: ['foto sebelum'], foto_sesudah_ref: ['foto sesudah'], permintaan_ref: ['permintaan'],
    nama_file_ref: ['nama file 2'], nama_file2_ref: ['nama file'],
  }, 'asset_maintenance', (get, r, seq) => {
    const spk = cleanKey(get(r, 'no_spk'));
    if (!spk) return null;
    return {
      no_spk: spk, sub_spk: cleanText(get(r, 'sub_spk')), nopol: cleanText(get(r, 'nopol')),
      tgl_laporan: parseDateISO(get(r, 'tgl_laporan')), keterangan_awal: cleanText(get(r, 'keterangan_awal')),
      bengkel: cleanText(get(r, 'bengkel')), status: cleanText(get(r, 'status')),
      ref_npbg: cleanKey(get(r, 'ref_npbg')), tgl_selesai: parseDateISO(get(r, 'tgl_selesai')),
      keterangan_akhir: cleanText(get(r, 'keterangan_akhir')),
      foto_sebelum_ref: raw(get(r, 'foto_sebelum_ref')), foto_sesudah_ref: raw(get(r, 'foto_sesudah_ref')),
      permintaan_ref: raw(get(r, 'permintaan_ref')), nama_file_ref: raw(get(r, 'nama_file_ref')), nama_file2_ref: raw(get(r, 'nama_file2_ref')),
    };
  }, (v) => [v.no_spk, v.sub_spk, v.nopol, v.tgl_laporan]);
  return { maint: r };
}

// ─────────────────────────── Manufacturing ───────────────────────────
export function ingestManufacturing(db, file) {
  const wb = openWorkbook(file), fname = baseName(file), mtime = mtimeOf(file);
  const mk = (jenis, sheet, dokCand, subCand) => runSheet(db, wb, fname, mtime, 'mfg', sheet, ['hasil produk', 'proses'], {
    seq_no: ['no'], tgl: ['tanggal'], no_dok: dokCand, sub: subCand, item_no: ['item no'], lokasi: ['lokasi'],
    hasil_produk: ['hasil produk'], no_seri: ['no. seri', 'no seri'], proses: ['proses'],
    keterangan_awal: ['keterangan awal'], status: ['status hasil pengerjaan'],
    ref_npbg: ['no. npbg', 'no npbg'], tgl_selesai: ['tgl selesai'], ref_ri: ['no. ri', 'no ri'],
    keterangan_akhir: ['keterangan akhir'], foto_ref: ['foto hasil'], nama_file_ref: ['nama file'],
  }, 'manufacturing', (get, r, seq) => {
    const hp = cleanText(get(r, 'hasil_produk'));
    if (!hp) return null;
    return {
      jenis, no_dok: cleanKey(get(r, 'no_dok')), sub: cleanText(get(r, 'sub')), item_no: parseNum(get(r, 'item_no')),
      tgl: parseDateISO(get(r, 'tgl')), lokasi: cleanText(get(r, 'lokasi')),
      hasil_produk: hp, hasil_produk_norm: descNorm(hp), no_seri: cleanText(get(r, 'no_seri')),
      proses: cleanText(get(r, 'proses')), keterangan_awal: cleanText(get(r, 'keterangan_awal')),
      status: cleanText(get(r, 'status')), ref_npbg: cleanKey(get(r, 'ref_npbg')),
      tgl_selesai: parseDateISO(get(r, 'tgl_selesai')), ref_ri: cleanKey(get(r, 'ref_ri')),
      keterangan_akhir: cleanText(get(r, 'keterangan_akhir')),
      foto_ref: raw(get(r, 'foto_ref')), nama_file_ref: raw(get(r, 'nama_file_ref')),
    };
  }, (v) => [v.jenis, v.no_dok, v.sub, v.item_no, v.hasil_produk_norm]);

  const ma = mk('MA', 'Manufaktur & Assembly', ['no. manufaktur & assembly', 'no manufaktur'], ['sub ma']);
  const mj = mk('MJ', 'Manufaktur & Jasa Lain-Lain', ['no. manufaktur & jasa', 'no manufaktur'], ['sub mj']);
  return { ma, mj };
}

// ─────────────────────────── Used returns (Pengembalian Bekas) ───────────────────────────
export function ingestUsedReturns(db, file) {
  const wb = openWorkbook(file), fname = baseName(file), mtime = mtimeOf(file);

  // Spare Part — WIDE: unpivot part-type columns
  const wideBatch = newBatch(db, { filename: fname, module: 'used_returns:Spare Part', source_mtime: mtime });
  {
    const rows = sheetRows(wb, 'Spare Part');
    const { headerIndex, header, dataRows } = detectHeader(rows, ['no npbg', 'no ri']);
    const up = header.map((h) => h.replace(/\s+/g, ' ').trim());
    const ci = (n) => up.findIndex((h) => h.toUpperCase().includes(n));
    const cTglN = ci('TGL NPBG'), cNoN = ci('NO NPBG'), cStatus = ci('STATUS'), cTglR = ci('TGL RI'), cNoR = ci('NO RI'), cKet = ci('KETERANGAN');
    const keyCols = new Set([ci('NO'), cTglN, cNoN, cStatus, cTglR, cNoR, cKet].filter((x) => x >= 0));
    const partCols = up.map((h, i) => ({ h, i })).filter(({ h, i }) => h && !keyCols.has(i) && i > cNoR && i < (cKet >= 0 ? cKet : up.length));
    let inserted = 0, dup = 0, neg = 0;
    db.exec('BEGIN');
    for (let r = 0; r < dataRows.length; r++) {
      const row = dataRows[r];
      const refNpbg = cleanKey(row[cNoN]), refRi = cleanKey(row[cNoR]);
      if (!refNpbg && !refRi) continue;
      for (const { h, i } of partCols) {
        const qty = parseNum(row[i]);
        if (qty === null) continue;
        if (qty < 0) neg++;
        const v = {
          format: 'WIDE', ref_npbg: refNpbg, tgl_npbg: parseDateISO(row[cTglN]),
          ref_ri: refRi, tgl_ri: parseDateISO(row[cTglR]), status: cleanText(row[cStatus]),
          part_type: h, deskripsi: null, deskripsi_norm: null, qty, satuan_raw: null,
          keterangan: cleanText(row[cKet]), foto_keluar_ref: null, foto_terima_ref: null,
          row_hash: rowHash(['used_returns', 'WIDE', refNpbg, refRi, h, qty, r]),
          source_file: fname, source_sheet: 'Spare Part', source_row: headerIndex + 2 + r, upload_batch_id: wideBatch,
        };
        const res = insertOrIgnore(db, 'used_returns', v);
        if (res.inserted) inserted++; else dup++;
      }
    }
    db.exec('COMMIT');
    if (neg) note(db, wideBatch, 'column', `${neg} nilai qty negatif (shortage bekas, dipertahankan)`);
    finishBatch(db, wideBatch, { total: dataRows.length, inserted, duplicate: dup, status: 'OK' });
  }

  // Spare Part Lain — LONG
  const long = runSheet(db, wb, fname, mtime, 'used_returns', 'Spare Part Lain', ['no npbg', 'deskripsi barang'], {
    tgl_npbg: ['tgl npbg'], ref_npbg: ['no npbg'], deskripsi: ['deskripsi barang'], qty: ['kuantitas'],
    satuan: ['satuan'], status: ['status'], ref_ri: ['no ri'], keterangan: ['keterangan'],
    foto_keluar_ref: ['foto keluar'], foto_terima_ref: ['foto terima'],
  }, 'used_returns', (get, r, seq) => {
    const d = cleanText(get(r, 'deskripsi'));
    if (!d) return null;
    return {
      format: 'LONG', ref_npbg: cleanKey(get(r, 'ref_npbg')), tgl_npbg: parseDateISO(get(r, 'tgl_npbg')),
      ref_ri: cleanKey(get(r, 'ref_ri')), tgl_ri: null, status: cleanText(get(r, 'status')),
      part_type: null, deskripsi: d, deskripsi_norm: descNorm(d), qty: parseNum(get(r, 'qty')),
      satuan_raw: cleanText(get(r, 'satuan')), keterangan: cleanText(get(r, 'keterangan')),
      foto_keluar_ref: raw(get(r, 'foto_keluar_ref')), foto_terima_ref: raw(get(r, 'foto_terima_ref')),
    };
  }, (v, srcRow) => ['LONG', v.ref_npbg, v.ref_ri, v.deskripsi_norm, v.qty, srcRow]);

  return { long };
}
