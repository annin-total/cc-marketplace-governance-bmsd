"""settings.json への標準設定の適用。標準ライブラリのみで動く。

読み取り・mtime 検査・バックアップ・原子的置換・適用結果の返却を受け持つ。操作の中身は
`_policy_ops.py`、`<config_dir>/governance/` 配下のファイルは `_govdir.py` にある。
キューにも契約の DB 定義にも触れない。返すのはキーごとの
(key_name, value, prev_value, apply_result) の list だけ。
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Optional

import _govdir
from _policy_ops import apply_ops, unapplied

Row = tuple[str, Optional[str], Optional[str], str]


def _load(path: Path):
    """設定ファイルを読む。('ok'/'missing'/'parse_failed', data, mtime_ns) の組で返す。

    存在しない場合は data={} として扱う。パース失敗・トップレベルが dict でない場合は
    data=None とし、例外は外に漏らさない。
    """
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return "missing", {}, None
    # 非 UTF-8 のバイト列を含むファイルでは strict デコードが UnicodeDecodeError を投げる。
    # これは OSError ではなく ValueError 派生であり、捕まえ損ねると SessionStart のたびに
    # 例外が漏れ、お知らせも policy イベントも到達しないままその端末が画面から消える。
    except (OSError, ValueError):
        return "parse_failed", None, None
    try:
        mtime_ns = path.stat().st_mtime_ns
    except OSError:
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
    """シンボリックリンクなら実体を指すパスに解決する。

    `os.replace` はリンクそのものを置き換えるため、解決しないと dotfiles 管理下の端末で
    リンクが普通のファイルに化け、実体側は古い内容のまま取り残される。しかも結果は
    `applied` と記録されるため、壊れたことが画面からは分からない。
    """
    try:
        return path.resolve()
    except (OSError, RuntimeError):
        return path


def _stat_mtime_ns(path: Path) -> Optional[int]:
    """mtime をナノ秒単位で返す。読めなければ None。"""
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return None


def _write(config_path: Path, data: dict, expected_mtime_ns, gov_dir: Path) -> str:
    """原子的に置換する。'applied'/'skipped_conflict'/'write_failed' を返す。

    置換の直前に元のファイルを丸ごとバックアップし、それに失敗したら書かない。
    """
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
    """`policy` の SET / ADD / REMOVE / ONCE を settings.json に当て、差分があれば書く。

    `gov_dir` はバックアップと ONCE の記録の置き場。例外は呼び出し元に漏らさない。
    """
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
