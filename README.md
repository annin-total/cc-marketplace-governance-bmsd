# cc-marketplace-governance-bmsd

BMSD 本部が配布する Claude Code マーケットプレイスの実体である。**配布専用のリポジトリで
あり、開発の履歴は持たない。** 収録するプラグインの開発は `cc-governance-bmsd` リポジトリ
（`plugin/`）で行い、完成したものをこのリポジトリへ差し込む。

## リポジトリの分離

| リポジトリ | 役割 |
| --- | --- |
| `cc-governance-bmsd` | 開発リポジトリ。プラグイン本体（`plugin/`）とサーバを同居させ、収集項目の契約を 1 か所で共有する |
| `cc-marketplace-governance-bmsd`（このリポジトリ） | 配布用マーケットプレイス。完成したプラグインを差し込む箱であり、開発中のコミットは入れない |

マーケットプレイスは全利用者の端末が直接 clone する先である。そこに開発の履歴（作業中の
コミット・サーバのソース・実験ブランチ）を混ぜないため、配布経路にはこのリポジトリの内容
だけを置く。

## 構造

```
cc-marketplace-governance-bmsd/
  .claude-plugin/marketplace.json
  plugins/
    governance/             # 開発リポジトリの plugin/ を差し込んだ結果
      .claude-plugin/plugin.json
      hooks/
      notices.json
      config.json
  templates/plugin/          # プラグインの雛形（他部署が自分のプラグインを作るための実体）
    .claude-plugin/plugin.json
    skills/example/SKILL.md
    README.md
  scripts/validate.py        # 収録プラグイン・雛形の検証
```

`.claude-plugin/marketplace.json` は、マーケットプレイス自体の名前と所有者、そして収録
プラグインの一覧を持つ。

```json
{
  "name": "cc-marketplace-governance-bmsd",
  "owner": { "name": "<管理チーム名>", "email": "<連絡先>" },
  "plugins": [
    {
      "name": "governance",
      "source": "./plugins/governance",
      "description": "Claude Code のガバナンス設定の適用・お知らせ配信・利用状況の収集"
    }
  ]
}
```

## `plugins/governance/` は手で編集しない

`plugins/governance/` は、開発リポジトリ `cc-governance-bmsd` の `plugin/` を差し込んだ
結果である。**このリポジトリで直接編集しない。** 変更は必ず開発リポジトリの `plugin/` に
対して行い、リリース手順に従って差し込む。

## `templates/plugin/` はプラグインの雛形である

BMSD 本部以外の部署が、自部署の Claude Code プラグインを作るときの出発点である。
`governance` プラグイン固有の内容は含まない、最小構成のプラグイン（`plugin.json` と
サンプルスキル 1 件）である。使い方は `templates/plugin/README.md` を参照する。

`plugins/governance/` とは異なり、これは複製ではなく実体そのものである。
`scripts/validate.py` が検証にかけるため、雛形として配る内容が壊れたまま残ることはない。

## リリース手順

リリースの手順は開発リポジトリ側にある。`cc-governance-bmsd/docs/release.md` を参照する。
概要は次のとおりである。

1. 開発リポジトリで変更をマージし、`plugin/.claude-plugin/plugin.json` の `version` を
   上げる
2. 開発リポジトリの `plugin/` を、このリポジトリの `plugins/governance/` へ差し込む
   （フォルダの内容をそのまま置き換える）
3. このリポジトリで `python scripts/validate.py` を実行し、`[NG]` が無いことを確認する
4. このリポジトリで PR を作り、マージする。マージされた時点で配布される

`scripts/validate.py` は、マニフェストとしての形式検証（`marketplace.json` /
`plugin.json` の構文・必須項目・未知フィールド）を `claude plugin validate --strict`
に委譲する。このスクリプト自身が見るのは、上流が見ない項目だけである。

- 標準ライブラリ以外の import が無いこと（プラグインは pip install を要求できない）
- hook が隔離環境で exit 0・無出力で終わること
- `.gitignore` に飲まれて配布物が欠落していないこと

`templates/plugin/` も収録プラグインと同じ検査にかける。`plugin.json` の `version`
が上がっているか、`POLICY` からキーが削除されていないかは検証しない。これらは開発
リポジトリ側の確認項目である。

## 利用者への導入手順

```
/plugin marketplace add <配布用リポジトリの URL>
/plugin install governance@cc-marketplace-governance-bmsd
```

導入後、最初の `SessionStart` で設定の適用とお知らせの表示が働く。導入できたことは
`/plugin` の一覧に版番号つきで現れることで確認する。設定ファイルに記載があるだけでは
導入が完了しないことがある。

## 更新の伝播

社外のマーケットプレイスは、自動更新が既定で無効である。有効になっているかどうかは
利用者の `settings.json` の `extraKnownMarketplaces` エントリの `autoUpdate` で決まり、
プラグイン自身がセッションごとに強制設定する。

更新は即時ではない。push してから端末が取り込むまでに遅れがあり、反映されるのは次に
起動したセッションからである。手動で更新するときは 2 段階である。
`claude plugin marketplace update <名前>` がカタログを更新し、
`claude plugin update <プラグイン名>` が本体の版を上げる。
