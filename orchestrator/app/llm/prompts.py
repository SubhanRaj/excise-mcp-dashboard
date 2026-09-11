"""System prompts, the schema-card slot, and few-shot examples for each pipeline
stage. MCP_ENGINES.md §Pipeline stages.

The fact tables (revenues, sales_volumes, ...) are empty until the real NITI
workbook lands (ROADMAP.md Milestone 1) — the district/zone/division examples
below are the ones that return real rows today; the rest teach the model the
shape of the other views for when data is present.
"""

from app.schemas import Turn

SQL_SYSTEM_PROMPT = """You are a PostgreSQL analyst for the UP Excise department.

Write exactly one read-only SQL statement (SELECT, or WITH ... SELECT) against
the `analytics` schema described below. You have no write privilege: never use
INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE, COPY, GRANT, CALL, SET, VACUUM,
or ANALYZE. Reference only tables in the `analytics` schema, unqualified or as
`analytics.<name>`. Always include a LIMIT. Money columns are already in
rupees. Return only the JSON the schema asks for, no prose, no markdown fence.
"""

FEW_SHOT_SQL_EXAMPLES: list[dict[str, str]] = [
    {
        "question": "How many districts are in each zone?",
        "sql": "SELECT zone, COUNT(*) AS district_count "
        "FROM analytics.districts GROUP BY zone ORDER BY zone LIMIT 100;",
    },
    {
        "question": "List the divisions in the Varanasi zone.",
        "sql": "SELECT DISTINCT division FROM analytics.districts "
        "WHERE zone = 'Varanasi' ORDER BY division LIMIT 100;",
    },
    {
        "question": "What financial years do we have data for?",
        "sql": "SELECT label, start_year FROM analytics.financial_years "
        "ORDER BY start_year LIMIT 100;",
    },
    {
        "question": "Show total excise duty revenue by district for FY2023-24.",
        "sql": "SELECT district, SUM(amount_inr) AS total_inr FROM analytics.revenues "
        "WHERE financial_year = 'FY2023-24' AND metric = 'excise_duty' "
        "GROUP BY district ORDER BY total_inr DESC LIMIT 100;",
    },
    {
        "question": "What was the dispatch volume trend for Lucknow since FY2018-19?",
        "sql": "SELECT financial_year, SUM(quantity) AS total_bl FROM analytics.sales_volumes "
        "WHERE district = 'Lucknow' AND metric = 'dispatch_bl' AND start_year >= 2018 "
        "GROUP BY financial_year, start_year ORDER BY start_year LIMIT 100;",
    },
    {
        "question": "How many enforcement raids happened each financial year?",
        "sql": "SELECT financial_year, SUM(value) AS raids FROM analytics.operations "
        "WHERE metric = 'raids' GROUP BY financial_year, start_year "
        "ORDER BY start_year LIMIT 100;",
    },
    {
        "question": "What is the duty rate for foreign liquor in FY2022-23?",
        "sql": "SELECT license_category, basis, rate, unit FROM analytics.duty_rates "
        "WHERE financial_year = 'FY2022-23' AND license_category = 'FL' LIMIT 100;",
    },
    {
        "question": "How many shops are there per district?",
        "sql": "SELECT district, COUNT(*) AS shop_count FROM analytics.shops "
        "GROUP BY district ORDER BY shop_count DESC LIMIT 100;",
    },
]


def build_sql_prompt(question: str, schema_card: str, history: list[Turn]) -> str:
    examples = "\n\n".join(f"Q: {ex['question']}\nSQL: {ex['sql']}" for ex in FEW_SHOT_SQL_EXAMPLES)
    history_block = "\n".join(f"{t.role}: {t.content}" for t in history) or "(none)"
    return (
        f"{SQL_SYSTEM_PROMPT}\n\n{schema_card}\n\n"
        f"Examples:\n{examples}\n\n"
        f"Conversation so far:\n{history_block}\n\n"
        f"Question: {question}\n"
    )


PLOT_SYSTEM_PROMPT = """You are writing a short Python script to chart a SQL
result for a UP Excise analyst. A pandas DataFrame `df` is already loaded and
an `OUT` directory path is already set — do not read any other file, do not
open a socket, do not import anything beyond pandas/numpy/matplotlib/seaborn/
plotly (already imported as pd/np/plt/sns/go/px if you need them).

Build a Plotly figure and call `fig.write_json(f"{OUT}/chart.plotly.json")`.
That is the only output to produce right now — do not call `fig.write_image`
or `plt.savefig`, and set `outputs` to `["plotly_json"]` only. Only write
`chart.plotly.json`, only into OUT. Pick chart types that make sense for
excise data: a line for a trend over financial years, a bar for a comparison
across districts/categories.
"""


def build_plot_prompt(question: str, columns: list[str], dtypes: list[str], row_count: int) -> str:
    columns_block = "\n".join(f"  {c}: {d}" for c, d in zip(columns, dtypes, strict=True))
    return (
        f"{PLOT_SYSTEM_PROMPT}\n\n"
        f"The question was: {question}\n\n"
        f"df has {row_count} rows and these columns:\n{columns_block}\n\n"
        "Return only the JSON the schema asks for, no prose, no markdown fence."
    )


SUMMARY_SYSTEM_PROMPT = """You are summarizing a query result for a UP Excise
analyst who just asked a question and got a chart and a table back. Write a
2-4 sentence plain-language reading of the numbers — what they show, any
standout value or trend. No markdown, no restating the question, no "In
summary". Plain text only.
"""


def build_summary_prompt(
    question: str, columns: list[str], row_count: int, rows_preview: list[dict[str, object]]
) -> str:
    preview_block = "\n".join(str(r) for r in rows_preview[:10])
    return (
        f"{SUMMARY_SYSTEM_PROMPT}\n\n"
        f"Question: {question}\n"
        f"Columns: {', '.join(columns)}\n"
        f"Row count: {row_count}\n"
        f"Sample rows:\n{preview_block}\n"
    )
