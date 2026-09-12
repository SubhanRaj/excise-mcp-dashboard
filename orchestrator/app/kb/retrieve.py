"""FTS retrieval over kb.chunks. MCP_ENGINES.md §Retrieval.

The pgvector path behind KB_EMBEDDINGS_ENABLED is not built yet —
DATA_PIPELINE.md §Embeddings has the design; kb.chunks.embedding stays
unpopulated until a later milestone flips the flag and this module gains that
second code path.
"""

from app.schemas import KbChunk
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


async def retrieve(query: str, k: int) -> list[KbChunk]:
    pool = await get_pool()
    rows = await pool.fetch(_RETRIEVE_QUERY, query, k)
    return [KbChunk(**dict(r)) for r in rows]
