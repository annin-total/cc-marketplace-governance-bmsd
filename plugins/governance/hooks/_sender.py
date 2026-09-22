"""detach して POST する送信プロセス。標準ライブラリのみで動く。

`python3 _sender.py` として独立プロセスで起動される想定。リトライループ・
指数バックオフ・ACK は持たない。1 ファイルの失敗で後続のファイルを止めない。
どの経路でも例外を外に出さず、終了コードは常に 0 とする。
"""

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

import _spool

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"

_DEFAULT_CONFIG = {
    "ingest_url": "",
    "ingest_token": "",
    "flush_interval_sec": _spool.DEFAULT_FLUSH_INTERVAL_SEC,
    "timeout_sec": 60,
    "spool_max_bytes": _spool.DEFAULT_SPOOL_MAX_BYTES,
    "spool_max_days": _spool.DEFAULT_SPOOL_MAX_DAYS,
}


def _load_config() -> Optional[dict[str, Any]]:
    """`config.json` を読む。読めない・壊れている・dict でない場合は None を返す。"""
    try:
        with open(_CONFIG_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    return {key: data.get(key, default) for key, default in _DEFAULT_CONFIG.items()}


def _spool_files_sorted() -> list[Path]:
    """spool 内の `.jsonl` ファイルを、ファイル名（epoch 昇順）でソートして返す。"""
    spool_dir = _spool._spool_dir()
    if not spool_dir.is_dir():
        return []
    return sorted(spool_dir.glob("*.jsonl"))


def _post_file(path: Path, config: dict[str, Any]) -> None:
    """1 ファイルを POST する。2xx なら削除、それ以外は残す。例外は外に出さない。"""
    try:
        body = path.read_bytes()
    except OSError:
        return

    request = urllib.request.Request(
        config["ingest_url"],
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/x-ndjson",
            "X-Ingest-Token": config["ingest_token"],
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=config["timeout_sec"]) as response:
            status = response.status
    except urllib.error.HTTPError as err:
        status = err.code
    except (urllib.error.URLError, OSError):
        return

    if 200 <= status < 300:
        try:
            os.remove(path)
        except OSError:
            pass


def run() -> None:
    """送信プロセス本体。config を読み、退避 → 破棄 → 古い順に POST する。

    hook プロセスと同様に、例外を外に出さない（想定外の例外も握り潰す）。
    """
    try:
        config = _load_config()
        if config is None or not config["ingest_url"]:
            return
        _spool.rotate()
        _spool.prune(config["spool_max_bytes"], config["spool_max_days"])
        for path in _spool_files_sorted():
            _post_file(path, config)
    except Exception:  # noqa: BLE001, S110 (送信プロセスは例外を外に出さない)
        pass


def launch() -> None:
    """送信プロセスを detach して起動する。待たない。

    `stdin` / `stdout` / `stderr` を `DEVNULL` にし、`start_new_session=True` で
    親（hook プロセス）から切り離す。
    """
    try:
        subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve())],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        pass


if __name__ == "__main__":
    run()
