"""STOCKWISE — Inventory Intelligence System. Entry point / navigation router.

    streamlit run Home.py

(The old single-Excel dashboard app.py is kept for reference; this is the app.)
"""
import streamlit as st

from stockwise.ui import boot, setup_status

boot()

_s = setup_status()
_incomplete = not _s["ready"]

get_started = st.Page("pages/get_started.py", title="Mulai", icon="🚀", default=_incomplete)
dashboard = st.Page("pages/executive.py", title="Dashboard", icon="📊", default=not _incomplete)
inventory = st.Page("pages/inventory.py", title="Inventory", icon="📋")
procurement = st.Page("pages/procurement.py", title="Procurement", icon="🚚")
usage = st.Page("pages/usage.py", title="Pemakaian", icon="📉")
tracking = st.Page("pages/tracking.py", title="Tracking", icon="📍")
ask = st.Page("pages/ask.py", title="Tanya STOCKWISE", icon="💬")
kelola = st.Page("pages/data_management.py", title="Kelola Data", icon="🗄️")
matching = st.Page("pages/matching_review.py", title="Cocokkan Barang", icon="🤝")
ss_review = st.Page("pages/safety_stock_review.py", title="Safety Stock", icon="🛡️")
master_data = st.Page("pages/master_data.py", title="Master Barang", icon="🗂️")
item_detail = st.Page("pages/item_detail.py", title="Detail Barang", icon="🔍")

groups = {
    "Pantau": [dashboard, inventory, procurement, usage, tracking],
    "Tanya": [ask],
    "Beresi Data": [kelola, matching, ss_review],
    "Referensi": [master_data, item_detail],
}
if _incomplete:
    groups = {"Setup": [get_started], **groups}

st.navigation(groups).run()
