"""`<config_dir>/governance/` の管理。settings.json のバックアップ・ONCE の記録・statusline.js の同期。

config_dir は `CLAUDE_CONFIG_DIR`、無ければ `~/.claude`。ここに置くものはプラグインを
アンインストールしても残る（`CLAUDE_PLUGIN_DATA` と違い、利用者の設定から参照されうるため）。
"""

import datetime
import json
import os
from pathlib import Path

_CONFIG_DIR_ENV = "CLAUDE_CONFIG_DIR"
_SETTINGS_FILENAME = "settings.json"
_GOVERNANCE_DIRNAME = "governance"
_BACKUP_DIRNAME = "backups"
_BACKUP_KEEP = 10
# 本人だけが読める権限で作る。settings.json の env にはトークンが入りうる（Windows では無害）
_BACKUP_MODE = 0o600
_ONCE_FILENAME = "once.json"
_STATUSLINE_FILENAME = "statusline.js"
_STATUSLINE_SRC = (
    Path(__file__).resolve().parent.parent / "statusline" / _STATUSLINE_FILENAME
)


def config_dir() -> Path:
    """config_dir を解決する。呼び出しのたびに評価する（テストや隔離環境の差し替えを効かせる）。"""
    value = os.environ.get(_CONFIG_DIR_ENV)
    return Path(value) if value else Path.home() / ".claude"


def settings_path() -> Path:
    return config_dir() / _SETTINGS_FILENAME


def governance_dir() -> Path:
    return config_dir().absolute() / _GOVERNANCE_DIRNAME


def backup(settings: Path, gov_dir: Path) -> bool:
    """settings.json を丸ごと日時付きで保存し、直近 `_BACKUP_KEEP` 世代だけ残す。保存できれば真。

    時計の粒度が粗い OS でも名前が衝突しないよう連番を付け、既存のファイルは上書きしない（O_EXCL）。
    古い世代を消せなくても保存は済んでいるので真を返す。
    """
    backup_dir = gov_dir / _BACKUP_DIRNAME
    stamp = datetime.datetime.now().astimezone().strftime("%Y%m%d-%H%M%S-%f")
    try:
        content = settings.read_bytes()
        backup_dir.mkdir(parents=True, exist_ok=True)
        for n in range(_BACKUP_KEEP):
            try:
                name = backup_dir / f"settings-{stamp}-{n:02d}.json"
                fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, _BACKUP_MODE)
                with os.fdopen(fd, "wb") as f:
                    f.write(content)
                break
            except FileExistsError:
                continue
        else:
            return False
    except OSError:
        return False
    for old in sorted(backup_dir.glob("settings-*.json"))[:-_BACKUP_KEEP]:
        try:
            old.unlink()
        except OSError:
            pass
    return True


def load_once(gov_dir: Path) -> set:
    """適用済みの ONCE のキーを読む。読めなければ空（＝未適用として扱う）。"""
    try:
        data = json.loads((gov_dir / _ONCE_FILENAME).read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError):
        return set()
    return {k for k in data if isinstance(k, str)} if isinstance(data, list) else set()


def save_once(gov_dir: Path, keys: set) -> None:
    """適用済みの ONCE のキーを書く。失敗すると次のセッションで再適用される。"""
    try:
        gov_dir.mkdir(parents=True, exist_ok=True)
        text = json.dumps(sorted(keys), ensure_ascii=False, indent=2)
        (gov_dir / _ONCE_FILENAME).write_text(text + "\n", encoding="utf-8")
    except OSError:
        pass


def clear_once(gov_dir: Path) -> None:
    """ONCE の記録を消す。無ければ何もしない。"""
    try:
        (gov_dir / _ONCE_FILENAME).unlink()
    except FileNotFoundError:
        pass


def sync_statusline(gov_dir: Path, src: Path = _STATUSLINE_SRC) -> None:
    """同梱の statusline.js を内容が違うときだけ `gov_dir` へ複製する。失敗しても何もしない。

    一時ファイルから置き換えるのは、書きかけのファイルをステータスラインが実行しないため。
    """
    try:
        content = src.read_bytes()
        dst = gov_dir / _STATUSLINE_FILENAME
        if dst.is_file() and dst.read_bytes() == content:
            return
        gov_dir.mkdir(parents=True, exist_ok=True)
        tmp = gov_dir / f".{_STATUSLINE_FILENAME}.tmp"
        tmp.write_bytes(content)
        os.replace(tmp, dst)
    except OSError:
        pass
