"""spool を POST する送信プロセス（`python3 _sender.py`）。例外を外に出さない。"""

import http.client
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
    "timeout_sec": 60,
    "spool_max_bytes": _spool.DEFAULT_SPOOL_MAX_BYTES,
    "spool_max_days": _spool.DEFAULT_SPOOL_MAX_DAYS,
}


def _load_config() -> Optional[dict[str, Any]]:
    """`config.json` を読む。読めなければ None。"""
    try:
        with open(_CONFIG_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    return {key: data.get(key, default) for key, default in _DEFAULT_CONFIG.items()}


def _spool_files_sorted() -> list[Path]:
    """spool の `.jsonl` をファイル名（epoch）の昇順で返す。"""
    spool_dir = _spool._spool_dir()
    if not spool_dir.is_dir():
        return []
    return sorted(spool_dir.glob("*.jsonl"))


def _post_file(path: Path, config: dict[str, Any]) -> bool:
    """1 ファイルを POST し、2xx なら消す。サーバに届かなかったら偽。"""
    try:
        body = path.read_bytes()
    except OSError:
        return True

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
    # 応答が壊れていると OSError 派生でない HTTPException が出る。逃がすと prune が飛ぶ
    except (urllib.error.URLError, OSError, http.client.HTTPException):
        return False

    if 200 <= status < 300:
        try:
            os.remove(path)
        except OSError:
            pass
    return True


def run() -> None:
    """退避 → 古い順に POST → 破棄。破棄を後に置き、上限超えのファイルにも 1 回は送る。"""
    try:
        config = _load_config()
        if config is None:
            return
        _spool.rotate()
        # 送信先が空でも退避と破棄は行う。行わないと queue.jsonl が上限なしに増える
        paths = _spool_files_sorted() if config["ingest_url"] else []
        for path in paths:
            # 応答しないサーバに対して、ファイル数 × timeout_sec 粘らない
            if not _post_file(path, config):
                break
        _spool.prune(config["spool_max_bytes"], config["spool_max_days"])
    except Exception:  # noqa: BLE001, S110 (送信プロセスは例外を外に出さない)
        pass


def launch() -> None:
    """送信プロセスを detach して起動する。待たない。"""
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
