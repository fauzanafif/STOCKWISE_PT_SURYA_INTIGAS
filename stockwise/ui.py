"""Shared Streamlit UI: app chrome (boot), page headers, KPI cards, badges, lineage."""
from __future__ import annotations

import base64
from pathlib import Path

import streamlit as st

from stockwise.config import ROOT, STATUS_COLORS, STATUS_LABELS
from stockwise.db import db_exists

_LOGO = ROOT / "assets" / "logo.png"

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
:root {
  --sw-ink:#14213a; --sw-blue:#1f5fbf; --sw-blue-d:#12306f;
  --sw-line:rgba(18,48,111,.16); --sw-tint:rgba(31,95,191,.05); --sw-muted:#5c6b86;
}
html, body, [class*="css"] { font-family:'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif; }
.block-container { padding-top:1.9rem; padding-bottom:3rem; max-width:1440px; }
[data-testid="stSidebar"] { border-right:1px solid var(--sw-line); }

.sw-brand { display:flex; align-items:center; gap:10px; padding:2px 0 14px; margin-bottom:10px;
            border-bottom:1px solid var(--sw-line); }
.sw-brand img { width:34px; height:34px; object-fit:contain; }
.sw-brand b { font-size:.95rem; letter-spacing:.06em; color:var(--sw-blue-d); text-transform:uppercase; line-height:1.15; }
.sw-brand span { display:block; font-size:.68rem; font-weight:500; color:var(--sw-muted); letter-spacing:.02em; text-transform:none; }

.sw-h { font-size:1.55rem; font-weight:800; color:var(--sw-blue-d); letter-spacing:-.02em; margin:0; }
.sw-hs { color:var(--sw-muted); font-size:.92rem; margin:3px 0 1.3rem; }
.sw-sec { font-size:1.02rem; font-weight:700; color:var(--sw-blue-d); margin:.2rem 0 .1rem;
          padding-left:9px; border-left:3px solid var(--sw-blue); }

.sw-kpis { display:grid; grid-template-columns:repeat(auto-fit,minmax(158px,1fr)); gap:11px; margin:6px 0 4px; }
.sw-kpi { border:1px solid var(--sw-line); border-top:3px solid var(--sw-line); border-radius:11px;
          padding:11px 13px 12px; background:var(--sw-tint); }
.sw-kpi .l { font-size:.68rem; font-weight:700; letter-spacing:.04em; text-transform:uppercase; color:var(--sw-muted); }
.sw-kpi .v { font-size:1.42rem; font-weight:800; line-height:1.3; font-variant-numeric:tabular-nums; }
.sw-kpi .s { font-size:.7rem; color:var(--sw-muted); }

.sw-badge { display:inline-block; padding:2px 9px; border-radius:999px; font-size:.72rem; font-weight:700; white-space:nowrap; }
.sw-lin { font-size:.74rem; color:var(--sw-muted); border-left:3px solid var(--sw-line); padding:3px 10px; margin-top:6px; }
div[data-testid="stMetric"] { background:var(--sw-tint); border:1px solid var(--sw-line); border-radius:10px; padding:10px 14px; }
</style>
"""


@st.cache_data
def _logo_uri() -> str:
    try:
        return "data:image/png;base64," + base64.b64encode(_LOGO.read_bytes()).decode("ascii")
    except OSError:
        return ""


def boot():
    """Call once from the entry point (Home.py) — page config + CSS + sidebar brand."""
    st.set_page_config(page_title="STOCKWISE", page_icon="📦", layout="wide")
    st.markdown(_CSS, unsafe_allow_html=True)
    uri = _logo_uri()
    img = f'<img src="{uri}">' if uri else ""
    st.sidebar.markdown(
        f'<div class="sw-brand">{img}<div><b>STOCKWISE</b>'
        f'<span>Inventory Intelligence · PT Surya Inti Gas</span></div></div>',
        unsafe_allow_html=True,
    )


def page_header(title: str, subtitle: str = "", icon: str = ""):
    st.markdown(f'<p class="sw-h">{(icon + " ") if icon else ""}{title}</p>', unsafe_allow_html=True)
    if subtitle:
        st.markdown(f'<p class="sw-hs">{subtitle}</p>', unsafe_allow_html=True)


def section(title: str):
    st.markdown(f'<div class="sw-sec">{title}</div>', unsafe_allow_html=True)


def require_db() -> bool:
    if db_exists():
        return True
    st.warning(
        "**stockwise.db belum ada.** Buka **Data Management → Upload Center** untuk upload Excel, "
        "atau jalankan `node --experimental-sqlite tools/build_stockwise_db.mjs` untuk mengisi dari `DATAFIX/`."
    )
    return False


def kpi_grid(cards: list[tuple]):
    """cards: (label, value, sub, accent_hex)"""
    html = ['<div class="sw-kpis">']
    for label, value, sub, accent in cards:
        html.append(
            f'<div class="sw-kpi" style="border-top-color:{accent}">'
            f'<div class="l">{label}</div><div class="v" style="color:{accent}">{value}</div>'
            f'<div class="s">{sub}</div></div>'
        )
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)


def status_badge(status: str) -> str:
    color = STATUS_COLORS.get(status, "#8a8a8a")
    return f'<span class="sw-badge" style="background:{color}22;color:{color}">{STATUS_LABELS.get(status, status)}</span>'


def lineage(source_file, source_sheet=None, source_row=None, extra: str = ""):
    bits = [f"📄 {source_file}"]
    if source_sheet:
        bits.append(f"sheet `{source_sheet}`")
    if source_row:
        bits.append(f"baris {int(source_row)}")
    if extra:
        bits.append(extra)
    st.markdown(f'<div class="sw-lin">Sumber: {" · ".join(str(b) for b in bits)}</div>', unsafe_allow_html=True)


def fmt_num(v, dash="—"):
    if v is None:
        return dash
    try:
        f = float(v)
        return f"{f:,.0f}" if f == int(f) else f"{f:,.2f}"
    except (TypeError, ValueError):
        return str(v)


def open_item(item_id: str):
    st.session_state["detail_item_id"] = item_id
    st.switch_page("pages/item_detail.py")
