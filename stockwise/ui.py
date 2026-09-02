"""Shared Streamlit UI helpers for the STOCKWISE pages."""
from __future__ import annotations

import streamlit as st

from stockwise.config import STATUS_COLORS, STATUS_LABELS
from stockwise.db import db_exists

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
html, body, [class*="css"] { font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif; }
.block-container { padding-top: 2rem; max-width: 1400px; }
.sw-title { font-size: 1.6rem; font-weight: 800; color: #14328c; letter-spacing: -0.02em; margin: 0; }
.sw-sub { color: #5b6b8c; font-size: 0.92rem; margin: 2px 0 1.2rem; }
.sw-kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; margin-bottom: 8px; }
.sw-kpi { border: 1px solid rgba(20,60,160,.18); border-top: 3px solid rgba(20,60,160,.30);
          border-radius: 12px; padding: 12px 14px; background: rgba(20,60,160,.04); }
.sw-kpi .l { font-size: .72rem; font-weight: 600; text-transform: uppercase; letter-spacing: .03em; opacity: .7; }
.sw-kpi .v { font-size: 1.5rem; font-weight: 800; line-height: 1.25; }
.sw-kpi .s { font-size: .72rem; opacity: .6; }
.sw-badge { display: inline-block; padding: 2px 9px; border-radius: 999px; font-size: .74rem; font-weight: 700; }
.sw-lineage { font-size: .75rem; color: #5b6b8c; border-left: 3px solid rgba(20,60,160,.3); padding: 4px 10px; margin-top: 6px; }
</style>
"""


def page_header(title: str, subtitle: str = "", icon: str = "📊"):
    st.set_page_config(page_title=f"STOCKWISE — {title}", page_icon="📦", layout="wide")
    st.markdown(_CSS, unsafe_allow_html=True)
    st.markdown(f'<p class="sw-title">{icon} {title}</p>', unsafe_allow_html=True)
    if subtitle:
        st.markdown(f'<p class="sw-sub">{subtitle}</p>', unsafe_allow_html=True)


def require_db() -> bool:
    """Show a friendly gate if stockwise.db isn't built yet. Returns True if OK."""
    if db_exists():
        return True
    st.warning(
        "**stockwise.db belum ada.** Buka halaman **Data Management** untuk upload Excel, "
        "atau jalankan `node --experimental-sqlite tools/build_stockwise_db.mjs` untuk mengisi "
        "dari folder `DATAFIX/`."
    )
    return False


def kpi_grid(cards: list[tuple]):
    """cards: (label, value, sub, accent_hex)"""
    html = ['<div class="sw-kpi-grid">']
    for label, value, sub, accent in cards:
        html.append(
            f'<div class="sw-kpi" style="border-top-color:{accent}">'
            f'<div class="l">{label}</div>'
            f'<div class="v" style="color:{accent}">{value}</div>'
            f'<div class="s">{sub}</div></div>'
        )
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)


def status_badge(status: str) -> str:
    color = STATUS_COLORS.get(status, "#8a8a8a")
    label = STATUS_LABELS.get(status, status)
    return f'<span class="sw-badge" style="background:{color}22;color:{color}">{label}</span>'


def lineage(source_file, source_sheet=None, source_row=None, extra: str = ""):
    bits = [f"📄 {source_file}"]
    if source_sheet:
        bits.append(f"sheet `{source_sheet}`")
    if source_row:
        bits.append(f"baris {int(source_row)}")
    if extra:
        bits.append(extra)
    st.markdown(f'<div class="sw-lineage">Sumber: {" · ".join(str(b) for b in bits)}</div>', unsafe_allow_html=True)


def fmt_num(v, dash="—"):
    if v is None:
        return dash
    try:
        f = float(v)
        return f"{f:,.0f}" if f == int(f) else f"{f:,.2f}"
    except (TypeError, ValueError):
        return str(v)


def goto_item(item_id: str):
    st.session_state["detail_item_id"] = item_id
    st.switch_page("pages/6_🔍_Item_Detail.py")
