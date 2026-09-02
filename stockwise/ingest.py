"""Live upload path. To avoid maintaining two ingest implementations, the actual
parsing/matching/UPSERT is done by the Node tool (tools/ingest_one.mjs), which is
the same code path the bootstrap build uses and is tested against the real files.
Python just hands it a file and reads back the JSON summary.

Requires Node.js on PATH (already used by tools/). If Node is unavailable, the
page falls back to telling the user to run the CLI build.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from stockwise.config import ROOT

INGEST_SCRIPT = ROOT / "tools" / "ingest_one.mjs"
BUILD_SCRIPT = ROOT / "tools" / "build_stockwise_db.mjs"


def node_available() -> str | None:
    return shutil.which("node")


def _run_node(script: Path, args: list[str], timeout: int = 900) -> dict:
    node = node_available()
    if not node:
        raise RuntimeError("Node.js tidak ditemukan di PATH — jalankan lewat CLI: "
                           f"node --experimental-sqlite {script.name}")
    proc = subprocess.run(
        [node, "--experimental-sqlite", str(script), *args],
        cwd=str(ROOT), capture_output=True, text=True, timeout=timeout,
    )
    out = proc.stdout.strip()
    # the script prints one JSON line last
    result = {}
    for line in reversed(out.splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                result = json.loads(line)
                break
            except json.JSONDecodeError:
                continue
    result.setdefault("ok", proc.returncode == 0)
    result.setdefault("stdout", out)
    result.setdefault("stderr", proc.stderr.strip())
    result["returncode"] = proc.returncode
    return result


def ingest_upload(module: str, uploaded_file) -> dict:
    """uploaded_file: a Streamlit UploadedFile. Returns the ingest summary dict."""
    suffix = Path(uploaded_file.name).suffix or ".xlsx"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(uploaded_file.getbuffer())
        tmp_path = tmp.name
    try:
        return _run_node(INGEST_SCRIPT, [module, tmp_path, "--name", uploaded_file.name])
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def rebuild_from_datafix() -> dict:
    return _run_node(BUILD_SCRIPT, [], timeout=1800)
