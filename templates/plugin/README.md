# プラグインの雛形

BMSD 本部以外の部署が、自部署の Claude Code プラグインを作るための雛形である。
`governance` プラグイン固有の内容は含まない。

## 使い方

1. `templates/plugin/` ごと自分の作業領域へコピーし、ディレクトリ名をプラグイン名に変える
2. `.claude-plugin/plugin.json` の `name`・`description`・`author` を書き換える
3. `skills/example/` を実際のスキルに差し替える（ディレクトリ名・`SKILL.md` の
   `name`・`description`・本文）。複数のスキルを持たせる場合は `skills/` 配下に
   ディレクトリを増やす
4. `claude plugin validate . --strict` が通ることを確認する
5. 自分のマーケットプレイスの `plugins/` に差し込み、`marketplace.json` に登録する

## この雛形が検証されていること

このリポジトリの `scripts/validate.py` は、`templates/plugin/` も他の収録プラグインと
同じ検査（`claude plugin validate --strict` への委譲、標準ライブラリ以外の import が
無いこと、hook の終了コード、`.gitignore` に飲まれた配布物の欠落）にかける。
雛形として配る内容が実際に検証を通ることを、このリポジトリ自身の CI で保証する。
