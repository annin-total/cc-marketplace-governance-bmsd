#!/usr/bin/env python3
"""validate.py — 配布用マーケットプレイスの検証。

マニフェストの形式検証（`marketplace.json` / `plugin.json` の構文・必須項目・
未知フィールド）は `claude plugin validate --strict` に委譲する。このスクリプトが
自前で見るのは、上流が見ない項目だけである。

- 標準ライブラリ以外の import（プラグインは pip install を要求できない）
- hook の終了コード（隔離環境で実行し、exit 0・無出力を確かめる）
- .gitignore に飲まれた配布物の欠落（配布に必要なファイルが git 管理外になっていないか）

使い方: python scripts/validate.py [リポジトリのルート]（既定: カレントディレクトリ）
        python3 でも python でも起動できる。標準ライブラリだけで動く。
"""

import ast
import json
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path
from shutil import which

FAIL = False

HOOK_TIMEOUT_SECONDS = 5
ISOLATED_USER_EMAIL = "validate-py@example.invalid"


def ok(message: str) -> None:
    """検証通過を1行で報告する。"""
    print(f"[OK] {message}")


def ng(message: str) -> None:
    """検証失敗を1行で報告し、全体の失敗フラグを立てる。"""
    global FAIL
    print(f"[NG] {message}")
    FAIL = True


def skip(message: str) -> None:
    """検証をスキップしたことを1行で報告する。"""
    print(f"[SKIP] {message}")


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


def _walk_hook_commands(node: object, out: list) -> None:
    """hooks.json のツリーから command 文字列を再帰的に集める。"""
    if isinstance(node, dict):
        cmd = node.get("command")
        if isinstance(cmd, str):
            out.append(cmd)
        for v in node.values():
            _walk_hook_commands(v, out)
    elif isinstance(node, list):
        for v in node:
            _walk_hook_commands(v, out)


# --- 標準ライブラリ以外の import が無い（pip install を要求しない）---
def check_stdlib_only(name: str, source_dir: Path) -> None:
    stdlib_names = getattr(sys, "stdlib_module_names", None)
    if stdlib_names is None:
        skip(f"'{name}': 標準ライブラリ判定はこの python では行えない（3.10 未満）")
        return

    py_files = list(source_dir.rglob("*.py"))
    local_modules = {f.stem for f in py_files}

    failed = False
    for f in py_files:
        try:
            with f.open(encoding="utf-8") as fh:
                tree = ast.parse(fh.read(), filename=str(f))
        except (OSError, SyntaxError):
            continue

        bad_names: list = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    bad_names.append(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.level and node.level > 0:
                    continue  # 相対importは常にローカル
                if node.module:
                    bad_names.append(node.module.split(".")[0])

        for module_name in bad_names:
            if module_name in stdlib_names or module_name in local_modules:
                continue
            ng(f"'{name}': 標準ライブラリ外の import: {module_name} ({f})")
            failed = True

    if not failed:
        ok(f"'{name}': すべての *.py が標準ライブラリ（と自モジュール）だけで動く")


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


def _settings_hash(settings_path: Path) -> str:
    """実 settings.json のハッシュを求める。無ければ MISSING を返す。"""
    import hashlib

    if not settings_path.is_file():
        return "MISSING"
    digest = hashlib.sha1()
    with settings_path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _expand_plugin_root(command: str, plugin_dir: Path) -> str:
    """${CLAUDE_PLUGIN_ROOT} をプラグインの実パスに展開する。"""
    return command.replace("${CLAUDE_PLUGIN_ROOT}", str(plugin_dir))


def _rmtree(path: Path) -> None:
    """一時ディレクトリを後始末する。"""
    import shutil

    shutil.rmtree(path, ignore_errors=True)


# --- hook が常に exit 0 で終わり、標準エラーに何も出さない（隔離実行）---
# 利用者の実ファイルに触れうる唯一の検査なので、実行前後で実 settings.json の
# ハッシュを比較する安全網を持つ。
def check_hook_execution(name: str, hooks_json: Path, plugin_dir: Path) -> None:
    try:
        with hooks_json.open(encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        ng(f"'{name}': hooks.json のパースに失敗: {hooks_json}")
        return

    commands: list = []
    _walk_hook_commands(data, commands)

    real_settings = Path.home() / ".claude" / "settings.json"
    hash_before = _settings_hash(real_settings)

    isolation_dir = tempfile.mkdtemp(prefix="cc-marketplace-validate-")
    try:
        isolated_plugin_data = Path(isolation_dir) / "plugin-data"
        isolated_config_dir = Path(isolation_dir) / "config-dir"
        isolated_plugin_data.mkdir(parents=True, exist_ok=True)
        isolated_config_dir.mkdir(parents=True, exist_ok=True)

        env = os.environ.copy()
        env["CLAUDE_PLUGIN_ROOT"] = str(plugin_dir)
        env["CLAUDE_PLUGIN_DATA"] = str(isolated_plugin_data)
        env["CLAUDE_CONFIG_DIR"] = str(isolated_config_dir)
        env["CC_GOVERNANCE_USER_EMAIL"] = ISOLATED_USER_EMAIL
        # 無効化スイッチは立てない。立てると hook が冒頭で return し、
        # 実際の収集経路を一度も通らないまま「exit 0 だった」と判定してしまう。
        env.pop("CC_GOVERNANCE_DISABLE", None)
        env["PYTHONDONTWRITEBYTECODE"] = "1"

        failed = False
        for cmd in commands:
            expanded = _expand_plugin_root(cmd, Path(plugin_dir.as_posix()))
            argv = shlex.split(expanded, posix=True)
            try:
                result = subprocess.run(
                    argv,
                    input="{}",
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    env=env,
                    timeout=HOOK_TIMEOUT_SECONDS,
                    check=False,
                )
                rc = result.returncode
                stderr_content = result.stderr
            except subprocess.TimeoutExpired:
                rc = -1
                stderr_content = "(timeout)"
            except OSError as exc:
                rc = -1
                stderr_content = str(exc)

            if rc != 0 or stderr_content:
                ng(f"'{name}': hook が exit 0・無出力で終わらない（rc={rc}）: {cmd}")
                failed = True

        if not failed:
            ok(f"'{name}': すべての hook が exit 0 で終わり、標準エラーに何も出さない")
    finally:
        _rmtree(Path(isolation_dir))

    hash_after = _settings_hash(real_settings)
    if hash_before == hash_after:
        ok(f"'{name}': 実 ~/.claude/settings.json は変更されていない（隔離が効いている）")
    else:
        ng(f"'{name}': 実 ~/.claude/settings.json が変更された（隔離が効いていない・重大）")


def _validate_plugin_entry(repo_root: Path, name: str, source: str) -> None:
    """1件の plugins 要素（上流委譲 + 自作の3検査）を検証する。"""
    if not name or not source:
        ng(f"plugins 要素の name/source が不足（name={name!r}, source={source!r}）")
        return

    relative_source = source.removeprefix("./")
    source_dir = repo_root / relative_source
    if not source_dir.is_dir():
        ng(f"'{name}' の source ディレクトリが存在しない: {source_dir}")
        return

    check_manifest(f"'{name}'", source_dir)
    check_stdlib_only(name, source_dir)
    check_no_gitignored_files(name, repo_root, relative_source)

    hooks_json = source_dir / "hooks" / "hooks.json"
    if hooks_json.is_file():
        check_hook_execution(name, hooks_json, source_dir)
    else:
        skip(f"'{name}': hook 実行検査: hooks/hooks.json が無い")


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
