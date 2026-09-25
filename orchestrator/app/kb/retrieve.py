"""FTS retrieval over kb.chunks. MCP_ENGINES.md §Retrieval.

The pgvector path behind KB_EMBEDDINGS_ENABLED is not built yet —
DATA_PIPELINE.md §Embeddings has the design; kb.chunks.embedding stays
unpopulated until a later milestone flips the flag and this module gains that
second code path.
"""

import string

from app.schemas import KbChunk, KbDocument
from app.sql.runner import get_pool

# kb.chunks.fts is indexed with the 'simple' text search config (no stopword list,
# no stemming) — confirmed live: a chat model's own search_knowledge query is often
# its full question verbatim ("What does the excise policy say about MGQ?"), and
# websearch_to_tsquery('simple', ...) ANDs every one of those words, including
# "what"/"does"/"say"/"about", so a chunk has to contain all of them next to the
# real search term to match at all — it never does. An 'english' config's stopword
# list would filter these before they ever reach the query, but switching configs
# needs a full reindex of the generated fts column (106k+ rows); dropping the same
# small set of words here first gets the same result with no schema change.
#
# "excise" and "policy" are in this list too, past the usual grammatical filler —
# confirmed live, "excise policy mgq" (what a real question strips down to) matched
# zero real documents even though "mgq" alone matches plenty, because "policy" as a
# literal word doesn't happen to appear in the same chunk as "mgq" anywhere in this
# corpus (fts is built from heading_path + content only, never the document title,
# so requiring "policy" never actually found a document by its title either — it
# only ever filtered on an incidental word match). Every document in this corpus is
# about excise policy in the broad sense; in a "what does excise policy say about
# X" question, both words are the question's own frame, not the search intent.
# Trialled and reverted: falling back to an OR of the same words when AND finds
# nothing returns something for a case like this, but it also returns something
# for a genuinely unrelated query ("xyzzy nonexistent gibberish" started matching
# real chunks on "gibberish" or similar single-word overlap) — breaking the "no
# real match returns no context, not a guess" guarantee this corpus already relies
# on elsewhere. Stopword-list precision costs nothing that guarantee; OR does.
_STOPWORDS = frozenset(
    "a an and are as at be by do does for from had has have how in is it its of on "
    "or say says said tell that the this to was were what when where which who why"
    " about can could should would excise policy".split()
)


def _strip_stopwords(query: str) -> str:
    kept = [w for w in query.split() if w.strip(string.punctuation).lower() not in _STOPWORDS]
    return " ".join(kept) or query


_RETRIEVE_QUERY = """
    SELECT c.content, c.heading_path, d.title, d.source_url, d.doc_type, d.effective_from,
           d.state, ts_rank(c.fts, websearch_to_tsquery('simple', $1)) AS rank
    FROM kb.chunks c
    JOIN kb.documents d ON d.id = c.document_id
    WHERE d.withdrawn_at IS NULL
      AND c.fts @@ websearch_to_tsquery('simple', $1)
      AND (d.state IS NULL OR d.state = ANY($3::text[]))
    ORDER BY rank DESC
    LIMIT $2
"""

_DOCUMENTS_PAGE_QUERY = """
    SELECT id, title, doc_type, state, effective_from, source_url, ingested_at, withdrawn_at
    FROM kb.documents
    ORDER BY ingested_at DESC
    LIMIT $1 OFFSET $2
"""

# The corpus's own default scope — every question gets this unless it names other
# states explicitly. A state-agnostic document (state IS NULL — a generic Act or GO,
# not tied to any one state) is always in scope regardless, the same rule
# `_DOCUMENTS_QUERY`'s old sync-time filter used to apply for every question at once;
# retrieval enforces it per-question now that ingestion no longer does
# (DATA_PIPELINE.md §Knowledge base).
_DEFAULT_STATES = ["Uttar Pradesh"]


async def retrieve(query: str, k: int, states: list[str] | None = None) -> list[KbChunk]:
    pool = await get_pool()
    rows = await pool.fetch(_RETRIEVE_QUERY, _strip_stopwords(query), k, states or _DEFAULT_STATES)
    return [KbChunk(**dict(r)) for r in rows]


async def list_documents(page: int, per_page: int) -> tuple[list[KbDocument], int]:
    """Paginated, unranked listing for the admin "browse the corpus" screen —
    distinct from retrieve()'s ranked FTS search (MCP_ENGINES.md §HTTP surface).
    """
    pool = await get_pool()
    offset = (page - 1) * per_page
    rows = await pool.fetch(_DOCUMENTS_PAGE_QUERY, per_page, offset)
    total = int(await pool.fetchval("SELECT count(*) FROM kb.documents") or 0)
    return [KbDocument(**dict(r)) for r in rows], total
