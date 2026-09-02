"""Smoke test for the stockwise package + queries against the real stockwise.db.
Not a Streamlit test — it just exercises every query function and the calc engine
so import errors / SQL bugs surface without opening a browser.

    python tools/smoke_test.py
"""
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

FAILS = []


def check(name, fn):
    try:
        out = fn()
        n = len(out) if hasattr(out, "__len__") else out
        print(f"  ok  {name}  -> {n}")
    except Exception as e:  # noqa: BLE001
        FAILS.append((name, e))
        print(f"  FAIL {name}: {e}")
        traceback.print_exc()


def main():
    from stockwise import calc, config, db, queries, textnorm, ui  # noqa: F401

    print("imports ok")
    assert db.db_exists(), "stockwise.db not found — run tools/build_stockwise_db.mjs first"

    print("textnorm:")
    assert textnorm.parse_stock_num("STOK 15 PCS") == 15
    assert textnorm.parse_stock_num("STOK O PCS") == 0
    assert textnorm.parse_num("1,5") == 1.5
    assert textnorm.desc_core("(BEKAS) REGULATOR O2") == textnorm.desc_core("REGULATOR O2")
    assert textnorm.parse_date_iso("2026-08-22") == "2026-08-22"
    print("  ok")

    print("queries:")
    check("data_fingerprint", queries.data_fingerprint)
    check("latest_calc_run", queries.latest_calc_run)
    check("executive_kpis", queries.executive_kpis)
    check("filter_options", queries.filter_options)
    check("inventory_table (all)", lambda: queries.inventory_table())
    check("inventory_table (filtered)", lambda: queries.inventory_table(status=["TIDAK_AMAN", "OUT_OF_STOCK"], only_critical=True))
    check("inventory_table (search)", lambda: queries.inventory_table(search="regulator"))
    check("procurement_priority", queries.procurement_priority)
    check("ppb_ri_status", queries.ppb_ri_status)
    check("usage_summary", queries.usage_summary)
    check("tracking_counts", queries.tracking_counts)
    check("upload_history", queries.upload_history)
    check("matching_queue", queries.matching_queue)
    check("data_quality", queries.data_quality)

    row = db.fetch_one("SELECT id FROM master_items WHERE kode_barang IS NOT NULL LIMIT 1")
    check("item_detail", lambda: queries.item_detail(row["id"]))

    print("calc engine (re-run):")
    check("calc.run_calc", lambda: calc.run_calc(notes="smoke_test"))

    print()
    if FAILS:
        print(f"{len(FAILS)} FAILURE(S):")
        for n, e in FAILS:
            print(f"  - {n}: {e!r}")
        sys.exit(1)
    print("ALL GREEN - OK")


if __name__ == "__main__":
    main()
