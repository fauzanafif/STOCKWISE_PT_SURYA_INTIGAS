# STOCKWISE

**Inventory Intelligence System — PT Surya Inti Gas.**

Satu aplikasi Streamlit. Halaman utama = workspace master inventory (upload, edit, dashboard,
chart, insight, export — seperti sebelumnya). Halaman-halaman berikutnya di sidebar menambah:
Procurement (PPB→PO→RI), Pemakaian (NPBG), Tracking, pencocokan barang, resolusi safety stock,
dan upload semua Excel sekaligus. Semua membaca satu database (`stockwise.db`) dan setiap angka
bisa ditelusuri ke baris Excel aslinya.

```
streamlit run app.py
```

---

## Daftar Isi

- [Cara kerja singkat](#cara-kerja-singkat)
- [Instalasi](#instalasi)
- [FLOW — cara pakai](#flow--cara-pakai)
- [Halaman](#halaman)
- [File Excel yang diupload](#file-excel-yang-diupload)
- [Arsitektur & struktur kode](#arsitektur--struktur-kode)
- [Model data](#model-data)
- [Rumus / calculation engine](#rumus--calculation-engine)
- [Konsep stok](#konsep-stok)
- [Tes](#tes)
- [Status & batasan](#status--batasan)

---

## Cara kerja singkat

```
   app.py  (halaman utama)                    pages/  (menu sidebar)
   upload master DATA.xlsx                     Procurement · Pemakaian · Tracking ·
   edit di tabel, chart, insight, export       Detail Barang · Cocokkan Barang ·
        │                                      Safety Stock · Kelola Data · Tanya
        │  setiap upload/edit → sync                    │
        ▼                                               ▼
   ┌──────────────────  stockwise.db  ──────────────────┐
   │  SQLite, satu file, .gitignore. SINGLE SOURCE OF   │
   │  TRUTH. Diisi dari: (a) master via app.py,         │
   │  (b) 9 file via Kelola Data / CLI.                 │
   └──────────────────────┬────────────────────────────┘
                          ▼
              CALCULATION ENGINE  (utils/calc_engine.py)
       selisih · defisit · status · priority · incoming ·
       projected stock · rata-rata pemakaian → calc_results
                          ▼
              semua halaman baca calc_results / v_inventory
```

- Excel = *import layer*. `stockwise.db` = *sumber kebenaran*.
- Halaman tidak pernah parsing Excel saat render (spec §22, §35).
- ETL (baca Excel, matching, dedup) ditulis di Node (`tools/*.mjs`) karena bisa dites langsung ke
  data asli. Logika normalisasi & kalkulasi dicerminkan di Python (`utils/textnorm.py`,
  `utils/calc_engine.py`) untuk dipakai di dalam app — **harus tetap sinkron** dengan versi `.mjs`.

---

## Instalasi

Butuh **Python 3.12+** dan **Node.js 22+** (Node punya `node:sqlite` bawaan).

```bash
pip install -r requirements.txt          # dependency Python
cd tools && npm install && cd ..          # dependency Node (sekali) — untuk ETL

# opsional: isi database dari folder DATAFIX/ untuk lihat dengan data lengkap
node --experimental-sqlite tools/build_stockwise_db.mjs      # ~35 detik

streamlit run app.py                     # buka http://localhost:8501
```

Tanpa langkah `build_stockwise_db.mjs`, cukup buka app, upload master Excel di halaman utama, lalu
upload sisanya di **Kelola Data**.

---

## FLOW — cara pakai

### Setup pertama kali

```
1. Buka app.py (halaman utama) → upload DATA.xlsx di sidebar
        → katalog barang + sisa stok masuk, otomatis tersimpan ke stockwise.db

2. Menu "Kelola Data" → tab Upload → tarik 8 file lainnya sekaligus → "Proses semua"
        → sistem kenali tiap file, proses master dulu, buang duplikat, cocokkan barang,
          hitung ulang. Sekali klik.

3. Menu "Cocokkan Barang" → "Terima massal ≥ 0.98" untuk yang jelas, review sisanya
        (barang transaksi ↔ master; ~55% cocok otomatis)

4. Menu "Safety Stock" → untuk barang yang nilai SS/Lead Time-nya beda antar sheet,
        pilih sheet yang benar
```

Langkah 3–4 **bisa dicicil**. Dashboard tetap jalan; barang yang belum beres statusnya jujur
(`belum bisa dinilai` / `belum di-match`), bukan ditebak.

### Pemakaian bulanan

Tarik file Excel bulan ini (kumulatif penuh) ke **Kelola Data ▸ Upload ▸ Proses semua**.
UPSERT by `row_hash` → baris lama tidak digandakan, baris baru ditambahkan, status dokumen yang
berubah ikut ter-update (spec §21). Tidak ada "hapus data lama".

### Setelah review

Keputusan di **Cocokkan Barang** / **Safety Stock** langsung tersimpan. Di dashboard muncul tombol
**↻ Terapkan sekarang** → hitung ulang sekali, semua angka ikut. (Aksi massal hitung ulang sendiri.)

### Menjawab pertanyaan manajemen

- **Tanya STOCKWISE** — pertanyaan preset ("barang apa yang habis?", "PPB mana belum selesai?",
  "divisi mana paling banyak pakai?", "barang dipinjam siapa?") + mode **tanya satu barang**
  (sisa · safety · defisit · sudah PPB? · PO/diterima? · outstanding · pemakaian).
- **Drill-down** — klik baris di Procurement atau cari di Detail Barang → view 360° per barang
  dengan **lineage ke baris Excel** (file, sheet, nomor baris).

---

## Halaman

| Sidebar | Isi |
|---|---|
| **app** (utama) | **Inventory Master**: upload master, edit di `st.data_editor`, 7 chart, insight otomatis, tab Procurement (di atas master), export Excel berwarna / PDF / CSV, download template. *(Semua fitur lama dipertahankan.)* |
| 🚚 Procurement | Priority Buy List (klik baris → detail) · status **PPB → PO → RI** · outstanding per PPB |
| 📉 Pemakaian | konsumsi NPBG: trend bulanan, top barang, per divisi / klasifikasi / pelanggan / proyek |
| 📍 Tracking | Borrow/Lend · STPP · Ban Luar (+BPN, +Deliver/Receive) · Maintenance Kendaraan · Manufaktur & Assembly · Pengembalian Bekas — semua bisa dicari |
| 🔎 Detail Barang | 360° per barang: stok, PPB/RI, pemakaian per bulan, tracking, blueprint, **lineage ke baris Excel**; tombol kembali |
| 🤝 Cocokkan Barang | antrian matching + terima massal + buat master item dari barang baru |
| 🛡️ Safety Stock | untuk barang dengan SS/LT beda antar 13 sheet: lihat semua varian, pilih yang benar |
| 🗄️ Kelola Data | Upload (multi-file, 1 klik) · Riwayat proses · Kualitas Data · Hitung ulang · Rebuild |
| 💬 Tanya | pertanyaan preset + mode tanya satu barang |

---

## File Excel yang diupload

9 file, satu per modul. Dikenali otomatis dari nama & sheet-nya (`tools/lib/detect_module.mjs`).

| Modul | File | Sheet yang dibaca |
|---|---|---|
| Master Inventory | `DATA.xlsx` | `DATABASE UTAMA` + 13 × `SAFETY STOCK *` |
| Procurement | `1. PPB - RI.xlsx` | `PPB`, `RI`, `PPB Perubahan` |
| Pemakaian (NPBG) | `2. NPBG.xlsx` | `NPBG` |
| Borrow & Lend | `3. Tracking Borrow & Lend.xlsx` | `Lend`, `Borrow` |
| STPP | `4. Tracking STPP.xlsx` | `STPP`, `Maintenance` |
| Ban Luar | `5. Tracking Ban Luar.xlsx` | `Ban Luar`, `Ban Luar BPN`, `Deliver & Receive Ban SIG-BPN` |
| Maintenance Kendaraan | `6. Tracking Maintenance Assets.xlsx` | `Maintenance Kendaraan` |
| Manufaktur & Assembly | `7. Tracking Manufaktur & Assembly.xlsx` | `Manufaktur & Assembly`, `Manufaktur & Jasa Lain-Lain` |
| Pengembalian Bekas | `8. Tracking Pengembalian Bekas.xlsx` | `Spare Part`, `Spare Part Lain` |

- Master (`DATA.xlsx`) diproses duluan. Urutan lain bebas, boleh dicicil.
- Sheet `cetak`, `Sheet2`, `Sheet6`, `Export List_Klasifikasi`, dan tiap `Dropdown List` diabaikan.
- Header boleh di baris 2/3/4 — dideteksi per-sheet dari signature kolom.
- `Sisa Stok` boleh teks (`STOK 15 PCS`, `STOK O PCS` → 0). Kosong = *belum terdata*, **bukan 0**.

CLI: `node --experimental-sqlite tools/ingest_batch.mjs --dir <folder>` (banyak file) ·
`tools/ingest_one.mjs <modul> <file>` (satu) · `tools/build_stockwise_db.mjs` (rebuild penuh dari `DATAFIX/`).

---

## Arsitektur & struktur kode

```
STOCKWISE/
├── app.py                    entry point — Inventory Master workspace (fitur lama, + sync ke DB)
├── pages/                    halaman tambahan (Streamlit folder-based multipage)
│   1_🚚_Procurement.py  2_📉_Pemakaian.py  3_📍_Tracking.py  4_🔎_Detail_Barang.py
│   5_🤝_Cocokkan_Barang.py  6_🛡️_Safety_Stock.py  7_🗄️_Kelola_Data.py  8_💬_Tanya.py
├── components/               kpi.py · charts.py · data_editor.py   (dipakai app.py — tetap)
├── utils/
│   ├── calculations.py       rumus lama (dipakai app.py — tetap)
│   ├── excel_handler.py      parser master Excel (dipakai app.py — tetap)
│   ├── insights.py · pdf_export.py · recommendations.py · theme.py   (dipakai app.py — tetap)
│   ├── database.py           koneksi SQLite + read_df
│   ├── textnorm.py           normalisasi (mirror tools/lib/textnorm.mjs)
│   ├── calc_engine.py        calculation engine (mirror tools/lib/calc.mjs)
│   ├── queries.py            semua query halaman
│   ├── master_sync.py        app.py → stockwise.db (dipanggil setelah recalculate)
│   ├── ingest.py             panggil Node ETL untuk upload lewat UI
│   ├── report_pdf.py         export laporan PDF
│   ├── dashboard_ui.py       chrome halaman: page_header, KPI, badge, banner "Terapkan"
│   └── sw_config.py          path + parameter bisnis
├── tools/                    ETL Node — `npm install` di sini
│   ├── build_stockwise_db.mjs   bootstrap: DATAFIX/ → stockwise.db + AUDIT/03
│   ├── ingest_batch.mjs         banyak file, auto-detect modul
│   ├── ingest_one.mjs           satu file
│   ├── smoke_test.py            tes query/calc/PDF (Python)
│   ├── test_pages.py            tes render app.py + semua halaman (Python)
│   └── lib/                     parser per modul, matcher, calc, detect_module
├── db/schema.sql            skema SQLite
├── AUDIT/                   00 keputusan/asumsi · 01 data dictionary · 02 ERD · 03 laporan ingest
├── DATAFIX/                 9 workbook sumber
└── stockwise.db            dibuat saat build/upload (gitignore)
```

`streamlit run app.py` + folder `pages/` = satu sidebar, satu app. Tidak ada entry point kedua.

---

## Model data

Skema: [`db/schema.sql`](db/schema.sql) · ERD: [`AUDIT/02_erd.md`](AUDIT/02_erd.md) ·
Data dictionary (Excel → kolom DB): [`AUDIT/01_data_dictionary.md`](AUDIT/01_data_dictionary.md).

Tabel inti: `master_items` · `inventory_snapshots` · `safety_stock_params` (+`_variants`) ·
`monthly_consumption` · `ppb_lines` · `ppb_changes` · `ri_lines` · `po_derived` · `npbg_lines` ·
`borrow_lend` · `stpp` · `tire_transactions` (+`_bpn_snapshots`, +`_deliver_receive`) ·
`asset_maintenance` · `manufacturing` · `used_returns` · `vehicles` · `matching_reviews` ·
`calc_runs` / `calc_results` · `upload_batches` / `import_errors` / `import_notes`.

- ID internal barang: `ITEM-000001…`. `kode_barang` bisa NULL / duplikat (dipertahankan + flag).
- Tiap baris transaksi menyimpan `source_file`, `source_sheet`, `source_row`, `upload_batch_id`, `row_hash`.
- Dedup: `row_hash = sha1(modul | no_dokumen | line_no | deskripsi_norm | qty | tgl)`.
- `v_inventory` = `master_items` ⋈ `calc_results` (run terbaru) — dipakai semua query dashboard.
- **app.py sync**: `master_items` + `inventory_snapshots` di-upsert dari dataframe app.py; ID lama
  dipakai ulang lewat pencocokan `kode_barang` / deskripsi ternormalisasi supaya link transaksi tidak
  putus. `safety_stock_params` hanya ditimpa untuk baris di mana user benar-benar mengisi SS / MIN PR
  (`source_sheet = 'input manual (app.py)'`); nilai dari 13 sheet dibiarkan untuk sisanya.

---

## Rumus / calculation engine

Satu tempat: [`utils/calc_engine.py`](utils/calc_engine.py) (mirror `tools/lib/calc.mjs`). Semua
halaman baca `calc_results`. *(Rumus lama `utils/calculations.py` tetap dipakai app.py untuk tampilan
in-memory-nya; calc_engine adalah model yang lebih lengkap untuk data DB-wide.)*

| Field | Rumus |
|---|---|
| `selisih` | `sisa_stok − safety_stock` (jika keduanya diketahui) |
| `defisit` | `max(safety_stock − sisa_stok, 0)` |
| `stock_status` | `UNKNOWN` · `BEP` (sisa=0 & SS 0/tak ada) · `NO_SAFETY_STOCK` (sisa ada, SS tak ada) · `OUT_OF_STOCK` (sisa=0, SS>0) · `TIDAK_AMAN` (0<sisa<SS) · `AMAN` (sisa≥SS) |
| `is_critical` | `TIDAK_AMAN`/`OUT_OF_STOCK` **dan** (defisit ≥ P75 defisit unsafe **atau** priority HIGH) |
| `priority_score` | unsafe → `defisit×2.0 + lead_time×1.0` ; else `0` |
| `priority_level` | unsafe → `HIGH` bila defisit ≥ median(defisit unsafe) atau lead_time ≥ threshold ; else `MEDIUM` ; safe → `LOW` |
| `incoming_qty` | `max( Σ qty PPB belum-final − Σ qty RI ber-PPB, 0 )` — perkiraan, [A-17] |
| `projected_stock` | `sisa_stok + incoming_qty` |
| `avg_monthly_usage` | `avg_12_bln` dari sheet SAFETY STOCK, else `Σ qty NPBG / jumlah bulan aktif` |
| Skor Kesehatan | `AMAN / (AMAN + TIDAK_AMAN + OUT_OF_STOCK) × 100` |

Parameter di [`utils/sw_config.py`](utils/sw_config.py) — **menunggu konfirmasi bisnis**
([`AUDIT/00_decisions.md`](AUDIT/00_decisions.md)): `LEAD_TIME_HIGH_THRESHOLD_DAYS = 14`,
bobot defisit `2.0`, bobot lead time `1.0`.

---

## Konsep stok

| Istilah | Arti |
|---|---|
| **Current Stock** (`sisa_stok`) | stok fisik sekarang. Kosong → `UNKNOWN`. |
| **Safety Stock** | batas minimum aman (13 sheet `SAFETY STOCK *` atau input manual). Tak ada → `NO_SAFETY_STOCK`, **bukan 0**. |
| **Deficit** | `Safety − Current` bila positif. |
| **Incoming** | sudah dipesan (PPB belum-final) tapi belum diterima (RI). |
| **Projected Stock** | `Current + Incoming`. |
| `OUT_OF_STOCK` ≠ `TIDAK_AMAN` | habis (=0) vs di bawah safety (0<x<SS). |

---

## Tes

```bash
python tools/smoke_test.py     # semua fungsi query + calc engine + PDF, terhadap stockwise.db asli
python tools/test_pages.py     # render app.py + tiap halaman headless (streamlit.testing), tangkap exception
```

Keduanya hijau per commit ini (Python 3.12.10, Streamlit 1.63). ETL juga diuji: 9 file → DB ~30 dtk,
re-upload → 0 duplikat, `sync_master` menjaga link transaksi.

---

## Status & batasan

- **Safety Stock** ada untuk ~8.600 item; **~3.800 nilainya beda antar sheet** → kerjakan di
  **Safety Stock**. Item tanpa SS statusnya `NO_SAFETY_STOCK`, bukan 0.
- **Sisa Stok** kosong untuk ~71% item → `UNKNOWN`, bukan 0.
- **Matching** ~55–58% otomatis. Sisanya: ~2.500 di **Cocokkan Barang** (ada kandidat) + sisanya
  barang baru.
- Keputusan bisnis terbuka (rumus SS internal sheet, threshold, definisi status): `[A-n]` di
  [`AUDIT/00_decisions.md`](AUDIT/00_decisions.md) — bisa diubah tanpa membuang kerja.
- Belum ada: login/multi-user, Tanya STOCKWISE natural-language (sekarang preset).

Audit sumber lengkap: [`AUDIT/`](AUDIT/).
