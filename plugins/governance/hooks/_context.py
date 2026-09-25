"""transcript 末尾の最後の `message.usage` から context_tokens を求める。例外を外に出さない。"""

import json
from typing import Optional

_TAIL_BYTES = 256 * 1024
_USAGE_KEYS = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")


def context_tokens(path: Optional[str], tail: int = _TAIL_BYTES) -> Optional[int]:
    """末尾 `tail` バイトから context_tokens を求める。取れなければ None。"""
    chunk = _read_tail(path, tail)
    if chunk is None:
        return None
    for line in reversed(chunk.split(b"\n")):
        total = _usage_total(line)
        # 合計 0 は API エラー応答の行であり、採ると文脈量 0 の実データと画面上で区別できない。
        if total:
            return total
    return None


def _read_tail(path: Optional[str], tail: int) -> Optional[bytes]:
    """ファイル末尾 `tail` バイトを読む。読めなければ None。

    `str` 以外を弾く。`open(True)` は fd 1 として開き、閉じるときに標準出力を閉じてしまう。
    """
    if not isinstance(path, str) or not path:
        return None
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - tail))
            return f.read()
    except OSError:
        return None


def _usage_total(line: bytes) -> Optional[int]:
    """1 行の `message.usage` の 3 値の合計。取れなければ None。"""
    try:
        obj = json.loads(line)
    except ValueError:
        return None
    if not isinstance(obj, dict):
        return None
    message = obj.get("message")
    if not isinstance(message, dict):
        return None
    usage = message.get("usage")
    if not isinstance(usage, dict):
        return None
    try:
        return sum(_as_number(usage.get(key, 0)) for key in _USAGE_KEYS)
    except TypeError:
        return None


def _as_number(value):
    """真偽値・数値以外なら TypeError を投げる。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError
    return value
