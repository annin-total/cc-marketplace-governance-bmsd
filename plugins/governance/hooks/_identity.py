"""識別子（user_email / host / event_id）とプラグインの版の解決。"""

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

# hook 全体の timeout（hooks.json の 5 秒）より短くする。
_GIT_TIMEOUT_SEC = 3


def _identity_path() -> Path:
    return _state_dir() / "identity.json"


def _load_cache() -> Optional[dict]:
    """`identity.json` を読む。無い・壊れていれば None。"""
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
    """`user_email` の解決結果を `identity.json` に書く。失敗は無視する。"""
    path = _identity_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"user_email": user_email}, f)
    except OSError:
        pass


def _resolve_via_git() -> Optional[str]:
    """`git config --global user.email` を小文字化して返す。取れなければ None。"""
    try:
        proc = subprocess.run(
            ["git", "config", "--global", "user.email"],
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_SEC,
            check=False,
        )
    # git が非 UTF-8 を返すと UnicodeDecodeError（ValueError 派生、OSError ではない）になる。
    # 捕まえ損ねると収集が恒久的に無言で止まる。
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    value = proc.stdout.strip()
    if not value:
        return None
    return value.lower()


def get_user_email(refresh: bool = False) -> Optional[str]:
    """環境変数 → キャッシュ → git の順で user_email を解決する。

    解決できなかった結果（None）もキャッシュする。`refresh` ならキャッシュを読まずに解決し直す。
    """
    env_value = os.environ.get(_ENV_USER_EMAIL)
    if env_value:
        email = env_value.lower()
        _save_cache(email)
        return email

    if not refresh:
        cache = _load_cache()
        if cache is not None and "user_email" in cache:
            return cache["user_email"]

    email = _resolve_via_git()
    _save_cache(email)
    return email


def get_host() -> str:
    return platform.node()


def new_event_id() -> str:
    return str(uuid.uuid4())


def _plugin_root() -> Path:
    """`CLAUDE_PLUGIN_ROOT`、無ければこのファイルの 2 階層上。毎回評価する。"""
    root = os.environ.get(_ENV_PLUGIN_ROOT)
    if root:
        return Path(root)
    return Path(__file__).resolve().parent.parent


def get_plugin_version() -> Optional[str]:
    """`plugin.json` の `version`。読めない・文字列でなければ None。"""
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
