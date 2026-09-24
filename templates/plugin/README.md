# プラグインの雛形

自部署の Claude Code プラグインを作るための雛形である。

## 使い方

1. このディレクトリごと自分の作業領域へコピーし、ディレクトリ名をプラグイン名に変える
2. `.claude-plugin/plugin.json` の `name`・`description`・`author` を書き換える
3. `skills/example/` を実際のスキルに差し替える（ディレクトリ名・`SKILL.md` の
   `name`・`description`・本文）。スキルを増やすときは `skills/` 配下にディレクトリを足す
4. `claude plugin validate . --strict` が通ることを確認する
5. 自分のマーケットプレイスの `plugins/` に置き、`marketplace.json` に登録する
