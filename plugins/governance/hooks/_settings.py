"""settings.json へのポリシー値の強制適用。標準ライブラリのみで動く。

読み取り・`.` 区切りパスの解決・mtime 検査・原子的置換・適用結果の返却をこの 1 ファイルに閉じ込める。
キューにも契約の DB 定義にも触れない。受け取るのは設定ファイルのパスと POLICY、
返すのはキーごとの (key_name, value, prev_value, apply_result) の list だけ。
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Optional

from contract import coerce, dig

_VARCHAR_TYPE = "VARCHAR(255)"

Row = tuple[str, Optional[str], Optional[str], str]


def _load(path: Path):
    """設定ファイルを読む。('ok'/'missing'/'parse_failed', data, mtime_ns) の組で返す。

    存在しない場合は data={} として扱う。パース失敗・トップレベルが dict でない場合は
    data=None とし、例外は外に漏らさない。
    """
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return "missing", {}, None
    # 非 UTF-8 のバイト列を含むファイルでは strict デコードが UnicodeDecodeError を投げる。
    # これは OSError ではなく ValueError 派生であり、捕まえ損ねると SessionStart のたびに
    # 例外が漏れ、お知らせも policy イベントも到達しないままその端末が画面から消える。
    except (OSError, ValueError):
        return "parse_failed", None, None
    try:
        mtime_ns = path.stat().st_mtime_ns
    except OSError:
        return "parse_failed", None, None
    try:
        data = json.loads(text)
    # 深く入れ子になった JSON は RecursionError を投げる（ValueError 派生ではない）。
    except (ValueError, RecursionError):
        return "parse_failed", None, None
    if not isinstance(data, dict):
        return "parse_failed", None, None
    return "ok", data, mtime_ns


def _resolve(path: Path) -> Path:
    """シンボリックリンクなら実体を指すパスに解決する。

    `os.replace` はリンクそのものを置き換えるため、解決しないと dotfiles 管理下の端末で
    リンクが普通のファイルに化け、実体側は古い内容のまま取り残される。しかも結果は
    `applied` と記録されるため、壊れたことが画面からは分からない。
    """
    try:
        return path.resolve()
    except (OSError, RuntimeError):
        return path


def _equal_strict(a: Any, b: Any) -> bool:
    """型まで含めて一致するときだけ真。型が違えば値が等価でも一致とみなさない。"""
    return type(a) is type(b) and a == b


def _container_ok(data: dict, container_segments: list[str]) -> bool:
    """コンテナ段を書き込めるか判定する（作成はしない）。`env` の 1 段だけ、無くても可とする。"""
    cur: Any = data
    for i, seg in enumerate(container_segments):
        if isinstance(cur, dict) and seg in cur:
            nxt = cur[seg]
            if not isinstance(nxt, dict):
                return False
            cur = nxt
            continue
        return i == 0 and seg == "env" and len(container_segments) == 1
    return True


def _get_or_create_container(data: dict, container_segments: list[str]) -> dict:
    """コンテナ段をたどる。`_container_ok` で許可された経路のみ渡される前提で、無ければ作る。"""
    cur = data
    for seg in container_segments:
        if seg not in cur or not isinstance(cur[seg], dict):
            cur[seg] = {}
        cur = cur[seg]
    return cur


def _stat_mtime_ns(path: Path) -> Optional[int]:
    """mtime をナノ秒単位で返す。読めなければ None。"""
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return None


def _write(config_path: Path, data: dict, pending: list, expected_mtime_ns) -> str:
    """pending のキーだけ反映して原子的に置換する。'applied'/'skipped_conflict'/'write_failed' を返す。"""
    for entry in pending:
        container = _get_or_create_container(data, entry["segments"][:-1])
        container[entry["segments"][-1]] = entry["policy_value"]

    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            dir=str(config_path.parent), prefix=".settings-", suffix=".tmp"
        )
    except OSError:
        return "write_failed"

    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False, indent=2))
            f.write("\n")

        if _stat_mtime_ns(config_path) != expected_mtime_ns:
            os.remove(tmp_path)
            return "skipped_conflict"

        os.replace(tmp_path, config_path)
        return "applied"
    except OSError:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        return "write_failed"


def apply_settings(config_path, policy: dict) -> list[Row]:
    """POLICY のキーごとに現在値を調べ、差分があれば settings.json に強制適用する。

    例外は呼び出し元に漏らさない。書けたかどうかに関わらず value は常にポリシー値。
    """
    config_path = _resolve(Path(config_path))
    status, data, mtime_ns = _load(config_path)

    if status == "parse_failed":
        return [
            (key, coerce(value, _VARCHAR_TYPE), None, "parse_failed")
            for key, value in policy.items()
        ]

    plan = []
    for key_path, policy_value in policy.items():
        segments = key_path.split(".")
        prev_raw = dig(data, segments)
        entry = {
            "key": key_path,
            "segments": segments,
            "policy_value": policy_value,
            "value_repr": coerce(policy_value, _VARCHAR_TYPE),
            "prev_repr": coerce(prev_raw, _VARCHAR_TYPE),
        }
        if _equal_strict(prev_raw, policy_value):
            entry["result"] = "already_ok"
        elif _container_ok(data, segments[:-1]):
            entry["result"] = "pending"
        else:
            entry["result"] = "skipped_missing"
        plan.append(entry)

    pending = [e for e in plan if e["result"] == "pending"]
    if pending:
        write_status = _write(config_path, data, pending, mtime_ns)
        for e in pending:
            e["result"] = write_status

    return [(e["key"], e["value_repr"], e["prev_repr"], e["result"]) for e in plan]
