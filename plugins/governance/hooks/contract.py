"""端末プラグインとサーバが共有する契約の正本。標準ライブラリのみで動く。"""

from typing import Any, Optional

HOOK_FIELDS = (
    # (列名, キーパス, 型) の 3 つ組。行末の註記は届く hook であって要素ではない
    ("session_id", ("session_id",), "VARCHAR(255)"),  # 全 hook
    ("prompt_id", ("prompt_id",), "VARCHAR(255)"),  # 広範
    ("tool_name", ("tool_name",), "VARCHAR(255)"),  # PostToolUse / PostToolUseFailure
    ("source", ("source",), "VARCHAR(255)"),  # SessionStart
    ("compact_trigger", ("trigger",), "VARCHAR(255)"),  # PreCompact
    ("command_name", ("command_name",), "VARCHAR(255)"),  # UserPromptExpansion
    ("command_source", ("command_source",), "VARCHAR(255)"),  # UserPromptExpansion
    ("skill_name", ("tool_input", "skill"), "VARCHAR(255)"),  # PostToolUse
    (
        "effort_level",
        ("effort", "level"),
        "VARCHAR(255)",
    ),  # PostToolUse / Stop / PostToolUseFailure
    ("permission_mode", ("permission_mode",), "VARCHAR(255)"),  # 複数 hook
    ("agent_id", ("agent_id",), "VARCHAR(255)"),  # サブエージェントのツール呼出
    ("is_interrupt", ("is_interrupt",), "INTEGER"),  # PostToolUseFailure
)

EXTRA_COLUMNS = (
    # 端末側で組み立てる列。(列名, 型) の 2 つ組
    ("event_id", "VARCHAR(36)"),
    ("ts", "INTEGER"),
    ("day", "INTEGER"),
    ("user_email", "VARCHAR(255)"),
    ("host", "VARCHAR(255)"),
    ("hook_event", "VARCHAR(64)"),
    ("context_tokens", "INTEGER"),
)

POLICY_COLUMNS = (
    # policy_state の列。(列名, 型) の 2 つ組
    ("event_id", "VARCHAR(36)"),
    ("ts", "INTEGER"),
    ("day", "INTEGER"),
    ("user_email", "VARCHAR(255)"),
    ("host", "VARCHAR(255)"),
    ("key_name", "VARCHAR(128)"),
    ("value", "VARCHAR(255)"),
    ("prev_value", "VARCHAR(255)"),
    ("apply_result", "VARCHAR(32)"),
    ("plugin_version", "VARCHAR(32)"),
)

POLICY = {
    # settings.json 内のドット区切りパス -> 適用する値
    "env.CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": "60",
    "extraKnownMarketplaces.cc-marketplace-governance-bmsd.autoUpdate": True,
}

CSV_COLUMNS = (
    # (CSV ヘッダ名, DB 列名, 型) の 3 つ組。source_file はヘッダを持たないため None
    ("Date", "day", "INTEGER"),
    ("User Email", "user_email", "VARCHAR(255)"),
    ("Provider", "provider", "VARCHAR(255)"),
    ("Model", "model", "VARCHAR(255)"),
    ("Currency", "currency", "VARCHAR(255)"),
    ("Cost", "cost", "DOUBLE"),
    ("Input Tokens", "input_tokens", "BIGINT"),
    ("Output Tokens", "output_tokens", "BIGINT"),
    ("Cache Read Tokens", "cache_read_tokens", "BIGINT"),
    ("Cache Write Tokens", "cache_write_tokens", "BIGINT"),
    ("Cached Input Tokens", "cached_input_tokens", "BIGINT"),
    ("Uncached Input Tokens", "uncached_input_tokens", "BIGINT"),
    (None, "source_file", "VARCHAR(255)"),
)


def dig(obj: Any, path: tuple) -> Optional[Any]:
    """キーパスを先頭から順にたどり、たどれなければ None を返す。"""
    cur = obj
    for key in path:
        cur = cur.get(key) if isinstance(cur, dict) else None
    return cur


def _varchar_length(type_str: str) -> int:
    """`VARCHAR(n)` から宣言長 n を取り出す。"""
    start = type_str.index("(") + 1
    end = type_str.index(")")
    return int(type_str[start:end])


def _coerce_varchar(value: Any, type_str: str) -> Optional[str]:
    """VARCHAR へ変換する。スカラでない値（dict・list 等）は None にする。

    符号化できない文字（孤立サロゲート等）は置換してから、宣言長で切り詰める。
    """
    if isinstance(value, bool):
        text = "true" if value else "false"
    elif isinstance(value, (str, int, float)):
        text = str(value)
    else:
        return None
    text = text.encode("utf-8", "replace").decode("utf-8")
    return text[: _varchar_length(type_str)]


_INT64_MIN = -(2**63)
_INT64_MAX = 2**63 - 1


def _coerce_int_like(value: Any) -> Optional[int]:
    """INTEGER / BIGINT へ変換する。真偽値・整数・整数文字列のみ int に寄せ、符号付き 64bit の範囲に収める。"""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        result = value
    elif isinstance(value, str):
        try:
            result = int(value)
        except ValueError:
            return None
    else:
        return None
    if result < _INT64_MIN or result > _INT64_MAX:
        return None
    return result


def _coerce_double(value: Any) -> Optional[float]:
    """DOUBLE へ変換する。数値・数値文字列のみ float に寄せる。"""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def coerce(value: Any, type_str: str) -> Any:
    """列の型に合わせて値を変換する。None はそのまま通す。"""
    if value is None:
        return None
    token = type_str.split("(")[0]
    if token == "VARCHAR":
        return _coerce_varchar(value, type_str)
    if token in ("INTEGER", "BIGINT"):
        return _coerce_int_like(value)
    if token == "DOUBLE":
        return _coerce_double(value)
    return None


_JST_OFFSET_SECONDS = 9 * 3600
_SECONDS_PER_DAY = 86400


def to_day(ts: int) -> int:
    """epoch 秒を JST 基準の epoch 日へ変換する。現在時刻は読まない。"""
    return (ts + _JST_OFFSET_SECONDS) // _SECONDS_PER_DAY


def _create_table_sql(table_name: str, columns: tuple) -> str:
    """列の並びから CREATE TABLE IF NOT EXISTS 文を組み立てる。"""
    columns_sql = ", ".join(f"{name} {type_str}" for name, type_str in columns)
    return f"CREATE TABLE IF NOT EXISTS {table_name} ({columns_sql})"


def ddl() -> tuple:
    """events / policy_state / cost_daily の CREATE TABLE 文を組み立てる。"""
    hook_names = {name for name, _, _ in HOOK_FIELDS}
    extra_names = {name for name, _ in EXTRA_COLUMNS}
    duplicated = hook_names & extra_names
    if duplicated:
        raise ValueError(
            "HOOK_FIELDS と EXTRA_COLUMNS で列名が重複している: "
            + ", ".join(sorted(duplicated))
        )

    events_columns = tuple(EXTRA_COLUMNS) + tuple(
        (name, type_str) for name, _, type_str in HOOK_FIELDS
    )
    policy_columns = POLICY_COLUMNS
    cost_columns = tuple((db_name, type_str) for _, db_name, type_str in CSV_COLUMNS)

    return (
        _create_table_sql("events", events_columns),
        _create_table_sql("policy_state", policy_columns),
        _create_table_sql("cost_daily", cost_columns),
    )
