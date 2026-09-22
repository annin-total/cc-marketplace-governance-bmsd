"""ローカルキューへの追記・spool への退避・上限を超えた spool の破棄。標準ライブラリのみで動く。

hook が同期的に行う I/O は「1 回の追記」と「送信条件判定のための stat」だけである。
リトライループ・指数バックオフ・ACK は持たない。いずれの関数も失敗を呼び出し元に伝えず、
例外を外に出さない（hook は利用者の作業を妨げない）。
"""

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
    """端末の状態の置き場所を解決する。`CLAUDE_PLUGIN_DATA` が無ければ代替経路を使う。

    解決規則はここ 1 か所に置く。`_identity.py` はこの関数を呼ぶだけにする。
    `Path.home()` は呼び出しのたびに評価する。import 時に評価して定数化すると、
    テストや隔離環境での `HOME` の差し替えが効かなくなり、利用者本人の `~/.claude/` に書き込む。
    """
    plugin_data = os.environ.get(_STATE_DIR_ENV)
    if plugin_data:
        return Path(plugin_data)
    return Path.home().joinpath(*_FALLBACK_STATE_DIR_SUFFIX)


def _queue_path() -> Path:
    """`queue.jsonl` のパスを返す。"""
    return _state_dir() / _QUEUE_FILENAME


def _spool_dir() -> Path:
    """`spool/` のパスを返す。"""
    return _state_dir() / _SPOOL_DIRNAME


def _sent_at_path() -> Path:
    """`sent_at` のパスを返す。"""
    return _state_dir() / _SENT_AT_FILENAME


def append(row: dict[str, Any]) -> None:
    """1 行分の dict を `queue.jsonl` に追記する。`open(..., "a")` + 1 回の `write` のみ。

    `ensure_ascii=True` で書き出す。孤立サロゲートを含む文字列は `\\uXXXX` 形式で
    エスケープされ、UTF-8 での符号化に失敗しない（`ensure_ascii=False` は失敗しうる）。
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

    ファイル名に UUID を含めるのは、複数のセッションが同一秒に退避しても
    `os.rename` が既存ファイルを黙って置き換えて先行イベントを消さないようにするため。
    `queue.jsonl` が無い・0 バイトのときは何もしない。
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
    """送信条件を判定する。行数による条件は持たない。

    `queue.jsonl` が無ければ偽（送るものが無い）。`sent_at` が無ければ真。
    それ以外は `sent_at` の mtime から `threshold_sec` 秒以上経過していれば真。
    """
    try:
        if not _queue_path().exists():
            return False
        sent_at_path = _sent_at_path()
        if not sent_at_path.exists():
            return True
        elapsed = time.time() - sent_at_path.stat().st_mtime
        return elapsed >= threshold_sec
    except OSError:
        return False


def mark_sent() -> None:
    """`sent_at` の mtime を現在時刻に更新する（無ければ作る）。"""
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
    """spool の合計サイズ・保持日数の上限を超えたファイルを、古い順に削除する。

    `.jsonl` 以外のファイルは対象にしない。`spool/` が無ければ何もしない。
    """
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
