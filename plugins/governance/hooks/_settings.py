"""settings.json への標準設定の適用（読み取り・mtime 検査・バックアップ・原子的置換）。"""

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Optional

import _govdir
from _policy_ops import apply_ops, unapplied

Row = tuple[str, Optional[str], Optional[str], str]


def _load(path: Path):
    """('ok'/'missing'/'parse_failed', data, mtime_ns) を返す。無ければ data={}。"""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return "missing", {}, None
    # 非 UTF-8 なら UnicodeDecodeError（ValueError 派生、OSError ではない）。捕まえ損ねると
    # SessionStart のたびに例外が漏れ、その端末の policy イベントが届かなくなる。
    except (OSError, ValueError):
        return "parse_failed", None, None
    mtime_ns = _stat_mtime_ns(path)
    if mtime_ns is None:
        return "parse_failed", None, None
    try:
        data = json.loads(text)
    # 深く入れ子になった JSON は RecursionError を投げる（ValueError 派生ではない）。
    except (ValueError, RecursionError):
        return "parse_failed", None, None
    if not isinstance(data, dict):
        return "parse_failed", None, None
    return "ok", data, mtime_ns


def _resolve(path: Path) -> Path:
    """シンボリックリンクを実体のパスに解決する。

    `os.replace` はリンク自体を置き換えるため、解決しないとリンクが普通のファイルに化ける。
    """
    try:
        return path.resolve()
    except (OSError, RuntimeError):
        return path


def _stat_mtime_ns(path: Path) -> Optional[int]:
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return None


def _write(config_path: Path, data: dict, expected_mtime_ns, gov_dir: Path) -> str:
    """原子的に置換する。バックアップに失敗したら書かない。"""
    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            dir=str(config_path.parent), prefix=".settings-", suffix=".tmp"
        )
    except OSError:
        return "write_failed"

    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False, indent=2))
            f.write("\n")

        if _stat_mtime_ns(config_path) != expected_mtime_ns:
            os.remove(tmp_path)
            return "skipped_conflict"

        if expected_mtime_ns is not None and not _govdir.backup(config_path, gov_dir):
            os.remove(tmp_path)
            return "write_failed"

        os.replace(tmp_path, config_path)
        return "applied"
    except OSError:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        return "write_failed"


def _row(entry: dict) -> Row:
    return (entry["key"], entry["value"], entry["prev"], entry["result"])


def apply_settings(config_path, policy: Any, gov_dir: Path) -> list[Row]:
    """`policy` を settings.json に当て、差分があれば書く。キーごとの結果を返す。"""
    config_path = _resolve(Path(config_path))
    status, data, mtime_ns = _load(config_path)
    if status == "parse_failed":
        return [_row(e) for e in unapplied(policy, "parse_failed")]

    done = _govdir.load_once(gov_dir)
    entries = apply_ops(data, policy, done, gov_dir.as_posix())
    pending = [e for e in entries if e["result"] == "pending"]
    if pending:
        write_status = _write(config_path, data, mtime_ns, gov_dir)
        for e in pending:
            e["result"] = write_status

    # 書けた組と、既に値が一致していた組だけを適用済みにする。失敗した組は次回やり直す
    applied = {
        e["once_key"]
        for e in entries
        if "once_key" in e and e["result"] in ("applied", "already_ok")
    }
    if applied != done:
        _govdir.save_once(gov_dir, applied)
    return [_row(e) for e in entries]
