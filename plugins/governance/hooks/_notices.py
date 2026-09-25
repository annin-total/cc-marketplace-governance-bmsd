"""SessionStart の未読お知らせ処理。契約（`contract`）にも識別子（`_identity`）にも依存しない。

`notices.json` を読み、未読を選び、出力用の文字列と開く URL を組み立て、既読を記録するところまでを担う。
出力そのもの（標準出力への書き出し）、ブラウザの起動、既読を書き込むタイミングの判断は
呼び出し元（`session_start.py`）が持つ。ここでは出力も既読の書き込みも行わない。
"""

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


def _write_seen(seen_ids: set) -> bool:
    """既読 ID の集合を `seen.json` に書く。書けたら真。失敗しても例外を外に出さない。"""
    path = _seen_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(sorted(seen_ids), f)
    except OSError:
        return False
    return True


def _valid_url(notice: dict) -> Optional[str]:
    """お知らせの `url` が開いてよい形なら返す。そうでなければ None。

    https だけを許し、ASCII 以外・空白・制御文字・区切り文字を含むものと、長すぎるもの、
    ホストが空のものを拒否する。不正な `url` は項目ごとではなく `url` だけを無視する。
    """
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
    """未読のうち、開いてよい `url` を持つ先頭の 1 件の URL を返す。無ければ None。"""
    for notice in unread:
        url = _valid_url(notice)
        if url:
            return url
    return None


def _format_message(unread: list) -> str:
    """未読のお知らせを、空行 1 つで区切った 1 つの文字列にまとめる。件ごとの接頭辞は付けない。"""
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
