-- STOCKWISE data model (SQLite) — see AUDIT/00_decisions.md and AUDIT/02_erd.md
-- Every ingested row keeps lineage: source_file, source_sheet, source_row, upload_batch_id.
-- Unknown numeric values are NULL, never 0 (RULE 11/13).

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- ────────────────────────────────────────────────────────────────────────────
-- Ingest bookkeeping
-- ────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS upload_batches (
    id              INTEGER PRIMARY KEY,
    batch_uid       TEXT NOT NULL UNIQUE,          -- sha1(file + mtime + module)
    filename        TEXT NOT NULL,
    module          TEXT NOT NULL,                 -- master | safety_stock | ppb | ri | npbg | ...
    source_mtime    TEXT,
    uploaded_by     TEXT DEFAULT 'system',
    uploaded_at     TEXT NOT NULL DEFAULT (datetime('now')),
    total_rows      INTEGER DEFAULT 0,
    inserted        INTEGER DEFAULT 0,
    updated         INTEGER DEFAULT 0,
    duplicate       INTEGER DEFAULT 0,
    invalid         INTEGER DEFAULT 0,
    need_review     INTEGER DEFAULT 0,
    status          TEXT DEFAULT 'OK',             -- OK | PARTIAL | FAILED
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS import_errors (
    id              INTEGER PRIMARY KEY,
    upload_batch_id INTEGER NOT NULL REFERENCES upload_batches(id),
    sheet           TEXT,
    source_row      INTEGER,
    column          TEXT,
    rule            TEXT,                          -- MISSING_COLUMN | BAD_TYPE | NULL_KEY | ...
    severity        TEXT DEFAULT 'WARNING',        -- INFO | WARNING | INVALID
    message         TEXT
);

CREATE TABLE IF NOT EXISTS import_notes (
    id              INTEGER PRIMARY KEY,
    upload_batch_id INTEGER REFERENCES upload_batches(id),
    scope           TEXT,                          -- file | sheet | column
    message         TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ────────────────────────────────────────────────────────────────────────────
-- Master data
-- ────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS master_items (
    id                  TEXT PRIMARY KEY,          -- ITEM-000001
    kode_barang         TEXT,                      -- business key; may be NULL / duplicated (A-9)
    kategori_induk      TEXT,
    kategori_anak_1     TEXT,
    kategori_anak_2     TEXT,
    kategori_anak_3     TEXT,
    deskripsi           TEXT NOT NULL,
    deskripsi_norm      TEXT NOT NULL,             -- LEVEL-3 match key (full)
    deskripsi_core      TEXT NOT NULL,             -- condition-tag stripped, typo-fixed
    uom                 TEXT,
    perlu_blueprint     INTEGER,                   -- 1 / 0 / NULL
    letak_gudang        TEXT,
    letak_rak           TEXT,
    blueprint_img_ref   TEXT,
    blueprint_pdf_ref   TEXT,
    blueprint_3d_ref    TEXT,
    dq_flags            TEXT,                      -- comma list: KODE_MISSING,KODE_DUPLICATE,DESC_MASS_DUPLICATE
    source_file         TEXT,
    source_sheet        TEXT,
    source_row          INTEGER,
    upload_batch_id     INTEGER REFERENCES upload_batches(id)
);
CREATE INDEX IF NOT EXISTS ix_master_kode      ON master_items(kode_barang);
CREATE INDEX IF NOT EXISTS ix_master_descnorm  ON master_items(deskripsi_norm);
CREATE INDEX IF NOT EXISTS ix_master_desccore  ON master_items(deskripsi_core);
CREATE INDEX IF NOT EXISTS ix_master_kat       ON master_items(kategori_induk);

CREATE TABLE IF NOT EXISTS item_aliases (
    id              INTEGER PRIMARY KEY,
    master_item_id  TEXT NOT NULL REFERENCES master_items(id),
    alias           TEXT NOT NULL,
    alias_norm      TEXT NOT NULL,
    source          TEXT,
    UNIQUE(master_item_id, alias_norm)
);
CREATE INDEX IF NOT EXISTS ix_alias_norm ON item_aliases(alias_norm);

CREATE TABLE IF NOT EXISTS inventory_snapshots (
    id                  INTEGER PRIMARY KEY,
    master_item_id      TEXT NOT NULL REFERENCES master_items(id),
    snapshot_date       TEXT,                      -- from column header "SISA STOK (22/08/2026)"
    sisa_stok_raw       TEXT,                      -- "STOK 15 PCS"
    sisa_stok_num       REAL,                      -- 15  (NULL if unknown)
    sisa_stok_known     INTEGER NOT NULL DEFAULT 0,
    source_file         TEXT, source_sheet TEXT, source_row INTEGER,
    upload_batch_id     INTEGER REFERENCES upload_batches(id),
    UNIQUE(master_item_id, snapshot_date)
);

-- one logical table fed by the 13 "SAFETY STOCK <CATEGORY>" sheets (A-1)
CREATE TABLE IF NOT EXISTS safety_stock_params (
    id                  INTEGER PRIMARY KEY,
    item_description    TEXT NOT NULL,
    item_desc_norm      TEXT NOT NULL,
    master_item_id      TEXT REFERENCES master_items(id),   -- resolved by matcher; may be NULL
    lead_time_days      REAL,
    sqrt_lt             REAL,
    safety_stock        REAL,
    min_pr              REAL,
    avg_1_bln           REAL,
    avg_3_bln           REAL,
    avg_6_bln           REAL,
    avg_12_bln          REAL,
    source_sheet        TEXT,
    dq_flag             TEXT,                      -- SS_CONFLICT
    source_file         TEXT, source_row INTEGER,
    upload_batch_id     INTEGER REFERENCES upload_batches(id),
    UNIQUE(item_desc_norm)
);
CREATE INDEX IF NOT EXISTS ix_ssp_master ON safety_stock_params(master_item_id);

-- Pre-aggregated monthly usage from the 13 SAFETY STOCK sheets (A-1): one row
-- per (item, month) — the sheets are near-mirrors, so first non-null wins.
-- Transaction-level usage still comes from npbg_lines, which is richer.
CREATE TABLE IF NOT EXISTS monthly_consumption (
    id                  INTEGER PRIMARY KEY,
    item_desc_norm      TEXT NOT NULL,
    master_item_id      TEXT REFERENCES master_items(id),
    period_month        TEXT NOT NULL,             -- 'Agt' .. 'Juli' (kept verbatim)
    period_ym           TEXT,                      -- resolved YYYY-MM
    qty                 REAL,
    source_sheet        TEXT,
    upload_batch_id     INTEGER REFERENCES upload_batches(id),
    UNIQUE(item_desc_norm, period_month)
);

CREATE TABLE IF NOT EXISTS vehicles (
    nopol           TEXT PRIMARY KEY,              -- "W 8246 NZ (NISSAN CWB)"
    keterangan      TEXT,
    first_seen      TEXT,
    last_seen       TEXT
);

-- ────────────────────────────────────────────────────────────────────────────
-- Procurement
-- ────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ppb_lines (
    id              INTEGER PRIMARY KEY,
    row_hash        TEXT NOT NULL UNIQUE,
    no_ppb          TEXT NOT NULL,
    line_no         INTEGER,
    tgl_ppb         TEXT,
    deskripsi       TEXT,
    deskripsi_norm  TEXT,
    master_item_id  TEXT REFERENCES master_items(id),
    match_status    TEXT,                          -- MATCHED | POSSIBLE_MATCH | NEED_REVIEW | NEW_ITEM
    qty             REAL,
    satuan_raw      TEXT,
    peminta         TEXT,
    divisi          TEXT,
    status          TEXT,                          -- Completed | Requested | Amend | Close | Shortage | Error
    keterangan      TEXT,
    cnt_ri          INTEGER, sum_ri REAL, cnt_amend INTEGER, cnt_close INTEGER,
    source_file TEXT, source_sheet TEXT, source_row INTEGER,
    upload_batch_id INTEGER REFERENCES upload_batches(id)
);
CREATE INDEX IF NOT EXISTS ix_ppb_no    ON ppb_lines(no_ppb);
CREATE INDEX IF NOT EXISTS ix_ppb_item  ON ppb_lines(master_item_id);

CREATE TABLE IF NOT EXISTS ppb_changes (
    id              INTEGER PRIMARY KEY,
    row_hash        TEXT NOT NULL UNIQUE,
    no_ppb          TEXT NOT NULL,
    tgl_perubahan   TEXT,
    deskripsi       TEXT,
    deskripsi_norm  TEXT,
    master_item_id  TEXT REFERENCES master_items(id),
    match_status    TEXT,
    qty             REAL,
    satuan_raw      TEXT,
    peminta         TEXT,
    divisi          TEXT,
    tipe_perubahan  TEXT,                          -- AMEND | CLOSE
    keterangan      TEXT,
    source_file TEXT, source_sheet TEXT, source_row INTEGER,
    upload_batch_id INTEGER REFERENCES upload_batches(id)
);
CREATE INDEX IF NOT EXISTS ix_ppbchg_no ON ppb_changes(no_ppb);

CREATE TABLE IF NOT EXISTS ri_lines (
    id              INTEGER PRIMARY KEY,
    row_hash        TEXT NOT NULL UNIQUE,
    no_ri           TEXT NOT NULL,
    line_no         INTEGER,
    tgl_ri          TEXT,
    deskripsi       TEXT,
    deskripsi_norm  TEXT,
    master_item_id  TEXT REFERENCES master_items(id),
    match_status    TEXT,
    qty             REAL,                          -- qty received
    satuan_raw      TEXT,
    no_ppb          TEXT,                          -- FK-ish -> ppb_lines.no_ppb (NULL / '-' -> NULL)
    no_po           TEXT,
    vendor          TEXT,
    no_surat_jalan  TEXT,
    pemeriksa       TEXT,
    keterangan      TEXT,
    source_file TEXT, source_sheet TEXT, source_row INTEGER,
    upload_batch_id INTEGER REFERENCES upload_batches(id)
);
CREATE INDEX IF NOT EXISTS ix_ri_no    ON ri_lines(no_ri);
CREATE INDEX IF NOT EXISTS ix_ri_ppb   ON ri_lines(no_ppb);
CREATE INDEX IF NOT EXISTS ix_ri_po    ON ri_lines(no_po);
CREATE INDEX IF NOT EXISTS ix_ri_item  ON ri_lines(master_item_id);

-- derived from ri_lines (A-17)
CREATE TABLE IF NOT EXISTS po_derived (
    no_po           TEXT PRIMARY KEY,
    vendor          TEXT,
    first_ri_date   TEXT,
    last_ri_date    TEXT,
    ri_count        INTEGER,
    total_qty       REAL
);

-- ────────────────────────────────────────────────────────────────────────────
-- Consumption
-- ────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS npbg_lines (
    id              INTEGER PRIMARY KEY,
    row_hash        TEXT NOT NULL UNIQUE,
    no_npbg         TEXT NOT NULL,
    line_no         INTEGER,
    tgl_npbg        TEXT,
    tipe            TEXT,                          -- PENJUALAN | NON-PENJUALAN | NULL
    klasifikasi     TEXT,                          -- UMUM | PROYEK | STPP | LEND / BORROW | MANUFAKTUR | MAINTENANCE * | JASA
    pelanggan       TEXT,
    nama_proyek     TEXT,
    no_seri_nopol   TEXT,
    deskripsi       TEXT,
    deskripsi_norm  TEXT,
    master_item_id  TEXT REFERENCES master_items(id),
    match_status    TEXT,
    qty             REAL,
    satuan_raw      TEXT,
    peminta         TEXT,
    dikeluarkan_oleh TEXT,
    divisi          TEXT,
    keterangan      TEXT,
    source_file TEXT, source_sheet TEXT, source_row INTEGER,
    upload_batch_id INTEGER REFERENCES upload_batches(id)
);
CREATE INDEX IF NOT EXISTS ix_npbg_no     ON npbg_lines(no_npbg);
CREATE INDEX IF NOT EXISTS ix_npbg_item   ON npbg_lines(master_item_id);
CREATE INDEX IF NOT EXISTS ix_npbg_klas   ON npbg_lines(klasifikasi);
CREATE INDEX IF NOT EXISTS ix_npbg_tgl    ON npbg_lines(tgl_npbg);

-- ────────────────────────────────────────────────────────────────────────────
-- Tracking modules
-- ────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS borrow_lend (
    id              INTEGER PRIMARY KEY,
    row_hash        TEXT NOT NULL UNIQUE,
    arah            TEXT NOT NULL,                 -- LEND | BORROW
    seq_no          INTEGER,
    tgl_pinjam      TEXT,
    deskripsi       TEXT,
    deskripsi_norm  TEXT,
    master_item_id  TEXT REFERENCES master_items(id),
    match_status    TEXT,
    qty             REAL,
    satuan_raw      TEXT,
    pihak           TEXT,                          -- peminta (LEND) / vendor (BORROW)
    keperluan       TEXT,
    est_hari        REAL,
    ref_keluar      TEXT,                          -- -> npbg no
    status          TEXT,
    ref_kembali     TEXT,                          -- -> ri no
    tgl_kembali     TEXT,
    keterangan      TEXT,
    source_file TEXT, source_sheet TEXT, source_row INTEGER,
    upload_batch_id INTEGER REFERENCES upload_batches(id)
);
CREATE INDEX IF NOT EXISTS ix_bl_item ON borrow_lend(master_item_id);
CREATE INDEX IF NOT EXISTS ix_bl_status ON borrow_lend(status);

CREATE TABLE IF NOT EXISTS stpp (
    id              INTEGER PRIMARY KEY,
    row_hash        TEXT NOT NULL UNIQUE,
    no_seri         TEXT,                          -- SN-0001
    seq_no          INTEGER,
    deskripsi       TEXT,
    deskripsi_norm  TEXT,
    master_item_id  TEXT REFERENCES master_items(id),
    match_status    TEXT,
    qty             REAL,
    satuan_raw      TEXT,
    peminta         TEXT,
    penempatan      TEXT,
    tgl_npbg        TEXT,
    ref_npbg        TEXT,
    item_no         INTEGER,
    status          TEXT,
    tgl_ri          TEXT,
    ref_kembali     TEXT,                          -- -> ri no (Tanda Kembali)
    keterangan      TEXT,
    bukti_keluar_ref TEXT, bukti_terima_ref TEXT, nama_file_ref TEXT, nama_file2_ref TEXT,
    source_file TEXT, source_sheet TEXT, source_row INTEGER,
    upload_batch_id INTEGER REFERENCES upload_batches(id)
);
CREATE INDEX IF NOT EXISTS ix_stpp_item ON stpp(master_item_id);
CREATE INDEX IF NOT EXISTS ix_stpp_status ON stpp(status);

CREATE TABLE IF NOT EXISTS tire_transactions (
    id              INTEGER PRIMARY KEY,
    row_hash        TEXT NOT NULL UNIQUE,
    nopol           TEXT,
    tgl_npbg        TEXT,
    ref_npbg        TEXT,                          -- 'ORIGIN' sentinel kept as-is here
    deskripsi_ban_baru TEXT,
    deskripsi_ban_baru_norm TEXT,
    master_item_id  TEXT REFERENCES master_items(id),
    match_status    TEXT,
    no_seri_baru    TEXT,
    deskripsi_ban_lama TEXT,
    no_seri_lama    TEXT,
    ban_pos         REAL,                          -- kolom "Ban"
    pergantian      REAL,
    keterangan_keluar TEXT,
    status          TEXT,
    tgl_ri          TEXT,
    ref_ri          TEXT,
    keterangan_kembali TEXT,
    foto_out_ref TEXT, foto_in_ref TEXT,
    source_file TEXT, source_sheet TEXT, source_row INTEGER,
    upload_batch_id INTEGER REFERENCES upload_batches(id)
);
CREATE INDEX IF NOT EXISTS ix_tire_nopol ON tire_transactions(nopol);
CREATE INDEX IF NOT EXISTS ix_tire_seri  ON tire_transactions(no_seri_baru);

CREATE TABLE IF NOT EXISTS tire_bpn_snapshots (
    id              INTEGER PRIMARY KEY,
    row_hash        TEXT NOT NULL UNIQUE,
    seq_no          INTEGER,
    tanggal_cut_off TEXT,
    nopol           TEXT,
    deskripsi_ban   TEXT,
    no_seri         TEXT,
    foto_ref        TEXT,
    keterangan      TEXT,
    source_file TEXT, source_sheet TEXT, source_row INTEGER,
    upload_batch_id INTEGER REFERENCES upload_batches(id)
);

CREATE TABLE IF NOT EXISTS tire_deliver_receive (
    id              INTEGER PRIMARY KEY,
    row_hash        TEXT NOT NULL UNIQUE,
    seq_no          INTEGER,
    nopol           TEXT,
    tgl_npbg        TEXT,
    ref_npbg        TEXT,
    deskripsi_out   TEXT,
    no_seri_out     TEXT,
    foto_out_ref    TEXT,
    ket_out         TEXT,
    tgl_ri          TEXT,
    ref_ri          TEXT,
    deskripsi_in    TEXT,
    no_seri_in      TEXT,
    foto_in_ref     TEXT,
    ket_in          TEXT,
    source_file TEXT, source_sheet TEXT, source_row INTEGER,
    upload_batch_id INTEGER REFERENCES upload_batches(id)
);

CREATE TABLE IF NOT EXISTS asset_maintenance (
    id              INTEGER PRIMARY KEY,
    row_hash        TEXT NOT NULL UNIQUE,
    no_spk          TEXT,
    sub_spk         TEXT,
    nopol           TEXT,
    tgl_laporan     TEXT,
    keterangan_awal TEXT,
    bengkel         TEXT,
    status          TEXT,
    ref_npbg        TEXT,
    tgl_selesai     TEXT,
    keterangan_akhir TEXT,
    foto_sebelum_ref TEXT, foto_sesudah_ref TEXT, permintaan_ref TEXT,
    nama_file_ref TEXT, nama_file2_ref TEXT,
    source_file TEXT, source_sheet TEXT, source_row INTEGER,
    upload_batch_id INTEGER REFERENCES upload_batches(id)
);
CREATE INDEX IF NOT EXISTS ix_maint_spk   ON asset_maintenance(no_spk);
CREATE INDEX IF NOT EXISTS ix_maint_nopol ON asset_maintenance(nopol);
CREATE INDEX IF NOT EXISTS ix_maint_status ON asset_maintenance(status);

CREATE TABLE IF NOT EXISTS manufacturing (
    id              INTEGER PRIMARY KEY,
    row_hash        TEXT NOT NULL UNIQUE,
    jenis           TEXT NOT NULL,                 -- MA | MJ
    no_dok          TEXT,
    sub             TEXT,
    item_no         INTEGER,
    tgl             TEXT,
    lokasi          TEXT,
    hasil_produk    TEXT,
    hasil_produk_norm TEXT,
    master_item_id  TEXT REFERENCES master_items(id),
    match_status    TEXT,
    no_seri         TEXT,
    proses          TEXT,
    keterangan_awal TEXT,
    status          TEXT,
    ref_npbg        TEXT,
    tgl_selesai     TEXT,
    ref_ri          TEXT,
    keterangan_akhir TEXT,
    foto_ref TEXT, nama_file_ref TEXT,
    source_file TEXT, source_sheet TEXT, source_row INTEGER,
    upload_batch_id INTEGER REFERENCES upload_batches(id)
);
CREATE INDEX IF NOT EXISTS ix_mfg_dok ON manufacturing(no_dok);
CREATE INDEX IF NOT EXISTS ix_mfg_status ON manufacturing(status);

CREATE TABLE IF NOT EXISTS used_returns (
    id              INTEGER PRIMARY KEY,
    row_hash        TEXT NOT NULL UNIQUE,
    format          TEXT NOT NULL,                 -- WIDE | LONG
    ref_npbg        TEXT,
    tgl_npbg        TEXT,
    ref_ri          TEXT,
    tgl_ri          TEXT,
    status          TEXT,
    part_type       TEXT,                          -- WIDE: column name (Bonit BR ...)
    deskripsi       TEXT,                          -- LONG
    deskripsi_norm  TEXT,
    master_item_id  TEXT REFERENCES master_items(id),
    match_status    TEXT,
    qty             REAL,                          -- may be negative (A-7)
    satuan_raw      TEXT,
    keterangan      TEXT,
    foto_keluar_ref TEXT, foto_terima_ref TEXT,
    source_file TEXT, source_sheet TEXT, source_row INTEGER,
    upload_batch_id INTEGER REFERENCES upload_batches(id)
);
CREATE INDEX IF NOT EXISTS ix_ur_npbg ON used_returns(ref_npbg);

-- ────────────────────────────────────────────────────────────────────────────
-- Matching review queue (fuzzy is NEVER auto-applied — RULE 8)
-- ────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS matching_reviews (
    id                  INTEGER PRIMARY KEY,
    source_table        TEXT NOT NULL,
    source_row_id       INTEGER NOT NULL,
    source_desc         TEXT,
    source_desc_norm    TEXT,
    candidate_item_id   TEXT REFERENCES master_items(id),
    candidate_desc      TEXT,
    confidence          REAL,
    method              TEXT,                      -- EXACT_NORM | EXACT_CORE | ALIAS | FUZZY_TOKEN
    decision            TEXT NOT NULL DEFAULT 'PENDING',   -- PENDING | ACCEPT | REJECT | NEW_ITEM
    decided_by          TEXT,
    decided_at          TEXT,
    UNIQUE(source_table, source_row_id, candidate_item_id)
);
CREATE INDEX IF NOT EXISTS ix_mr_decision ON matching_reviews(decision);
CREATE INDEX IF NOT EXISTS ix_mr_src ON matching_reviews(source_table, source_row_id);

-- ────────────────────────────────────────────────────────────────────────────
-- Calculation output (one row per master item per calc run; latest wins)
-- ────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS calc_runs (
    id              INTEGER PRIMARY KEY,
    run_at          TEXT NOT NULL DEFAULT (datetime('now')),
    lead_time_threshold REAL,
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS calc_results (
    master_item_id  TEXT NOT NULL REFERENCES master_items(id),
    calc_run_id     INTEGER NOT NULL REFERENCES calc_runs(id),
    sisa_stok       REAL,
    sisa_stok_known INTEGER,
    safety_stock    REAL,
    safety_stock_known INTEGER,
    lead_time_days  REAL,
    selisih         REAL,
    defisit         REAL,
    stock_status    TEXT,                          -- A-3
    is_critical     INTEGER,
    priority_score  REAL,
    priority_level  TEXT,
    rekomendasi     TEXT,
    incoming_qty    REAL,                          -- outstanding PPB not yet received
    projected_stock REAL,
    avg_monthly_usage REAL,
    PRIMARY KEY (master_item_id, calc_run_id)
);
CREATE INDEX IF NOT EXISTS ix_calc_status ON calc_results(calc_run_id, stock_status);

-- Convenience view: latest calc per item joined to master
CREATE VIEW IF NOT EXISTS v_inventory AS
SELECT m.*, c.*
FROM master_items m
LEFT JOIN calc_results c ON c.master_item_id = m.id
WHERE c.calc_run_id = (SELECT MAX(id) FROM calc_runs);
