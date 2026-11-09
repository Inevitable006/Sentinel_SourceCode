# Private document search

Save documents in Workspace → Documents. All-words search is available immediately. Meaning search uses a small English embedding model entirely on this PC; it does not send text to a provider.

Choose **Prepare next document** to index one saved document, then choose **Meaning (English)**. Preparation is explicit, bounded to one document per request and two CPU threads. The coverage count shows which documents are ready. An edit removes that document's old vectors immediately; prepare it again. Deleting a document removes its active index entries. Existing backups may still contain the older encrypted database.

Results show source titles and excerpts. Similarity is not confidence: even an unrelated question can produce a nearest result. Verify the source before relying on an answer. The model is English-focused; keyword search remains available for other languages. Chat searches require the existing read-access confirmation. Retrieved instructions are untrusted source text, not authority to run tools.

The index is capped at 10,000 overlapping chunks and shares the existing SQLCipher database, backups and lock lifecycle. Locking, manual cancellation or resource pressure invalidates work; an already-running native inference call may finish before its result is discarded. The model is released after each operation. There is no background file crawling, automatic upload or runtime model download.

## Setup and checks

Run `tools/setup_search_model.ps1` from the source checkout. It downloads only the pinned 36,806,944-byte public GGUF and verifies its SHA-256 before replacement. Run `backend/.venv/Scripts/python.exe tools/smoke_semantic.py` for the synthetic offline native-model check.

Model: [CompendiumLabs BGE small English v1.5 GGUF](https://huggingface.co/CompendiumLabs/bge-small-en-v1.5-gguf), revision `d32f8c040ea3b516330eeb75b72bcc2d3a780ab7`, Q8_0. Upstream: [BAAI BGE small English v1.5](https://huggingface.co/BAAI/bge-small-en-v1.5), published under MIT. Exact hash, dimensions and size are in `backend/embedding-model.json`. Uses the existing pinned llama-cpp-python runtime; no new Python package.

## Verification status, 2026-10-31

The actual local embedding model passes a synthetic offline ranking check and an end-to-end SQLCipher smoke: indexing, source ranking, deletion and refusing locked searches. All 17 document/semantic lifecycle tests and the 627-test backend regression suite pass. Frontend and JavaScript checks pass. The earlier Windows Application Control block no longer reproduces; the agent did not change OS security settings.

The installer now includes only this pinned small model as an explicit resource, with its upstream MIT notice. Other large chat/voice/vision model setup remains separate. For a packaged-runtime check, run `dist/win-unpacked/resources/python/python.exe tools/smoke_semantic.py --backend dist/win-unpacked/resources/backend`. All smoke data is synthetic and temporary.
