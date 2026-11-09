# T-18: Selective Colibri-inspired improvements

Owner authorized using useful Colibri parts, 2026-11-02. Scope: tools/bench_gpu.py, coordination brief and this report. Adapt ideas; do not copy native engines, launch downloaded code, add dependencies/models or change inference routing. Findings: C:/Muthu project/New one/COLIBRI_REVIEW.md.

Immediate backend/tooling work: correct existing benchmark's per-model prompt formatting and distinguish streamed chunks from tokenizer tokens. No new benchmark framework. Validate syntax without starting GPU workloads or touching owner data. AntiGravity gets model-status clarity using the existing API in its own scoped task. Optional Colibri engine adapter remains a separately tested future task, not silently enabled by this adoption.

## Report
Implemented Qwen ChatML versus Llama 3 prompt/stop selection and honest first-chunk/chunks-per-second labels. Syntax checked without importing the benchmark (which creates a temporary profile on import). No performance result or speed improvement claimed; no code copied from Colibri. Real GPU remeasurement remains a separate run.
