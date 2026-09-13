"""FTS retrieval over kb.chunks. MCP_ENGINES.md §Retrieval.

The pgvector path behind KB_EMBEDDINGS_ENABLED is not built yet —
DATA_PIPELINE.md §Embeddings has the design; kb.chunks.embedding stays
unpopulated until a later milestone flips the flag and this module gains that
second code path.
"""

from app.schemas import KbChunk, KbDocument
from app.sql.runner import get_pool

_RETRIEVE_QUERY = """
    SELECT c.content, c.heading_path, d.title, d.source_url, d.doc_type,
           ts_rank(c.fts, websearch_to_tsquery('simple', $1)) AS rank
    FROM kb.chunks c
    JOIN kb.documents d ON d.id = c.document_id
    WHERE d.withdrawn_at IS NULL
      AND c.fts @@ websearch_to_tsquery('simple', $1)
    ORDER BY rank DESC
    LIMIT $2
"""

_DOCUMENTS_PAGE_QUERY = """
    SELECT id, title, doc_type, source_url, ingested_at, withdrawn_at
    FROM kb.documents
    ORDER BY ingested_at DESC
    LIMIT $1 OFFSET $2
"""


async def retrieve(query: str, k: int) -> list[KbChunk]:
    pool = await get_pool()
    rows = await pool.fetch(_RETRIEVE_QUERY, query, k)
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
