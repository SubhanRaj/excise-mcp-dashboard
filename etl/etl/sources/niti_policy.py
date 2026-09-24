"""Policy Rules -> policy_entries; Duty Rates -> quarantined outright.
DATA_PIPELINE.md §Source adapters.

Policy Rules is a wide table (24 policy attributes per state x financial
year) but policy_entries is shaped for a narrative document (title, summary,
one `category` enum, effective dates) - there's no column for "who does the
wholesale" or "date CCTV became compulsory" individually. Each state x FY row
becomes one policy_entries row whose `summary` lists every non-blank
attribute as "label: value" - the only faithful transformation available
given the fixed target shape, not a guess at which single field to keep.
`category` stays NULL: a row this wide covers pricing, licensing, and
enforcement attributes all at once, and forcing it into one of the five
enum-ish values would misdescribe the other attributes in the same row.

Duty Rates' Rate column holds formula strings referencing EDP (ex-distillery
price) - '7.2*EDP', '200+0.425*EDP' - not the plain number duty_rates.rate
(NUMERIC NOT NULL) requires. Every row is quarantined with that reason
instead of inserted; nothing here computes or truncates a number out of a
formula.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date

import asyncpg
import openpyxl

from etl import quarantine
from etl.normalize import NormalizationError, parse_financial_year

POLICY_SHEET = "9. Policy Rules"
DUTY_RATES_SHEET = "8. Duty Rates"

# (column index, label used in the synthesized summary line)
_POLICY_COLUMNS: tuple[tuple[int, str], ...] = (
    (2, "Who does the wholesale"),
    (3, "How the wholesale margin is fixed"),
    (4, "How the retail margin is fixed"),
    (5, "How retail shops were allotted this year"),
    (6, "Minimum quantity every shop had to lift"),
    (7, "Percent increase per year for that minimum"),
    (8, "Minimum revenue every shop had to guarantee"),
    (9, "Ex-distillery price capped at neighbouring states' price"),
    (10, "That cap in effect from"),
    (11, "Minimum selling price rule"),
    (12, "QR code / hologram tracking compulsory from"),
    (13, "Flow meters compulsory at distilleries from"),
    (14, "CCTV compulsory from"),
    (15, "Card machines compulsory at shops from"),
    (16, "GPS on tankers compulsory from"),
    (17, "Composite shops introduced from"),
    (18, "Number of distillery licences"),
    (19, "Number of brewery licences"),
    (20, "Brand label applications received"),
    (21, "Brand label applications approved"),
    (22, "Brand label applications rejected"),
    (23, "People employed in the liquor trade in this state"),
)


@dataclass(frozen=True)
class RunCounts:
    seen: int
    upserted: int
    quarantined: int


@dataclass(frozen=True)
class PolicyRow:
    state: str
    financial_year_raw: str
    fields: dict[str, object]
    source_document: str | None
    source_ref: str


@dataclass(frozen=True)
class DutyRateRow:
    state: str
    drink_type: str | None
    pack_or_strength: str | None
    rate_raw: object
    unit: str | None
    notification: str | None
    source_ref: str


def _fmt(value: object) -> str:
    if isinstance(value, date):
        return value.strftime("%d-%m-%Y")
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def read_policy_rows(path: str) -> Iterator[PolicyRow]:
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    sheet = workbook[POLICY_SHEET]
    rows = sheet.iter_rows(values_only=True)
    next(rows)
    for r in rows:
        if r[0] is None:
            continue
        fields: dict[str, object] = {
            label: r[col] for col, label in _POLICY_COLUMNS if r[col] is not None
        }
        yield PolicyRow(
            state=str(r[0]).strip(),
            financial_year_raw=str(r[1]).strip() if r[1] else "",
            fields=fields,
            source_document=str(r[24]).strip() if r[24] else None,
            source_ref=f"niti_policy_rules:{path}:{r[0]}:{r[1]}",
        )
    workbook.close()


def read_duty_rate_rows(path: str) -> Iterator[DutyRateRow]:
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    sheet = workbook[DUTY_RATES_SHEET]
    rows = sheet.iter_rows(values_only=True)
    next(rows)
    for i, r in enumerate(rows, start=2):
        if r[0] is None:
            continue
        yield DutyRateRow(
            state=str(r[0]).strip(),
            drink_type=str(r[1]).strip() if r[1] else None,
            pack_or_strength=str(r[2]).strip() if r[2] else None,
            rate_raw=r[4],
            unit=str(r[5]).strip() if r[5] else None,
            notification=str(r[6]).strip() if r[6] else None,
            source_ref=f"niti_duty_rates:{path}:{i}",
        )
    workbook.close()


async def _resolve_financial_year(
    conn: asyncpg.Connection, cache: dict[str, tuple[int, int]], raw: str
) -> tuple[int, int]:
    """Returns (financial_year_id, start_year)."""
    if raw in cache:
        return cache[raw]
    start_year = parse_financial_year(raw)
    fy_id = await conn.fetchval("SELECT id FROM financial_years WHERE start_year = $1", start_year)
    if fy_id is None:
        raise NormalizationError(f"no financial_years row for start_year={start_year}")
    cache[raw] = (int(fy_id), start_year)
    return cache[raw]


async def sync_policy_rows(
    conn: asyncpg.Connection, run_id: int, rows: list[PolicyRow]
) -> RunCounts:
    seen = upserted = quarantined = 0
    fy_cache: dict[str, tuple[int, int]] = {}
    for row in rows:
        seen += 1
        try:
            fy_id, start_year = await _resolve_financial_year(
                conn, fy_cache, row.financial_year_raw
            )
        except NormalizationError as exc:
            await quarantine.record(conn, run_id, row.__dict__, str(exc))
            quarantined += 1
            continue

        title = f"Policy rules — {row.state} FY{start_year}-{str(start_year + 1)[-2:]}"
        summary_lines = [f"{label}: {_fmt(value)}" for label, value in row.fields.items()]
        if row.source_document:
            summary_lines.append(f"Source document: {row.source_document}")
        summary = "\n".join(summary_lines) if summary_lines else "No policy attributes recorded."

        await conn.execute(
            """
            INSERT INTO policy_entries (financial_year_id, effective_from, effective_to, title,
                                         category, summary, source_ref, published_at)
            VALUES ($1, $2, $3, $4, NULL, $5, $6, now())
            ON CONFLICT (source_ref) DO UPDATE SET
                financial_year_id = EXCLUDED.financial_year_id,
                effective_from = EXCLUDED.effective_from, effective_to = EXCLUDED.effective_to,
                title = EXCLUDED.title, summary = EXCLUDED.summary, updated_at = now()
            """,
            fy_id,
            date(start_year, 4, 1),
            date(start_year + 1, 3, 31),
            title,
            summary,
            row.source_ref,
        )
        upserted += 1
    return RunCounts(seen=seen, upserted=upserted, quarantined=quarantined)


async def sync_duty_rate_rows(
    conn: asyncpg.Connection, run_id: int, rows: list[DutyRateRow]
) -> RunCounts:
    seen = quarantined = 0
    for row in rows:
        seen += 1
        await quarantine.record(
            conn,
            run_id,
            row.__dict__,
            "duty_rates.rate is a required plain NUMERIC, but this sheet's Rate column holds a "
            "formula string referencing EDP (ex-distillery price), e.g. '7.2*EDP' or "
            "'200+0.425*EDP' - not loaded without a decision on how to represent that formula",
        )
        quarantined += 1
    return RunCounts(seen=seen, upserted=0, quarantined=quarantined)


async def sync(conn: asyncpg.Connection, run_id: int, path: str, kind: str) -> RunCounts:
    if kind == "policy":
        return await sync_policy_rows(conn, run_id, list(read_policy_rows(path)))
    if kind == "duty":
        return await sync_duty_rate_rows(conn, run_id, list(read_duty_rate_rows(path)))
    raise ValueError(f"unknown niti_policy kind: {kind!r}")
