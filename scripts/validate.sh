#!/usr/bin/env bash
# validate.sh — 配布用マーケットプレイスの形式検証。
#
# marketplace.json に列挙された plugins を「発見」して、それぞれの
# プラグインディレクトリの形式だけを見る。プラグインの個数・名前は
# 一切決め打ちしない。中身（config.json の値、ファイル一覧、
# 契約のキーなど）や、開発リポジトリとの差分比較も検証しない。
# 仕様やプラグインの増減があってもこのスクリプトが壊れないための方針。
#
# 使い方: scripts/validate.sh [リポジトリのルート]（既定: カレントディレクトリ）

set -u
export PYTHONDONTWRITEBYTECODE=1

REPO_ROOT="${1:-$(pwd)}"
REPO_ROOT="$(cd "$REPO_ROOT" && pwd)"
MARKETPLACE_JSON="$REPO_ROOT/.claude-plugin/marketplace.json"

FAIL=0
ok()  { echo "[OK] $1"; }
ng()  { echo "[NG] $1"; FAIL=1; }

# --- 1. marketplace.json の存在・パース可否・plugins が配列 ---
if [ ! -f "$MARKETPLACE_JSON" ]; then
  ng "marketplace.json が存在しない: $MARKETPLACE_JSON"
  echo "=== 検証に失敗した項目がある ==="
  exit 1
fi

if ! python3 -c "
import json, sys
data = json.load(open(sys.argv[1], encoding='utf-8'))
sys.exit(0 if isinstance(data.get('plugins'), list) else 1)
" "$MARKETPLACE_JSON" 2>/dev/null; then
  ng "marketplace.json のパース失敗、または plugins が配列でない"
  echo "=== 検証に失敗した項目がある ==="
  exit 1
fi
ok "marketplace.json: パース可能かつ plugins は配列"

# --- 2. 各 plugins 要素の name/source、source ディレクトリの実在 ---
# name\tsource の形式で1件1行、タブ区切りで取り出す（発見的に処理する）
ENTRIES=$(python3 -c "
import json, sys
data = json.load(open(sys.argv[1], encoding='utf-8'))
for p in data.get('plugins', []):
    name = p.get('name', '')
    source = p.get('source', '')
    print(f'{name}\t{source}')
" "$MARKETPLACE_JSON")

if [ -z "$ENTRIES" ]; then
  ng "marketplace.json の plugins が空"
fi

while IFS=$'\t' read -r NAME SOURCE; do
  [ -z "$NAME" ] && [ -z "$SOURCE" ] && continue

  if [ -z "$NAME" ]; then
    ng "plugins 要素に name が無い（source: ${SOURCE}）"
    continue
  fi
  if [ -z "$SOURCE" ]; then
    ng "plugins 要素 '$NAME' に source が無い"
    continue
  fi

  SOURCE_DIR="$REPO_ROOT/${SOURCE#./}"
  if [ ! -d "$SOURCE_DIR" ]; then
    ng "'$NAME' の source ディレクトリが存在しない: $SOURCE_DIR"
    continue
  fi
  ok "'$NAME': marketplace.json の name/source を確認、source ディレクトリが実在"

  # --- 3. source 直下の plugin.json: 存在・パース可否・name 一致・version 非空 ---
  PLUGIN_JSON="$SOURCE_DIR/.claude-plugin/plugin.json"
  if [ ! -f "$PLUGIN_JSON" ]; then
    ng "'$NAME': plugin.json が存在しない: $PLUGIN_JSON"
  elif python3 -c "
import json, sys
data = json.load(open(sys.argv[1], encoding='utf-8'))
name = data.get('name')
version = data.get('version')
ok = name == sys.argv[2] and isinstance(version, str) and version.strip()
sys.exit(0 if ok else 1)
" "$PLUGIN_JSON" "$NAME" 2>/dev/null; then
    ok "'$NAME': plugin.json の name が一致し version が非空"
  else
    ng "'$NAME': plugin.json のパース失敗、name 不一致、または version が空"
  fi

  # --- 4. source 配下の全 *.json がパースできる ---
  JSON_FAIL=0
  while IFS= read -r -d '' f; do
    if ! python3 -c "import json,sys; json.load(open(sys.argv[1], encoding='utf-8'))" "$f" "$f" 2>/dev/null; then
      ng "'$NAME': JSON パース失敗: $f"
      JSON_FAIL=1
    fi
  done < <(find "$SOURCE_DIR" -name '*.json' -print0)
  [ "$JSON_FAIL" -eq 0 ] && ok "'$NAME': すべての *.json がパース可能"

  # --- 5. 開発用ファイルの混入なし ---
  DEV_ARTIFACTS=$(find "$SOURCE_DIR" \( \
    -name '__pycache__' -o \
    -name '*.pyc' -o \
    -name '.pytest_cache' -o \
    -name 'conftest.py' -o \
    -name 'test_*.py' -o \
    -name '*_test.py' -o \
    -name '.git' \
    \))
  if [ -n "$DEV_ARTIFACTS" ]; then
    while IFS= read -r a; do
      ng "'$NAME': 開発用ファイル/ディレクトリが混入: $a"
    done <<< "$DEV_ARTIFACTS"
  else
    ok "'$NAME': 開発用ファイル・生成物の混入なし"
  fi

  # --- 6. git に無視されているファイルが無い ---
  RELATIVE_SOURCE="${SOURCE#./}"
  IGNORED=$(git -C "$REPO_ROOT" ls-files --others --ignored --exclude-standard -- "$RELATIVE_SOURCE")
  if [ -n "$IGNORED" ]; then
    while IFS= read -r i; do
      ng "'$NAME': git に無視されているファイルが存在: $i"
    done <<< "$IGNORED"
  else
    ok "'$NAME': git に無視されているファイルは無い"
  fi
done <<< "$ENTRIES"

if [ "$FAIL" -eq 0 ]; then
  echo "=== すべての検証に合格 ==="
  exit 0
else
  echo "=== 検証に失敗した項目がある ==="
  exit 1
fi
