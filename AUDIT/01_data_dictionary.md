# STOCKWISE — Data Dictionary (Fase 1)

Peta **kolom Excel sumber → kolom database**. Nama & tipe kolom DB yang otoritatif ada di
[`db/schema.sql`](../db/schema.sql); dokumen ini menghubungkannya ke sumbernya dan menandai transformasi.

Konvensi:
- `*_norm` / `*_core` = kunci matching (uppercase, rapikan spasi/tanda baca; `_core` juga buang tag `(BEKAS)`/`(REFURBISHED)`).
- `*_raw` = nilai apa adanya dari sel, disimpan untuk audit.
- `*_ref` = referensi file/foto (`=DISPIMG(...)`, `"Open File"`, nama file) — **bukan URL**, tidak dirender.
- Sentinel (`-`, `--`, `N/A`, `ORIGIN`, kosong) → `NULL` di kolom kunci.
- Tanggal → `YYYY-MM-DD` (date-only; offset LMT parser dikoreksi +7 jam).
- Angka → titik desimal; `"STOK 15 PCS"` → `15`; `"STOK O PCS"` → `0`.

---

## 1. `DATA.xlsx` → `DATABASE UTAMA` → `master_items` (+ `inventory_snapshots`, `item_aliases`)

| Kolom Excel | Kolom DB | Transformasi |
|---|---|---|
| Kode Barang | `master_items.kode_barang` | trim; blank → NULL + `dq_flags=KODE_MISSING`; duplikat → `KODE_DUPLICATE` |
| Kategori Induk / Anak 1..3 | `kategori_induk`, `kategori_anak_1..3` | trim |
| Deskripsi Barang | `deskripsi` + `deskripsi_norm` + `deskripsi_core` | norm/core untuk matching |
| UoM | `uom` | trim |
| Perlu Blueprint? | `perlu_blueprint` | `Ya`→1, `Tidak`→0, lain→NULL |
| Nama Alias | `item_aliases.alias` | hanya jika **bukan** `Ya`/`Tidak` (isinya placeholder — [A-6]); 2.361 nilai di-drop |
| LETAK GUDANG / LETAK RAK | `letak_gudang`, `letak_rak` | trim |
| BLUEPRINT IMG / DETAIL PDF / 3D VIEW | `blueprint_img_ref` / `_pdf_ref` / `_3d_ref` | teks referensi (IMG & PDF 100% kosong) |
| SISA STOK (22/08/2026) | `inventory_snapshots.sisa_stok_raw` + `sisa_stok_num` + `sisa_stok_known` | `snapshot_date` diambil dari tanggal di nama kolom; 71% kosong → `known=0` |
| LEAD TIME / √LT / SAFETY STOCK / MIN PR | — (kosong di sheet ini) | **diambil dari sheet `SAFETY STOCK *`**, lihat §2 |

`master_items.id` = `ITEM-000001..` (urut baris). `Selisih/Status/Defisit/Priority/Rekomendasi` **tidak** dari Excel — dihitung `calc_results`.

## 2. `DATA.xlsx` → 13× `SAFETY STOCK <KATEGORI>` → `safety_stock_params` + `monthly_consumption`

Header 2 baris (row 1 grup merge, row 2 sub-label). Key = `ITEM DESCRIPTION` (tanpa Kode Barang).

| Kolom Excel | Kolom DB | Catatan |
|---|---|---|
| ITEM DESCRIPTION | `item_description` + `item_desc_norm` (UNIQUE) | join ke master via `deskripsi_norm` |
| LT | `lead_time_days` | diasumsikan hari [A-8] |
| √LT | `sqrt_lt` | passthrough |
| SS | `safety_stock` | passthrough — **rumus belum direkayasa ulang [A-1]** |
| MIN PR | `min_pr` | passthrough |
| 1/3/6/12 BLN | `avg_1_bln`..`avg_12_bln` | rata-rata pengeluaran |
| Agt..Juli (12 kolom) | `monthly_consumption` (1 baris per desc×bulan) | Agt 2025–Juli 2026 → `period_ym` |

13 sheet digabung jadi 1 tabel logis; jika nilai beda antar-sheet untuk deskripsi sama → `dq_flag=SS_CONFLICT`,
ambil baris paling lengkap. **6.211 dari 8.736 punya konflik** → butuh review bisnis.

## 3. `1. PPB - RI.xlsx`

### `PPB` (header row 3) → `ppb_lines`
`No PPB`→`no_ppb` · `Tgl PPB`→`tgl_ppb` · `Deskripsi Barang`→`deskripsi(+norm)` · `Kuantitas`→`qty` ·
`Satuan`→`satuan_raw` · `Peminta`/`Divisi`/`Keterangan` · `Status`→`status` (Completed/Requested/Amend/Close/Shortage/Error) ·
`cntRI/sumRI/cntAmend/cntClose`→`cnt_ri/sum_ri/cnt_amend/cnt_close`. `line_no` = urutan item dalam satu No PPB.
`row_hash = sha1(ppb | no_ppb | deskripsi_norm | qty | tgl)`.

### `RI` (header row 3, kolom A kosong) → `ri_lines`
`No RI`→`no_ri` · `Tgl RI`→`tgl_ri` · `Deskripsi Barang` · `Kuantitas`→`qty` (diterima) · `Satuan` ·
`No PPB`→`no_ppb` (sentinel→NULL) · `No PO`→`no_po` · `Vendor` · `No Surat Jalan`→`no_surat_jalan` · `Pemeriksa` · `Keterangan`.

### `PPB Perubahan` (header row 3) → `ppb_changes`
`No PPB` · `Tgl Perubahan` · `Deskripsi Barang` · `Kuantitas` · `Satuan` · `Peminta` · `Divisi` ·
`Tipe Perubahan`→`tipe_perubahan` (AMEND/CLOSE) · `Keterangan`.

### `po_derived` (turunan, bukan sheet)
Agregasi `ri_lines` per `no_po`: `vendor`, `first_ri_date`, `last_ri_date`, `ri_count`, `total_qty`.

## 4. `2. NPBG.xlsx` → `NPBG` (header row 3, kolom A kosong) → `npbg_lines`
`No NPBG`→`no_npbg` · `Tgl NPBG` · `Tipe NPBG`→`tipe` · `Klasifikasi`→`klasifikasi` (13 nilai: UMUM/PROYEK/STPP/LEND / BORROW/MANUFAKTUR/MAINTENANCE */JASA) ·
`Pelanggan` · `Nama Proyek` · `No Seri / Nopol`→`no_seri_nopol` · `Deskripsi Barang` · `Kuantitas`→`qty` (bisa 0) ·
`Satuan` · `Peminta` · `Dikeluarkan Oleh`→`dikeluarkan_oleh` · `Divisi` · `Keterangan`. Sheet `Export List_Klasifikasi` di-skip.

## 5. `3. Tracking Borrow & Lend.xlsx` → `borrow_lend`
`Lend` (header row 4) `arah=LEND`: `Tgl Pinjam`→`tgl_pinjam` · `Deskripsi Barang` · `Kuantitas`→`qty` · `Satuan` ·
`Peminta`→`pihak` · `Keperluan` · `Est. Pinjam (hari)`→`est_hari` · `Tanda Keluar`→`ref_keluar` (→NPBG) · `Status` ·
`Tanda Kembali`→`ref_kembali` (→RI) · `Tgl Kembali` · `Keterangan Kembali`→`keterangan`.
`Borrow` (header row 3) `arah=BORROW`: `Vendor`→`pihak` · `Tanda Terima`→`ref_kembali` · `Tanda Keluar`→`ref_keluar` · dst.

## 6. `4. Tracking STPP.xlsx` → `stpp`
`STPP` (header row 4): `No Seri`→`no_seri` (SN-nnnn) · `Deskripsi Barang` · `Kuantitas`→`qty` · `Satuan` · `Peminta` ·
`Penempatan` · `Tgl NPBG` · `No. NPBG`→`ref_npbg` · `Item No`→`item_no` · `Status` · `Tgl RI` · `Tanda Kembali`→`ref_kembali` ·
`Bukti Keluar`/`Bukti Terima`/`Nama File(.#ext)`/`(.#ext2)`→`*_ref` · `Keterangan Kembali`→`keterangan`.
Sheet `Maintenance` (header row 2): 16 baris terisi, sisanya kosong; `status='MAINTENANCE'`.

## 7. `5. Tracking Ban Luar.xlsx`
`Ban Luar` (header row 3) → `tire_transactions`: `Nopol (Kendaraan)`→`nopol` · `Tgl NPBG` · `No NPBG`→`ref_npbg` (raw, bisa `ORIGIN`) ·
`Deskripsi Ban Baru`(+norm) · `No Seri Baru`→`no_seri_baru` · `Ban`→`ban_pos` · `Pergantian` · `Status` · `Tgl RI` · `No. RI`→`ref_ri` ·
`Deskripsi Ban Lama` · `No Seri Lama` · `Foto Ban (Out-OLD)2`/`Foto Ban (In)`→`foto_*_ref` · `Keterangan Keluar/Kembali`.
`Ban Luar BPN` (header row 3) → `tire_bpn_snapshots`: `TANGGAL CUT OFF`→`tanggal_cut_off` · `NOPOL` · `DESKRIPSI BAN` · `NO SERI` · `Foto`→`foto_ref` · `KETERANGAN`.
`Deliver & Receive Ban SIG-BPN` (header row 3, kolom nama dobel) → `tire_deliver_receive`: kolom sisi kirim `*_out`, sisi terima `*_in` (dipetakan posisional).

## 8. `6. Tracking Maintenance Assets.xlsx` → `Maintenance Kendaraan` (header row 3) → `asset_maintenance`
`No. SPK`→`no_spk` · `Sub SPK`→`sub_spk` (PK = SPK+Sub) · `Nopol (Kendaraan)`→`nopol` · `Tgl Laporan` · `Keterangan Awal` ·
`Bengkel` · `Status Hasil Pengerjaan`→`status` · `No. NPBG`→`ref_npbg` (material dipakai) · `Tgl Selesai Pengerjaan`→`tgl_selesai` ·
`Keterangan Akhir` · `Foto Sebelum/Sesudah`/`Permintaan`/`Nama File`/`Nama File 2`→`*_ref`.

## 9. `7. Tracking Manufaktur & Assembly.xlsx` → `manufacturing`
`Manufaktur & Assembly` (header row 3) `jenis=MA`: `No. Manufaktur & Assembly`→`no_dok` · `Sub MA`→`sub` · `Item No`→`item_no` ·
`Tanggal`→`tgl` · `Lokasi` · `Hasil Produk`→`hasil_produk`(+norm — dimatch ke master) · `No. Seri`→`no_seri` · `Proses` ·
`Keterangan Awal` · `Status Hasil Pengerjaan`→`status` · `No. NPBG`→`ref_npbg` · `Tgl Selesai Pengerjaan`→`tgl_selesai` · `No. RI`→`ref_ri` · `Keterangan Akhir`.
`Manufaktur & Jasa Lain-Lain` (header row 3) `jenis=MJ`: sama, `No. Manufaktur & Jasa`→`no_dok`, `Sub MJ`→`sub`.

## 10. `8. Tracking Pengembalian Bekas.xlsx` → `used_returns` ([A-7])
`Spare Part` (header row 4, **wide**) → di-unpivot: 1 baris per (dokumen × tipe part). `format='WIDE'`,
`No NPBG`→`ref_npbg` · `No RI`→`ref_ri` · `Status` · nama kolom tipe part (`Bonit BR`, `Mur CS`, `Baut GI`, …)→`part_type` · nilai→`qty` (**bisa negatif** = shortage) · `Keterangan`.
`Spare Part Lain` (header row 3, **long**) → 1 baris per barang. `format='LONG'`, `Deskripsi Barang`(+norm) · `Kuantitas`→`qty` · `Satuan` · `Foto Keluar/Terima`→`*_ref`.

---

## Bookkeeping (semua ingest)

`upload_batches` (1 per file×modul) · `import_errors` (kolom hilang / tipe salah) · `import_notes` (sheet dilewati, baris kosong, nilai di-drop).
Tiap baris transaksi: `source_file`, `source_sheet`, `source_row` (nomor baris Excel), `upload_batch_id`, `row_hash`.
