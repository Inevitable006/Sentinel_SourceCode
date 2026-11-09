# Approved-effect broker: implementation design

Status: design only, 2026-11-01. No broker endpoint, transport or new permission is enabled. Four pure calculators are already contained (T-16). This document defines the next backend increment without changing AntiGravity's interfaces.

## Existing boundaries to preserve

- SecureRunner checks owner skill switches, hourly limits, policy and exact-argument confirmation; consumes a single-use approval token; sets current_job, current_approval and egress tool_context around execution.
- file_ops.preview/apply enforce approved targets, fingerprints, containment and undo. The token-backed preview association must stay in the parent.
- egress and network_utils enforce outbound permission and address validation. A worker must never select arbitrary hosts or acquire a reusable HTTP client.
- SkillRouter currently injects memory callbacks into in-process skills. These callbacks cannot be serialized or passed into workers.
- document_analysis has an empty capability list despite approved read/search behavior. Do not treat absence of declared capabilities as permission to read, and do not grant every action described in a manifest. Introduce explicit reviewed operation mappings per migrated tool.

## Parent-owned request authority

Create one in-memory authority only after existing approval and resource checks succeed. Bind it to the canonical tool, a frozen deep copy of validated arguments, the verified module hash, request/job ID, lock generation, deadline and an explicit operation budget. Store approval/preview state only in the parent. No token, key, parent callback or full environment crosses the process boundary.

The child is attached to that authority by its dedicated inherited pipes, not by a worker-supplied session/request ID. A random child-visible request handle, if needed, is only a correlation label, never independent authorization. Requests cannot switch tool, owner, paths or permissions. Parse JSON data only; no pickle, eval, dotted-function lookup or arbitrary method dispatch.

On lock, cancellation, timeout, child exit, protocol violation or completion: revoke authority, close transport and terminate the child. Refuse late replies even after unlock. Check revocation immediately before effects and before releasing results. Never replay a mutation automatically after an ambiguous crash. Record the outcome as uncertain if the parent cannot establish whether the effect committed; inspect existing action/undo records rather than repeat it.

## Smallest useful first adapter

Start with one approved, bounded read operation; do not implement network or mutations in the initial broker. The worker requests an operation enum and monotonic sequence number. The parent supplies the target from frozen approved arguments, not from a fresh worker path. Reject extra fields, unknown operations, repeated/out-of-order sequence numbers and requests beyond budget before touching storage.

Use existing document path/read validation rather than introducing a broader filesystem resolver. Before migration, separate trusted path/bounded byte acquisition from untrusted format parsing in a scoped task. Plain-text reading can move first; archive/PDF parsers remain explicitly in-process until a dependency-compatible worker exists. Do not claim document isolation if the parent still parses the document.

Limits proposed for initial transport: 8 KiB request frame, 16 KiB text result frame, one read per approved call, one outstanding message, 15-second wall deadline. Enforce byte lengths before allocation, reject partial frames/invalid UTF-8/nonfinite JSON, and account for total output. These are proposed defaults, not current runtime guarantees. Do not silently change existing document output behavior; use explicit truncation/error metadata.

## Migration order

1. Parent authority lifecycle and deny-by-default dispatch, with in-memory tests only. No production route yet.
2. Bounded pipe transport and one read adapter, real crash/cancel/lock tests, then activate only the explicitly migrated tool.
3. Database reads through narrow result DTOs; queries and limits remain parent-owned, encrypted connections never leave it.
4. File mutations through existing preview/apply/undo only. Preserve exact approved arguments and conflict checks; no child-selected destination or retry on uncertain completion.
5. Network actions through existing egress context and validated endpoints; offline changes revoke pending work. No direct sockets in children.

All other skills keep their existing execution path until their adapter is verified. No generic broker fallback and no in-process fallback for a tool already migrated to containment.

## Required evidence before activation

Prove: no authority before approval; changed arguments/token reuse refused; disabled/rate-limited skills cannot start; unknown operation/extra fields/oversized frame refused before effect; duplicate request causes at most one effect; lock/cancel/expiry prevent later effects; late replies discarded; child crash/EOF releases resources; output caps hold; private errors and request credentials never appear in child messages/logs. Keep fixtures synthetic and storage isolated. Use existing end-to-end approval tests in addition to unit tests.

Release notes must list the exact tools migrated and those still in-process. Audit hooks and Windows Job Objects are containment for trusted built-ins, not a hostile-code OS security boundary. Independent security review and clean-machine verification remain separate evidence.
