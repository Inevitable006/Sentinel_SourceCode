# Readiness API contract — version 1

Owner: Codex. Status: IMPLEMENTED and backend-tested (640 tests pass, 2026-10-31). A1 integration review is in progress. Changes require a versioned update recorded in CODEX_STATUS before either side depends on them.

`GET /api/workspace/readiness`

Uses the existing session header and unlocked-owner dependency. No new auth scheme. Read-only local status: no download, inference/model load, provider call, microphone access, filesystem write or change to owner settings.

Successful response:

```json
{
  "version": 1,
  "checks": [
    {
      "id": "document_search",
      "label": "Document meaning search",
      "state": "setup_required",
      "detail": "Some saved documents still need preparation in Workspace → Documents."
    }
  ]
}
```

The example is synthetic. Do not ship it as runtime fallback.

All fields shown are required. `checks` contains at most six unique IDs from this list: `chat`, `dictation`, `speech`, `document_search`, `google`, `backup`. The backend normally returns all six. Each `label` is nonempty, at most 80 characters; `detail` is nonempty, at most 400 characters. Do not include filenames, accounts, tokens, user content, raw exceptions or raw provider responses.

`state` is one of:
- `ready`: the specific local readiness check passed; this does not certify hardware, remote account access or every feature in the roadmap.
- `setup_required`: owner setup is missing, such as a model, authorization, prepared documents or backup. Explain the existing screen/action in detail.
- `unavailable`: a capability or dependency cannot currently be used, with a safe explanation.
- `unknown`: the check could not establish readiness. Never translate it into ready.

Semantics:
- **chat:** existing profile/model/runtime availability, without loading the model or claiming a successful conversation.
- **dictation:** existing local recognizer/model status; never imply microphone quality is tested.
- **speech:** initialized local speech-engine availability; do not synthesize audio as part of this request.
- **document_search:** installed model and prepared-document coverage; presence alone is not an integrity verification. No saved/prepared documents is setup_required. Native integrity is checked on actual use.
- **google:** configured/stored authorization state only; ready wording must explicitly say live access has not been checked. Never call Google to compute this status.
- **backup:** a known existing local backup record, not proof that restore on another PC passed. Without one, setup_required.

The API does not return arbitrary URLs, HTML, executable actions or a global readiness boolean. Each check is independently isolated: a failed optional check becomes unknown/unavailable rather than hiding the others. Authentication/lock errors remain request-level errors.

Existing HTTP behavior: missing session header may be 422, invalid session 401, locked 423. A1 must gracefully handle 404 until C1 is integrated, invalid/unsupported response versions, timeout/network failure and retry. On a request-level failure, discard previously displayed readiness data. Do not log the response body. Use existing API helper error semantics.

Frontend checks: known state labels, at most six entries, required fields and supported version. Unknown future IDs may be omitted; an invalid response must not generate positive readiness badges. Text is escaped by React.
