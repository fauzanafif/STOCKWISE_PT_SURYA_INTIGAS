# STOCKWISE

Dashboard inventory berbasis **Python + Streamlit + Pandas + Plotly**. Upload file Excel inventory, edit datanya langsung di tabel interaktif, dan lihat KPI, chart, insight, serta rekomendasi procurement ter-update otomatis — tanpa refresh halaman, tanpa database, tanpa login. File Excel yang diupload adalah satu-satunya sumber data; semua kalkulasi jalan ulang di memori setiap kali ada perubahan.

## Daftar Isi

- [Tech Stack](#tech-stack)
- [Struktur Project](#struktur-project)
- [Menjalankan Secara Lokal](#menjalankan-secara-lokal)
- [Download Template](#download-template)
- [Upload Excel](#upload-excel)
- [Skema Data (Kolom Excel)](#skema-data-kolom-excel)
- [Cara Membaca Dashboard](#cara-membaca-dashboard)
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
| Tulis Excel | [XlsxWriter](https://xlsxwriter.readthedocs.io) `>=3.1` | Generate file export & template dengan conditional formatting (warna AMAN/TIDAK AMAN) |
| Charting | [Plotly](https://plotly.com/python/) `>=5.20` (`plotly.express` + `plotly.graph_objects`) | Semua 7 visualisasi di dashboard, dirender via `st.plotly_chart` |
| State | `st.session_state` (bawaan Streamlit) | Menyimpan dataframe aktif & pengaturan (threshold lead time) antar-rerun, tidak butuh Redux/Zustand |
| Styling | CSS custom (`st.markdown(unsafe_allow_html=True)`) di `app.py` | Font Inter (Google Fonts), kartu KPI, health bar, kartu insight |
| Auth / DB | **Tidak ada** | Single-user, stateless per sesi browser; tidak ada login, role, atau database — "database"-nya adalah file Excel itu sendiri |

Tidak ada framework frontend terpisah (React/Vue dst.) — satu file `app.py` di-render penuh oleh Streamlit, navigasi antar-halaman cukup pakai `st.tabs`.

## Struktur Project

```text
STOCKWISE/
├── app.py                     # entry point: page config, CSS, sidebar, 4 tab, wiring reaktif
├── requirements.txt
├── assets/logo.png             # logo aplikasi (di-embed sebagai base64)
├── data/                       # (opsional) tempat menaruh file Excel contoh
├── utils/
│   ├── excel_handler.py        # deteksi sheet & baris header, fuzzy-match kolom, parsing "STOK 15 PCS", export & template
│   ├── calculations.py         # pipeline reaktif: Selisih, Status, Defisit, Priority Score/Level
│   ├── insights.py             # generator teks insight otomatis (rule-based)
│   ├── recommendations.py      # generator rekomendasi procurement per baris (rule-based)
│   └── theme.py                 # palet warna bersama — dipakai KPI, chart, dan badge status
└── components/
    ├── kpi.py                  # kartu KPI + health bar
    ├── charts.py                # ke-7 visualisasi Plotly
    └── data_editor.py           # st.data_editor + column_config (kolom mana editable, mana read-only)
```

## Menjalankan Secara Lokal

```bash
pip install -r requirements.txt
streamlit run app.py
```

Aplikasi terbuka di `http://localhost:8501`.

## Download Template

Belum punya file, atau ingin memastikan format Excel Anda sesuai? Klik **📥 Download Template Excel** di sidebar (atau di layar awal sebelum upload). Template memakai layout yang sama seperti export STOCKWISE asli (judul di baris 1-4, header di baris 5) lengkap dengan 2 baris contoh data — satu AMAN, satu TIDAK AMAN — supaya format `Sisa Stok` seperti `STOK 15 PCS` langsung terlihat jelas.

## Upload Excel

1. Buka sidebar **Data** → **Upload Excel Inventory**.
2. Jika workbook Anda punya beberapa sheet (mis. `Data`, `Dropdown List`, `cetak`, `Sheet2`), aplikasi otomatis memakai sheet bernama **"Data"** sebagai dataset utama — sheet `cetak`/`Sheet2`/`Dropdown List` tidak pernah dibaca sebagai data inventory. Jika tidak ada sheet bernama "Data", aplikasi jatuh ke sheet pertama yang bukan salah satu dari ketiganya.
3. Baris header **tidak harus di baris pertama** — aplikasi otomatis mencari baris yang memuat kolom "Kode Barang" (sampai 50 baris pertama sheet tersebut), jadi file dengan judul/baris kosong di atas header tetap terbaca.
4. Nama kolom tidak harus persis sama — kolom seperti `Safety Stock` atau `SISA STOK (22/08/2026)` dikenali lewat pencocokan kata kunci (`SAFETY`+`STOCK`, `SISA`+`STOK`), begitu juga `√LT` dan `MIN PR`, jadi variasi penulisan/tanggal di nama kolom tidak masalah.
5. Kolom `Sisa Stok` boleh berformat teks seperti `STOK 15 PCS` — nilai numeriknya diekstrak otomatis lewat regex (`STOK 15 PCS` → `15`). `Safety Stock` dan `MIN PR` boleh sepenuhnya kosong — dianggap valid dan dinormalisasi jadi `0` untuk kalkulasi.
6. Jika ada sheet **"Dropdown List"**, pilihannya (Kategori Induk/Anak 1-3, UoM) otomatis mengisi pilihan selectbox di tabel edit, digabung dengan nilai yang sudah ada di data.
7. Jika kolom wajib (`Kode Barang`, `Deskripsi Barang`, `Safety Stock`, `Sisa Stok`) tetap tidak ditemukan setelah pencocokan otomatis, muncul pesan error jelas — termasuk sheet & baris header yang terdeteksi dan daftar kolom yang berhasil dibaca — tanpa crash.
8. Buka expander **🐞 Debug Excel** di tab Data Inventory untuk melihat sheet yang dipakai, baris header, kolom yang terdeteksi, dan pilihan dropdown yang terbaca.

## Skema Data (Kolom Excel)

Didefinisikan di `utils/excel_handler.py`.

**Kolom wajib** (aplikasi error kalau tidak ketemu): `Kode Barang`, `Deskripsi Barang`, `Safety Stock`, `Sisa Stok`.

**Kolom master lain yang dikenali** (opsional): Kategori Induk, Kategori Anak 1/2/3, UoM, Perlu Blueprint?, Nama Alias, Letak Gudang, Letak Rak, Blueprint IMG/Detail PDF/3D View, Lead Time, `√LT`, MIN PR.

**Kolom numerik** (dipaksa jadi angka, kosong → 0): `Safety Stock`, `Sisa Stok`, `Lead Time`, `MIN PR`.

**Kolom hasil kalkulasi** (read-only, dibuat otomatis, jangan diisi manual di Excel karena akan ditimpa): `Selisih`, `Status`, `Defisit`, `Priority Score`, `Priority Level`, `Rekomendasi`.

## Cara Membaca Dashboard

Tab **Dashboard** tersusun dari atas ke bawah dalam 4 blok. Semua angka di sini selalu mengikuti filter sidebar yang sedang aktif.

### 1. KPI Cards + Health Bar (paling atas)

7 kartu angka besar, lalu satu progress bar "Skor Kesehatan Inventory":

| Kartu | Arti |
|---|---|
| 📦 Total Barang | Jumlah baris/kode barang di data yang sedang difilter |
| ✅ Barang Aman | Jumlah barang dengan Status = AMAN |
| 🚨 Barang Tidak Aman | Jumlah barang dengan Status = TIDAK AMAN |
| 🎯 Barang BEP | Jumlah barang dengan Status = BEP (`Sisa Stok` dan `Safety Stock` sama-sama 0) |
| 🏬 Total Stok | Total `Sisa Stok` dijumlahkan semua barang |
| 🛡️ Total Safety Stock | Total `Safety Stock` dijumlahkan semua barang |
| 📉 Defisit Stok | Total `Defisit` — makin besar makin banyak yang perlu dibeli. Warna kartu ini otomatis merah kalau > 0, hijau kalau 0 |

Health bar di bawahnya menunjukkan persentase **Barang Aman** (bukan BEP, bukan Tidak Aman) terhadap total. Warna berubah otomatis: **hijau "Sehat"** ≥80%, **kuning "Perlu Perhatian"** 50–79%, **merah "Kritis"** <50%.

### 2. "Kondisi Inventory Saat Ini" — 3 chart

- **Donut "Status Inventory"** (kiri) — proporsi AMAN (hijau), TIDAK AMAN (merah), dan BEP (ungu). Cara baca: makin besar irisan merah, makin banyak barang di bawah safety stock; irisan ungu menandakan barang yang belum punya kebijakan stok sama sekali (stok maupun safety stock-nya 0).
- **Bar horizontal "Top Barang dengan Defisit Terbesar"** (kanan) — 10 barang dengan `Defisit` terbesar, diurutkan menurun, warna gradasi biru sesuai besarnya defisit. Barang BEP tidak pernah muncul di sini karena Defisit-nya selalu 0. Kalau tidak ada barang defisit, chart ini diganti pesan sukses.
- **Grouped bar "Stok vs Safety Stock"** (lebar penuh) — untuk 10 barang dengan defisit terbesar yang sama, membandingkan batang biru (`Sisa Stok`) vs oranye (`Safety Stock`) berdampingan. Kalau batang biru lebih pendek dari oranye, barang itu di bawah ambang aman.

### 3. "Analisis per Lokasi & Kategori" — 4 chart, 2 kolom

- **Stacked bar "Inventory per Gudang — Status"** — per `Letak Gudang`, tumpukan hijau (AMAN) + merah (TIDAK AMAN) + ungu (BEP). Gudang diurutkan dari yang jumlah barangnya paling banyak.
- **Grouped bar "Inventory per Gudang — Stok vs Safety Stock"** — per gudang, total `Sisa Stok` (biru) vs total `Safety Stock` (oranye) dijumlahkan semua barang di gudang itu.
- **Stacked bar "Inventory per Kategori Induk"** — logika sama seperti chart gudang, tapi dikelompokkan per `Kategori Induk`.
- **Scatter "Lead Time vs Defisit"** — setiap titik = satu barang (bukan agregat). Sumbu X = `Lead Time`, sumbu Y = `Defisit`, warna titik = Status (hijau/merah/ungu), ukuran titik makin besar = defisit makin besar. Titik BEP selalu menempel di Defisit = 0. **Cara baca paling penting**: titik merah besar yang letaknya di kanan atas (lead time lama + defisit besar) adalah kandidat prioritas procurement tertinggi — logika yang sama persis dengan `Priority Score`.

### 4. Inventory Insight (paling bawah)

3–4 kalimat ringkas otomatis (lihat [rumus insight](#insight-otomatis) di bawah) — semacam "TL;DR" dari semua chart di atasnya, langsung dalam bahasa natural.

## Rumus Perhitungan — Detail Lengkap

Semua kolom turunan dihitung ulang oleh `recalculate()` di [`utils/calculations.py`](utils/calculations.py) setiap kali data berubah (upload baru atau edit tabel). Tidak ada nilai yang disimpan permanen — semuanya dihitung ulang dari `Sisa Stok`, `Safety Stock`, dan `Lead Time` mentah setiap rerun.

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
BEP ("Break Even Point" dalam konteks aplikasi ini berarti stok maupun ambang batas amannya sama-sama 0) dicek terpisah dari Selisih: `Sisa Stok = 0` dan `Safety Stock = 0` membuat `Selisih = 0` juga, yang secara formula murni AMAN — tapi kondisi ini lebih menandakan barang yang belum diberi kebijakan stok sama sekali (bukan benar-benar "aman"), jadi dipisahkan jadi status sendiri.

**3. Defisit** (seberapa jauh di bawah safety stock, tidak pernah negatif)
```
Defisit = max(Safety Stock − Sisa Stok, 0)
```
Barang AMAN maupun BEP otomatis punya Defisit = 0 (karena `Safety Stock − Sisa Stok` akan ≤ 0 lalu dipangkas ke 0).

**4. Priority Score** (dasar pengurutan tab Procurement)
```
jika Status = TIDAK AMAN:
    Priority Score = (Defisit × 2.0) + (Lead Time × 1.0)
jika Status = AMAN:
    Priority Score = 0
```
Bobot `2.0` untuk Defisit dan `1.0` untuk Lead Time adalah default hardcoded di `compute_priority_score()` — artinya besarnya kekurangan stok dianggap **2× lebih penting** daripada lamanya lead time saat menentukan urutan prioritas beli.

**5. Priority Level**
```
jika Status = AMAN atau BEP → "LOW"
jika Status = TIDAK AMAN:
    threshold_defisit = median(Defisit dari semua barang TIDAK AMAN)
    "HIGH"   jika Defisit ≥ threshold_defisit  ATAU  Lead Time ≥ Ambang Lead Time
    "MEDIUM" untuk sisanya
```
"Ambang Lead Time" (default sidebar) dihitung oleh `suggest_lead_time_threshold()`: **persentil ke-75 dari kolom Lead Time** di seluruh dataset, dibulatkan; jatuh ke default `14` kalau kolom kosong/tidak valid. Nilai ini bisa diubah manual lewat input **"Ambang Lead Time Tinggi"** di sidebar, dan perubahannya langsung memengaruhi Priority Level & Rekomendasi di semua tab.

**6. Rekomendasi** (teks per baris)
```
jika Selisih ≥ 0 dan Sisa Stok = 0 dan Safety Stock = 0 → "Stok dan Safety Stock sama-sama 0 (BEP) — cek apakah barang ini memang non-aktif atau datanya belum diisi."
jika Selisih ≥ 0 (selain kondisi BEP di atas)            → "Stok aman, tidak perlu replenishment segera."
jika Selisih < 0 dan Lead Time ≥ Ambang Lead Time        → "Prioritas tinggi untuk procurement."
jika Selisih < 0 dan Lead Time <  Ambang Lead Time       → "Segera lakukan replenishment."
```

**7. Skor Kesehatan Inventory** (health bar KPI)
```
Skor Kesehatan (%) = round(Barang Aman / Total Barang × 100, 1)
```
≥80% → "Sehat" (hijau), 50–79.9% → "Perlu Perhatian" (kuning), <50% → "Kritis" (merah).

### Insight Otomatis

`utils/insights.py` menghasilkan kalimat berdasarkan aturan berikut, dievaluasi terhadap data yang sedang difilter:

1. Kalau ada barang berstatus BEP → tampil dulu jumlahnya, sebagai pengingat untuk dicek apakah barang itu memang non-aktif atau datanya belum diisi.
2. Kalau tidak ada barang TIDAK AMAN → tampil "✅ Semua stok lainnya aman, masih di atas safety stock."
3. Kalau ada → tampil jumlah barang TIDAK AMAN.
4. Barang dengan `Defisit` terbesar (`Defisit.idxmax()`) disebutkan namanya secara spesifik beserta jumlah kekurangannya.
5. Kalau ada barang TIDAK AMAN dengan `Lead Time ≥ Ambang Lead Time`, jumlahnya disebutkan sebagai "yang paling perlu diprioritaskan buat dibeli".

## Tab Procurement

Berisi hanya barang dengan `Status = TIDAK AMAN`, **diurutkan menurun berdasarkan Priority Score** (bukan Defisit atau Lead Time saja — jadi barang dengan kombinasi defisit besar + lead time lama akan selalu di atas).

3 metric di atas tabel:
- **Barang Perlu Aksi** = jumlah baris TIDAK AMAN.
- **Total Defisit** = jumlah `Defisit` dari semua barang tersebut.
- **Prioritas Tinggi** = jumlah baris dengan `Priority Level = "HIGH"`.

Baris `Priority Level` diwarnai (merah=HIGH, kuning=MEDIUM, hijau=LOW) langsung di tabel untuk pemindaian cepat.

## Filter (Sidebar)

Semua filter berikut bekerja bersama (AND) dan langsung memengaruhi KPI, ke-7 chart, insight, dan tab Procurement secara serentak — tidak perlu tombol "Apply":

- Kategori Induk, Kategori Anak 1/2/3, UoM, Letak Gudang, Status, "Perlu Blueprint?" (multiselect)
- Pencarian bebas di Kode Barang / Deskripsi Barang
- Range Lead Time (slider min–max)
- **Ambang Lead Time Tinggi** — bukan filter data, tapi mengubah parameter rumus Priority Level & Rekomendasi (lihat bagian rumus di atas)

## Edit Data

Buka tab **Data Inventory**. Semua kolom master (Kode Barang, kategori, deskripsi, UoM, lokasi, Safety Stock, Sisa Stok, Lead Time, `√LT`, MIN PR, dst.) bisa diedit langsung di tabel (`st.data_editor`). Kolom hasil kalkulasi (`Selisih`, `Status`, `Defisit`, `Priority Score`, `Priority Level`, `Rekomendasi`) bersifat read-only karena selalu dihitung ulang otomatis.

## Export Data

Buka tab **Export**, pilih **Seluruh Data** atau **Data Terfilter**, lalu unduh sebagai Excel (dengan warna conditional Status AMAN=hijau/TIDAK AMAN=merah) atau CSV. Hasil export selalu menyertakan `Selisih`, `Status`, `Defisit`, `Priority Score`, `Priority Level`, dan `Rekomendasi` — bukan cuma data mentahnya.

## Bagaimana Reactive Calculation Bekerja

1. Data yang sedang aktif disimpan di `st.session_state.df`, sehingga tidak hilang saat Streamlit melakukan rerun.
2. Setiap kali `st.data_editor` mendeteksi perubahan (Safety Stock, Sisa Stok, tambah/hapus baris, dll), Streamlit menjalankan ulang seluruh script dari atas.
3. Hasil edit pada subset yang terfilter digabungkan kembali ke dataset penuh (`merge_edits`), supaya edit di tampilan terfilter tidak menghapus baris lain.
4. `utils.calculations.recalculate()` dipanggil ulang: menghitung `Selisih`, `Status`, `Defisit`, `Priority Score`, `Priority Level`, dan `Rekomendasi` dari nol berdasarkan rumus di atas.
5. Dataset yang sudah dihitung ulang disimpan kembali ke `session_state`, lalu difilter ulang sesuai sidebar sebelum dipakai oleh KPI, chart, insight, dan tab Procurement.

Karena semua tab dan komponen membaca dari dataframe yang sama (yang baru saja dihitung ulang di run yang sama), KPI, chart, dan insight selalu konsisten satu sama lain — tanpa perlu tombol refresh manual.
