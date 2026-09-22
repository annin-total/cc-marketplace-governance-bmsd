"""transcript 末尾から context_tokens を取得する。標準ライブラリのみで動く。

末尾 256KB だけをバイト列として読み、行を逆順に走査して最初に見つかった
`message.usage` の 3 値を合計する。合計が 0 の usage（API エラー応答）は採らず、
さらに前の行へ遡る。どの入力でも例外を外に出さない。
"""

import json
from typing import Optional

_TAIL_BYTES = 256 * 1024
_USAGE_KEYS = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")


def context_tokens(path: Optional[str], tail: int = _TAIL_BYTES) -> Optional[int]:
    """transcript の末尾 `tail` バイトから context_tokens を算出する。取得できなければ None。"""
    chunk = _read_tail(path, tail)
    if chunk is None:
        return None
    for line in reversed(chunk.split(b"\n")):
        total = _usage_total(line)
        if total:
            return total
    return None


def _read_tail(path: Optional[str], tail: int) -> Optional[bytes]:
    """ファイル末尾 `tail` バイトを読む。読めない場合は None を返す。

    `path` が `str` でなければ即座に None を返す。`bool` / `int` を素通しすると
    `open()` がファイル記述子として解釈し、`True`（== 1）は標準出力を閉じてしまう。
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
    """1 行から `message.usage` の 3 値の合計を取り出す。取れない場合は None。"""
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
    """usage の 1 項を数値に寄せる。真偽値・数値以外は合算不能として例外を投げる。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError
    return value
