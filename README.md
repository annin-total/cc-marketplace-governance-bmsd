# cc-marketplace-governance-bmsd

BMSD 本部が配布する Claude Code マーケットプレイスの実体である。**配布専用のリポジトリであり、開発の履歴は持たない。**

## このリポジトリの役割

- `.claude-plugin/marketplace.json` に、収録するプラグイン（`governance` 1 件）を定義する
- `plugins/governance/` に、配布するプラグイン本体を置く

## `plugins/governance/` は手で編集しない

`plugins/governance/` は、開発リポジトリ（`cc-governance-bmsd`）の `governance/` を差し込んだ結果である。**このリポジトリで直接編集しない。** 変更は必ず開発リポジトリの `governance/` に対して行い、リリース手順に従って差し込む。

## リリース手順

リリースの手順は開発リポジトリ側にある。`cc-governance-bmsd/docs/release.md` を参照する。差し込んだら PR を作る前に、このリポジトリで `scripts/validate.sh` を実行し、`[NG]` が無いことを確認する。
