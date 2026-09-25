---
name: reapply
description: 標準設定を settings.json に今すぐ適用し直す。1 回だけ配る設定（ステータスラインなど）も初期状態に戻す。
disable-model-invocation: true
---

# 標準設定の再適用

次のコマンドを 1 回だけ実行する。ほかのコマンドは実行しない。

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/reapply.py"
```

出力は 1 行に 1 項目で、`<結果>` と `<項目>` がタブで区切られている。これを次の表にまとめて利用者に見せる。
`<項目>` の `add:` / `remove:` / `once:` は操作の種類（付いていなければ値の上書き）を表す。

| 結果 | 利用者への説明 |
| --- | --- |
| `applied` | 書き込んだ |
| `already_ok` | 既に標準どおりだった |
| `skipped_missing` | 書き込み先の形が想定と違うため書かなかった |
| `skipped_conflict` | 同時に別の変更があったため書かなかった。もう一度実行すればよい |
| `parse_failed` | settings.json が JSON として読めないため何もしなかった |
| `write_failed` | 書き込めなかった |

最後に次の 2 点を添える。

- 書き込む直前の settings.json は `<config_dir>/governance/backups/` に保存されている（config_dir は通常 `~/.claude`）
- 設定によっては、反映に Claude Code の再起動が要る

コマンドが失敗した場合は、エラーの内容をそのまま見せ、`python3` が使えるかを確かめるよう伝える。
