"""STOCKWISE v2 — Inventory Intelligence System. Entry point / navigation router.

    streamlit run Home.py

The legacy single-Excel dashboard is still at app.py (`streamlit run app.py`), untouched.
"""
import streamlit as st

from stockwise.ui import boot

boot()

executive = st.Page("pages/executive.py", title="Executive", icon="📦", default=True)
inventory = st.Page("pages/inventory.py", title="Inventory", icon="📋")
procurement = st.Page("pages/procurement.py", title="Procurement", icon="🚚")
usage = st.Page("pages/usage.py", title="Usage Analysis", icon="📉")
tracking = st.Page("pages/tracking.py", title="Tracking", icon="📍")
master_data = st.Page("pages/master_data.py", title="Master Data", icon="🗂️")
item_detail = st.Page("pages/item_detail.py", title="Item Detail", icon="🔍")
data_management = st.Page("pages/data_management.py", title="Data Management", icon="🗄️")
matching_review = st.Page("pages/matching_review.py", title="Matching Review", icon="🤝")
ask = st.Page("pages/ask.py", title="Ask STOCKWISE", icon="💬")

nav = st.navigation({
    "Ringkasan": [executive, ask],
    "Operasional": [inventory, procurement, usage, tracking],
    "Data & Referensi": [master_data, item_detail, matching_review, data_management],
})
nav.run()
