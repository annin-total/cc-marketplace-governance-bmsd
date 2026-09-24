"""起動形態の判定と、お知らせの URL を既定ブラウザで開く処理。例外を外に出さない。

起動形態は Claude Code が hook に渡す `CLAUDE_CODE_ENTRYPOINT` で判定する。
ブラウザを開くのは対話セッション（許可リストの値）のときだけで、値が無い・未知なら開かない。
"""

import os
import subprocess
import sys

_ENTRYPOINT_ENV = "CLAUDE_CODE_ENTRYPOINT"
_INTERACTIVE_ENTRYPOINTS = frozenset({"cli"})
_HEADLESS_ENTRYPOINT_PREFIX = "sdk-"


def is_interactive() -> bool:
    """人が見ている対話セッションなら真。値が無い・未知なら偽（開かない側に倒す）。"""
    return os.environ.get(_ENTRYPOINT_ENV) in _INTERACTIVE_ENTRYPOINTS


def is_headless() -> bool:
    """`claude -p` や SDK からの非対話起動なら真。値が無い・未知なら偽。"""
    return os.environ.get(_ENTRYPOINT_ENV, "").startswith(_HEADLESS_ENTRYPOINT_PREFIX)


def open_url(url: str) -> None:
    """`url` を OS の既定ブラウザで開く。待たない。macOS と Windows 以外では何もしない。

    Windows は `os.startfile`（ShellExecute）で開く。`cmd /c start` はシェルを通るため、
    URL の `&` などでコマンドが分断される。macOS は `open` を detach して起動する。
    """
    try:
        if sys.platform == "win32":
            os.startfile(url)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(
                ["open", url],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
    except Exception:  # noqa: BLE001, S110 (hook は例外を外に出さない)
        pass
