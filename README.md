# STOCKWISE

Dashboard inventory berbasis **Python + Streamlit + Pandas + Plotly**. Upload file Excel inventory (plus opsional PPB & NPBG), edit datanya langsung di tabel interaktif, dan lihat KPI, chart, insight, serta rekomendasi procurement ter-update otomatis — tanpa refresh halaman, tanpa database, tanpa login. File Excel yang diupload adalah satu-satunya sumber data; semua kalkulasi jalan ulang di memori setiap kali ada perubahan.

## Daftar Isi

- [Tech Stack](#tech-stack)
- [Struktur Project](#struktur-project)
- [Menjalankan Secara Lokal](#menjalankan-secara-lokal)
- [Download Template](#download-template)
- [Upload Data (Inventory, PPB, NPBG)](#upload-data-inventory-ppb-npbg)
- [Skema Data (Kolom Excel)](#skema-data-kolom-excel)
- [Struktur Tab](#struktur-tab)
- [Cara Membaca Dashboard](#cara-membaca-dashboard)
- [Kolom NPBG & Pencocokan Deskripsi](#kolom-npbg--pencocokan-deskripsi)
- [Rumus Perhitungan — Detail Lengkap](#rumus-perhitungan--detail-lengkap)
- [Tab Procurement](#tab-procurement)
- [Filter (Sidebar)](#filter-sidebar)
- [Edit Data](#edit-data)
- [Export Data](#export-data)
- [Bagaimana Reactive Calculation Bekerja](#bagaimana-reactive-calculation-bekerja)

## Tech Stack

| Layer | Library/Tool | Kegunaan |
|---|---|---|
| Bahasa | Python 3 | Seluruh logika, tidak ada JS/TS |
| UI framework | [Streamlit](https://streamlit.io) `>=1.36` | Render halaman, tab, sidebar, `st.data_editor`, sekaligus jadi "server" (rerun script tiap ada interaksi) |
| Data processing | [pandas](https://pandas.pydata.org) `>=2.0` | Semua transformasi tabel: filter, groupby, kalkulasi kolom |
| Numerik | [numpy](https://numpy.org) `>=1.26` | `np.where` untuk kolom Status, operasi vektor |
| Baca Excel | [openpyxl](https://openpyxl.readthedocs.io) `>=3.1` | Parsing file `.xlsx` yang diupload, deteksi sheet & header |
| Tulis Excel | [XlsxWriter](https://xlsxwriter.readthedocs.io) `>=3.1` | Generate file export & template dengan conditional formatting (warna AMAN/TIDAK AMAN/BEP) |
| Tulis PDF | [ReportLab](https://www.reportlab.com/opensource/) `>=4.0` | Generate laporan PDF (KPI, tabel barang, Procurement Priority) — pure Python, tidak butuh binary eksternal |
| Charting | [Plotly](https://plotly.com/python/) `>=5.20` (`plotly.express` + `plotly.graph_objects`) | Semua visualisasi di dashboard & tab, dirender via `st.plotly_chart` |
| Fuzzy matching | `difflib` (stdlib) | Cocokkan deskripsi barang Inventory ↔ NPBG untuk kolom `NPBG` (tanpa dependency tambahan) |
| State | `st.session_state` (bawaan Streamlit) | Menyimpan dataframe aktif & pengaturan (threshold lead time) antar-rerun, tidak butuh Redux/Zustand |
| Styling | CSS custom (`st.markdown(unsafe_allow_html=True)`) di `app.py` | Font Inter (Google Fonts), kartu KPI, health bar, kartu insight, overlay spinner (logo berputar) |
| Auth / DB | **Tidak ada** | Single-user, stateless per sesi browser; tidak ada login, role, atau database — "database"-nya adalah file Excel itu sendiri |

Tidak ada framework frontend terpisah (React/Vue dst.) — satu file `app.py` di-render penuh oleh Streamlit, navigasi antar-halaman cukup pakai `st.tabs`.

## Struktur Project

```text
STOCKWISE/
├── app.py                     # entry point: page config, CSS, sidebar, 6 tab, dashboard gabungan, wiring reaktif
├── requirements.txt
├── assets/logo.png            # logo aplikasi (di-embed sebagai base64, juga jadi spinner berputar saat proses)
├── data/                      # (opsional) tempat menaruh file Excel contoh
├── utils/
│   ├── excel_handler.py       # deteksi sheet & baris header, fuzzy-match kolom, parsing "STOK 15 PCS", export & template Excel
│   ├── ppb_handler.py         # parser file PPB (sheet PPB): deteksi header, buang baris kosong, ringkasan
│   ├── npbg_handler.py        # parser file NPBG (sheet NPBG): idem — barang keluar gudang
│   ├── npbg_match.py          # normalisasi teks + fuzzy matching deskripsi Inventory ↔ NPBG → kolom NPBG
│   ├── pdf_export.py          # generator laporan PDF (KPI, tabel barang, Procurement Priority) via ReportLab
│   ├── calculations.py        # pipeline reaktif: Selisih, Status, Defisit, Priority Score/Level, Rekomendasi
│   ├── insights.py            # generator teks insight otomatis (rule-based)
│   ├── recommendations.py     # generator rekomendasi procurement per baris (rule-based)
│   └── theme.py               # palet warna bersama — dipakai KPI, chart, dan badge status
└── components/
    ├── kpi.py                 # 8 kartu KPI + health bar "Kondisi Stok Keseluruhan"
    ├── charts.py              # visualisasi Plotly inventory (donut status, top defisit, per gudang, per kategori, scatter lead time)
    └── data_editor.py         # st.data_editor + column_config (kolom mana editable, mana read-only, termasuk NPBG)
```

## Menjalankan Secara Lokal

```bash
pip install -r requirements.txt
streamlit run app.py
```

Aplikasi terbuka di `http://localhost:8501`.

## Download Template

Belum punya file, atau ingin memastikan format Excel Anda sesuai? Klik **📥 Download Template Excel** di sidebar (atau di layar awal sebelum upload). Template memakai layout yang sama seperti export STOCKWISE asli (judul di baris 1-4, header di baris 5) lengkap dengan 2 baris contoh data — satu AMAN, satu TIDAK AMAN — supaya format `Sisa Stok` seperti `STOK 15 PCS` langsung terlihat jelas.

## Upload Data (Inventory, PPB, NPBG)

Sidebar **📤 Upload Data** punya 3 slot: **1. Excel Inventory**, **2. Excel PPB**, **3. Excel NPBG**.

| Slot | File | Isi |
|---|---|---|
| **1. Excel Inventory** | mis. `DATA.xlsx` | Master barang & stok — sumber utama semua kalkulasi |
| **2. Excel PPB** | mis. `1. PPB - RI.xlsx` | *Permintaan Pembelian Barang* — barang yang diminta untuk dibeli |
| **3. Excel NPBG** | mis. `2. NPBG.xlsx` | *Nota Pengeluaran Barang Gudang* — barang yang **keluar** dari gudang |

- File yang dipilih **tidak langsung diproses**. Muncul status `⏳ menunggu diproses` per slot.
- Klik tombol **🚀 Proses N file** untuk memproses (dipakai kalau cuma mau 1–2 file).
- Kalau **ketiga slot terisi**, file otomatis diproses tanpa perlu klik tombol.
- Saat memproses, muncul overlay **logo berputar** dengan teks "Membaca & memproses data…" di tengah layar.
- Setelah diproses, status jadi `✅ nama-file — ringkasan`. Ganti file di slot yang sama → status kembali `⏳` dan tombol/otomatisasi jalan lagi.
- PPB & NPBG **bisa dibuka tanpa data inventory** — kalau hanya PPB/NPBG yang diupload, aplikasi menampilkan dashboard ringkas (bagian PPB/NPBG saja) plus tab detailnya.

### Detail parser Inventory

1. Jika workbook Anda punya beberapa sheet (mis. `Data`, `Dropdown List`, `cetak`, `Sheet2`), aplikasi otomatis memakai sheet bernama **"Data"** sebagai dataset utama — sheet `cetak`/`Sheet2`/`Dropdown List` tidak pernah dibaca sebagai data inventory. Jika tidak ada sheet bernama "Data", aplikasi jatuh ke sheet pertama yang bukan salah satu dari ketiganya.
2. Baris header **tidak harus di baris pertama** — aplikasi otomatis mencari baris yang memuat kolom "Kode Barang" (sampai 50 baris pertama sheet tersebut), jadi file dengan judul/baris kosong di atas header tetap terbaca.
3. Nama kolom tidak harus persis sama — kolom seperti `Safety Stock` atau `SISA STOK (22/08/2026)` dikenali lewat pencocokan kata kunci (`SAFETY`+`STOCK`, `SISA`+`STOK`), begitu juga `√LT` dan `MIN PR`.
4. Kolom `Sisa Stok` boleh berformat teks seperti `STOK 15 PCS` — nilai numeriknya diekstrak otomatis lewat regex (`STOK 15 PCS` → `15`). `Safety Stock` dan `MIN PR` boleh sepenuhnya kosong — dianggap valid dan dinormalisasi jadi `0` untuk kalkulasi.
5. Jika ada sheet **"Dropdown List"**, pilihannya (Kategori Induk/Anak 1-3, UoM) otomatis mengisi pilihan selectbox di tabel edit, digabung dengan nilai yang sudah ada di data.
6. Jika kolom wajib (`Kode Barang`, `Deskripsi Barang`, `Safety Stock`, `Sisa Stok`) tetap tidak ditemukan setelah pencocokan otomatis, muncul pesan error jelas — termasuk sheet & baris header yang terdeteksi dan daftar kolom yang berhasil dibaca — tanpa crash.
7. Buka expander **🐞 Debug Excel** di tab Data Inventory untuk melihat sheet yang dipakai, baris header, kolom yang terdeteksi, dan pilihan dropdown yang terbaca.

### Detail parser PPB & NPBG

- Otomatis memakai sheet bernama **PPB** / **NPBG**, mencari baris header (yang memuat kolom *No PPB* / *No NPBG*), dan membuang baris kosong. Sheet asli mendeklarasikan range yang sangat besar (ribuan baris kosong) dan kolom rollup memakai *array-formula* — baris item asli dikenali dari **No dokumen + Deskripsi Barang** yang sama-sama terisi.
- Nama kolom boleh sedikit beda (mis. `Nomor PPB`, `Qty`, `Jenis NPBG`) — dicocokkan otomatis.
- Satu No PPB / No NPBG bisa punya banyak baris (satu baris per item).
- **Kolom PPB yang dibaca:** `Tgl PPB`, `No PPB`, `Deskripsi Barang`, `Kuantitas`, `Satuan`, `Peminta`, `Divisi`, `Status`, `Keterangan`. Wajib: `No PPB`, `Deskripsi Barang`.
- **Kolom NPBG yang dibaca:** `Tgl NPBG`, `No NPBG`, `Tipe NPBG`, `Klasifikasi`, `Deskripsi Barang`, `Kuantitas`, `Satuan`, `Peminta`, `Divisi`, `Pelanggan`, `Nama Proyek`, `No Seri / Nopol`, `Dikeluarkan Oleh`, `Keterangan`. Wajib: `No NPBG`, `Deskripsi Barang`.

## Skema Data (Kolom Excel)

Didefinisikan di `utils/excel_handler.py`.

**Kolom wajib** (aplikasi error kalau tidak ketemu): `Kode Barang`, `Deskripsi Barang`, `Safety Stock`, `Sisa Stok`.

**Kolom master lain yang dikenali** (opsional): Kategori Induk, Kategori Anak 1/2/3, UoM, Perlu Blueprint?, Nama Alias, Letak Gudang, Letak Rak, Blueprint IMG/Detail PDF/3D View, Lead Time, `√LT`, MIN PR.

**Kolom numerik** (dipaksa jadi angka, kosong → 0): `Safety Stock`, `Sisa Stok`, `Lead Time`, `MIN PR`.

**Kolom hasil kalkulasi** (read-only, dibuat otomatis, jangan diisi manual di Excel karena akan ditimpa): `Selisih`, `Status`, `Defisit`, `Priority Score`, `Priority Level`, `Rekomendasi`, `NPBG`.

`NPBG` hanya terisi kalau file NPBG ikut diupload — lihat [Kolom NPBG & Pencocokan Deskripsi](#kolom-npbg--pencocokan-deskripsi).

## Struktur Tab

Deret tab atas (kiri → kanan):

| Tab | Isi | Butuh data |
|---|---|---|
| **📊 Dashboard** | Satu halaman ringkasan **semua** data (Inventory + PPB + NPBG) — lihat [Cara Membaca Dashboard](#cara-membaca-dashboard) | minimal salah satu |
| **🗂️ Data Inventory** | Tabel master yang bisa diedit (`st.data_editor`) + kelola kolom + Debug Excel | Inventory |
| **📋 Data PPB** | **Tabel saja**: Daftar PPB + filter (Status/Divisi/cari) + download CSV + Debug PPB. Ringkasannya ada di Dashboard | PPB |
| **📤 Data NPBG** | **Tabel saja**: Daftar NPBG + filter (Klasifikasi/Divisi/Tipe/cari) + download CSV + Debug NPBG. Ringkasannya ada di Dashboard | NPBG |
| **🚚 Procurement** | Barang TIDAK AMAN diurutkan Priority Score — lihat [Tab Procurement](#tab-procurement) | Inventory |
| **⬇️ Export** | Download Excel / PDF / CSV, scope Seluruh Data atau Data Terfilter | Inventory |

KPI dan chart PPB/NPBG **digabung ke Dashboard**; tab Data PPB / Data NPBG sengaja dibuat berisi tabel & filter saja.

## Cara Membaca Dashboard

Tab **Dashboard** menampilkan semua data yang sudah diupload dalam satu layar. Bagian yang berhubungan dengan inventory selalu mengikuti filter sidebar yang sedang aktif.

### 1. Ringkasan Barang (8 kartu + health bar)

Kartu KPI dari data inventory (dulu ada di tab Data Inventory, sekarang dipindah ke Dashboard). Urutannya: identitas → 4 kelompok status → 3 angka kuantitas.

| Kartu | Arti |
|---|---|
| 📦 Total Barang | Jumlah baris/kode barang di data yang sedang difilter |
| ✅ Barang Aman | Jumlah barang dengan Status = AMAN |
| 🛒 Perlu Dibeli | Jumlah barang dengan Status = TIDAK AMAN (stok di bawah batas aman) |
| ⛔ Stok Habis | Jumlah barang dengan `Sisa Stok` = 0 |
| 🎯 Barang BEP | Jumlah barang dengan Status = BEP (`Sisa Stok` dan `Safety Stock` sama-sama 0) |
| 🏬 Total Stok | Total `Sisa Stok` dijumlahkan semua barang |
| 🛡️ Total Batas Aman | Total `Safety Stock` dijumlahkan semua barang |
| 📉 Total Kekurangan | Total `Defisit` — makin besar makin banyak yang perlu dibeli. Warna kartu otomatis merah kalau > 0, hijau kalau 0 |

Di bawahnya **"Kondisi Stok Keseluruhan"** — progress bar persentase **Barang Aman + Barang BEP** terhadap total (BEP dihitung "aman" di skor ini). Warna: **hijau "Sehat"** ≥80%, **kuning "Perlu Perhatian"** 50–79%, **merah "Kritis"** <50%.

### 2. Yang Perlu Diperhatikan

Kartu peringatan bahasa natural: berapa barang di bawah batas aman, berapa yang stoknya benar-benar habis, berapa baris PPB yang belum *Completed*. Kalau tidak ada yang mendesak → satu kartu hijau "✅ Tidak ada yang mendesak".

### 3. Kondisi Stok (chart inventory)

- **Donut "Aman vs Perlu Dibeli"** — proporsi AMAN (hijau) / TIDAK AMAN (merah) / BEP (ungu). Persen ditulis di irisan, legenda di bawah chart.
- **Bar "10 Barang Paling Kurang Stok"** — 10 barang dengan `Defisit` terbesar. Kalau tidak ada defisit → pesan sukses.
- **"Stok Sekarang vs Batas Aman"** — hanya muncul kalau ada barang defisit; bar horizontal membandingkan `Sisa Stok` (biru) vs `Safety Stock` (oranye), label dipotong biar terbaca.
- **"Per Gudang — Aman / Tidak Aman"** dan **"Per Kategori — Aman / Tidak Aman"** — stacked bar jumlah barang per status, dikelompokkan per `Letak Gudang` / `Kategori Induk`.
- **"Per Gudang — Stok vs Batas Aman"** — total `Sisa Stok` vs total `Safety Stock` per gudang.
- **"Lead Time vs Kekurangan Stok"** — scatter, tiap titik satu barang: X = `Lead Time`, Y = `Defisit`, warna = Status, ukuran = besar defisit. Titik merah besar di kanan-atas = kandidat prioritas procurement tertinggi.
- **"Catatan Otomatis"** — 3–4 kalimat ringkas otomatis (lihat [rumus insight](#insight-otomatis)).

### 4. Yang Perlu Segera Dibeli

Muncul kalau ada barang TIDAK AMAN: tabel 8 barang paling mendesak (urut Priority Score) dengan kolom bahasa awam — Stok Sekarang, Batas Aman, Kurang, "Seberapa Mendesak" (🔴/🟠/🟢), dan Saran. Daftar lengkapnya ada di tab Procurement.

### 5. Permintaan Pembelian (PPB) — kalau file PPB diupload

Kartu KPI (Jumlah PPB, Baris Item, Total Kuantitas, Masih 'Requested'), periode tanggal, plus chart **Status PPB** dan **PPB per Divisi (Top 10)**.

### 6. Barang Keluar Gudang (NPBG) — kalau file NPBG diupload

Kartu KPI (Jumlah NPBG, Baris Item Keluar, Total Kuantitas Keluar, Rata-rata/Bulan), periode + jumlah baris tipe PENJUALAN, plus chart **Barang Keluar per Bulan**, **Untuk Apa Barang Dikeluarkan (Top 10)**, **Divisi Pemakai Terbanyak (Top 10)**.

## Kolom NPBG & Pencocokan Deskripsi

Kalau file **Excel NPBG** ikut diupload, tab **Data Inventory** menambahkan kolom **`NPBG`** = **berapa banyak baris NPBG untuk barang tersebut**. Logikanya di `utils/npbg_match.py`.

### Aturan pengisian

```
JIKA Status == "AMAN":
    cocokkan Deskripsi Barang inventory dengan seluruh baris di file NPBG
    JIKA ada MATCH → NPBG = jumlah semua baris NPBG yang match (dijumlahkan lintas varian nama)
    JIKA tidak    → NPBG = NULL
SELAIN ITU (TIDAK AMAN / BEP):
    NPBG = NULL
```

`NULL` (sel kosong) berarti **tidak ada pasangan / bukan barang AMAN** — tidak pernah diubah jadi `0`. Kolom `NPBG` read-only di tabel edit.

### Cara pencocokan

Tidak memakai *exact match* saja, karena nama barang bisa punya typo 1–2 huruf, beda huruf besar/kecil, beda spasi, beda format satuan, singkatan, atau urutan kata yang sedikit berbeda.

1. **Normalisasi teks**: huruf kecil, buang aksen & tanda baca, `6 M3` → `6m3`, `1,5` → `1.5`, `10 x 100` → `10x100`.
2. **Penjaga spesifikasi (`spec_key`)**: kumpulan angka pada nama harus **identik** dulu. `OXYGEN GAS 6M3` vs `OXYGEN GAS 10M3` → angka beda (6 vs 10) → **NO MATCH**, sekalipun teksnya sangat mirip. Ini mencegah barang dengan kapasitas/ukuran/model beda tertukar.
3. **Similarity** (rasio `difflib`, tahan terhadap urutan kata yang sedikit beda):

   | Similarity | Verdict |
   |---|---|
   | ≥ 0.90 | **MATCH** — dihitung |
   | 0.80 – 0.89 | REVIEW — mirip tapi **tidak** dianggap match otomatis |
   | < 0.80 | NO MATCH |

**Contoh MATCH:** `OXYGEN GAS 6M3` ↔ `OXYGEN GAZ 6M3` (typo 1 huruf) · `OXYGEN GAS 6M3` ↔ `Oxygen Gas 6 M3` (beda spasi/kapital).
**Contoh NO MATCH:** `OXYGEN GAS 6M3` ↔ `OXYGEN GAS 10M3` (kapasitas beda).

**Contoh penjumlahan:** kalau di file NPBG ada `OXYGEN GAS 6M3` (2 baris) + `OXYGEN GAZ 6M3` (4 baris) + `Oxygen Gas 6 M3` (3 baris), maka barang inventory `Oxygen Gas 6M3` yang berstatus AMAN → `NPBG = 9`.

Hasil matching di-cache (`@st.cache_data`) berdasarkan daftar deskripsi NPBG + himpunan barang AMAN, jadi mengedit sel lain di tabel tidak memicu perhitungan ulang.

## Rumus Perhitungan — Detail Lengkap

Kolom turunan `Selisih`, `Status`, `Defisit`, `Priority Score`, `Priority Level`, `Rekomendasi` dihitung ulang oleh `recalculate()` di [`utils/calculations.py`](utils/calculations.py) setiap kali data berubah. Kolom `NPBG` dihitung terpisah oleh `utils/npbg_match.py` setelah `recalculate()`. Tidak ada nilai yang disimpan permanen.

**1. Selisih**
```
Selisih = Sisa Stok − Safety Stock
```
Nilai kosong dianggap 0 sebelum dikurangkan. Selisih negatif = stok sudah di bawah batas aman.

**2. Status**
```
Status = "AMAN"       jika Selisih ≥ 0
Status = "TIDAK AMAN" jika Selisih <  0
Status = "BEP"        jika Sisa Stok = 0  DAN  Safety Stock = 0   (menang di atas dua aturan di atas)
```
BEP ("Break Even Point" dalam konteks aplikasi ini berarti stok maupun ambang batas amannya sama-sama 0) dicek terpisah dari Selisih: kondisi ini lebih menandakan barang yang belum diberi kebijakan stok sama sekali (bukan benar-benar "aman"), jadi dipisahkan jadi status sendiri.

**3. Defisit** (seberapa jauh di bawah safety stock, tidak pernah negatif)
```
Defisit = max(Safety Stock − Sisa Stok, 0)
```
Barang AMAN maupun BEP otomatis punya Defisit = 0.

**4. Priority Score** (dasar pengurutan tab Procurement)
```
jika Status = TIDAK AMAN:
    Priority Score = (Defisit × 2.0) + (Lead Time × 1.0)
selain itu:
    Priority Score = 0
```
Bobot `2.0` untuk Defisit dan `1.0` untuk Lead Time hardcoded di `compute_priority_score()` — besarnya kekurangan stok dianggap **2× lebih penting** daripada lamanya lead time.

**5. Priority Level**
```
jika Status = AMAN atau BEP → "LOW"
jika Status = TIDAK AMAN:
    threshold_defisit = median(Defisit dari semua barang TIDAK AMAN)
    "HIGH"   jika Defisit ≥ threshold_defisit  ATAU  Lead Time ≥ Ambang Lead Time
    "MEDIUM" untuk sisanya
```
"Ambang Lead Time" (default sidebar) dihitung oleh `suggest_lead_time_threshold()`: **persentil ke-75 dari kolom Lead Time**, dibulatkan; jatuh ke default `14` kalau kolom kosong/tidak valid. Bisa diubah manual lewat input **"Ambang Lead Time Tinggi"** di sidebar.

**6. Rekomendasi** (teks per baris)
```
jika Selisih ≥ 0 dan Sisa Stok = 0 dan Safety Stock = 0 → "Stok dan Safety Stock sama-sama 0 (BEP) — cek apakah barang ini memang non-aktif atau datanya belum diisi."
jika Selisih ≥ 0 (selain kondisi BEP di atas)            → "Stok aman, tidak perlu replenishment segera."
jika Selisih < 0 dan Lead Time ≥ Ambang Lead Time        → "Prioritas tinggi untuk procurement."
jika Selisih < 0 dan Lead Time <  Ambang Lead Time       → "Segera lakukan replenishment."
```

**7. Kondisi Stok Keseluruhan** (health bar)
```
Skor (%) = round((Barang Aman + Barang BEP) / Total Barang × 100, 1)
```
BEP dihitung "aman" khusus untuk skor ini. ≥80% → "Sehat" (hijau), 50–79.9% → "Perlu Perhatian" (kuning), <50% → "Kritis" (merah).

**8. NPBG** — lihat [Kolom NPBG & Pencocokan Deskripsi](#kolom-npbg--pencocokan-deskripsi).

### Insight Otomatis

`utils/insights.py` menghasilkan kalimat berdasarkan aturan berikut, dievaluasi terhadap data yang sedang difilter:

1. Kalau ada barang berstatus BEP → tampil dulu jumlahnya, sebagai pengingat untuk dicek apakah barang itu memang non-aktif atau datanya belum diisi.
2. Kalau tidak ada barang TIDAK AMAN → tampil "✅ Semua stok lainnya aman, masih di atas safety stock."
3. Kalau ada → tampil jumlah barang TIDAK AMAN.
4. Barang dengan `Defisit` terbesar (`Defisit.idxmax()`) disebutkan namanya secara spesifik beserta jumlah kekurangannya.
5. Kalau ada barang TIDAK AMAN dengan `Lead Time ≥ Ambang Lead Time`, jumlahnya disebutkan sebagai "yang paling perlu diprioritaskan buat dibeli".

## Tab Procurement

Terletak setelah tab Data NPBG. Berisi hanya barang dengan `Status = TIDAK AMAN`, **diurutkan menurun berdasarkan Priority Score** (jadi barang dengan kombinasi defisit besar + lead time lama selalu di atas).

3 metric di atas tabel:
- **Barang Perlu Aksi** = jumlah baris TIDAK AMAN.
- **Total Defisit** = jumlah `Defisit` dari semua barang tersebut.
- **Prioritas Tinggi** = jumlah baris dengan `Priority Level = "HIGH"`.

Baris `Priority Level` diwarnai (merah=HIGH, kuning=MEDIUM, hijau=LOW) langsung di tabel untuk pemindaian cepat.

## Filter (Sidebar)

Semua filter berikut bekerja bersama (AND) dan langsung memengaruhi KPI, chart, insight, dan tab Procurement secara serentak — tidak perlu tombol "Apply". Berlaku untuk tab **Dashboard, Data Inventory, dan Procurement**; tab Data PPB & Data NPBG punya filter sendiri di dalamnya.

- Kategori Induk, Kategori Anak 1/2/3, UoM, Letak Gudang, Status, "Perlu Blueprint?" (multiselect)
- **Barang dengan NPBG** (radio: Semua / Ada NPBG / Belum ada NPBG) — hanya tampil kalau file NPBG sudah diupload. "Ada NPBG" = kolom `NPBG` terisi, "Belum ada NPBG" = kosong/NULL. Berguna untuk melihat barang mana yang benar-benar pernah keluar gudang.
- Pencarian bebas di Kode Barang / Deskripsi Barang
- Range Lead Time (angka min–max)
- Range Selisih (angka min–max) — bisa negatif; berguna mencari barang yang cuma "dikit di bawah" safety stock (mis. Selisih -5 sampai -1) atau yang sangat kelebihan stok.
- **Ambang Lead Time Tinggi** — bukan filter data, tapi mengubah parameter rumus Priority Level & Rekomendasi.

Kalau ada filter aktif, tab Export otomatis default ke **"Data Terfilter"**.

## Edit Data

Buka tab **Data Inventory**. Semua kolom master (Kode Barang, kategori, deskripsi, UoM, lokasi, Safety Stock, Sisa Stok, Lead Time, `√LT`, MIN PR, dst.) bisa diedit langsung di tabel (`st.data_editor`). Kolom hasil kalkulasi (`Selisih`, `Status`, `Defisit`, `Priority Score`, `Priority Level`, `Rekomendasi`) dan kolom `NPBG` bersifat read-only karena selalu dihitung ulang otomatis.

Tombol **⋮ Kelola Kolom** menyembunyikan kolom dari tampilan tabel **dan** dari download Excel/CSV (laporan PDF tetap lengkap).

## Export Data

Buka tab **Export**, pilih **Seluruh Data** atau **Data Terfilter**, lalu unduh dalam 3 format:

- **Excel (.xlsx)** — data lengkap semua kolom (termasuk `NPBG`), dengan warna conditional di kolom Status (AMAN=hijau, TIDAK AMAN=merah, BEP=ungu).
- **PDF** — laporan siap cetak (`utils/pdf_export.py`, [ReportLab](https://www.reportlab.com/opensource/), tidak butuh binary eksternal), landscape A4: ringkasan KPI, tabel daftar barang (Kode, Deskripsi, Kategori Induk, Gudang, UoM, Safety Stock, Sisa Stok, Selisih, Status berwarna), dan lampiran **Procurement Priority**. Beda dari Excel/CSV, PDF ini ringkasan yang sudah dikurasi kolomnya.
- **CSV** — data lengkap semua kolom, untuk sistem lain yang butuh format polos.

Excel dan CSV mengikuti kolom yang sedang terlihat (kolom yang disembunyikan lewat **Kelola Kolom** ikut hilang); PDF selalu memakai kolom lengkap yang dibutuhkan ringkasannya.

## Bagaimana Reactive Calculation Bekerja

1. Data yang sedang aktif disimpan di `st.session_state.df` (juga `ppb_df` / `npbg_df`), sehingga tidak hilang saat Streamlit rerun.
2. Setiap kali `st.data_editor` mendeteksi perubahan (Safety Stock, Sisa Stok, tambah/hapus baris, dll), Streamlit menjalankan ulang seluruh script dari atas.
3. Hasil edit pada subset yang terfilter digabungkan kembali ke dataset penuh (`merge_edits`), supaya edit di tampilan terfilter tidak menghapus baris lain.
4. `utils.calculations.recalculate()` dipanggil ulang: menghitung `Selisih`, `Status`, `Defisit`, `Priority Score`, `Priority Level`, `Rekomendasi` dari nol.
5. `utils.npbg_match.attach_npbg_column()` dipanggil setelahnya untuk menyegarkan kolom `NPBG` (Status bisa berubah karena edit, file NPBG bisa baru diupload) — bagian fuzzy matching-nya di-cache.
6. Dataset yang sudah dihitung ulang disimpan kembali ke `session_state`, lalu difilter ulang sesuai sidebar sebelum dipakai oleh Dashboard, tab Procurement, dsb.

Karena semua tab dan komponen membaca dari dataframe yang sama (yang baru saja dihitung ulang di run yang sama), KPI, chart, dan insight selalu konsisten satu sama lain — tanpa perlu tombol refresh manual.
