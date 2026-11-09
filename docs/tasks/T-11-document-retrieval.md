# T-11: Encrypted document retrieval foundation

Owner scope: continue the full roadmap on phase1/security. Add keyword retrieval over documents explicitly saved in Workspace, reusing SQLCipher/FTS5 and existing document skill confirmation. No dependencies, network, automatic file crawling or embedding-model downloads.

Allowed changes: document index/search module, additive database schema initialization (not key/open/lock logic), authenticated unlocked Workspace routes, document skill/registration/pins, Documents UI and tests. Index titles/content only for document work items; edits/deletes stay synchronized transactionally. Excerpts are untrusted source material, never instructions. Use bounded queries/results and plaintext React rendering.

This is the encrypted retrieval foundation, not learned semantic search. Verify migration/backfill, updates/deletion, parameterized query handling, ranking, locked/unauthorized access, encrypted storage and tool confirmation. No commits or pushes.

## Report

Completed. Encrypted keyword retrieval foundation over documents saved in Sentinel Workspace is implemented and verified.

- **Storage & Indexing**: Uses SQLCipher FTS5 virtual table (`document_fts`) with transactional sync on create, edit, delete, and kind changes.
- **Security & Privacy**: Excludes private drafts (emails, calendar); locked database strictly denies search; excerpts are untrusted source material, bounded to 1,200 chars and max 5 results; tool confirmation enforced (Tier 2).
- **API & UI**: Authenticated Workspace routes (`/api/workspace/documents/search` and `/{id}`) with DocumentSearch UI component embedded in the Documents workspace tab.
- **Verification**: All 9 unit and integration tests in `tests/integration/test_document_search.py` pass; full test suite passes.
