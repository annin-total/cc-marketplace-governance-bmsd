"""キューへの追記・spool への退避・上限超えの破棄。いずれも例外を外に出さない。"""

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

_STATE_DIR_ENV = "CLAUDE_PLUGIN_DATA"
_FALLBACK_STATE_DIR_SUFFIX = (".claude", "cc-governance")

_QUEUE_FILENAME = "queue.jsonl"
_SPOOL_DIRNAME = "spool"
_SENT_AT_FILENAME = "sent_at"
_SPOOL_SUFFIX = ".jsonl"

DEFAULT_FLUSH_INTERVAL_SEC = 600
DEFAULT_SPOOL_MAX_BYTES = 5 * 1024 * 1024
DEFAULT_SPOOL_MAX_DAYS = 7

_SECONDS_PER_DAY = 86400


def _state_dir() -> Path:
    """端末の状態の置き場所（`CLAUDE_PLUGIN_DATA`、無ければ代替経路）。

    毎回評価する。定数化すると隔離の差し替えが効かず、利用者本人の `~/.claude/` に書き込む。
    """
    plugin_data = os.environ.get(_STATE_DIR_ENV)
    if plugin_data:
        return Path(plugin_data)
    return Path.home().joinpath(*_FALLBACK_STATE_DIR_SUFFIX)


def _queue_path() -> Path:
    return _state_dir() / _QUEUE_FILENAME


def _spool_dir() -> Path:
    return _state_dir() / _SPOOL_DIRNAME


def _sent_at_path() -> Path:
    return _state_dir() / _SENT_AT_FILENAME


def append(row: dict[str, Any]) -> None:
    """1 行を `queue.jsonl` に 1 回の `write` で追記する。

    `ensure_ascii=True` にする。`False` だと孤立サロゲートで UTF-8 の符号化に失敗する。
    """
    try:
        line = json.dumps(row, ensure_ascii=True) + "\n"
        path = _queue_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass


def rotate() -> None:
    """`queue.jsonl` を `spool/<epoch>-<uuid4hex>.jsonl` に退避する。

    UUID を含めるのは、同一秒の退避で `os.rename` が先行ファイルを黙って上書きしないため。
    """
    try:
        queue_path = _queue_path()
        if not queue_path.exists() or queue_path.stat().st_size == 0:
            return
        spool_dir = _spool_dir()
        spool_dir.mkdir(parents=True, exist_ok=True)
        dest = spool_dir / f"{int(time.time())}-{uuid.uuid4().hex}{_SPOOL_SUFFIX}"
        os.rename(queue_path, dest)
    except OSError:
        pass


def should_send(threshold_sec: int = DEFAULT_FLUSH_INTERVAL_SEC) -> bool:
    """キューがあり、`sent_at` が無いか `threshold_sec` 秒以上前なら真。

    mtime が未来のときも真にする（偽にするとその時刻まで送信が止まる）。
    """
    try:
        if not _queue_path().exists():
            return False
        sent_at_path = _sent_at_path()
        if not sent_at_path.exists():
            return True
        elapsed = time.time() - sent_at_path.stat().st_mtime
        return elapsed < 0 or elapsed >= threshold_sec
    except OSError:
        return False


def mark_sent() -> None:
    try:
        path = _sent_at_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=True)
    except OSError:
        pass


def prune(
    max_bytes: int = DEFAULT_SPOOL_MAX_BYTES,
    max_days: int = DEFAULT_SPOOL_MAX_DAYS,
) -> None:
    """spool の合計サイズ・保持日数の上限を超えた `.jsonl` を古い順に消す。"""
    try:
        spool_dir = _spool_dir()
        if not spool_dir.is_dir():
            return

        entries = []
        for entry in spool_dir.iterdir():
            if entry.suffix != _SPOOL_SUFFIX or not entry.is_file():
                continue
            try:
                st = entry.stat()
            except OSError:
                continue
            entries.append((st.st_mtime, st.st_size, entry))

        now = time.time()
        max_age_sec = max_days * _SECONDS_PER_DAY
        kept = []
        for mtime, size, entry in entries:
            if now - mtime > max_age_sec:
                entry.unlink(missing_ok=True)
            else:
                kept.append((mtime, size, entry))

        kept.sort(key=lambda item: item[0])
        total = sum(size for _, size, _ in kept)
        for mtime, size, entry in kept:
            if total <= max_bytes:
                break
            entry.unlink(missing_ok=True)
            total -= size
    except OSError:
        pass
