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

A question naming more than one category ("how many X and Y shops", "revenue
and volume") wants each one broken out as its own row, and the total across
them, not summed into a single row alone — a combined total hides which
category is which, and a breakdown with no total leaves the reader to add
the rows up themselves. Use `GROUP BY ROLLUP(...)` to get a correct total row
alongside the per-category ones in the same query, rather than a second query
or asking anyone downstream to sum the rows by hand.
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
        # There is no analytics.financial_years view — financial_year and start_year are
        # denormalized onto every fact view instead (analytics.revenues, sales_volumes,
        # operations, dispatches, sro_shops, shop_years, duty_rates, policy_entries), the
        # same way district is. This example's own earlier version pointed at
        # analytics.financial_years directly; guard_sql let it through (a syntactically
        # valid single SELECT against a schema-qualified name), and it failed at run_sql
        # with an undefined-table error every time, since the table it named was never
        # real.
        "question": "What financial years do we have data for?",
        "sql": "SELECT DISTINCT financial_year, start_year FROM analytics.revenues "
        "ORDER BY start_year LIMIT 100;",
    },
    {
        "question": "Show total excise duty revenue by district for FY2023-24.",
        "sql": "SELECT district, SUM(amount_inr) AS total_inr FROM analytics.revenues "
        "WHERE financial_year = 'FY2023-24' AND metric = 'excise_duty' "
        "GROUP BY district ORDER BY total_inr DESC LIMIT 100;",
    },
    {
        # metric on sales_volumes names a liquor type ('beer', 'imfl', 'wine', ...), not a
        # dispatch/consumption distinction — a plain "dispatch volume trend" question with
        # no type named sums across every metric instead of guessing one to filter on
        # (confirmed live against real data, schema_card.py's own VIEW_NOTES).
        "question": "What was the sales volume trend for Lucknow since FY2018-19?",
        "sql": "SELECT financial_year, SUM(quantity) AS total_bl FROM analytics.sales_volumes "
        "WHERE district = 'Lucknow' AND start_year >= 2018 "
        "GROUP BY financial_year, start_year ORDER BY start_year LIMIT 100;",
    },
    {
        # 'raids' was never a real metric value on this view — confirmed live, the actual
        # value is 'inspections_raids' (schema_card.py's own VIEW_NOTES lists every real one).
        "question": "How many enforcement raids happened each financial year?",
        "sql": "SELECT financial_year, SUM(value) AS raids FROM analytics.operations "
        "WHERE metric = 'inspections_raids' GROUP BY financial_year, start_year "
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
    {
        # Confirmed live: without a worked example in exactly this shape, the model
        # pattern-matched the shops-per-district example above, joined shops to
        # districts, and referenced transport_pass_issued_at on that join anyway —
        # a column that only exists on analytics.dispatches, which UndefinedColumnError
        # on. dispatches already carries district and retail_license_category as its
        # own columns, so a shop-count-by-district-and-month question needs no join for
        # that part, just COUNT(DISTINCT shop_id) since one shop has many dispatch rows.
        #
        # A second bug lived in this same example for a while: a general category name
        # like "composite" is not one code, and this example's own earlier version
        # (retail_license_category IN ('CL5C', 'CL5CC')) hardcoded the wrong pair —
        # undercounting a live version of this question by 417 shops, every one of
        # them FL5DB. CL5CC is kind='country_liquor' (a Country Liquor shop with a beer
        # endorsement, not a separate shop type — confirmed against
        # ~/Projects/up-excise-spatial-revenue-optimizer's own shop-type glossary);
        # FL5DB (Foreign Liquor + Beer) is the only kind='composite' code. The model
        # copies this worked example's pattern directly rather than reasoning about
        # which codes a kind covers, so filtering on license_categories.kind — correct
        # regardless of how many codes a kind has today or gains later — belongs in
        # the example itself, not just in VIEW_NOTES' prose.
        #
        # A third bug lived here past both of those: this example summed both named
        # categories into one COUNT, so a live run answered "1006" with no breakdown
        # and charted as a single bar — the question names two categories and the
        # answer collapsed them into one anyway. Grouped by kind first (589 country
        # liquor, 417 composite, confirmed live), which fixed the breakdown but then
        # dropped the total the two rows used to give for free — a person asking "how
        # many X and Y" still wants to know how many altogether, not just each part.
        # ROLLUP adds that back as a real third row, its own COUNT(DISTINCT ...) over
        # the combined group rather than the two subtotals added together, so it stays
        # correct even if a shop's category ever varies across dispatch rows within the
        # month (1006 either way, confirmed live: 417 + 589 with no overlap today).
        "question": ("How many country liquor and composite shops are in Lucknow in August 2026?"),
        "sql": "SELECT COALESCE(INITCAP(REPLACE(lc.kind, '_', ' ')), 'Total') AS category, "
        "COUNT(DISTINCT d.shop_id) AS shop_count FROM analytics.dispatches d "
        "JOIN analytics.license_categories lc ON lc.code = d.retail_license_category "
        "WHERE d.district = 'Lucknow' AND lc.kind IN ('country_liquor', 'composite') "
        "AND EXTRACT(MONTH FROM d.transport_pass_issued_at) = 8 "
        "AND EXTRACT(YEAR FROM d.transport_pass_issued_at) = 2026 "
        "GROUP BY ROLLUP(lc.kind) ORDER BY lc.kind NULLS LAST LIMIT 100;",
    },
    {
        # Confirmed live: asked for statewide beer revenue in FY2025-26, the model
        # guessed analytics.revenues WHERE license_category IN ('CL5CC', 'FL5DB') —
        # those are shop licence codes, not a liquor-type filter, and analytics.revenues
        # has no column that isolates beer revenue at all. It matched nothing, SUM()
        # over zero matching rows returned one row with total_revenue = NULL (not zero
        # rows — see pipeline.py's own no_data check), and the summarizing model, having
        # nothing to say NULL meant empty, invented a full answer with a fabricated
        # urban/rural split nothing in the query even asked for. The Excise Policy 2025
        # abolished standalone beer shops, so beer revenue is a component within two
        # other shop_types' own totals on analytics.sro_shops, not a filterable category
        # anywhere: composite_lf_beer + composite_mgr_beer for a COMPOSITE_SHOP, and
        # special_beer_lf + special_beer_mgr for a COUNTRY_LIQUOR shop with
        # has_cl5cc = true. This example sums both (schema_card.py's sro_shops note has
        # the same reasoning).
        "question": (
            "How much revenue was generated from beer sale across Uttar Pradesh in FY 2025-26?"
        ),
        "sql": "SELECT "
        "SUM(CASE WHEN shop_type = 'COMPOSITE_SHOP' "
        "THEN COALESCE(composite_lf_beer, 0) + COALESCE(composite_mgr_beer, 0) ELSE 0 END) "
        "+ SUM(CASE WHEN has_cl5cc "
        "THEN COALESCE(special_beer_lf, 0) + COALESCE(special_beer_mgr, 0) ELSE 0 END) "
        "AS total_beer_revenue "
        "FROM analytics.sro_shops WHERE financial_year = 'FY2025-26' LIMIT 100;",
    },
    {
        # A bare code (CL5C, FL4A, FL5DB, ...) means nothing to a reader who hasn't
        # memorized analytics.license_categories — join it in by name whenever a
        # question groups or filters by a shop's license category, so the row itself
        # carries the plain-language type instead of asking the summarizing step to
        # recall or guess it.
        "question": "What was the dispatched volume by shop category in Lucknow in August 2026?",
        "sql": "SELECT d.retail_license_category, lc.name AS category_name, "
        "SUM(d.dispatched_bulk_litres) AS total_bl FROM analytics.dispatches d "
        "JOIN analytics.license_categories lc ON lc.code = d.retail_license_category "
        "WHERE d.district = 'Lucknow' "
        "AND EXTRACT(MONTH FROM d.transport_pass_issued_at) = 8 "
        "AND EXTRACT(YEAR FROM d.transport_pass_issued_at) = 2026 "
        "GROUP BY d.retail_license_category, lc.name ORDER BY total_bl DESC LIMIT 100;",
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


PLOT_SYSTEM_PROMPT = """You are choosing a charting engine and writing a short
script to chart a SQL result for a UP Excise analyst. Do not read any file
other than the data already loaded for you, do not open a socket, do not
import or use anything beyond what your chosen engine's line below says is
already loaded.

Pick the "engine" that best fits the outputs you want, then write "script"
as a script for that engine only — do not mix syntax from the other engine.
Pick chart types that make sense for excise data: a line for a trend over
financial years, a bar for a comparison across districts/categories.

Give the chart human-readable axis titles — a raw column name like
"retail_license_category" or "total_bl" means nothing to someone reading the
chart, only to the query that produced it.
"""

# MCP_ENGINES.md §Routing — one line per engine, no heuristic beyond this: the
# LLM reads these and picks. Only engines actually in the live registry are
# ever listed, so an unavailable engine (octave not installed, matlab/wolfram
# stubs) is never offered.
#
# chat/prompts.py's make_chart tool description states the same `df`/`OUT`/
# forbidden-fig.write_image() facts for its own script contract in different
# words, since chat always fixes outputs=["plotly_json"] and can't reuse this
# text as-is without also offering the matplotlib/static branch chat's engine
# call never collects — keep both in sync by hand if the sandbox contract
# below (or python_engine.py's PREAMBLE) changes.
_ENGINE_CAPABILITIES = {
    "python": (
        "python: a pandas DataFrame `df` is already loaded, `OUT` is the output "
        "directory. For an interactive chart, build a Plotly figure and call "
        '`fig.write_json(f"{OUT}/chart.plotly.json")` with outputs=["plotly_json"]. '
        "For a static chart, use matplotlib and call `plt.savefig(...)` into OUT "
        'with outputs=["png"|"svg"|"pdf"]. Never call a Plotly figure\'s '
        "`fig.write_image()` — it needs a headless Chrome this sandbox cannot launch."
    ),
    "octave": (
        "octave: each result column is already loaded as a plain variable "
        "named after its column alias (a numeric column vector, or a cell "
        "array of strings for text) — no `table`/`readtable`, Octave doesn't "
        "have it. `OUT` is the output directory, and a figure is already open "
        "(invisible, non-interactive) — call a plotting function like "
        "`plot`/`bar`/`histogram` directly, do not create a new figure. "
        "Static output only, no interactive chart — use Octave's `print()` "
        'with a cairo device: `print(fullfile(OUT, "chart.png"), '
        "'-dpngcairo')`, `-dsvg` for chart.svg, `-dpdfcairo` for chart.pdf. "
        "Never `-dpng` or `-dpdf` (they fail in this sandbox) and never set "
        'outputs to "plotly_json".'
    ),
}


def build_plot_prompt(
    question: str,
    columns: list[str],
    dtypes: list[str],
    row_count: int,
    available_engines: list[str],
) -> str:
    columns_block = "\n".join(f"  {c}: {d}" for c, d in zip(columns, dtypes, strict=True))
    capability_block = "\n".join(
        f"- {_ENGINE_CAPABILITIES[name]}"
        for name in available_engines
        if name in _ENGINE_CAPABILITIES
    )
    return (
        f"{PLOT_SYSTEM_PROMPT}\n\n"
        f"Available engines:\n{capability_block}\n\n"
        f"The question was: {question}\n\n"
        f"The data has {row_count} rows and these columns:\n{columns_block}\n\n"
        "Return only the JSON the schema asks for, no prose, no markdown fence."
    )


SUMMARY_SYSTEM_PROMPT = """You are summarizing a query result for a UP Excise
analyst who just asked a question and got a chart and a table back. Write a
2-4 sentence plain-language reading of the numbers — what they show, any
standout value or trend. State each figure once; the table already shows it,
so the summary should not repeat it in a second format. If the result breaks
a total down into parts — a "Total" row alongside category rows, or several
rows that together answer one combined question — state the total and each
part, not the total alone or the parts alone.

Every money figure in this data is Indian Rupees, never dollars — write ₹,
never $. State a large amount in lakh or crore rather than a long digit
string: "₹24,098.37 crore" reads plainly, "₹2,409,837,306,156" does not. One
lakh is ₹1,00,000; one crore is ₹1,00,00,000.

State what the numbers show, not commentary about the number itself — never
"this figure represents a significant amount", "this is the only available
data point", or "this suggests a substantial contribution". No markdown, no
restating the question, no "In summary", no "showcase", "underscore",
"leverage", "robust", or similar inflated words. Plain text only.
"""


_MONEY_COLUMN_HINTS = ("inr", "revenue", "amount", "fee", "duty", "mgr", "_lf", "price", "mrp")


def _looks_like_money_column(name: str) -> bool:
    lowered = name.lower()
    return any(hint in lowered for hint in _MONEY_COLUMN_HINTS)


def format_inr(value: float) -> str:
    """Indian-digit-grouping lakh/crore rendering, computed exactly — confirmed live,
    asked to state a figure "in crore" itself, the summarizing model divided by the
    wrong power of ten and reported a district's revenue tenfold too large with full
    confidence (₹28,608 crore for a real ₹2,860.80 crore). `build_summary_prompt` and
    `chat/tools.py`'s run_sql_query both hand the model this pre-computed string for
    every money-looking column instead of asking it to do the division itself.
    """
    magnitude = abs(value)
    if magnitude >= 1_00_00_000:
        return f"₹{value / 1_00_00_000:,.2f} crore"
    if magnitude >= 1_00_000:
        return f"₹{value / 1_00_000:,.2f} lakh"
    return f"₹{value:,.2f}"


def money_annotations(columns: list[str], rows: list[dict[str, object]]) -> str:
    """One line per row, converting every money-looking column's value to its exact
    lakh/crore rendering — empty string if no column looks like money or none of the
    values are numeric.
    """
    money_cols = [c for c in columns if _looks_like_money_column(c)]
    if not money_cols:
        return ""
    lines = []
    for row in rows:
        parts = []
        for c in money_cols:
            value = row.get(c)
            if isinstance(value, int | float) and not isinstance(value, bool):
                parts.append(f"{c} = {format_inr(float(value))}")
        if parts:
            lines.append("; ".join(parts))
    if not lines:
        return ""
    return (
        "\nPre-converted amounts (use these exact figures verbatim for any lakh/crore "
        "value — do not recompute the conversion yourself):\n" + "\n".join(lines) + "\n"
    )


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
        f"{money_annotations(columns, rows_preview[:10])}"
    )
