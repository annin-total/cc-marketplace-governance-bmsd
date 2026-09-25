"""未読のお知らせの選択と表示文字列の組み立て。出力・ブラウザ起動・既読を書く時機は呼び出し元が持つ。"""

import json
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlsplit

from _spool import _state_dir

_SEEN_FILENAME = "seen.json"
_URL_SCHEME = "https://"
_URL_MAX_LENGTH = 2048
# 空白・制御文字（0x20 以下と 0x7f）に加え、引数やシェルの区切りになりうる文字を拒否する。
_URL_FORBIDDEN_CHARS = (
    frozenset('"<>\\^`|{}') | {chr(c) for c in range(0x21)} | {"\x7f"}
)
_NOTICES_PATH = Path(__file__).resolve().parent.parent / "notices.json"


def _seen_path() -> Path:
    return _state_dir() / _SEEN_FILENAME


def _read_notices(path: Path = _NOTICES_PATH) -> list:
    """`notices.json` を読む。読めなければ空。壊れた項目だけを飛ばし、他の項目は残す。"""
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
    """既読 ID の集合を読む。読めなければ空。"""
    try:
        with open(_seen_path(), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return set()
    if not isinstance(data, list):
        return set()
    return {item for item in data if isinstance(item, str)}


def _select_unread(notices: list, seen: set) -> list:
    return [n for n in notices if n["id"] not in seen]


def _write_seen(seen_ids: set) -> bool:
    """既読 ID の集合を書く。書けたら真。"""
    path = _seen_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(sorted(seen_ids), f)
    except OSError:
        return False
    return True


def _valid_url(notice: dict) -> Optional[str]:
    """`url` が開いてよい形（https・ASCII・禁止文字なし・長さ上限内・ホストあり）なら返す。"""
    url = notice.get("url")
    if not isinstance(url, str) or not url.startswith(_URL_SCHEME):
        return None
    if len(url) > _URL_MAX_LENGTH or not url.isascii():
        return None
    if any(c in _URL_FORBIDDEN_CHARS for c in url):
        return None
    try:
        host = urlsplit(url).hostname
    except ValueError:
        return None
    return url if host else None


def first_url(unread: list) -> Optional[str]:
    """開いてよい `url` を持つ先頭の 1 件の URL。無ければ None。"""
    for notice in unread:
        url = _valid_url(notice)
        if url:
            return url
    return None


def _format_message(unread: list) -> str:
    """未読のお知らせを空行区切りの 1 つの文字列にする。"""
    parts = []
    for notice in unread:
        title = notice.get("title")
        body = str(notice.get("body", ""))
        url = _valid_url(notice)
        if url:
            body = f"{body}\n詳細: {url}" if body else f"詳細: {url}"
        parts.append(f"{title}\n{body}" if isinstance(title, str) and title else body)
    return "\n\n".join(parts)


def notices_step(disabled: bool, notices_path: Path = _NOTICES_PATH) -> tuple:
    """(output, unread, seen) を返す。出力は呼び出し元が 1 回だけ行うため、ここでは書かない。"""
    if disabled:
        return {}, [], set()

    seen = _read_seen()
    unread = _select_unread(_read_notices(notices_path), seen)

    output: dict[str, Any] = {}
    if unread:
        output["systemMessage"] = _format_message(unread)
    return output, unread, seen
