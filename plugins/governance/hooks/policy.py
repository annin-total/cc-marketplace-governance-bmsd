"""端末の settings.json へ配る標準設定。変えたら plugin.json の version を上げてリリースする。

キーは settings.json 内の `.` 区切りのパス（途中の名前に `.` を含められない）。
各項目の上に、なぜ配るかをコメントで書く。書き方の見本は `policy_sample.py`、
操作の意味は `docs/spec/plugin.md` の「設定の自動適用」にある。
"""

from typing import Any

# 値で上書きする。dict・list も丸ごと置き換える。None はキーを消す
SET: dict[str, Any] = {
    # 自動圧縮を早めに走らせ、長い文脈のまま払うコストを抑える（/effect の効果測定の対象）
    "env.CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": "60",
    # このプラグインの更新を端末へ自動で届ける（社外のマーケットプレイスは既定で自動更新しない）
    "extraKnownMarketplaces.cc-marketplace-governance-bmsd.autoUpdate": True,
}

# 配列に無い要素だけ足す
ADD: dict[str, list] = {}

# 配列にある要素だけ消す
REMOVE: dict[str, list] = {}

# (パス, 値) の組ごとに 1 回だけ書く。以後は利用者が変えても戻さない
ONCE: dict[str, Any] = {}
