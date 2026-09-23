"""Single-read-only-SELECT parser and reject list. SECURITY.md §SQL guard.

Defense in depth, not the primary control — excise_ro's own grants (SELECT on
analytics.* only, default_transaction_read_only = on) are what actually stops
a write. This guard exists so a bad statement never reaches the database at
all, and so we can record which analytics.* views a query touched.
"""

from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp

from app.schemas import SqlRejectedError

ALLOWED_SCHEMA = "analytics"

# analytics.shops is a present-day snapshot with no time dimension — created_at/updated_at
# are when the row was last loaded, not a business date. A live "how many X shops in
# [month/year]" question filtered on this twice and silently got zero rows back both
# times, instead of the real count from analytics.dispatches.transport_pass_issued_at.
# schema_card.py's VIEW_NOTES already tells the SQL-planning model not to do this, but it's
# a small local model and doesn't always follow that — rejecting the pattern outright
# reuses the same reprompt-and-retry-once guard_sql's other rejections already get.
SHOPS_SNAPSHOT_COLUMNS = frozenset({"created_at", "updated_at"})

# Forbidden regardless of where they appear in the tree — side-effecting or
# information-disclosure functions with no legitimate role in a read query.
FORBIDDEN_FUNCTION_NAMES = frozenset(
    {
        "pg_read_file",
        "pg_read_binary_file",
        "pg_sleep",
        "pg_sleep_for",
        "pg_stat_file",
        "pg_ls_dir",
        "nextval",
        "setval",
        "dblink",
        "dblink_connect",
        "dblink_exec",
        "lo_import",
        "lo_export",
        "lo_read",
        "lo_write",
        "lo_creat",
        "lo_create",
        "lo_unlink",
        "lo_open",
    }
)

# Node types that never belong in a read-only single SELECT. Present as a
# defensive check in case a statement smuggles a DML/DDL clause into what
# otherwise parses as one statement (sqlglot flags most of these as their own
# root node type, so this mainly guards nested/odd constructs).
FORBIDDEN_NODE_TYPES: tuple[type[exp.Expression], ...] = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Merge,
    exp.Create,
    exp.Alter,
    exp.Drop,
    exp.TruncateTable,
    exp.Grant,
)


@dataclass
class GuardResult:
    sql: str
    tables_used: list[str] = field(default_factory=list)


def guard_sql(sql: str, row_limit: int) -> GuardResult:
    try:
        statements = sqlglot.parse(sql, read="postgres")
    except sqlglot.errors.SqlglotError as e:
        # ParseError (malformed SQL) and TokenError (text sqlglot's tokenizer
        # can't lex at all, e.g. a model reply that isn't SQL) are sibling
        # subclasses of SqlglotError, not one a subclass of the other — a
        # bare `except ParseError` let a TokenError escape uncaught and crash
        # the whole request instead of getting the same reject-and-retry
        # every other bad-SQL case gets. Confirmed live: qwen2.5-coder
        # returned a Chinese apology sentence instead of SQL, which failed
        # here with TokenError and killed the query as an unhandled 500.
        raise SqlRejectedError(f"could not parse: {e}") from e

    parsed = [s for s in statements if s is not None]
    if len(parsed) != 1:
        raise SqlRejectedError(f"expected exactly one statement, found {len(parsed)}")

    root = parsed[0]
    select_node = root.this if isinstance(root, exp.With) else root
    if not isinstance(select_node, exp.Select):
        raise SqlRejectedError(
            f"statement root must be SELECT or WITH ... SELECT, got {type(root).__name__}"
        )

    for node_type in FORBIDDEN_NODE_TYPES:
        if root.find(node_type) is not None:
            raise SqlRejectedError(f"statement contains a forbidden {node_type.__name__} clause")

    for func_node in root.find_all(exp.Func):
        # sql_name() is the canonical name for a function sqlglot recognizes
        # (COUNT, SUM, ...); an unrecognized function (pg_sleep, nextval, ...)
        # parses as exp.Anonymous with sql_name() == "ANONYMOUS" and the real
        # name on .name instead.
        raw_name = func_node.sql_name()
        if raw_name == "ANONYMOUS":
            raw_name = getattr(func_node, "name", "") or raw_name
        func_name = raw_name.lower()
        if func_name in FORBIDDEN_FUNCTION_NAMES:
            raise SqlRejectedError(f"call to forbidden function '{func_name}'")

    tables_used: list[str] = []
    for table_node in root.find_all(exp.Table):
        schema_name = (table_node.db or "").lower()
        if schema_name and schema_name != ALLOWED_SCHEMA:
            raise SqlRejectedError(
                f"cross-schema reference: {schema_name}.{table_node.name} "
                f"(only {ALLOWED_SCHEMA} is allowed)"
            )
        if table_node.name.lower() not in tables_used:
            tables_used.append(table_node.name.lower())

    where = select_node.args.get("where")
    if "shops" in tables_used and where is not None:
        for col in where.find_all(exp.Column):
            if col.name.lower() in SHOPS_SNAPSHOT_COLUMNS:
                raise SqlRejectedError(
                    f"analytics.shops.{col.name.lower()} is when this row was last loaded "
                    "into the database, not a business date — for a question about a "
                    "specific month or year, filter analytics.dispatches."
                    "transport_pass_issued_at instead"
                )

    if select_node.args.get("limit") is None:
        select_node.set("limit", exp.Limit(expression=exp.Literal.number(row_limit)))

    return GuardResult(sql=root.sql(dialect="postgres"), tables_used=tables_used)
