# STOCKWISE

**Inventory Intelligence System — PT Surya Inti Gas.**

Baca 9 workbook operasional Excel → satu database ternormalisasi (`stockwise.db`) → calculation
engine → dashboard yang bisa menjawab pertanyaan manajemen dan menelusuri **setiap angka** kembali
ke baris Excel aslinya.

```
streamlit run Home.py          ← ini aplikasinya
```

> `app.py` adalah dashboard lama (v1): satu file Excel, di memori, tanpa database. Masih bisa
> dijalankan (`streamlit run app.py`) tapi tidak dikembangkan lagi. Semua di bawah ini soal Home.py.

---

## Daftar Isi

- [Gambaran Singkat](#gambaran-singkat)
- [Arsitektur](#arsitektur)
- [Instalasi](#instalasi)
- [FLOW — cara pakai](#flow--cara-pakai)
  - [A. Setup pertama kali](#a-setup-pertama-kali)
  - [B. Pemakaian harian / bulanan](#b-pemakaian-harian--bulanan)
  - [C. Loop pembersihan data](#c-loop-pembersihan-data)
  - [D. Menjawab pertanyaan manajemen](#d-menjawab-pertanyaan-manajemen)
- [Peta Halaman](#peta-halaman)
- [File yang Diupload](#file-yang-diupload)
- [Model Data](#model-data)
- [Rumus / Calculation Engine](#rumus--calculation-engine)
- [Konsep Stok](#konsep-stok)
- [Kenapa ada Node.js di project Python](#kenapa-ada-nodejs-di-project-python)
- [Tes](#tes)
- [Status & Batasan](#status--batasan)
- [Struktur Project](#struktur-project)

---

## Gambaran Singkat

| | |
|---|---|
| **Input** | 9 file Excel di `DATAFIX/` (Master + PPB-RI + NPBG + 6 tracking). Diupload lewat UI. |
| **Penyimpanan** | `stockwise.db` — SQLite, satu file, di-`.gitignore`. **Single source of truth.** |
| **Yang dihitung** | Sisa stok, safety stock, selisih, defisit, status, priority, incoming, projected stock, rata-rata pemakaian — per barang, oleh satu calculation engine. |
| **Yang bisa ditelusuri** | Tiap angka → baris Excel: nama file, sheet, nomor baris. |
| **Stack** | Python 3.12 + Streamlit (UI) · SQLite (data) · Node.js (ETL: baca Excel, matching, dedup). |
| **Auth** | Belum ada (single-user). |

Excel = *import layer*. `stockwise.db` = *sumber kebenaran*. Halaman **tidak pernah** parsing Excel
saat render — semua baca dari DB (spec §22, §35).

---

## Arsitektur

```
   9 × Excel  (DATAFIX/ atau upload UI)
        │
        ▼
┌─────────────────────────────────────────────────────────────┐
│ INGEST  (tools/*.mjs — Node)                                 │
│  deteksi modul → deteksi header per-sheet → normalisasi →    │
│  parsing tipe → MATCHING barang ke master → dedup (row_hash) │
│  → UPSERT                                                    │
└─────────────────────────────────────────────────────────────┘
        │
        ▼
   stockwise.db  ◄── keputusan review manual disimpan di sini juga
        │           (matching_reviews, safety_stock_params.chosen_sheet)
        ▼
┌─────────────────────────────────────────────────────────────┐
│ CALCULATION ENGINE  (stockwise/calc.py)                      │
│  selisih · defisit · stock_status · priority · incoming ·    │
│  projected_stock · avg_monthly_usage   → tabel calc_results  │
└─────────────────────────────────────────────────────────────┘
        │
        ▼
   STREAMLIT  (Home.py = router + pages/*.py)
   Dashboard · Inventory · Procurement · Pemakaian · Tracking ·
   Tanya · Kelola Data · Cocokkan Barang · Safety Stock · Master · Item Detail
```

Matching & normalisasi ditulis dua kali dan **harus tetap sinkron**:
`tools/lib/textnorm.mjs` ↔ `stockwise/textnorm.py`, `tools/lib/calc.mjs` ↔ `stockwise/calc.py`.
Node dipakai untuk ETL (bisa dites langsung ke data asli); Python untuk app + calc di dalam UI.

---

## Instalasi

Butuh **Python 3.12+** dan **Node.js 22+** (Node punya `node:sqlite` bawaan).

```bash
# 1. dependency Python
pip install -r requirements.txt

# 2. dependency Node (sekali) — untuk ETL
cd tools && npm install && cd ..

# 3. isi database dari folder DATAFIX/ (bootstrap awal)
node --experimental-sqlite tools/build_stockwise_db.mjs
#    → stockwise.db + AUDIT/03_ingest_report.md   (~35 detik)

# 4. jalankan
streamlit run Home.py           # buka http://localhost:8501
```

Kalau belum ada `stockwise.db`, aplikasi membuka halaman **Mulai** dan menuntun upload.

---

## FLOW — cara pakai

### A. Setup pertama kali

Halaman **Mulai** (🚀) muncul otomatis dan menyorot **satu** langkah berikutnya:

```
1. Upload Master           →  Kelola Data ▸ Upload  ▸  tarik DATA.xlsx
2. Upload transaksi        →  Kelola Data ▸ Upload  ▸  tarik 8 file lainnya (sekaligus juga bisa)
3. Cocokkan barang         →  Cocokkan Barang       ▸  "Terima massal ≥ 0.98", review sisanya
4. Beresi Safety Stock     →  Safety Stock          ▸  pilih sheet yang benar per barang
```

- Langkah 1–2 wajib. Langkah 3–4 **bisa dicicil** — dashboard tetap jalan, barang yang belum
  beres statusnya jujur (`belum bisa dinilai` / `belum di-match`), bukan ditebak.
- Setelah master + transaksi masuk & sekali hitung, halaman **Mulai** hilang; **Dashboard** jadi
  halaman default.

**Upload = satu aksi.** Di **Kelola Data ▸ Upload**, tarik semua file Excel sekaligus. Sistem:
mengenali tiap file dari nama & isinya → memproses **master duluan** → membuang baris duplikat →
mencocokkan barang ke master → menghitung ulang. Sekali klik, sekali tunggu.

### B. Pemakaian harian / bulanan

```
Excel bulan ini (kumulatif penuh)
        │  tarik ke Kelola Data ▸ Upload ▸ "Proses semua"
        ▼
UPSERT by row_hash   →  baris lama TIDAK digandakan
                        baris baru ditambahkan
                        status dokumen yang berubah ikut ter-update
        │
        ▼
matching + hitung ulang otomatis  →  Dashboard langsung update
```

Tidak ada "hapus data lama" — upload file yang sudah nambah baris, selesai (spec §21).

### C. Loop pembersihan data

Dua antrian yang perlu dikerjakan manusia (bisa kapan saja, dicicil):

```
┌── Cocokkan Barang (🤝) ──────────────────────────────────────┐
│  ~2.500 barang transaksi belum pasti = master mana            │
│  • "Terima massal ≥ 0.98"  → ratusan/ribuan exact match       │
│  • per baris: pilih kandidat / "barang baru" (buat master)    │
│  • filter per tabel sumber & per confidence                   │
└──────────────────────────────────────────────────────────────┘

┌── Safety Stock (🛡️) ─────────────────────────────────────────┐
│  ~3.800 barang: nilai SS/Lead Time beda antar 13 sheet        │
│  • lihat semua varian bersebelahan                            │
│  • klik "Pakai sheet X" → jadi acuan calculation engine       │
└──────────────────────────────────────────────────────────────┘

Setiap keputusan langsung tersimpan. Di dashboard muncul tombol
   ↻ Terapkan sekarang
→ hitung ulang sekali, semua angka ikut. (Aksi massal hitung ulang sendiri.)
```

### D. Menjawab pertanyaan manajemen

**Tanya STOCKWISE** (💬) — dua mode:

| Mode | Contoh |
|---|---|
| Pertanyaan umum | "Barang apa yang habis?" · "Barang mana harus dibeli duluan?" · "PPB mana belum selesai?" · "Divisi mana paling banyak pakai?" · "Barang dipinjam siapa?" |
| Tanya satu barang | pilih barang → sisa · safety stock · defisit · **sudah PPB?** · **PO/diterima?** · **outstanding** · total pemakaian — satu layar |

Atau **drill-down**: Dashboard → klik tombol status / klik baris Inventory / Procurement →
**Item Detail** (360°: stok, PPB/RI, pemakaian per bulan, tracking, blueprint, **lineage ke baris Excel**)
→ tombol "← Kembali".

Contoh alur lengkap (dari spec §45):
```
Item "Regulator O2"
  Sisa 5 · Safety 15 · Defisit 10 · Status TIDAK AMAN · Priority HIGH
  → PPB: PPB/NA/25/.. (Requested)  → RI: 10 dari 20 diterima  → Outstanding 10
  → Projected Stock 15   → Rekomendasi: prioritas tinggi
  → Pemakaian NPBG: rata-rata X/bulan
Semua angka bisa diklik sampai ke baris Excel-nya.
```

---

## Peta Halaman

| Grup | Halaman | Isi |
|---|---|---|
| Setup | **Mulai** | checklist setup, sorot 1 langkah berikutnya. Hilang saat siap. |
| Pantau | **Dashboard** | KPI (item, stok, tidak aman, stok habis, critical, defisit, incoming, skor kesehatan), tombol drill per status, sebaran status, 10 item mendesak, **export PDF** |
| | **Inventory** | semua barang + filter cepat (Tidak Aman / Stok Habis / Critical / BEP / …) + grafik per kategori; klik baris → Item Detail; export CSV |
| | **Procurement** | *Priority Buy List* (klik baris → detail) + status **PPB → PO → RI** + outstanding per PPB |
| | **Pemakaian** | konsumsi NPBG: trend bulanan, top barang, per divisi / klasifikasi / pelanggan / proyek |
| | **Tracking** | Borrow/Lend · STPP · Ban Luar (+BPN, +Deliver/Receive) · Maintenance Kendaraan · Manufaktur & Assembly · Pengembalian Bekas — semua dengan kotak cari |
| Tanya | **Tanya STOCKWISE** | pertanyaan preset + mode tanya satu barang |
| Beresi Data | **Kelola Data** | Upload (multi-file, 1 klik) · Riwayat proses · Kualitas Data |
| | **Cocokkan Barang** | antrian matching + terima massal + buat master item |
| | **Safety Stock** | resolusi konflik SS/LT antar sheet |
| Referensi | **Master Barang** | katalog · parameter safety stock · alias |
| | **Item Detail** | 360° per barang + lineage (target drill-down) |

---

## File yang Diupload

9 file, satu per modul. Sistem mengenali otomatis dari nama & sheet-nya
(`tools/lib/detect_module.mjs`).

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

- Urutan tidak masalah — sistem proses master duluan. Bisa dicicil (upload sebagian dulu).
- Sheet `cetak`, `Sheet2`, `Sheet6`, `Export List_Klasifikasi`, dan tiap `Dropdown List` diabaikan otomatis.
- Header boleh di baris 2/3/4 — dideteksi per-sheet dari signature kolom.
- `Sisa Stok` boleh teks (`STOK 15 PCS`, `STOK O PCS` → 0). Nilai kosong = *belum terdata*, **bukan 0**.

CLI alternatif: `node --experimental-sqlite tools/ingest_batch.mjs --dir <folder>` (banyak file),
atau `tools/ingest_one.mjs <modul> <file>` (satu file).

---

## Model Data

Skema lengkap: [`db/schema.sql`](db/schema.sql). ERD: [`AUDIT/02_erd.md`](AUDIT/02_erd.md).
Data dictionary (Excel → kolom DB): [`AUDIT/01_data_dictionary.md`](AUDIT/01_data_dictionary.md).

Tabel inti: `master_items` · `inventory_snapshots` · `safety_stock_params` (+`_variants`) ·
`monthly_consumption` · `ppb_lines` · `ppb_changes` · `ri_lines` · `po_derived` · `npbg_lines` ·
`borrow_lend` · `stpp` · `tire_transactions` (+`_bpn_snapshots`, +`_deliver_receive`) ·
`asset_maintenance` · `manufacturing` · `used_returns` · `vehicles` · `matching_reviews` ·
`calc_runs` / `calc_results` · `upload_batches` / `import_errors` / `import_notes`.

- ID internal barang: `ITEM-000001…`. Business key `kode_barang` bisa NULL / duplikat (dipertahankan + flag).
- Tiap baris transaksi menyimpan `source_file`, `source_sheet`, `source_row`, `upload_batch_id`, `row_hash`.
- Dedup: `row_hash = sha1(modul | no_dokumen | line_no | deskripsi_norm | qty | tgl)`.
- `v_inventory` = `master_items` ⋈ `calc_results` (run terbaru) — dipakai semua query dashboard.

**Relasi transaksi** pakai nomor dokumen (bukan foreign key keras, karena sumber sering pakai
sentinel `-`/`ORIGIN`): `ppb.no_ppb` → `ri.no_ppb`; `ri.no_po` → `po_derived`; `stpp/borrow_lend/
tire/maintenance/manufacturing/used_returns` `.ref_npbg` → `npbg.no_npbg`, `.ref_ri` → `ri.no_ri`.

---

## Rumus / Calculation Engine

Satu tempat: [`stockwise/calc.py`](stockwise/calc.py) (dicerminkan `tools/lib/calc.mjs`).
Semua halaman baca `calc_results`, tidak ada yang hitung sendiri.

| Field | Rumus |
|---|---|
| `selisih` | `sisa_stok − safety_stock` (jika keduanya diketahui) |
| `defisit` | `max(safety_stock − sisa_stok, 0)` |
| `stock_status` | `UNKNOWN` (sisa tak terdata) · `BEP` (sisa=0 & SS 0/tak ada) · `NO_SAFETY_STOCK` (sisa ada, SS tak ada) · `OUT_OF_STOCK` (sisa=0, SS>0) · `TIDAK_AMAN` (0<sisa<SS) · `AMAN` (sisa≥SS) |
| `is_critical` | `TIDAK_AMAN`/`OUT_OF_STOCK` **dan** (defisit ≥ P75 defisit unsafe **atau** priority HIGH) |
| `priority_score` | unsafe → `defisit×2.0 + lead_time×1.0` ; else `0` |
| `priority_level` | unsafe → `HIGH` bila defisit ≥ median(defisit unsafe) atau lead_time ≥ threshold ; else `MEDIUM` ; safe → `LOW` |
| `incoming_qty` | `max( Σ qty PPB belum-final − Σ qty RI ber-PPB untuk barang itu, 0 )` — perkiraan, [A-17] |
| `projected_stock` | `sisa_stok + incoming_qty` |
| `avg_monthly_usage` | `avg_12_bln` dari sheet SAFETY STOCK, else `Σ qty NPBG / jumlah bulan aktif` |
| Skor Kesehatan | `AMAN / (AMAN + TIDAK_AMAN + OUT_OF_STOCK) × 100` |

Parameter (di [`stockwise/config.py`](stockwise/config.py), **menunggu konfirmasi bisnis** —
[`AUDIT/00_decisions.md`](AUDIT/00_decisions.md)): `LEAD_TIME_HIGH_THRESHOLD_DAYS = 14`,
bobot defisit `2.0`, bobot lead time `1.0`.

---

## Konsep Stok

| Istilah | Arti |
|---|---|
| **Current Stock** (`sisa_stok`) | stok fisik sekarang (dari `DATABASE UTAMA`). Kosong → `UNKNOWN`. |
| **Safety Stock** | batas minimum aman (dari 13 sheet `SAFETY STOCK *`). Tak ada → `NO_SAFETY_STOCK`, **bukan 0**. |
| **Deficit** | `Safety − Current` bila positif. |
| **Incoming** | sudah dipesan (PPB belum-final) tapi belum diterima (RI). |
| **Projected Stock** | `Current + Incoming` — perkiraan stok setelah barang datang. |
| `OUT_OF_STOCK` ≠ `TIDAK_AMAN` | habis (=0) vs di bawah safety (0<x<SS). Beda status. |

---

## Kenapa ada Node.js di project Python

ETL (baca Excel dengan header tak beraturan, normalisasi, matching ~50% non-exact, dedup) ditulis
di Node karena bisa diuji langsung terhadap data asli. `stockwise.db` yang dihasilkan portabel dan
dibaca Python. Upload lewat UI (`stockwise/ingest.py`) memanggil `tools/ingest_batch.mjs` — kode
yang sama dengan bootstrap. Logika normalisasi & kalkulasi dicerminkan di Python (`stockwise/
textnorm.py`, `stockwise/calc.py`) untuk dipakai di dalam UI; keduanya harus tetap sinkron dengan
versi `.mjs`.

---

## Tes

```bash
python tools/smoke_test.py     # semua fungsi query + calc engine + PDF, terhadap stockwise.db asli
python tools/test_pages.py     # render tiap halaman Streamlit headless (streamlit.testing), tangkap exception
```

Keduanya hijau per commit ini (Python 3.12.10, Streamlit 1.63). ETL juga diuji: 9 file → DB dalam
~35 detik, re-upload → 0 duplikat.

---

## Status & Batasan

- **Safety Stock** ada untuk ~8.600 item; **~3.800 di antaranya nilainya beda antar sheet** →
  kerjakan di **Safety Stock**. Item tanpa SS statusnya `NO_SAFETY_STOCK`, bukan 0.
- **Sisa Stok** kosong untuk ~71% item → `UNKNOWN`, bukan 0. Skor kesehatan hanya menghitung item
  yang datanya lengkap (biasanya tampil kecil di awal — itu jujur, bukan bug).
- **Matching** ~55–58% otomatis. Sisanya: ~2.500 di **Cocokkan Barang** (ada kandidat) + sisanya
  barang baru (buat master / biarkan).
- Keputusan bisnis yang masih terbuka (rumus SS internal sheet, threshold, definisi status): semua
  ditandai `[A-n]` di [`AUDIT/00_decisions.md`](AUDIT/00_decisions.md) — bisa diubah tanpa membuang kerja.
- Belum ada: login/multi-user, Tanya STOCKWISE natural-language (sekarang preset).

Audit sumber lengkap: [`AUDIT/`](AUDIT/) (`00` keputusan, `01` data dictionary, `02` ERD,
`03` laporan ingest).

---

## Struktur Project

```
STOCKWISE/
├── Home.py                      # entry point v2: router st.navigation
├── app.py                       # dashboard lama v1 (tidak dikembangkan)
├── pages/                       # halaman v2 (executive, inventory, ..., get_started)
├── stockwise/                   # paket Python
│   ├── config.py                #   path + parameter bisnis
│   ├── db.py                    #   koneksi SQLite + read_df
│   ├── textnorm.py              #   normalisasi (mirror .mjs)
│   ├── calc.py                  #   calculation engine (mirror .mjs)
│   ├── queries.py               #   semua query dashboard
│   ├── ingest.py                #   panggil Node ETL untuk upload UI
│   ├── report.py                #   export PDF
│   └── ui.py                    #   chrome, KPI, badge, banner "Terapkan"
├── tools/                       # ETL (Node) — butuh `npm install` di tools/
│   ├── build_stockwise_db.mjs   #   bootstrap: DATAFIX/ → stockwise.db + laporan
│   ├── ingest_batch.mjs         #   banyak file, auto-detect modul
│   ├── ingest_one.mjs           #   satu file
│   ├── smoke_test.py            #   tes query/calc (Python)
│   ├── test_pages.py            #   tes render halaman (Python)
│   └── lib/                     #   parser per modul, matcher, calc, dll
├── db/schema.sql                # skema SQLite
├── AUDIT/                       # 00 keputusan · 01 data dictionary · 02 ERD · 03 laporan ingest
├── DATAFIX/                     # 9 workbook sumber (gitignore-kan bila besar)
└── stockwise.db                 # dibuat saat build/upload (gitignore)
```
