"""`policy.py` の書き方の見本。hook はこのファイルを読まない。

`policy.py` へ写すときは、各項目の上に「なぜ配るか」を書く。
値の文字列中の `${GOVERNANCE_HOME}` は、書き込み時に `<config_dir>/governance` の絶対パスになる。
"""

from typing import Any

SET: dict[str, Any] = {
    # スカラ
    "model": "opus",
    "effortLevel": "high",
    # 入れ子（途中の dict は無ければ作る）
    "env.DISABLE_TELEMETRY": "1",
    "modelSettings.claude-opus-5.effortLevel": "high",
    # dict 値（丸ごと置き換える）
    "attribution": {"commit": "", "pr": ""},
    # list 値（丸ごと置き換える。足すだけなら ADD）
    "autoMode.environment": ["$defaults", "社内の開発端末"],
    # None（キーを消す）
    "apiKeyHelper": None,
    # 既存のマーケットプレイスにだけ書く（extraKnownMarketplaces の下は作らない）
    "extraKnownMarketplaces.cc-marketplace-governance-bmsd.autoUpdate": True,
}

ADD: dict[str, list] = {
    # 権限ルール（配列に無いものだけ足す）
    "permissions.deny": ["Read(./.env)", "Read(./.env.*)", "Read(./secrets/**)"],
    "permissions.allow": ["Bash(git status)", "Bash(git diff:*)"],
    "permissions.ask": ["Bash(git push:*)"],
    # auto mode の分類器ルール
    "autoMode.soft_deny": ["$defaults", "本番環境への書き込み"],
}

REMOVE: dict[str, list] = {
    # 配っていたルールを撤回する（配列にあるものだけ消す）
    "permissions.allow": ["Bash(curl:*)"],
}

ONCE: dict[str, Any] = {
    # 初回だけ書き、以後は利用者の変更を尊重する。値を変えて配ると再度 1 回だけ書く
    "statusLine": {
        "type": "command",
        "command": 'node "${GOVERNANCE_HOME}/statusline.js"',
    },
}
