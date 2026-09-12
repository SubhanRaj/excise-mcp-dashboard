-- kb_indexes.sql — the kb.* GIN/FTS index and the document/chunk lookup
-- indexes. kb.chunks.fts (the generated tsvector) and kb.chunks.embedding
-- are already columns on the table from schema.sql (Milestone 1); this file
-- only adds indexes over them.
--
-- Apply after schema.sql, as a superuser:
--   sudo -u postgres psql -d excise_bank -f kb_indexes.sql

\set ON_ERROR_STOP on

SET ROLE excise_owner;

CREATE INDEX IF NOT EXISTS kb_chunks_fts ON kb.chunks USING GIN (fts);
CREATE INDEX IF NOT EXISTS kb_chunks_doc ON kb.chunks (document_id);
CREATE INDEX IF NOT EXISTS kb_documents_withdrawn_idx
    ON kb.documents (withdrawn_at) WHERE withdrawn_at IS NULL;
