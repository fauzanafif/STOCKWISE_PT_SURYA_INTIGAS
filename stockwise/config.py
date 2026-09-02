"""Central configuration. No secrets here — paths and business parameters only."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# stockwise.db lives at the project root; override with STOCKWISE_DB env var.
DB_PATH = Path(os.environ.get("STOCKWISE_DB", ROOT / "stockwise.db"))
SCHEMA_PATH = ROOT / "db" / "schema.sql"
DATAFIX_DIR = Path(os.environ.get("STOCKWISE_DATAFIX", ROOT / "DATAFIX"))

# ── Business parameters (see AUDIT/00_decisions.md) ──────────────────────────
# [A-5] PENDING business confirmation — NOT auto-derived.
LEAD_TIME_HIGH_THRESHOLD_DAYS = int(os.environ.get("STOCKWISE_LT_THRESHOLD", 14))

# Priority Score weights (spec §11 / legacy utils/calculations.py).
DEFICIT_WEIGHT = 2.0
LEAD_TIME_WEIGHT = 1.0

# Matching thresholds (fuzzy never auto-resolves — RULE 8).
FUZZY_STRONG = 0.90   # -> POSSIBLE_MATCH
FUZZY_WEAK = 0.75     # -> NEED_REVIEW (below -> NEW_ITEM)

# Which workbook / sheets feed which module. Used by the upload UI and ingest.
MODULES = {
    "master":        {"label": "Master Inventory",        "file_hint": "DATA.xlsx",
                      "sheets": ["DATABASE UTAMA", "SAFETY STOCK *"]},
    "procurement":   {"label": "Procurement (PPB/PO/RI)", "file_hint": "1. PPB - RI.xlsx",
                      "sheets": ["PPB", "RI", "PPB Perubahan"]},
    "npbg":          {"label": "Pemakaian Barang (NPBG)", "file_hint": "2. NPBG.xlsx",
                      "sheets": ["NPBG"]},
    "borrow_lend":   {"label": "Borrow & Lend",           "file_hint": "3. Tracking Borrow & Lend.xlsx",
                      "sheets": ["Lend", "Borrow"]},
    "stpp":          {"label": "STPP",                    "file_hint": "4. Tracking STPP.xlsx",
                      "sheets": ["STPP", "Maintenance"]},
    "tire":          {"label": "Ban Luar",                "file_hint": "5. Tracking Ban Luar.xlsx",
                      "sheets": ["Ban Luar", "Ban Luar BPN", "Deliver & Receive Ban SIG-BPN"]},
    "asset_maint":   {"label": "Maintenance Kendaraan",   "file_hint": "6. Tracking Maintenance Assets.xlsx",
                      "sheets": ["Maintenance Kendaraan"]},
    "manufacturing": {"label": "Manufaktur & Assembly",   "file_hint": "7. Tracking Manufaktur & Assembly.xlsx",
                      "sheets": ["Manufaktur & Assembly", "Manufaktur & Jasa Lain-Lain"]},
    "used_returns":  {"label": "Pengembalian Bekas",      "file_hint": "8. Tracking Pengembalian Bekas.xlsx",
                      "sheets": ["Spare Part", "Spare Part Lain"]},
}

STATUS_LABELS = {
    "AMAN": "Aman",
    "TIDAK_AMAN": "Tidak Aman",
    "OUT_OF_STOCK": "Stok Habis",
    "BEP": "BEP (stok & SS = 0)",
    "NO_SAFETY_STOCK": "Belum ada Safety Stock",
    "UNKNOWN": "Stok belum terdata",
}

STATUS_COLORS = {
    "AMAN": "#0ca30c",
    "TIDAK_AMAN": "#d03b3b",
    "OUT_OF_STOCK": "#8a1c1c",
    "BEP": "#8a63d2",
    "NO_SAFETY_STOCK": "#c98500",
    "UNKNOWN": "#8a8a8a",
}
