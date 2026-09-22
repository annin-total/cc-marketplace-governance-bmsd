"""SessionStart の未読お知らせ処理。契約（`contract`）にも識別子（`_identity`）にも依存しない。

`notices.json` を読み、未読を選び、出力用の文字列を組み立て、既読を記録するところまでを担う。
出力そのもの（標準出力への書き出し）と、既読を書き込むタイミングの判断は呼び出し元
（`session_start.py`）が持つ。ここでは出力も既読の書き込みも行わない。
"""

import json
from pathlib import Path
from typing import Any

from _spool import _state_dir

_SEEN_FILENAME = "seen.json"
_NOTICES_PATH = Path(__file__).resolve().parent.parent / "notices.json"


def _seen_path() -> Path:
    """既読 ID 集合 `seen.json` のパスを返す。状態ディレクトリの規則は `_spool` に従う。"""
    return _state_dir() / _SEEN_FILENAME


def _read_notices(path: Path = _NOTICES_PATH) -> list:
    """`notices.json` を読む。無い・壊れている・配列でない場合は空リストとする。

    `body` が文字列でない項目は壊れているとみなして飛ばす。1 件の欠陥が、
    同じファイルの正常な項目まで隠さないようにするため。
    """
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return [
        n
        for n in data
        if isinstance(n, dict)
        and isinstance(n.get("id"), str)
        and isinstance(n.get("body", ""), str)
    ]


def _read_seen() -> set:
    """既読 ID の集合を読む。無い・壊れている・配列でない場合は空集合とする。"""
    try:
        with open(_seen_path(), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return set()
    if not isinstance(data, list):
        return set()
    return {item for item in data if isinstance(item, str)}


def _select_unread(notices: list, seen: set) -> list:
    """未読（`seen` に無い id）のお知らせだけを、`notices` の順序を保って返す。"""
    return [n for n in notices if n["id"] not in seen]


def _write_seen(seen_ids: set) -> None:
    """既読 ID の集合を `seen.json` に書く。失敗しても例外を外に出さない。"""
    path = _seen_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(sorted(seen_ids), f)
    except OSError:
        pass


def _format_message(unread: list) -> str:
    """未読のお知らせを、空行 1 つで区切った 1 つの文字列にまとめる。件ごとの接頭辞は付けない。"""
    parts = []
    for notice in unread:
        title = notice.get("title")
        body = notice.get("body", "")
        parts.append(
            f"{title}\n{body}" if isinstance(title, str) and title else str(body)
        )
    return "\n\n".join(parts)


def notices_step(disabled: bool, notices_path: Path = _NOTICES_PATH) -> tuple:
    """未読のお知らせから出力用の dict を組み立てる。戻り値は (output, unread, seen)。

    出力も既読の書き込みもここでは行わない。呼び出し元が必ず 1 回だけ出力できるようにするため。
    """
    if disabled:
        return {}, [], set()

    seen = _read_seen()
    unread = _select_unread(_read_notices(notices_path), seen)

    output: dict[str, Any] = {}
    if unread:
        output["systemMessage"] = _format_message(unread)
    return output, unread, seen
