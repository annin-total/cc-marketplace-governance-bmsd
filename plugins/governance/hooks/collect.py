"""全 hook 共通のイベント収集エントリ。hook の種類で分岐せず、契約のキーパスを読むだけ。

`python3 collect.py <hook_event>` として単体で実行できる入口を持つ。
標準入力から hook の JSON を読み、キューに追記し、`SessionStart` / `Stop` のときだけ
送信条件を判定して送信プロセスを起動する。例外は外に出さず、常に exit 0 とする。
"""

if __name__ == "__main__":
    # `except BaseException` は `main()` の実行中しか守らない。SIGINT がこの下の
    # import 文の最中に届くと、まだ try 節の外であるためトレースバックが標準エラーに漏れる
    # （実測で確認済み）。`_signal` は enum ラッパーを介さない素の C 拡張であり、
    # import より前に SIGINT を無視することで、この窓を最小化する。
    # スクリプトとして起動されたときだけ立てる。モジュールとして import しただけの
    # 呼び出し元プロセス（pytest 等）の SIGINT まで殺さないため。
    import _signal

    _signal.signal(_signal.SIGINT, _signal.SIG_IGN)

import json
import os
import sys
import time
from typing import Any, Optional

import _context
import _identity
import _spool
from contract import EXTRA_COLUMNS, HOOK_FIELDS, coerce, dig, to_day

_CONTEXT_TOKEN_HOOK_EVENTS = ("PreCompact", "Stop")
_SEND_CHECK_HOOK_EVENTS = ("SessionStart", "Stop")
_DISABLE_ENV = "CC_GOVERNANCE_DISABLE"


def extract_event(raw_input: Any, hook_event: Optional[str]) -> dict[str, Any]:
    """hook 入力から送信する1行分の dict を組み立てる。

    `raw_input` が dict でない場合も例外にせず、HOOK_FIELDS 由来の列をすべて None にする。
    `EXTRA_COLUMNS` / `HOOK_FIELDS` のどちらの値も、契約の `coerce` で列の型に合わせる。
    """
    obj = raw_input if isinstance(raw_input, dict) else {}

    ts = int(time.time())
    raw_extra = {
        "event_id": _identity.new_event_id(),
        "ts": ts,
        "day": to_day(ts),
        "user_email": _identity.get_user_email(),
        "host": _identity.get_host(),
        "hook_event": hook_event,
        "context_tokens": _resolve_context_tokens(obj, hook_event),
    }

    row: dict[str, Any] = {"kind": "event"}
    for name, type_str in EXTRA_COLUMNS:
        row[name] = coerce(raw_extra.get(name), type_str)

    for name, path, type_str in HOOK_FIELDS:
        row[name] = coerce(dig(obj, path), type_str)

    return row


def _resolve_context_tokens(obj: dict, hook_event: Optional[str]):
    """`PreCompact` / `Stop` のときだけ transcript から context_tokens を算出する。"""
    if hook_event not in _CONTEXT_TOKEN_HOOK_EVENTS:
        return None
    return _context.context_tokens(dig(obj, ("transcript_path",)))


def _read_stdin_json() -> Any:
    """標準入力を読んで JSON としてパースする。読めない・パースできない場合は None。"""
    try:
        text = sys.stdin.read()
    except (OSError, ValueError):
        return None
    try:
        return json.loads(text)
    except ValueError:
        return None


def main() -> None:
    """collect.py の入口。

    無効化スイッチ判定 -> 収集 -> `SessionStart` / `Stop` のときだけ送信条件判定の順で行う。
    `sent_at` の更新は送信プロセスの起動より先に行う（同時に開いたセッションの一斉起動を防ぐ）。
    """
    if os.environ.get(_DISABLE_ENV):
        return

    hook_event: Optional[str] = sys.argv[1] if len(sys.argv) > 1 else None
    raw_input = _read_stdin_json()
    row = extract_event(raw_input, hook_event)
    _spool.append(row)

    if hook_event in _SEND_CHECK_HOOK_EVENTS and _spool.should_send():
        _spool.mark_sent()
        import _sender

        _sender.launch()


if __name__ == "__main__":
    try:
        main()
    except BaseException:  # noqa: BLE001, S110 (hook は例外を外に出さず常に exit 0。SIGINT による
        # KeyboardInterrupt も含めて画面を汚さない。インタプリタ起動中の SIGINT はこの try の
        # 外側で発生するため防げないが、その窓では標準エラーへの出力自体がまだ無い)
        pass
