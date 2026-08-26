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
2. Jika workbook Anda punya beberapa sheet (mis. `Data`, `Dropdown List`, `cetak`, `Sheet2`), aplikasi otomatis memakai sheet bernama **"Data"** sebagai dataset utama — sheet `cetak`/`Sheet2`/`Dropdown List` tidak pernah dibaca sebagai data inventory. Jika tidak ada sheet bernama "Data", aplikasi jatuh ke sheet pertama yang bukan salah satu dari ketiganya (tidak pernah asal ambil sheet 1).
3. Baris header **tidak harus di baris pertama** — aplikasi otomatis mencari baris yang memuat kolom "Kode Barang" (sampai 50 baris pertama sheet tersebut), jadi file dengan judul/baris kosong di atas header (mis. baris 1-4 judul, header di baris 5) tetap terbaca.
4. Nama kolom tidak harus persis sama — kolom seperti `Safety Stock` atau `SISA STOK (22/08/2026)` dikenali lewat pencocokan kata kunci (`SAFETY`+`STOCK`, `SISA`+`STOK`), begitu juga kolom `√LT` dan `MIN PR`, jadi tanggal atau variasi penulisan di nama kolom tidak masalah.
5. Kolom `Sisa Stok` boleh berformat teks seperti `STOK 15 PCS` — nilai numeriknya diekstrak otomatis (`STOK 15 PCS` → `15`). `Safety Stock` dan `MIN PR` boleh sepenuhnya kosong — kolom yang ada tapi nilainya kosong tetap dianggap valid (bukan "kolom tidak ditemukan"), dan dinormalisasi jadi 0 untuk kalkulasi.
6. Jika ada sheet **"Dropdown List"**, pilihannya (Kategori Induk/Anak 1-3, UoM) otomatis ikut mengisi pilihan selectbox di tabel edit, digabung dengan nilai yang sudah ada di data.
7. Jika kolom wajib (`Kode Barang`, `Deskripsi Barang`, `Safety Stock`, `Sisa Stok`) tetap tidak ditemukan setelah pencocokan otomatis, aplikasi menampilkan pesan error yang jelas — termasuk sheet & baris header yang terdeteksi dan daftar kolom yang berhasil dibaca — tanpa crash.
8. Buka expander **🐞 Debug Excel** di tab Data Inventory untuk melihat sheet yang dipakai, baris header, kolom yang terdeteksi, dan pilihan dropdown yang terbaca — berguna kalau format Excel berubah lagi di kemudian hari.

## Edit Data

Buka tab **Data Inventory**. Semua kolom master (Kode Barang, kategori, deskripsi, UoM, lokasi, Safety Stock, Sisa Stok, Lead Time, `√LT`, `MIN PR`, dst.) bisa diedit langsung di tabel (`st.data_editor`). Kolom hasil kalkulasi (`Selisih`, `Status`, `Defisit`, `Priority Score`, `Priority Level`, `Rekomendasi`) bersifat read-only.

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
