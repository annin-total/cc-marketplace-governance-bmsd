"""SessionStart hook のエントリ。statusline.js の同期 -> 設定の適用 -> お知らせの表示 ->
イベントの収集の順に実行する。

お知らせは、非対話起動（`claude -p` など）では既読にしない。URL 付きの未読があれば、
既読の記録に成功した対話セッションに限り、先頭 1 件だけを既定ブラウザで開く。

4 つはそれぞれ個別に例外から守り、1 つの失敗が残りを巻き添えにしない。無効化スイッチ
（`CC_GOVERNANCE_DISABLE`）が止めるのは、お知らせの表示と利用ログの収集だけである。
statusline.js の同期・設定の適用・その policy イベントの記録・送信条件の判定はスイッチの外側で行う。
"""

if __name__ == "__main__":
    # collect.py と同じ理由（import 中の SIGINT でトレースバックが漏れる）で、スクリプト起動時だけ SIGINT を無視する。
    import _signal

    _signal.signal(_signal.SIGINT, _signal.SIG_IGN)

import json
import os
import sys
import time
from typing import Any, Optional

import _browser
import _govdir
import _identity
import _notices
import _spool
from _settings import apply_settings
from collect import _read_stdin_json, extract_event
from contract import POLICY_COLUMNS, coerce, to_day

_DISABLE_ENV = "CC_GOVERNANCE_DISABLE"

_NOTICES_PATH = _notices._NOTICES_PATH


def _policy_row(
    key_name: str,
    value: Optional[str],
    prev_value: Optional[str],
    apply_result: str,
    ts: int,
    plugin_version: Optional[str],
) -> dict:
    """1 件の適用結果を policy イベント（キューの 1 行）に組み立てる。"""
    raw = {
        "event_id": _identity.new_event_id(),
        "ts": ts,
        "day": to_day(ts),
        "user_email": _identity.get_user_email(),
        "host": _identity.get_host(),
        "key_name": key_name,
        "value": value,
        "prev_value": prev_value,
        "apply_result": apply_result,
        "plugin_version": plugin_version,
    }
    row: dict[str, Any] = {"kind": "policy"}
    for name, type_str in POLICY_COLUMNS:
        row[name] = coerce(raw.get(name), type_str)
    return row


def _apply_settings_step() -> None:
    """設定を適用し、結果を policy イベントとしてキューに積む。無効化スイッチの影響を受けない。

    `plugin_version` の取得もこの中で行う。ここより外に置くと、その失敗がお知らせの表示と
    収集まで巻き添えにする（「hook は無言で消えない」という原則に反する）。
    `policy` の import も同じ理由でここに置く（配った定義の誤りを設定の適用だけに閉じ込める）。
    """
    import policy

    plugin_version = _identity.get_plugin_version()
    rows = apply_settings(_govdir.settings_path(), policy, _govdir.governance_dir())
    ts = int(time.time())
    for key_name, value, prev_value, apply_result in rows:
        _spool.append(
            _policy_row(key_name, value, prev_value, apply_result, ts, plugin_version)
        )


def _notices_step(disabled: bool) -> tuple:
    """未読のお知らせから出力用の dict を組み立てる。実体は `_notices.notices_step`。"""
    return _notices.notices_step(disabled, _NOTICES_PATH)


def _mark_seen_and_open(unread: list, seen: set) -> None:
    """未読を既読に加え、書けた場合に限り対話セッションなら先頭の URL を開く。

    非対話起動では既読にしない（人が表示を見ていないため）。既読を書けない端末で
    ブラウザが毎回開かないよう、開くのは既読の記録に成功した後だけにする。
    """
    if _browser.is_headless():
        return
    if not _notices._write_seen(seen | {n["id"] for n in unread}):
        return
    if _browser.is_interactive():
        url = _notices.first_url(unread)
        if url:
            _browser.open_url(url)


def _emit_output(output: dict) -> bool:
    """hook の JSON 出力を標準出力へ 1 個だけ書く。書き出しと flush が例外なく終われば真。

    失敗した場合、fd 1 を `/dev/null` に差し替える。標準出力のパイプの読み口が閉じている
    ときなど、`write`/`flush` の失敗を捕まえてもなお、`TextIOWrapper` 内部の
    `BufferedWriter` に書き込み済みのデータが残っていることがある。それがインタプリタ
    終了時の最終 flush で再送され、そこでも失敗すると標準エラーに漏れて exit 120 になる
    （`sys.stdout` を差し替えるだけでは、この残ったバッファには効かない）。
    """
    try:
        sys.stdout.write(json.dumps(output, ensure_ascii=False))
        sys.stdout.write("\n")
        sys.stdout.flush()
        return True
    except Exception:  # noqa: BLE001 (hook は例外を外に出さない)
        try:
            os.dup2(os.open(os.devnull, os.O_WRONLY), 1)
        except OSError:
            pass
        return False


def _collect_step(hook_event: Optional[str], disabled: bool) -> None:
    """SessionStart の利用ログを収集する。送信条件の判定は無効化スイッチの外側で行う。

    標準入力の読み取りもこの中で行う。ここより外に置くと、その失敗（深い入れ子の JSON
    による `RecursionError` など）が設定の適用とお知らせの表示まで巻き添えにする。
    """
    if not disabled:
        raw_input = _read_stdin_json()
        _spool.append(extract_event(raw_input, hook_event))

    if _spool.should_send():
        _spool.mark_sent()
        import _sender

        _sender.launch()


def main() -> None:
    """statusline.js の同期 -> 設定の適用 -> お知らせの表示 -> イベントの収集の順に実行する。"""
    hook_event: Optional[str] = sys.argv[1] if len(sys.argv) > 1 else None
    disabled = bool(os.environ.get(_DISABLE_ENV))

    # 設定より先に置く。設定がこのファイルを指したとき、既に在るようにするため
    try:
        _govdir.sync_statusline(_govdir.governance_dir())
    except Exception:  # noqa: BLE001, S110 (hook は例外を外に出さない)
        pass

    try:
        _apply_settings_step()
    except Exception:  # noqa: BLE001, S110 (hook は例外を外に出さない)
        pass

    try:
        output, unread, seen = _notices_step(disabled)
    except Exception:  # noqa: BLE001 (hook は例外を外に出さない)
        output, unread, seen = {}, [], set()

    # 出力は必ず 1 回だけ行う。ここより上で何が失敗しても、少なくとも空の JSON を出す。
    if _emit_output(output) and unread:
        try:
            _mark_seen_and_open(unread, seen)
        except Exception:  # noqa: BLE001, S110 (hook は例外を外に出さない)
            pass

    try:
        _collect_step(hook_event, disabled)
    except Exception:  # noqa: BLE001, S110 (hook は例外を外に出さない)
        pass


if __name__ == "__main__":
    try:
        main()
    except BaseException:  # noqa: BLE001, S110 (hook は常に exit 0 で終わる)
        pass
