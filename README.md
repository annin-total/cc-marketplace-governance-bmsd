# cc-marketplace-governance-bmsd

BMSD が配布する Claude Code プラグインのマーケットプレイス

## 収録プラグイン

| プラグイン | 内容 |
| --- | --- |
| `governance` | BMSD 本部向けの利用状況収集とポリシー適用を行う端末プラグイン |

## 導入

Claude Code で次を実行する。

```
/plugin marketplace add <このリポジトリの URL>
/plugin install governance@cc-marketplace-governance-bmsd
```

`/plugin` の一覧に `governance` が版番号つきで現れれば導入は完了している。最初のセッション開始時に、設定の適用とお知らせの表示が働く。

新しい版が届かないときは、次の 2 段階を両方行う。1 段目はカタログを更新するだけで、プラグイン本体の版は上がらない。

```
claude plugin marketplace update cc-marketplace-governance-bmsd
claude plugin update governance
```

## 構成

```
.claude-plugin/marketplace.json   # マーケットプレイスの名前と収録プラグインの一覧
plugins/governance/               # 配布するプラグイン。このリポジトリでは編集しない
templates/plugin/                 # プラグインの雛形
scripts/validate.py               # 収録プラグインと雛形の検証（python scripts/validate.py）
```

## プラグインの雛形

`templates/plugin/` は、BMSD 以外の部署が自部署の Claude Code プラグインを作るときの出発点である。`plugin.json` とサンプルスキル 1 件だけの最小構成で、`governance` 固有の内容は含まない。使い方は `templates/plugin/README.md` にある。

## 検査

```bash
claude plugin validate --strict .
claude plugin validate --strict plugins/governance
python scripts/validate.py
```

`scripts/validate.py` は上の 2 つに加えて、`plugins/governance/config.json` の `ingest_url` と `ingest_token` が空でないことを確かめる。
