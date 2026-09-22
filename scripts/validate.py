#!/usr/bin/env python3
"""validate.py — 配布用マーケットプレイスの形式検証。

marketplace.json に列挙された plugins を「発見」して、それぞれの
プラグインディレクトリの形式だけを見る。プラグインの個数・名前は
一切決め打ちしない。中身（config.json の値、ファイル一覧、
契約のキーなど）や、開発リポジトリとの差分比較も検証しない。
仕様やプラグインの増減があってもこのスクリプトが壊れないための方針。

使い方: python scripts/validate.py [リポジトリのルート]（既定: カレントディレクトリ）
        python3 でも python でも起動できる。標準ライブラリだけで動く。
"""

import json
import re
import subprocess
import sys
from pathlib import Path

FAIL = False

DEV_ARTIFACT_NAMES = frozenset(
    {
        "__pycache__",
        ".pytest_cache",
        "conftest.py",
        ".git",
    }
)
DEV_ARTIFACT_PATTERNS = (re.compile(r"^test_.*\.py$"), re.compile(r".*_test\.py$"))


def ok(message: str) -> None:
    """検証通過を1行で報告する。"""
    print(f"[OK] {message}")


def ng(message: str) -> None:
    """検証失敗を1行で報告し、全体の失敗フラグを立てる。"""
    global FAIL
    print(f"[NG] {message}")
    FAIL = True


def _is_dev_artifact(path: Path) -> bool:
    """開発用ファイル・ディレクトリの命名規則に一致するか判定する。"""
    name = path.name
    if name in DEV_ARTIFACT_NAMES:
        return True
    if name.endswith(".pyc"):
        return True
    return any(p.match(name) for p in DEV_ARTIFACT_PATTERNS)


# --- 4. source 配下の全 *.json がパースできる ---
def check_all_json_parse(name: str, source_dir: Path) -> None:
    failed = False
    for f in source_dir.rglob("*.json"):
        try:
            with f.open(encoding="utf-8") as fh:
                json.load(fh)
        except (OSError, ValueError):
            ng(f"'{name}': JSON パース失敗: {f}")
            failed = True
    if not failed:
        ok(f"'{name}': すべての *.json がパース可能")


# --- 5. 開発用ファイルの混入なし ---
def check_no_dev_artifacts(name: str, source_dir: Path) -> None:
    found = [p for p in source_dir.rglob("*") if _is_dev_artifact(p)]
    if found:
        for a in sorted(found):
            ng(f"'{name}': 開発用ファイル/ディレクトリが混入: {a}")
    else:
        ok(f"'{name}': 開発用ファイル・生成物の混入なし")


# --- 6. git に無視されているファイルが無い ---
def check_no_gitignored_files(name: str, repo_root: Path, relative_source: str) -> None:
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(repo_root),
                "ls-files",
                "--others",
                "--ignored",
                "--exclude-standard",
                "--",
                relative_source,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        ignored = [ln for ln in result.stdout.splitlines() if ln.strip()]
    except OSError:
        ignored = []

    if ignored:
        for i in ignored:
            ng(f"'{name}': git に無視されているファイルが存在: {i}")
    else:
        ok(f"'{name}': git に無視されているファイルは無い")


def _validate_plugin_entry(repo_root: Path, name: str, source: str) -> None:
    """1件の plugins 要素（source ディレクトリ・plugin.json・中身）を検証する。"""
    if not name:
        ng(f"plugins 要素に name が無い（source: {source}）")
        return
    if not source:
        ng(f"plugins 要素 '{name}' に source が無い")
        return

    relative_source = source.removeprefix("./")
    source_dir = repo_root / relative_source
    if not source_dir.is_dir():
        ng(f"'{name}' の source ディレクトリが存在しない: {source_dir}")
        return
    ok(f"'{name}': marketplace.json の name/source を確認、source ディレクトリが実在")

    # --- 3. source 直下の plugin.json: 存在・パース可否・name 一致・version 非空 ---
    plugin_json = source_dir / ".claude-plugin" / "plugin.json"
    if not plugin_json.is_file():
        ng(f"'{name}': plugin.json が存在しない: {plugin_json}")
    else:
        try:
            with plugin_json.open(encoding="utf-8") as f:
                data = json.load(f)
            valid = (
                data.get("name") == name
                and isinstance(data.get("version"), str)
                and data.get("version").strip()
            )
        except (OSError, ValueError):
            valid = False
        if valid:
            ok(f"'{name}': plugin.json の name が一致し version が非空")
        else:
            ng(f"'{name}': plugin.json のパース失敗、name 不一致、または version が空")

    check_all_json_parse(name, source_dir)
    check_no_dev_artifacts(name, source_dir)
    check_no_gitignored_files(name, repo_root, relative_source)


def main(argv: list) -> int:
    repo_root = Path(argv[1]).resolve() if len(argv) > 1 else Path.cwd().resolve()
    marketplace_json = repo_root / ".claude-plugin" / "marketplace.json"

    # --- 1. marketplace.json の存在・パース可否・plugins が配列 ---
    if not marketplace_json.is_file():
        ng(f"marketplace.json が存在しない: {marketplace_json}")
        print("=== 検証に失敗した項目がある ===")
        return 1

    try:
        with marketplace_json.open(encoding="utf-8") as f:
            data = json.load(f)
        plugins = data.get("plugins")
    except (OSError, ValueError):
        plugins = None
    if not isinstance(plugins, list):
        ng("marketplace.json のパース失敗、または plugins が配列でない")
        print("=== 検証に失敗した項目がある ===")
        return 1
    ok("marketplace.json: パース可能かつ plugins は配列")

    # --- 2. 各 plugins 要素の name/source、source ディレクトリの実在 ---
    if not plugins:
        ng("marketplace.json の plugins が空")
    for entry in plugins:
        name = entry.get("name", "") if isinstance(entry, dict) else ""
        source = entry.get("source", "") if isinstance(entry, dict) else ""
        _validate_plugin_entry(repo_root, name, source)

    if FAIL:
        print("=== 検証に失敗した項目がある ===")
        return 1
    print("=== すべての検証に合格 ===")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
