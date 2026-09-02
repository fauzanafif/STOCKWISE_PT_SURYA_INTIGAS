# STOCKWISE — Laporan Ingest (2026-09-02 03:28)

Dibuat oleh `tools/build_stockwise_db.mjs` dari `DATAFIX/`. Sumber kebenaran = Excel; `stockwise.db` = layer normalized.

## Ringkasan tabel

| Tabel | Baris |
|---|--:|
| master_items | 8.964 |
| item_aliases | 0 |
| inventory_snapshots | 2.563 |
| safety_stock_params | 8.736 |
| monthly_consumption | 75.482 |
| ppb_lines | 3.716 |
| ppb_changes | 193 |
| ri_lines | 8.005 |
| po_derived | 1.895 |
| npbg_lines | 13.504 |
| borrow_lend | 387 |
| stpp | 793 |
| tire_transactions | 603 |
| tire_bpn_snapshots | 40 |
| tire_deliver_receive | 18 |
| asset_maintenance | 364 |
| manufacturing | 750 |
| used_returns | 489 |
| vehicles | 60 |
| matching_reviews | 4.354 |
| calc_results | 8.964 |

## Batch upload

| Modul | File | Total | Insert | Duplikat | Need review | Status |
|---|---|--:|--:|--:|--:|---|
| master | DATA.xlsx | 8964 | 8964 | 0 | 0 | OK |
| safety_stock | DATA.xlsx | 81483 | 8736 | 0 | 3824 | OK |
| ppb:PPB | 1. PPB - RI.xlsx | 11237 | 3716 | 57 | 0 | OK |
| ri:RI | 1. PPB - RI.xlsx | 8114 | 8005 | 109 | 0 | OK |
| ppb:PPB Perubahan | 1. PPB - RI.xlsx | 4985 | 193 | 5 | 0 | OK |
| npbg | 2. NPBG.xlsx | 13505 | 13504 | 0 | 0 | OK |
| borrow_lend:Lend | 3. Tracking Borrow & Lend.xlsx | 4157 | 360 | 0 | 0 | OK |
| borrow_lend:Borrow | 3. Tracking Borrow & Lend.xlsx | 4162 | 27 | 0 | 0 | OK |
| stpp:STPP | 4. Tracking STPP.xlsx | 4202 | 777 | 0 | 0 | OK |
| stpp:Maintenance | 4. Tracking STPP.xlsx | 4183 | 16 | 0 | 0 | OK |
| tire:Ban Luar | 5. Tracking Ban Luar.xlsx | 4164 | 603 | 2 | 0 | OK |
| tire_bpn:Ban Luar BPN | 5. Tracking Ban Luar.xlsx | 40 | 40 | 0 | 0 | OK |
| tire_dr:Deliver & Receive Ban SIG-BPN | 5. Tracking Ban Luar.xlsx | 18 | 18 | 0 | 0 | OK |
| asset_maint:Maintenance Kendaraan | 6. Tracking Maintenance Assets.xlsx | 4160 | 364 | 0 | 0 | OK |
| mfg:Manufaktur & Assembly | 7. Tracking Manufaktur & Assembly.xlsx | 4160 | 470 | 0 | 0 | OK |
| mfg:Manufaktur & Jasa Lain-Lain | 7. Tracking Manufaktur & Assembly.xlsx | 4160 | 280 | 10 | 0 | OK |
| used_returns:Spare Part | 8. Tracking Pengembalian Bekas.xlsx | 4159 | 101 | 0 | 0 | OK |
| used_returns:Spare Part Lain | 8. Tracking Pengembalian Bekas.xlsx | 4165 | 388 | 0 | 0 | OK |

## Hasil matching (barang transaksi → master)

| Tabel | MATCHED | POSSIBLE_MATCH | NEED_REVIEW | NEW_ITEM | % matched |
|---|--:|--:|--:|--:|--:|
| ppb_lines | 2153 | 82 | 262 | 1219 | 58% |
| ppb_changes | 124 | 4 | 5 | 60 | 64% |
| ri_lines | 4363 | 203 | 490 | 2949 | 55% |
| npbg_lines | 7843 | 218 | 993 | 4450 | 58% |
| borrow_lend | 119 | 16 | 29 | 223 | 31% |
| stpp | 400 | 32 | 74 | 287 | 50% |
| tire_transactions | 582 | 16 | 1 | 4 | 97% |
| manufacturing | 322 | 22 | 20 | 386 | 43% |
| used_returns | 246 | 42 | 49 | 51 | 63% |

Antrian review (`matching_reviews.decision = 'PENDING'`): **2.558** baris transaksi menunggu keputusan manual. Fuzzy tidak pernah auto-match (RULE 8).

## Kondisi stok (calc run #1, threshold lead time = 14 hari [A-5])

| stock_status | Jumlah item |
|---|--:|
| UNKNOWN | 6.401 |
| BEP | 1.473 |
| AMAN | 952 |
| OUT_OF_STOCK | 91 |
| NO_SAFETY_STOCK | 37 |
| TIDAK_AMAN | 10 |

- Item CRITICAL: **101**
- Item dengan Safety Stock diketahui: **8.625** dari 8.964
- Item yang bisa dinilai (stok & SS diketahui): **1.053**
- Skor Kesehatan [A-4] = AMAN / assessable = 90.4%
- median defisit item TIDAK_AMAN/OUT_OF_STOCK = 1 · P75 = 1

## Data quality flags

- master `DESC_MASS_DUPLICATE`: 126
- master `KODE_DUPLICATE`: 12
- master `KODE_MISSING`: 1
- safety_stock_params SS_CONFLICT: 3824
- used_returns qty negatif: 46
- import_errors: 1 (lihat tabel `import_errors`)

## Catatan ingest

- **master** (file): master sheet = "DATABASE UTAMA"; sheets skipped: Sheet6, cetak, Sheet2
- **master** (column): Nama Alias: 2361 nilai di-drop (isinya "Ya"/"Tidak", bukan alias)
- **safety_stock** (file): 12 sheet SAFETY STOCK diproses; 8736 deskripsi unik; 3824 deskripsi dengan SS/LT beda antar-sheet (dq_flag=SS_CONFLICT, semua varian di safety_stock_variants); 75482 baris monthly_consumption
- **npbg** (file): sheet dilewati: Export List_Klasifikasi, Dropdown List
- **borrow_lend:Lend** (sheet): 3797 baris kosong dilewati
- **borrow_lend:Borrow** (sheet): 4135 baris kosong dilewati
- **stpp:STPP** (sheet): 3425 baris kosong dilewati
- **stpp:Maintenance** (sheet): 4167 baris kosong dilewati
- **tire:Ban Luar** (sheet): 3559 baris kosong dilewati
- **asset_maint:Maintenance Kendaraan** (sheet): 3796 baris kosong dilewati
- **mfg:Manufaktur & Assembly** (sheet): 3690 baris kosong dilewati
- **mfg:Manufaktur & Jasa Lain-Lain** (sheet): 3870 baris kosong dilewati
- **used_returns:Spare Part** (column): 46 nilai qty negatif (shortage bekas, dipertahankan)
- **used_returns:Spare Part Lain** (sheet): 3777 baris kosong dilewati
