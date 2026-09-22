"""識別子（user_email / host / event_id）の解決とキャッシュ。標準ライブラリのみで動く。

状態ディレクトリの解決規則は `_spool.py` の 1 か所に置く。ここではそれを呼ぶだけにする。
"""

import json
import os
import platform
import subprocess
import uuid
from pathlib import Path
from typing import Optional

from _spool import _state_dir

_ENV_USER_EMAIL = "CC_GOVERNANCE_USER_EMAIL"
_ENV_PLUGIN_ROOT = "CLAUDE_PLUGIN_ROOT"
_PLUGIN_JSON_RELATIVE = (".claude-plugin", "plugin.json")

# hooks.json の hook 全体の timeout が 5 秒であるため、git 単体はそれより短くする。
_GIT_TIMEOUT_SEC = 3


def _identity_path() -> Path:
    """`identity.json` のパスを返す。"""
    return _state_dir() / "identity.json"


def _load_cache() -> Optional[dict]:
    """`identity.json` を読む。存在しない・壊れている場合は None を返す。"""
    path = _identity_path()
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def _save_cache(user_email: Optional[str]) -> None:
    """`user_email` の解決結果を `identity.json` に書き込む。親ディレクトリが無ければ作る。

    書き込みに失敗しても解決処理自体は妨げない（hook は利用者の作業を妨げない）ため、
    `OSError` は無視する。
    """
    path = _identity_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"user_email": user_email}, f)
    except OSError:
        pass


def _resolve_via_git() -> Optional[str]:
    """`git config --global user.email` を実行し、成功すれば小文字化して返す。"""
    try:
        proc = subprocess.run(
            ["git", "config", "--global", "user.email"],
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_SEC,
            check=False,
        )
    # `text=True` の strict デコードは git が非 UTF-8 を返すと UnicodeDecodeError を投げる。
    # これは ValueError 派生であり、捕まえ損ねると収集そのものが恒久的に無言で止まる。
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    value = proc.stdout.strip()
    if not value:
        return None
    return value.lower()


def get_user_email() -> Optional[str]:
    """user_email を解決する。

    環境変数 `CC_GOVERNANCE_USER_EMAIL` → `git config --global user.email` → None
    の順で解決する。環境変数は毎回優先して評価する（キャッシュより優先）。
    git を呼ぶ場合のみキャッシュを見て、キャッシュがあれば subprocess を起動しない。
    解決できなかった場合も、その結果をキャッシュする。
    """
    env_value = os.environ.get(_ENV_USER_EMAIL)
    if env_value:
        email = env_value.lower()
        _save_cache(email)
        return email

    cache = _load_cache()
    if cache is not None and "user_email" in cache:
        return cache["user_email"]

    email = _resolve_via_git()
    _save_cache(email)
    return email


def get_host() -> str:
    """host を返す。呼び出しごとに `platform.node()` をそのまま返す。"""
    return platform.node()


def new_event_id() -> str:
    """event_id を返す。呼び出しごとに新しい `uuid.uuid4()` の文字列を生成する。"""
    return str(uuid.uuid4())


def _plugin_root() -> Path:
    """プラグインのルートディレクトリを解決する。

    `CLAUDE_PLUGIN_ROOT` があればそのディレクトリ、無ければこのファイルの 2 階層上
    （`plugin/`）を使う。呼び出しごとに評価し、import 時に固定しない。
    """
    root = os.environ.get(_ENV_PLUGIN_ROOT)
    if root:
        return Path(root)
    return Path(__file__).resolve().parent.parent


def get_plugin_version() -> Optional[str]:
    """`${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json` の `version` を読む。

    読めない・壊れている・`version` が文字列でない場合は None を返す。例外は外に出さない。
    """
    path = _plugin_root().joinpath(*_PLUGIN_JSON_RELATIVE)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    version = data.get("version")
    return version if isinstance(version, str) else None
