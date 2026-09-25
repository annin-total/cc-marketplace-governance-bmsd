"""`/governance:reapply` のエントリ。ONCE の適用済みの記録を消し、標準設定を今すぐ適用し直す。

hook ではないので例外は隠さない。結果はキーごとに `<apply_result>\t<key_name>` を 1 行ずつ出す。
policy イベントは積まない（次の SessionStart がその時点の状態を記録する）。
"""

import sys

import _govdir
import policy
from _settings import apply_settings


def main() -> None:
    """statusline.js を同期し、ONCE の記録を消してから全体を適用する。"""
    sys.stdout.reconfigure(encoding="utf-8")
    gov_dir = _govdir.governance_dir()
    _govdir.sync_statusline(gov_dir)
    _govdir.clear_once(gov_dir)
    rows = apply_settings(_govdir.settings_path(), policy, gov_dir)
    for key_name, _value, _prev, apply_result in rows:
        print(f"{apply_result}\t{key_name}")


if __name__ == "__main__":
    main()
