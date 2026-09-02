# STOCKWISE — ERD (Fase 1)

Definisi lengkap kolom + tipe ada di [`db/schema.sql`](../db/schema.sql). Ini peta relasinya.

```
                          ┌─────────────────┐
                          │  upload_batches │──1:N──> import_errors, import_notes
                          └────────┬────────┘
             (setiap baris ingest menyimpan upload_batch_id + source_file/sheet/row)
                                   │
        ┌──────────────────────────┼───────────────────────────────────────────┐
        ▼                          ▼                                           ▼
┌───────────────┐        ┌──────────────────────┐                    ┌───────────────────┐
│ master_items  │◄─1:N───│ item_aliases         │                    │ safety_stock_     │
│ (ITEM-000001) │        └──────────────────────┘                    │ params            │
│               │◄─1:1───┤ inventory_snapshots (Sisa Stok)           │ (LT, SS, MIN PR,  │
│               │        └──────────────────────┐                    │  avg 1/3/6/12)    │
│               │◄─ resolved by matcher ────────┼── monthly_consumption               │
│               │                               │   (dari 13 sheet SAFETY STOCK)      │
│               │                               └──────────────────────────────────────┘
│               │
│               │◄─ master_item_id + match_status ─┬─ ppb_lines ──┐
│               │                                  ├─ ri_lines ───┤ no_ppb, no_po
│               │                                  ├─ npbg_lines  │
│               │                                  ├─ borrow_lend │
│               │                                  ├─ stpp        │
│               │                                  ├─ tire_transactions
│               │                                  ├─ manufacturing
│               │                                  └─ used_returns
│               │
│               │◄─1:N── calc_results ──N:1──> calc_runs   (v_inventory = master ⋈ calc_results terbaru)
└───────────────┘

matching_reviews  (source_table, source_row_id) ──> master_items(candidate_item_id)
                   decision: PENDING | ACCEPT | REJECT | NEW_ITEM   — fuzzy tidak pernah auto (RULE 8)

Procurement flow (kunci dokumen, bukan FK keras karena sumber tidak selalu lengkap):
   ppb_lines.no_ppb ──< ppb_changes.no_ppb
   ppb_lines.no_ppb ──< ri_lines.no_ppb          (98% baris RI yang berisi No PPB cocok)
   ri_lines.no_po   ──> po_derived.no_po          (po_derived diagregasi dari ri_lines — tidak ada sheet PO)

Tracking → NPBG/RI (kunci dokumen):
   stpp.ref_npbg / stpp.ref_kembali          -> npbg_lines.no_npbg / ri_lines.no_ri
   borrow_lend.ref_keluar / ref_kembali      -> npbg / ri
   tire_transactions.ref_npbg / ref_ri       -> npbg / ri   (nilai 'ORIGIN' = data awal, bukan dokumen)
   asset_maintenance.ref_npbg                -> npbg
   manufacturing.ref_npbg / ref_ri           -> npbg / ri
   used_returns.ref_npbg / ref_ri            -> npbg / ri

Dimensi bersama:
   vehicles(nopol)  <- tire_*, asset_maintenance, npbg_lines.no_seri_nopol
```

## Kunci & kardinalitas

| Entitas | PK | Business key | Catatan |
|---|---|---|---|
| master_items | `id` (ITEM-nnnnnn) | `kode_barang` (nullable, 6 duplikat — [A-9]) | 8.964 baris |
| inventory_snapshots | `id` | `(master_item_id, snapshot_date)` | 1 snapshot/item (header "SISA STOK (22/08/2026)") |
| safety_stock_params | `id` | `item_desc_norm` UNIQUE | 8.736; 6.211 punya SS_CONFLICT antar-sheet |
| ppb_lines / ri_lines / npbg_lines | `id` | `row_hash` UNIQUE (dedup kumulatif) | line item, banyak per nomor dokumen |
| po_derived | `no_po` | — | diturunkan dari ri_lines |
| matching_reviews | `id` | `(source_table, source_row_id, candidate_item_id)` | antrian keputusan manual |
| calc_results | `(master_item_id, calc_run_id)` | — | 1 baris/item/run; `v_inventory` pakai run terbaru |

FK keras (SQLite `REFERENCES`) hanya untuk relasi yang datanya pasti: `*.master_item_id → master_items.id`,
`*.upload_batch_id → upload_batches.id`. Relasi nomor dokumen (no_ppb, no_npbg, dst.) **tidak** dijadikan FK
karena sumber sering memakai sentinel (`-`, `ORIGIN`) atau nomornya belum ada saat baris dibuat.
