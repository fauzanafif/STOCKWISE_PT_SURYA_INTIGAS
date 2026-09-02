"""Live upload path. The actual parsing / matching / UPSERT is done by the Node
tools (tools/ingest_batch.mjs, tools/ingest_one.mjs) — the same code the bootstrap
build uses, tested against the real files. Python just hands over the files and
reads back the JSON summary.

Requires Node.js on PATH.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from stockwise.config import ROOT

BATCH_SCRIPT = ROOT / "tools" / "ingest_batch.mjs"
ONE_SCRIPT = ROOT / "tools" / "ingest_one.mjs"
BUILD_SCRIPT = ROOT / "tools" / "build_stockwise_db.mjs"


def node_available() -> str | None:
    return shutil.which("node")


def _run_node(script: Path, args: list[str], timeout: int = 1800) -> dict:
    node = node_available()
    if not node:
        raise RuntimeError(
            f"Node.js tidak ditemukan di PATH. Jalankan lewat terminal: node --experimental-sqlite {script.name} …")
    proc = subprocess.run(
        [node, "--experimental-sqlite", "--max-old-space-size=4096", str(script), *args],
        cwd=str(ROOT), capture_output=True, text=True, timeout=timeout,
    )
    out = proc.stdout.strip()
    result: dict = {}
    for line in reversed(out.splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                result = json.loads(line)
                break
            except json.JSONDecodeError:
                continue
    result.setdefault("ok", proc.returncode == 0)
    result.setdefault("stdout", out[-4000:])
    result.setdefault("stderr", proc.stderr.strip()[-4000:])
    result["returncode"] = proc.returncode
    return result


def ingest_uploads(uploaded_files) -> dict:
    """uploaded_files: list of Streamlit UploadedFile. Detects module per file,
    ingests all in the right order, runs matching + calc once."""
    tmpdir = Path(tempfile.mkdtemp(prefix="stockwise_up_"))
    try:
        paths, names = [], []
        for uf in uploaded_files:
            p = tmpdir / uf.name
            p.write_bytes(uf.getbuffer())
            paths.append(str(p))
            names.append(uf.name)
        return _run_node(BATCH_SCRIPT, [*paths, "--names", *names])
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def rebuild_from_datafix() -> dict:
    return _run_node(BUILD_SCRIPT, [])
