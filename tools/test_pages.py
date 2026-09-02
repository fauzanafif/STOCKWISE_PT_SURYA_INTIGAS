"""Headless render test for app.py + every page in pages/ via streamlit.testing.AppTest.
Catches exceptions raised during a page's top-to-bottom run without a browser.

    python tools/test_pages.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402
from streamlit.delta_generator import DeltaGenerator  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

# AppTest.from_file runs a page in isolation without the folder-based `pages/`
# registry, so st.page_link / st.switch_page to a sibling raise even though they
# work in a real `streamlit run`. Stub them (on st and DeltaGenerator).
_noop = lambda *a, **k: None  # noqa: E731
st.page_link = _noop
st.switch_page = _noop
DeltaGenerator.page_link = _noop
DeltaGenerator.switch_page = _noop

PAGES = ["app.py"] + sorted(str(p.relative_to(ROOT)) for p in (ROOT / "pages").glob("*.py"))

failed = 0
for page in PAGES:
    try:
        at = AppTest.from_file(str(ROOT / page), default_timeout=90)
        at.run()
        excs = list(at.exception)
        if excs:
            failed += 1
            print(f"FAIL  {page}")
            for e in excs:
                print(f"      {e.value}")
        else:
            print(f"ok    {page}  ({len(at.markdown)} md, {len(at.dataframe)} tables)")
    except Exception as e:  # noqa: BLE001
        failed += 1
        print(f"ERROR {page}: {type(e).__name__}: {e}")

print()
print("ALL PAGES OK" if not failed else f"{failed} PAGE(S) FAILED")
sys.exit(1 if failed else 0)
