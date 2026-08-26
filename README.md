# STOCKWISE

Dashboard inventory berbasis **Python + Streamlit + Pandas + Plotly**. Upload file Excel inventory, edit datanya langsung di tabel interaktif, dan lihat KPI, chart, insight, serta rekomendasi procurement ter-update otomatis — tanpa refresh halaman.

## Struktur Project

```text
STOCKWISE/
├── app.py                     # entry point, layout tab, sidebar, wiring reaktif
├── requirements.txt
├── data/                      # (opsional) tempat menaruh file Excel contoh
├── utils/
│   ├── excel_handler.py       # deteksi baris header, normalisasi/fuzzy-match kolom, parsing "STOK 15 PCS", export & template
│   ├── calculations.py        # Selisih, Status, Defisit, Priority Score/Level (pipeline reaktif)
│   ├── insights.py            # teks insight otomatis
│   ├── recommendations.py     # rule-based recommendation engine
│   └── theme.py                # palet warna bersama (KPI, chart, badge status)
└── components/
    ├── kpi.py                 # KPI cards
    ├── charts.py              # semua visualisasi Plotly
    └── data_editor.py         # st.data_editor + column_config
```

## Menjalankan Secara Lokal

```bash
pip install -r requirements.txt
streamlit run app.py
```

Aplikasi akan terbuka di `http://localhost:8501`.

## Download Template

Belum punya file, atau ingin memastikan format Excel Anda sesuai? Klik **📥 Download Template Excel** di sidebar (atau di layar awal sebelum upload). Template ini sudah memakai layout yang sama seperti export STOCKWISE asli (judul di baris 1-4, header di baris 5) lengkap dengan 2 baris contoh data — satu AMAN, satu TIDAK AMAN — supaya format `Sisa Stok` seperti `STOK 15 PCS` langsung terlihat jelas.

## Upload Excel

1. Buka sidebar **Data** → **Upload Excel Inventory**.
2. Pilih file `.xlsx` atau `.xls`. Baris header **tidak harus di baris pertama** — aplikasi otomatis mencari baris yang memuat kolom "Kode Barang" (sampai 50 baris pertama), jadi file dengan judul/baris kosong di atas header (mis. baris 1-4 judul, header di baris 5) tetap terbaca.
3. Nama kolom tidak harus persis sama — kolom seperti `Safety Stock` atau `SISA STOK (22/08/2026)` dikenali lewat pencocokan kata kunci (`SAFETY`+`STOCK`, `SISA`+`STOK`), jadi tanggal atau variasi penulisan di nama kolom tidak masalah.
4. Kolom `Sisa Stok` boleh berformat teks seperti `STOK 15 PCS` — nilai numeriknya diekstrak otomatis (`STOK 15 PCS` → `15`).
5. Jika kolom wajib (`Kode Barang`, `Deskripsi Barang`, `Safety Stock`, `Sisa Stok`) tetap tidak ditemukan setelah pencocokan otomatis, aplikasi menampilkan pesan error yang jelas — termasuk baris header yang terdeteksi dan daftar kolom yang berhasil dibaca — tanpa crash.

## Edit Data

Buka tab **Data Inventory**. Semua kolom master (Kode Barang, kategori, deskripsi, UoM, lokasi, Safety Stock, Sisa Stok, Lead Time, dst.) bisa diedit langsung di tabel (`st.data_editor`). Kolom hasil kalkulasi (`Selisih`, `Status`, `Defisit`, `Priority Score`, `Priority Level`, `Rekomendasi`) bersifat read-only.

Gunakan sidebar **Filter** (Kategori Induk, Kategori Anak 1, Gudang, Status, pencarian Kode/Deskripsi, range Lead Time) untuk mempersempit data yang ditampilkan — KPI, chart, dan insight otomatis mengikuti data yang sedang difilter.

## Export Data

Buka tab **Export**, pilih apakah ingin export **Seluruh Data** atau **Data Terfilter**, lalu unduh sebagai Excel (dengan warna Status AMAN/TIDAK AMAN) atau CSV. Hasil export sudah termasuk `Selisih`, `Status`, `Defisit`, `Priority Score`, `Priority Level`, dan `Rekomendasi`.

## Bagaimana Reactive Calculation Bekerja

1. Data yang sedang aktif disimpan di `st.session_state.df`, sehingga tidak hilang saat Streamlit melakukan rerun.
2. Setiap kali `st.data_editor` mendeteksi perubahan (Safety Stock, Sisa Stok, tambah/hapus baris, dll), Streamlit menjalankan ulang seluruh script.
3. Hasil edit pada subset yang terfilter digabungkan kembali ke dataset penuh (`merge_edits`).
4. `utils.calculations.recalculate()` dipanggil ulang: menghitung `Selisih = Sisa Stok - Safety Stock`, `Status` (AMAN/TIDAK AMAN), `Defisit`, `Priority Score`, `Priority Level`, dan `Rekomendasi`.
5. Dataset yang sudah dihitung ulang disimpan kembali ke `session_state`, lalu difilter ulang sesuai sidebar sebelum dipakai oleh KPI, chart, insight, dan tab Procurement.

Karena semua tab dan komponen membaca dari dataframe yang sama (yang baru saja dihitung ulang di run yang sama), KPI, chart, dan insight selalu konsisten dengan data terbaru — tanpa perlu tombol refresh manual.
