"""settings.json の dict へ SET / ADD / REMOVE / ONCE を当てる。ファイルには触れない。

結果の `result` は `pending`（書き換えた）/ `already_ok` / `skipped_missing`。
"""

import copy
import json
from typing import Any, Optional

from contract import coerce, policy_key_name, policy_text

PLACEHOLDER = "${GOVERNANCE_HOME}"

# この下には途中の dict を作らない。`source` の無いマーケットプレイスは無効な設定になる。
_NO_CREATE_UNDER = "extraKnownMarketplaces"


def _lookup(data: dict, segments: list) -> tuple:
    """パスをたどり (見つかったか, 値) を返す。JSON の null と「キーが無い」を区別する。"""
    cur: Any = data
    for seg in segments:
        if not isinstance(cur, dict) or seg not in cur:
            return False, None
        cur = cur[seg]
    return True, cur


def _container(data: dict, segments: list, create: bool) -> Optional[dict]:
    """途中の dict をたどり、`create` なら作る。書けなければ None。"""
    cur = data
    for seg in segments:
        if seg not in cur:
            if not create or segments[0] == _NO_CREATE_UNDER:
                return None
            cur[seg] = {}
        cur = cur[seg]
        if not isinstance(cur, dict):
            return None
    return cur


def _equal_strict(a: Any, b: Any) -> bool:
    """型まで含めて比べる（`1 == True` を一致とみなさない）。"""
    return type(a) is type(b) and a == b


def _contains(items: list, item: Any) -> bool:
    return any(_equal_strict(x, item) for x in items)


def _unique_new(items: list, existing: list) -> list:
    out: list = []
    for item in items:
        if not _contains(existing, item) and not _contains(out, item):
            out.append(item)
    return out


def _entry(op: str, path: str, value: Optional[str], prev: Any, result: str) -> dict:
    return {
        "key": policy_key_name(op, path),
        "value": value,
        "prev": coerce(prev, "VARCHAR(255)"),
        "result": result,
    }


def _put(data: dict, segments: list, value: Any) -> str:
    """1 キーを値で上書きする。None はキーを消す。"""
    found, prev = _lookup(data, segments)
    if value is None:
        if not found:
            return "already_ok"
        _container(data, segments[:-1], create=False).pop(segments[-1])
        return "pending"
    if found and _equal_strict(prev, value):
        return "already_ok"
    container = _container(data, segments[:-1], create=True)
    if container is None:
        return "skipped_missing"
    container[segments[-1]] = copy.deepcopy(value)
    return "pending"


def _set(data: dict, path: str, value: Any) -> dict:
    segments = path.split(".")
    prev = _lookup(data, segments)[1]
    result = _put(data, segments, value)
    return _entry("set", path, policy_text(value), prev, result)


def _add(data: dict, path: str, items: list) -> dict:
    segments = path.split(".")
    found, cur = _lookup(data, segments)
    if found and not isinstance(cur, list):
        return _entry("add", path, None, None, "skipped_missing")
    new = _unique_new(items, cur if found else [])
    if not new:
        return _entry("add", path, None, None, "already_ok")
    if found:
        cur.extend(copy.deepcopy(new))
    else:
        container = _container(data, segments[:-1], create=True)
        if container is None:
            return _entry("add", path, None, None, "skipped_missing")
        container[segments[-1]] = copy.deepcopy(new)
    return _entry("add", path, policy_text(new), None, "pending")


def _remove(data: dict, path: str, items: list) -> dict:
    found, cur = _lookup(data, path.split("."))
    if found and not isinstance(cur, list):
        return _entry("remove", path, None, None, "skipped_missing")
    removed = [x for x in _unique_new(items, []) if found and _contains(cur, x)]
    if not removed:
        return _entry("remove", path, None, None, "already_ok")
    cur[:] = [x for x in cur if not _contains(removed, x)]
    return _entry("remove", path, policy_text(removed), None, "pending")


def once_key(path: str, value: Any) -> str:
    """ONCE の適用済みの記録に使うキー。置換前の値で作る。"""
    return json.dumps([path, value], ensure_ascii=False, sort_keys=True)


def _substitute(value: Any, home: str) -> Any:
    if isinstance(value, str):
        return value.replace(PLACEHOLDER, home)
    if isinstance(value, dict):
        return {k: _substitute(v, home) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute(v, home) for v in value]
    return value


def _once(data: dict, path: str, value: Any, done: set, home: str) -> dict:
    segments = path.split(".")
    prev = _lookup(data, segments)[1]
    key = once_key(path, value)
    if key in done:
        result = "already_ok"
    else:
        result = _put(data, segments, _substitute(value, home))
    entry = _entry("once", path, policy_text(value), prev, result)
    entry["once_key"] = key
    return entry


def apply_ops(data: dict, policy: Any, done: set, home: str) -> list:
    """SET → ADD → REMOVE → ONCE の順に当てる。`done` は適用済みの ONCE のキー。"""
    entries = [_set(data, p, v) for p, v in policy.SET.items()]
    entries += [_add(data, p, items) for p, items in policy.ADD.items()]
    entries += [_remove(data, p, items) for p, items in policy.REMOVE.items()]
    entries += [_once(data, p, v, done, home) for p, v in policy.ONCE.items()]
    return entries


def unapplied(policy: Any, result: str) -> list:
    """設定ファイルを読めなかったときの結果。値は SET / ONCE だけ持つ。"""
    entries = [
        _entry("set", p, policy_text(v), None, result) for p, v in policy.SET.items()
    ]
    entries += [_entry("add", p, None, None, result) for p in policy.ADD]
    entries += [_entry("remove", p, None, None, result) for p in policy.REMOVE]
    entries += [
        _entry("once", p, policy_text(v), None, result) for p, v in policy.ONCE.items()
    ]
    return entries
