"""Calculation engine — the ONLY place inventory status/priority is computed
(spec §26). Mirror of tools/lib/calc.mjs. Every page reads calc_results, never
recomputes. See AUDIT/00_decisions.md [A-3][A-4][A-5].
"""
from __future__ import annotations

import statistics

from utils.sw_config import DEFICIT_WEIGHT, LEAD_TIME_HIGH_THRESHOLD_DAYS, LEAD_TIME_WEIGHT
from utils.database import connect

_FINAL_PPB = {"completed", "close", "error"}


def run_calc(threshold: float | None = None, notes: str = "app") -> dict:
    threshold = LEAD_TIME_HIGH_THRESHOLD_DAYS if threshold is None else threshold
    conn = connect()
    try:
        run_id = conn.execute(
            "INSERT INTO calc_runs (lead_time_threshold, notes) VALUES (?, ?)", (threshold, notes)
        ).lastrowid

        # resolve safety-stock / consumption onto master items by exact normalized desc
        conn.executescript(
            """
            UPDATE safety_stock_params
               SET master_item_id = (SELECT m.id FROM master_items m
                                     WHERE m.deskripsi_norm = safety_stock_params.item_desc_norm LIMIT 1)
             WHERE master_item_id IS NULL;
            UPDATE monthly_consumption
               SET master_item_id = (SELECT m.id FROM master_items m
                                     WHERE m.deskripsi_norm = monthly_consumption.item_desc_norm LIMIT 1)
             WHERE master_item_id IS NULL;
            """
        )

        # one row per master item — pick the latest snapshot and the preferred
        # safety-stock params (manual input wins over sheet-derived).
        items = conn.execute(
            """
            SELECT m.id,
              (SELECT s.sisa_stok_num  FROM inventory_snapshots s WHERE s.master_item_id = m.id
                 ORDER BY s.snapshot_date DESC, s.id DESC LIMIT 1) AS sisa,
              (SELECT s.sisa_stok_known FROM inventory_snapshots s WHERE s.master_item_id = m.id
                 ORDER BY s.snapshot_date DESC, s.id DESC LIMIT 1) AS sisa_known,
              (SELECT ssp.safety_stock  FROM safety_stock_params ssp WHERE ssp.master_item_id = m.id
                 ORDER BY (ssp.source_sheet = 'input manual (app.py)') DESC, ssp.id LIMIT 1) AS ss,
              (SELECT ssp.lead_time_days FROM safety_stock_params ssp WHERE ssp.master_item_id = m.id
                 ORDER BY (ssp.source_sheet = 'input manual (app.py)') DESC, ssp.id LIMIT 1) AS lt,
              (SELECT ssp.avg_12_bln     FROM safety_stock_params ssp WHERE ssp.master_item_id = m.id
                 ORDER BY (ssp.source_sheet = 'input manual (app.py)') DESC, ssp.id LIMIT 1) AS avg12
            FROM master_items m
            """
        ).fetchall()

        incoming = {
            r["id"]: max((r["ppb_open"] or 0) - (r["ri_recv"] or 0), 0)
            for r in conn.execute(
                """
                SELECT p.master_item_id AS id,
                       SUM(CASE WHEN LOWER(COALESCE(p.status,'')) NOT IN ('completed','close','error')
                                THEN COALESCE(p.qty,0) ELSE 0 END) AS ppb_open,
                       (SELECT COALESCE(SUM(r.qty),0) FROM ri_lines r
                         WHERE r.master_item_id = p.master_item_id AND r.no_ppb IS NOT NULL) AS ri_recv
                FROM ppb_lines p WHERE p.master_item_id IS NOT NULL
                GROUP BY p.master_item_id
                """
            ).fetchall()
        }
        npbg_use = {
            r["id"]: (r["total"] / r["months"] if r["months"] else None)
            for r in conn.execute(
                """
                SELECT master_item_id AS id, SUM(COALESCE(qty,0)) AS total,
                       COUNT(DISTINCT substr(tgl_npbg,1,7)) AS months
                FROM npbg_lines WHERE master_item_id IS NOT NULL AND tgl_npbg IS NOT NULL
                GROUP BY master_item_id
                """
            ).fetchall()
        }

        computed = []
        unsafe_def = []
        for it in items:
            sisa_known = it["sisa_known"] == 1 and it["sisa"] is not None
            ss_known = it["ss"] is not None
            sisa = it["sisa"] if sisa_known else None
            ss = it["ss"] if ss_known else None
            selisih = defisit = None

            if not sisa_known:
                status = "UNKNOWN"
            elif sisa == 0 and (not ss_known or ss == 0):
                status = "BEP"
            elif not ss_known:
                status = "NO_SAFETY_STOCK"
            else:
                selisih = sisa - ss
                defisit = max(ss - sisa, 0)
                if sisa == 0 and ss > 0:
                    status = "OUT_OF_STOCK"
                elif sisa < ss:
                    status = "TIDAK_AMAN"
                else:
                    status = "AMAN"

            unsafe = status in ("TIDAK_AMAN", "OUT_OF_STOCK")
            if unsafe and defisit is not None:
                unsafe_def.append(defisit)

            inc = incoming.get(it["id"])
            projected = (sisa + (inc or 0)) if sisa_known else None
            avg_use = it["avg12"] if it["avg12"] is not None else npbg_use.get(it["id"])
            computed.append((it, sisa, sisa_known, ss, ss_known, selisih, defisit, status, unsafe, inc, projected, avg_use))

        median = statistics.median(unsafe_def) if unsafe_def else None
        p75 = _pctl(unsafe_def, 0.75)

        rows = []
        for (it, sisa, sisa_known, ss, ss_known, selisih, defisit, status, unsafe, inc, projected, avg_use) in computed:
            lt = it["lt"]
            score, level = 0.0, "LOW"
            if unsafe:
                score = (defisit or 0) * DEFICIT_WEIGHT + (lt or 0) * LEAD_TIME_WEIGHT
                high = (defisit is not None and median is not None and defisit >= median) or (lt is not None and lt >= threshold)
                level = "HIGH" if high else "MEDIUM"
            critical = 1 if (unsafe and ((defisit is not None and p75 is not None and defisit >= p75) or level == "HIGH")) else 0
            rows.append((
                it["id"], run_id, sisa, 1 if sisa_known else 0, ss, 1 if ss_known else 0,
                lt, selisih, defisit, status, critical, round(score, 2), level,
                _recommend(status, lt, threshold), inc, projected,
                round(avg_use, 2) if avg_use is not None else None,
            ))

        conn.executemany(
            """
            INSERT INTO calc_results
              (master_item_id, calc_run_id, sisa_stok, sisa_stok_known, safety_stock, safety_stock_known,
               lead_time_days, selisih, defisit, stock_status, is_critical, priority_score, priority_level,
               rekomendasi, incoming_qty, projected_stock, avg_monthly_usage)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            rows,
        )
        conn.commit()
        return {"run_id": run_id, "items": len(rows), "median": median, "p75": p75, "threshold": threshold}
    finally:
        conn.close()


def _recommend(status, lt, threshold) -> str:
    return {
        "UNKNOWN": "Sisa stok belum terdata — input dulu di Master Inventory.",
        "NO_SAFETY_STOCK": "Safety stock belum tersedia untuk barang ini — belum bisa dinilai aman/tidak.",
        "BEP": "Sisa & Safety Stock sama-sama 0 — cek apakah barang non-aktif atau data belum diisi.",
        "OUT_OF_STOCK": "STOK HABIS. Segera adakan pembelian — cek status PPB/PO.",
        "AMAN": "Stok aman, tidak perlu replenishment segera.",
    }.get(status) or (
        "Prioritas tinggi untuk procurement (lead time panjang)."
        if (lt is not None and lt >= threshold)
        else "Segera lakukan replenishment."
    )


def _pctl(arr, p):
    if not arr:
        return None
    s = sorted(arr)
    idx = (len(s) - 1) * p
    lo, hi = int(idx), min(int(idx) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (idx - lo)
