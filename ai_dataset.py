"""
保存 AI 改写结果，供后续微调 / 蒸馏采集语料。

默认写入 data/ai_rewrites.jsonl（每行一条 JSON，已在 .gitignore）。
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

_DATA_DIR = Path(__file__).with_name("data")
_DATA_FILE = _DATA_DIR / "ai_rewrites.jsonl"
_lock = threading.Lock()
_lookup: dict[str, str] | None = None
_lookup_mtime: float = 0.0


def dataset_path() -> Path:
    return _DATA_FILE


def dataset_count() -> int:
    if not _DATA_FILE.exists():
        return 0
    count = 0
    with _DATA_FILE.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                count += 1
    return count


def _load_lookup(*, force: bool = False) -> dict[str, str]:
    """按 input 建索引；同 input 多条时保留文件里最后一条。"""
    global _lookup, _lookup_mtime

    if not _DATA_FILE.exists():
        _lookup = {}
        _lookup_mtime = 0.0
        return _lookup

    mtime = _DATA_FILE.stat().st_mtime
    if not force and _lookup is not None and mtime == _lookup_mtime:
        return _lookup

    data: dict[str, str] = {}
    with _DATA_FILE.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            src = str(row.get("input", "")).strip()
            dst = str(row.get("output", "")).strip()
            if src and dst and src != dst:
                data[src] = dst

    _lookup = data
    _lookup_mtime = mtime
    return _lookup


def invalidate_lookup_cache() -> None:
    """重载 config 或手动刷新语料索引时调用。"""
    global _lookup, _lookup_mtime
    _lookup = None
    _lookup_mtime = 0.0


def lookup_rewrite(text: str) -> str | None:
    """原文精确匹配语料库中的 input，命中则返回对应 output。"""
    key = text.strip()
    if not key:
        return None
    return _load_lookup().get(key)


def save_ai_rewrite(
    text: str,
    result: str,
    *,
    model: str,
    base_url: str = "",
    enabled: bool = True,
) -> None:
    """追加一条 AI 改写记录（input/output 相同则跳过）。"""
    if not enabled:
        return
    src = text.strip()
    dst = result.strip()
    if not src or not dst or src == dst:
        return

    record = {
        "input": src,
        "output": dst,
        "model": model,
        "base_url": base_url,
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    line = json.dumps(record, ensure_ascii=False) + "\n"

    with _lock:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        if _DATA_FILE.exists():
            with _DATA_FILE.open(encoding="utf-8") as f:
                for existing in f:
                    existing = existing.strip()
                    if not existing:
                        continue
                    try:
                        row = json.loads(existing)
                    except json.JSONDecodeError:
                        continue
                    if row.get("input") == src and row.get("output") == dst:
                        return
        with _DATA_FILE.open("a", encoding="utf-8") as f:
            f.write(line)
    invalidate_lookup_cache()
