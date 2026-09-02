"""Text / value normalization. Mirror of tools/lib/textnorm.mjs — keep in sync.

Any change here must be mirrored in the .mjs file (and vice versa) or the Node
bootstrap tool and the live Python ingest will disagree on matching keys.
"""
from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, timedelta

CONDITION_TAGS = [
    "BEKAS", "REFURBISHED", "REFURBHISED", "REFUBISHED", "REFURBISH",
    "BUANG", "VULKANISIR", "RECONDITION", "REKONDISI", "BARU",
]
SENTINELS = {"", "-", "--", "N/A", "NA", "NULL", "NONE", ".", "ORIGIN"}

_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def is_blank(v) -> bool:
    if v is None:
        return True
    return str(v).strip().upper() in SENTINELS


def clean_key(v):
    return None if is_blank(v) else str(v).strip()


def clean_text(v):
    if v is None:
        return None
    s = re.sub(r"\s+", " ", str(v)).strip()
    return s or None


def desc_norm(v) -> str:
    if v is None:
        return ""
    s = str(v).upper()
    s = re.sub(r"[“”″]", '"', s)
    s = re.sub(r"[‘’′´`]", "'", s)
    s = s.replace(" ", " ")
    s = re.sub(r"REFURBHISED|REFUBISHED", "REFURBISHED", s)
    s = re.sub(r"\s*[×xX]\s*(?=\d)", " X ", s)
    s = re.sub(r"\s*/\s*", " / ", s)
    s = re.sub(r"\s*-\s*", " - ", s)
    s = re.sub(r"[^\w\s\"'./%()-]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"[.\-/\s]+$", "", s).strip()
    return s


def desc_core(v) -> str:
    s = desc_norm(v)
    changed = True
    while changed:
        changed = False
        for tag in CONDITION_TAGS:
            new = re.sub(r"^\(?\s*" + tag + r"\s*\)?\s*[-:]?\s*", "", s)
            if new != s:
                s, changed = new, True
    return re.sub(r"\s+", " ", s).strip()


def parse_stock_num(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s:
        return None
    s = re.sub(r"\bSTOK\b|\bSISA\b", " ", s.upper())
    s = re.sub(r"(?<=\s)O(?=\s|$)|^O(?=\s|$)", "0", s)
    s = re.sub(r"(\d)[.,](\d)", r"\1.\2", s)
    m = _NUM_RE.search(s)
    return float(m.group()) if m else None


def parse_num(v):
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if is_blank(s):
        return None
    s = re.sub(r"(\d)[.,](\d)", r"\1.\2", s)
    m = _NUM_RE.search(re.sub(r"[^0-9.\-]", " ", s))
    return float(m.group()) if m else None


def parse_date_iso(v):
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return (v + timedelta(hours=7)).date().isoformat() if v.tzinfo is None else v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    s = str(v).strip()
    if is_blank(s):
        return None
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.match(r"^(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})", s)
    if m:
        d, mo, y = m.groups()
        y = ("20" + y) if len(y) == 2 else y
        return f"{y}-{int(mo):02d}-{int(d):02d}"
    return None


def parse_bool(v):
    if v is None or v == "":
        return None
    s = str(v).strip().upper()
    if s in {"YA", "Y", "YES", "TRUE", "1", "PERLU"}:
        return 1
    if s in {"TIDAK", "T", "NO", "FALSE", "0"}:
        return 0
    return None


def row_hash(parts) -> str:
    joined = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()


def token_jaccard(a: str, b: str) -> float:
    ta = {t for t in desc_core(a).split(" ") if t}
    tb = {t for t in desc_core(b).split(" ") if t}
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    return inter / (len(ta) + len(tb) - inter)
