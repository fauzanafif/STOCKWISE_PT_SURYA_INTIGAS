"""Bridge: push the master inventory that app.py loaded/edited into stockwise.db,
so the Procurement / Usage / Tracking / Matching pages all read the same data.

app.py stays the master editor (upload + grid edit). This runs after its
recalculate() so the DB always reflects what the user sees.

Design:
- master_items / inventory_snapshots are REPLACED from the app.py dataframe
  (app.py is authoritative for the catalogue + current stock).
- Existing master_items IDs are reused where kode_barang / normalized description
  matches, so transaction links (npbg_lines.master_item_id etc.) survive.
- safety_stock_params: only rows where the user actually entered SS / LT / MIN PR
  are written (source_sheet = "input manual (app.py)"). Sheet-derived values for
  everything else are left untouched.
"""
from __future__ import annotations

import pandas as pd

from utils.database import connect, init_db
from utils.textnorm import desc_core, desc_norm, parse_bool, parse_stock_num

_NUMCOL = {"Sisa Stok", "Safety Stock", "Lead Time", "MIN PR", "√LT"}


def _num(v):
    try:
        f = float(v)
        return f if f == f else None  # NaN check
    except (TypeError, ValueError):
        return None


def sync_master(df: pd.DataFrame, source_file: str = "app.py upload", snapshot_date: str | None = None) -> dict:
    """Returns {items, snapshots, ss_manual}."""
    if df is None or df.empty:
        return {"items": 0, "snapshots": 0, "ss_manual": 0}

    init_db()
    conn = connect()
    try:
        # reuse existing IDs so transaction FKs stay valid
        existing = conn.execute(
            "SELECT id, kode_barang, deskripsi_norm FROM master_items").fetchall()
        by_kode = {r["kode_barang"].upper(): r["id"] for r in existing if r["kode_barang"]}
        by_norm = {r["deskripsi_norm"]: r["id"] for r in existing if r["deskripsi_norm"]}
        used_ids: set[str] = set()
        max_seq = 0
        for r in existing:
            if r["id"] and r["id"].startswith("ITEM-"):
                try:
                    max_seq = max(max_seq, int(r["id"][5:]))
                except ValueError:
                    pass

        g = lambda row, col: row[col] if col in df.columns else None

        conn.execute("BEGIN")
        # snapshots + params reference master_items(id) — clear children first
        conn.execute("DELETE FROM inventory_snapshots")
        conn.execute("DELETE FROM safety_stock_params WHERE source_sheet = 'input manual (app.py)'")

        rows = []
        snaps: dict[str, tuple] = {}   # iid -> snapshot tuple (one per item)
        ss_rows: dict[str, tuple] = {}  # desc_norm -> ssp tuple
        for _, row in df.iterrows():
            kode = (str(g(row, "Kode Barang")).strip() or None) if g(row, "Kode Barang") is not None else None
            if kode in ("", "nan", "None"):
                kode = None
            deskripsi = str(g(row, "Deskripsi Barang") or "").strip() or "(tanpa deskripsi)"
            dn = desc_norm(deskripsi)

            iid = None
            if kode and kode.upper() in by_kode:
                iid = by_kode[kode.upper()]
            elif dn in by_norm:
                iid = by_norm[dn]
            if iid is None or iid in used_ids:
                max_seq += 1
                iid = f"ITEM-{max_seq:06d}"
            used_ids.add(iid)

            rows.append((
                iid, kode,
                _s(g(row, "Kategori Induk")), _s(g(row, "Kategori Anak 1")),
                _s(g(row, "Kategori Anak 2")), _s(g(row, "Kategori Anak 3")),
                deskripsi, dn, desc_core(deskripsi) or dn,
                _s(g(row, "UoM")), parse_bool(g(row, "Perlu Blueprint?")),
                _s(g(row, "Letak Gudang")), _s(g(row, "Letak Rak")),
                _s(g(row, "Blueprint IMG")), _s(g(row, "Blueprint Detail PDF")), _s(g(row, "Blueprint 3D View")),
                source_file,
            ))

            raw_stock = g(row, "Sisa Stok")
            num = _num(raw_stock)
            if num is None:
                num = parse_stock_num(raw_stock)
            snaps[iid] = (iid, snapshot_date, None if raw_stock is None else str(raw_stock),
                          num, 1 if num is not None else 0, source_file)

            # Only treat it as a manual safety-stock entry when SS or MIN PR is set.
            # A lead-time-only value from DATABASE UTAMA must NOT overwrite the
            # richer per-item params from the SAFETY STOCK sheets.
            ss = _num(g(row, "Safety Stock"))
            lt = _num(g(row, "Lead Time"))
            mp = _num(g(row, "MIN PR"))
            if ((ss and ss > 0) or (mp and mp > 0)) and dn not in ss_rows:
                ss_rows[dn] = (deskripsi, dn, iid, lt, _num(g(row, "√LT")), ss, mp)

        # upsert master_items — never delete (transactions may still reference an
        # item that this particular master file no longer lists)
        conn.executemany(
            """INSERT INTO master_items
               (id, kode_barang, kategori_induk, kategori_anak_1, kategori_anak_2, kategori_anak_3,
                deskripsi, deskripsi_norm, deskripsi_core, uom, perlu_blueprint,
                letak_gudang, letak_rak, blueprint_img_ref, blueprint_pdf_ref, blueprint_3d_ref, source_file)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                 kode_barang=excluded.kode_barang, kategori_induk=excluded.kategori_induk,
                 kategori_anak_1=excluded.kategori_anak_1, kategori_anak_2=excluded.kategori_anak_2,
                 kategori_anak_3=excluded.kategori_anak_3, deskripsi=excluded.deskripsi,
                 deskripsi_norm=excluded.deskripsi_norm, deskripsi_core=excluded.deskripsi_core,
                 uom=excluded.uom, perlu_blueprint=excluded.perlu_blueprint,
                 letak_gudang=excluded.letak_gudang, letak_rak=excluded.letak_rak,
                 blueprint_img_ref=excluded.blueprint_img_ref, blueprint_pdf_ref=excluded.blueprint_pdf_ref,
                 blueprint_3d_ref=excluded.blueprint_3d_ref, source_file=excluded.source_file""",
            rows)
        conn.executemany(
            """INSERT INTO inventory_snapshots
               (master_item_id, snapshot_date, sisa_stok_raw, sisa_stok_num, sisa_stok_known, source_file)
               VALUES (?,?,?,?,?,?)""", list(snaps.values()))
        conn.executemany(
            """INSERT INTO safety_stock_params
               (item_description, item_desc_norm, master_item_id, lead_time_days, sqrt_lt, safety_stock, min_pr, source_sheet)
               VALUES (?,?,?,?,?,?,?, 'input manual (app.py)')
               ON CONFLICT(item_desc_norm) DO UPDATE SET
                 master_item_id=excluded.master_item_id, lead_time_days=excluded.lead_time_days,
                 sqrt_lt=excluded.sqrt_lt, safety_stock=excluded.safety_stock, min_pr=excluded.min_pr,
                 source_sheet='input manual (app.py)', dq_flag=NULL""", list(ss_rows.values()))
        conn.commit()
    finally:
        conn.close()

    from utils.calc_engine import run_calc
    run_calc(notes="app.py master sync")
    return {"items": len(rows), "snapshots": len(snaps), "ss_manual": len(ss_rows)}


def _s(v):
    if v is None:
        return None
    s = str(v).strip()
    return None if s in ("", "nan", "None") else s
