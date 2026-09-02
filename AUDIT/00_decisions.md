# STOCKWISE — Fase 0: Keputusan & Asumsi

Dokumen ini mengunci jawaban sementara atas **P1–P8 (Data Conflicts)** dan **10 poin NEED REVIEW**
dari `DATA & CODE AUDIT REPORT`, supaya pembangunan bisa jalan tanpa menunggu.

**Status: ASUMSI KERJA — semua bisa dibatalkan/diganti tanpa membuang hasil kerja.**
Setiap asumsi ditandai `[A-n]` dan direferensikan di kode (`# see AUDIT/00_decisions.md [A-3]`).

Prinsip yang dipegang:
- Data aktual Excel > spec (RULE 2 / #43).
- Tidak ada data/kolom/sheet dihapus (RULE 3–5).
- Tidak ada blind insert kumulatif — UPSERT by `row_hash` (RULE 7).
- Fuzzy match tidak pernah otomatis jadi match final (RULE 8).
- Nilai yang tidak diketahui = `NULL` + flag, **bukan `0`** (RULE 11, 13).
- `app.py` + fitur lamanya dipertahankan (RULE 10). Satu-satunya tambahan: `_sync_to_db()` —
  menulis master yang diupload/diedit ke `stockwise.db` supaya halaman lain ikut kepakai; dibungkus
  try/except sehingga tidak pernah membuat dashboard lama gagal. Sistem baru = halaman di `pages/`.

---

## Konflik data

### [A-1] Sumber Safety Stock / Lead Time / MIN PR / √LT
`DATABASE UTAMA` kolom `SAFETY STOCK`, `MIN PR`, `√LT` **100% kosong**. Nilainya diambil dari
13 sheet `SAFETY STOCK <KATEGORI>` di `DATA.xlsx`, di-key oleh **normalized `ITEM DESCRIPTION`**
(tidak ada Kode Barang di sheet itu).

- 13 sheet diperlakukan sebagai **satu tabel logis** `safety_stock_params` (kolom `source_sheet` disimpan).
- Bila 1 deskripsi-normal muncul di >1 sheet dengan **SS atau LT berbeda** → baris paling lengkap
  dipakai sebagai default (`dq_flag = SS_CONFLICT`), dan **semua varian per-sheet disimpan di
  `safety_stock_variants`**. Halaman **Safety Stock Review** menampilkan varian bersebelahan; user
  memilih sheet yang benar → `safety_stock_params` di-update + `chosen_sheet`/`resolved_by` diisi +
  `dq_flag` dihapus. Lalu **Hitung ulang** di Data Management.
- Master item tanpa baris safety-stock → `safety_stock = NULL`, `lead_time_days = NULL`.
  Di UI ditampilkan **"SS belum tersedia"**, tidak pernah diperlakukan `0`.
- Kolom bulanan `Agt..Juli` → tabel `monthly_consumption` (per deskripsi, period = bulan).
- **Rumus SS/√LT/MIN PR internal sheet TIDAK direkayasa-ulang.** Nilai diambil apa adanya dari sel.
  Bila nanti dikonfirmasi rumusnya, `calc/safety_stock.py` akan menghitung ulang; sekarang = passthrough.

### [A-2] Nama sheet master
Sheet master dikenali dari daftar kandidat: `database utama`, `data`, `master`, plus fallback
"sheet pertama dengan signature kolom `kode barang` + `deskripsi barang`". Header di-scan 1–10.

### [A-3] Status stok — model diperluas, bukan diganti
`utils/calculations.py` lama (AMAN / TIDAK AMAN / BEP) **tetap dipertahankan apa adanya** untuk
`app.py` legacy. Sistem baru memakai dimensi `stock_status` yang lebih rinci (spec #13):

| stock_status | syarat |
|---|---|
| `UNKNOWN` | Sisa Stok tidak diketahui (sel kosong / tak terparse) |
| `OUT_OF_STOCK` | Sisa Stok = 0 **dan** Safety Stock diketahui & > 0 |
| `TIDAK_AMAN` | 0 < Sisa Stok < Safety Stock |
| `AMAN` | Sisa Stok ≥ Safety Stock (SS diketahui) |
| `BEP` | Sisa Stok = 0 **dan** (Safety Stock = 0 atau tidak diketahui) |

`CRITICAL` = flag turunan, bukan status: `TIDAK_AMAN` **dan** (`defisit ≥ P75 defisit item TIDAK_AMAN`
**atau** `priority_level = HIGH`). Threshold P75 dihitung dari populasi TIDAK_AMAN yang punya SS.

### [A-4] Skor Kesehatan
Dashboard baru memakai definisi spec #11: `stock_health = count(AMAN) / count(item dengan SS diketahui) × 100`,
1 desimal. Ditampilkan dengan catatan `"berdasarkan N item yang punya Safety Stock"` karena saat ini
SS hanya diketahui untuk sebagian kecil katalog. Nilai legacy `(AMAN+BEP)/total` tetap dipakai `app.py` lama.

### [A-5] Threshold Lead Time
`utils/sw_config.py`:
```
LEAD_TIME_HIGH_THRESHOLD_DAYS = 14   # PENDING konfirmasi bisnis — bukan auto-derive
```
Tidak di-generate dari P75 (spec: "jangan mengarang threshold tanpa persetujuan"). Satu tempat, eksplisit.

### [A-6] Matching tanpa alias
`Nama Alias` di master hanya berisi literal `"Tidak"` → dianggap **tidak ada alias**.
LEVEL 2 (alias) tetap diimplementasikan tapi tabel `item_aliases` kosong. Nilai `"Tidak"`/`"Ya"` di
kolom itu diperlakukan sebagai bukan-alias (di-drop saat ingest, dicatat di `import_notes`).

### [A-7] File #8 `Tracking Pengembalian Bekas.xlsx` — MASUK SCOPE
Alasan: data operasional nyata, jelas menaut ke `No NPBG` & `No RI`. Modul `used_returns`.
- `Spare Part` (wide) → di-unpivot: 1 baris per (dokumen × tipe_part) dengan `qty`, format=`WIDE`.
- `Spare Part Lain` (long) → 1 baris per item, format=`LONG`.
- Qty negatif **dipertahankan** (artinya shortage barang bekas), tidak di-clamp.

### [A-8] Satuan Lead Time = hari
Nilai di kolom `LEAD TIME` (5, 7, 14, 21, 30, ...) diasumsikan **hari**. `√LT` (jika ada) diasumsikan
`sqrt(lead_time_bulan)` mengikuti model safety-stock; tidak dihitung ulang (lihat [A-1]).

---

## NEED REVIEW

### [A-9] Kode Barang blank / duplikat
- 1 baris `Kode Barang` kosong → tetap dibuat `master_item` (`kode_barang = NULL`), `dq_flag = KODE_MISSING`.
- 6 kode dobel (`AUT.0631`, `MAI.0789`, `MAI.0792`, `HHN.0139`, `BSP.2832`, `SSP.2820`) → **kedua baris disimpan**,
  masing-masing `master_item_id` sendiri, `dq_flag = KODE_DUPLICATE`. Tidak di-merge.

### [A-10] Deskripsi berulang 126× (`(REFURBHISED) FLEXIBLE HOSE RUBBER R2 3/8"...`)
Semua baris disimpan apa adanya. `dq_flag = DESC_MASS_DUPLICATE` pada tiap baris grup itu.
Matching transaksi ke grup ini → otomatis `POSSIBLE_MATCH` (ambigu, > 1 kandidat), masuk review.

### [A-11] Duplikat baris transaksi (NPBG 139, PPB 95, RI 134)
Dalam 1 batch upload: baris dengan `row_hash` identik → hanya yang pertama di-insert, sisanya
dihitung sebagai `duplicate` di ringkasan batch. Antar batch: UPSERT (baris lama tidak digandakan).
`row_hash = sha1(module | no_dokumen | line_no | desc_norm | qty | tgl_iso)`.

### [A-12] Sheet `STPP → Maintenance` kosong
Di-ingest, menghasilkan 0 baris, dicatat `import_notes: "sheet Maintenance kosong (0 baris)"`. Struktur tetap dikenali.

### [A-13] `Ban Luar BPN` & `Deliver & Receive Ban SIG-BPN`
Schema beda material → tabel sendiri: `tire_bpn_snapshots`, `tire_deliver_receive`.
Tidak dipaksa masuk `tire_transactions`. Kolom nama-dobel di Deliver&Receive di-suffix `_out` / `_in`.

### [A-14] `cetak`, `Sheet2`, `Sheet6` di DATA.xlsx
Di-skip (derived / print / kosong). Dicatat di `import_notes`.

### [A-15] `Export List_Klasifikasi` di NPBG.xlsx
Di-skip (tabel analisa lepas). Dicatat.

### [A-16] Kolom foto (`=DISPIMG(...)`, `"Open File"`, nama file)
Disimpan sebagai **teks referensi** apa adanya di kolom `*_ref`. Tidak pernah dirender sebagai URL/gambar.
Sentinel `-`, `ORIGIN`, string kosong pada kolom kunci → `NULL`.

### [A-17] `No PO`
Tidak ada sheet PO. `po_derived` dibangun dari agregasi `ri_lines` (distinct `no_po` + vendor + total qty).
Status PO diturunkan, bukan dibaca.

### [A-18] Satuan / UoM tidak konsisten antar file
UoM master dipertahankan sebagai kebenaran item. `Satuan` transaksi disimpan apa adanya per baris
(`satuan_raw`) untuk audit; konversi antar-satuan TIDAK dilakukan (butuh tabel konversi yang belum ada).

---

## Yang tetap perlu jawaban manajemen (tidak menghalangi build, tapi memengaruhi angka final)

1. Rumus persis `SS`, `√LT`, `MIN PR`, `1/3/6/12 BLN` di sheet `SAFETY STOCK *` — [A-1] sekarang passthrough.
2. Apakah 13 sheet itu memang harus per-kategori (bukan gabungan)?  — [A-1]
3. Status BEP dipertahankan atau dihapus? — [A-3]
4. Definisi Skor Kesehatan final. — [A-4]
5. Threshold Lead Time tinggi (hari). — [A-5]
6. Threshold CRITICAL. — [A-3] sekarang P75 defisit.
7. Satuan Lead Time. — [A-8]
8. File #8 benar in-scope? — [A-7]
