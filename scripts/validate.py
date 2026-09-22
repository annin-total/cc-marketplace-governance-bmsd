#!/usr/bin/env python3
"""validate.py — 配布用マーケットプレイスの検証。

マニフェストの形式検証（`marketplace.json` / `plugin.json` の構文・必須項目・
未知フィールド）は `claude plugin validate --strict` に委譲する。

このスクリプトが自前で見るのは、配布リポジトリ固有の関心事である
「.gitignore に飲まれた配布物の欠落」だけである。標準ライブラリ以外の
import・hook の終了コードは、差し込み前に開発リポジトリの
`scripts/validate_plugin.py` が見る。配布物はその複製なので、開発側で
通っていれば配布側でも通っている。二重に検査しない。

使い方: python scripts/validate.py [リポジトリのルート]（既定: カレントディレクトリ）
        python3 でも python でも起動できる。標準ライブラリだけで動く。
"""

import json
import subprocess
import sys
from pathlib import Path
from shutil import which

FAIL = False


def ok(message: str) -> None:
    """検証通過を1行で報告する。"""
    print(f"[OK] {message}")


def ng(message: str) -> None:
    """検証失敗を1行で報告し、全体の失敗フラグを立てる。"""
    global FAIL
    print(f"[NG] {message}")
    FAIL = True


# --- マニフェストの形式検証は上流に委譲する ---
def check_manifest(label: str, target: Path) -> None:
    claude = which("claude")
    if claude is None:
        ng(f"{label}: claude コマンドが見つからない（PATH を確認する）")
        return
    result = subprocess.run(
        [claude, "plugin", "validate", str(target), "--strict"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode == 0:
        ok(f"{label}: claude plugin validate --strict に合格")
    else:
        ng(f"{label}: claude plugin validate --strict に失敗")
        detail = (result.stdout + result.stderr).strip()
        if detail:
            print(detail)


# --- .gitignore に飲まれた配布物の欠落が無い ---
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
    """1件のプラグイン（上流への委譲 + gitignore 検査）を検証する。"""
    if not name or not source:
        ng(f"plugins 要素の name/source が不足（name={name!r}, source={source!r}）")
        return

    relative_source = source.removeprefix("./")
    source_dir = repo_root / relative_source
    if not source_dir.is_dir():
        ng(f"'{name}' の source ディレクトリが存在しない: {source_dir}")
        return

    check_manifest(f"'{name}'", source_dir)
    check_no_gitignored_files(name, repo_root, relative_source)


def main(argv: list) -> int:
    repo_root = Path(argv[1]).resolve() if len(argv) > 1 else Path.cwd().resolve()
    marketplace_json = repo_root / ".claude-plugin" / "marketplace.json"

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
    if not isinstance(plugins, list) or not plugins:
        ng("marketplace.json のパース失敗、または plugins が空・配列でない")
        print("=== 検証に失敗した項目がある ===")
        return 1

    check_manifest("marketplace", repo_root)

    for entry in plugins:
        name = entry.get("name", "") if isinstance(entry, dict) else ""
        source = entry.get("source", "") if isinstance(entry, dict) else ""
        _validate_plugin_entry(repo_root, name, source)

    template_dir = repo_root / "templates" / "plugin"
    if template_dir.is_dir():
        _validate_plugin_entry(
            repo_root, "templates/plugin", str(template_dir.relative_to(repo_root))
        )

    if FAIL:
        print("=== 検証に失敗した項目がある ===")
        return 1
    print("=== すべての検証に合格 ===")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
