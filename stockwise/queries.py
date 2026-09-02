"""Read layer for the dashboard pages. All functions return DataFrames/dicts
from stockwise.db — pages never touch Excel or recompute (spec §22, §35).

Wrap calls in st.cache_data at the page level, keyed on the latest calc_run id
(`latest_calc_run()`), so cache invalidates when data changes.
"""
from __future__ import annotations

import pandas as pd

from stockwise.db import read_df, scalar


# ── freshness key for caching ───────────────────────────────────────────────
def latest_calc_run() -> int | None:
    return scalar("SELECT MAX(id) FROM calc_runs")


def data_fingerprint() -> str:
    parts = [
        scalar("SELECT COALESCE(MAX(id),0) FROM calc_runs"),
        scalar("SELECT COALESCE(MAX(id),0) FROM upload_batches"),
        scalar("SELECT COUNT(*) FROM matching_reviews WHERE decision <> 'PENDING'"),
    ]
    return "-".join(str(p) for p in parts)


# ── executive KPIs ─────────────────────────────────────────────────────────
def executive_kpis() -> dict:
    row = read_df(
        """
        SELECT
          (SELECT COUNT(*) FROM master_items)                                         AS total_item,
          (SELECT COALESCE(SUM(sisa_stok),0) FROM v_inventory WHERE sisa_stok_known=1) AS total_stok,
          SUM(stock_status='AMAN')            AS aman,
          SUM(stock_status='TIDAK_AMAN')      AS tidak_aman,
          SUM(stock_status='OUT_OF_STOCK')    AS out_of_stock,
          SUM(is_critical=1)                  AS critical,
          SUM(stock_status='NO_SAFETY_STOCK') AS no_ss,
          SUM(stock_status='UNKNOWN')         AS unknown_stok,
          SUM(safety_stock_known=1)           AS ss_known,
          COALESCE(SUM(defisit),0)            AS total_defisit,
          COALESCE(SUM(incoming_qty),0)       AS incoming
        FROM v_inventory
        """
    ).iloc[0].to_dict()
    row["ppb_outstanding"] = scalar(
        "SELECT COUNT(DISTINCT no_ppb) FROM ppb_lines WHERE LOWER(COALESCE(status,'')) NOT IN ('completed','close','error')"
    )
    row["po_outstanding"] = scalar(
        """SELECT COUNT(*) FROM po_derived p
           WHERE p.total_qty > (SELECT COALESCE(SUM(qty),0) FROM ri_lines r WHERE r.no_po = p.no_po)"""
    ) or 0
    row["ri_30d"] = scalar("SELECT COUNT(DISTINCT no_ri) FROM ri_lines WHERE tgl_ri >= date('now','-30 day')") or 0
    ss = row["ss_known"] or 0
    row["stock_health"] = round(100 * (row["aman"] or 0) / ss, 1) if ss else None
    return row


# ── inventory table ────────────────────────────────────────────────────────
def inventory_table(status: list[str] | None = None, kategori: list[str] | None = None,
                    gudang: list[str] | None = None, search: str | None = None,
                    only_critical: bool = False) -> pd.DataFrame:
    where, params = ["1=1"], {}
    if status:
        where.append(f"stock_status IN ({','.join('?' * len(status))})")
        params_list = list(status)
    else:
        params_list = []
    if only_critical:
        where.append("is_critical = 1")
    if kategori:
        where.append(f"kategori_induk IN ({','.join('?' * len(kategori))})")
        params_list += list(kategori)
    if gudang:
        where.append(f"letak_gudang IN ({','.join('?' * len(gudang))})")
        params_list += list(gudang)
    if search:
        where.append("(deskripsi LIKE ? OR kode_barang LIKE ?)")
        params_list += [f"%{search}%", f"%{search}%"]
    sql = f"""
        SELECT id, kode_barang, deskripsi, kategori_induk, kategori_anak_1,
               uom, letak_gudang, letak_rak,
               sisa_stok, sisa_stok_known, safety_stock, safety_stock_known,
               selisih, defisit, stock_status, is_critical,
               priority_score, priority_level, rekomendasi,
               incoming_qty, projected_stock, avg_monthly_usage, dq_flags
        FROM v_inventory
        WHERE {' AND '.join(where)}
        ORDER BY is_critical DESC, priority_score DESC, deskripsi
    """
    return read_df(sql, tuple(params_list))


def filter_options() -> dict:
    return {
        "kategori": [r for r in read_df(
            "SELECT DISTINCT kategori_induk k FROM master_items WHERE kategori_induk IS NOT NULL ORDER BY 1")["k"]],
        "gudang": [r for r in read_df(
            "SELECT DISTINCT letak_gudang g FROM master_items WHERE letak_gudang IS NOT NULL ORDER BY 1")["g"]],
        "status": [r for r in read_df(
            "SELECT DISTINCT stock_status s FROM v_inventory WHERE s IS NOT NULL ORDER BY 1")["s"]],
    }


# ── item 360 ───────────────────────────────────────────────────────────────
def item_detail(item_id: str) -> dict:
    master = read_df("SELECT * FROM master_items WHERE id = ?", (item_id,))
    calc = read_df("SELECT * FROM v_inventory WHERE id = ?", (item_id,))
    return {
        "master": master.iloc[0].to_dict() if len(master) else None,
        "calc": calc.iloc[0].to_dict() if len(calc) else None,
        "ppb": read_df(
            "SELECT no_ppb, tgl_ppb, qty, satuan_raw, status, peminta, divisi, keterangan, source_file, source_row "
            "FROM ppb_lines WHERE master_item_id = ? ORDER BY tgl_ppb DESC", (item_id,)),
        "ri": read_df(
            "SELECT no_ri, tgl_ri, qty, satuan_raw, no_ppb, no_po, vendor, no_surat_jalan, source_file, source_row "
            "FROM ri_lines WHERE master_item_id = ? ORDER BY tgl_ri DESC", (item_id,)),
        "npbg": read_df(
            "SELECT no_npbg, tgl_npbg, qty, satuan_raw, klasifikasi, divisi, pelanggan, nama_proyek, keterangan, source_file, source_row "
            "FROM npbg_lines WHERE master_item_id = ? ORDER BY tgl_npbg DESC", (item_id,)),
        "borrow_lend": read_df(
            "SELECT arah, tgl_pinjam, qty, pihak, status, ref_keluar, ref_kembali, tgl_kembali "
            "FROM borrow_lend WHERE master_item_id = ? ORDER BY tgl_pinjam DESC", (item_id,)),
        "stpp": read_df(
            "SELECT no_seri, deskripsi, qty, peminta, penempatan, status, ref_npbg, ref_kembali "
            "FROM stpp WHERE master_item_id = ? ORDER BY tgl_npbg DESC", (item_id,)),
        "manufacturing": read_df(
            "SELECT jenis, no_dok, sub, hasil_produk, proses, status, ref_npbg, ref_ri, tgl "
            "FROM manufacturing WHERE master_item_id = ? ORDER BY tgl DESC", (item_id,)),
        "usage_monthly": read_df(
            """SELECT substr(tgl_npbg,1,7) ym, SUM(qty) qty
               FROM npbg_lines WHERE master_item_id = ? AND tgl_npbg IS NOT NULL
               GROUP BY 1 ORDER BY 1""", (item_id,)),
    }


# ── procurement ────────────────────────────────────────────────────────────
def procurement_priority() -> pd.DataFrame:
    return read_df(
        """
        SELECT kode_barang, deskripsi, letak_gudang, kategori_induk,
               sisa_stok, safety_stock, defisit, lead_time_days,
               incoming_qty, projected_stock, priority_score, priority_level,
               stock_status, rekomendasi, id
        FROM v_inventory
        WHERE stock_status IN ('TIDAK_AMAN','OUT_OF_STOCK')
        ORDER BY priority_score DESC
        """
    )


def ppb_ri_status() -> pd.DataFrame:
    return read_df(
        """
        SELECT p.no_ppb, MIN(p.tgl_ppb) tgl_ppb, MAX(p.status) status,
               COUNT(*) n_item, COALESCE(SUM(p.qty),0) qty_ppb,
               (SELECT COALESCE(SUM(r.qty),0) FROM ri_lines r WHERE r.no_ppb = p.no_ppb) qty_ri,
               (SELECT COUNT(DISTINCT r.no_po) FROM ri_lines r WHERE r.no_ppb = p.no_ppb) n_po,
               (SELECT GROUP_CONCAT(DISTINCT r.vendor) FROM ri_lines r WHERE r.no_ppb = p.no_ppb) vendor
        FROM ppb_lines p
        GROUP BY p.no_ppb
        ORDER BY tgl_ppb DESC
        """
    )


# ── usage analysis (NPBG) ──────────────────────────────────────────────────
def usage_summary() -> dict:
    return {
        "monthly": read_df(
            """SELECT substr(tgl_npbg,1,7) ym, SUM(qty) qty, COUNT(DISTINCT no_npbg) dokumen
               FROM npbg_lines WHERE tgl_npbg IS NOT NULL GROUP BY 1 ORDER BY 1"""),
        "top_items": read_df(
            """SELECT COALESCE(m.deskripsi, n.deskripsi) deskripsi, m.kode_barang,
                      SUM(n.qty) total_qty, COUNT(*) n_baris, n.match_status
               FROM npbg_lines n LEFT JOIN master_items m ON m.id = n.master_item_id
               GROUP BY COALESCE(m.id, n.deskripsi_norm)
               ORDER BY total_qty DESC LIMIT 50"""),
        "by_divisi": read_df(
            "SELECT divisi, SUM(qty) qty, COUNT(DISTINCT no_npbg) dokumen FROM npbg_lines "
            "WHERE divisi IS NOT NULL GROUP BY 1 ORDER BY qty DESC"),
        "by_klasifikasi": read_df(
            "SELECT klasifikasi, SUM(qty) qty FROM npbg_lines WHERE klasifikasi IS NOT NULL GROUP BY 1 ORDER BY qty DESC"),
        "by_pelanggan": read_df(
            "SELECT pelanggan, SUM(qty) qty FROM npbg_lines WHERE pelanggan IS NOT NULL GROUP BY 1 ORDER BY qty DESC LIMIT 30"),
    }


# ── tracking ───────────────────────────────────────────────────────────────
def tracking_counts() -> dict:
    return {
        "borrow_lend_active": scalar("SELECT COUNT(*) FROM borrow_lend WHERE UPPER(COALESCE(status,'')) NOT LIKE '%KEMBALI%' AND UPPER(COALESCE(status,'')) NOT LIKE '%LUNAS%'"),
        "stpp_active": scalar("SELECT COUNT(*) FROM stpp WHERE UPPER(COALESCE(status,'')) = 'ACTIVE'"),
        "maint_open": scalar("SELECT COUNT(*) FROM asset_maintenance WHERE UPPER(COALESCE(status,'')) <> 'COMPLETED'"),
        "mfg_open": scalar("SELECT COUNT(*) FROM manufacturing WHERE UPPER(COALESCE(status,'')) <> 'COMPLETED'"),
        "tire_total": scalar("SELECT COUNT(*) FROM tire_transactions"),
    }


# ── data management ────────────────────────────────────────────────────────
def upload_history() -> pd.DataFrame:
    return read_df(
        "SELECT id, module, filename, uploaded_at, total_rows, inserted, duplicate, need_review, status "
        "FROM upload_batches ORDER BY id DESC")


def matching_queue(limit: int = 200) -> pd.DataFrame:
    return read_df(
        """
        SELECT id, source_table, source_row_id, source_desc, candidate_item_id, candidate_desc,
               confidence, method, decision
        FROM matching_reviews
        WHERE decision = 'PENDING'
        ORDER BY confidence DESC
        LIMIT ?
        """, (limit,))


def data_quality() -> dict:
    return {
        "master_flags": read_df(
            "SELECT dq_flags, COUNT(*) n FROM master_items WHERE dq_flags IS NOT NULL GROUP BY 1"),
        "import_errors": read_df(
            "SELECT rule, severity, COUNT(*) n FROM import_errors GROUP BY 1,2 ORDER BY n DESC"),
        "unmatched": read_df(
            """SELECT 'npbg' src, COUNT(*) n FROM npbg_lines WHERE match_status <> 'MATCHED'
               UNION ALL SELECT 'ppb', COUNT(*) FROM ppb_lines WHERE match_status <> 'MATCHED'
               UNION ALL SELECT 'ri', COUNT(*) FROM ri_lines WHERE match_status <> 'MATCHED'"""),
        "no_ss": scalar("SELECT COUNT(*) FROM v_inventory WHERE safety_stock_known = 0"),
        "no_stock": scalar("SELECT COUNT(*) FROM v_inventory WHERE sisa_stok_known = 0"),
    }
