"""STOCKWISE — Inventory Intelligence System (data layer + calc engine).

The single-file legacy dashboard (`app.py`) is untouched and still works on its
own. This package is the new multi-source system: Excel -> ingest -> stockwise.db
(single source of truth) -> calc engine -> Streamlit pages under `pages/`.
"""
__all__ = ["config", "db", "textnorm", "calc", "queries"]
