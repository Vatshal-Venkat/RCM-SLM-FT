# Training artifacts

Fine-tuning data and LoRA adapters for the RCM SLM (base: `Qwen/Qwen3-1.7B`).
Nothing here is loaded by the backend at runtime — the API serves the quantized GGUF in
`backend/models/`. Runtime data (SQLite DB, RAG index) stays in `backend/data/`.

```text
training/
├── datasets/
│   ├── rcm_terminology_anchor.jsonl   # 46 curated RCM term/concept Q&A rows
│   ├── v2/train.jsonl                 # superseded by v2_1 (kept for lineage)
│   └── v2_1/                          # current dataset
│       ├── train.jsonl                # 1,671 rows
│       ├── validation.jsonl           #   209 rows
│       └── test.jsonl                 #   211 rows
└── adapters/
    └── rcm_qwen3_1.7b_v2_1_lora.zip   # PEFT LoRA trained on v2_1 (git-ignored)
```

## Record format

Alpaca-style JSONL, one object per line:

```json
{"instruction": "...", "input": "...", "output": "...", "category": "..."}
```

`input` is empty for knowledge questions and holds a claim record for claim tasks.

## Dataset versions

| Version | train | validation | test | Notes |
|---|---|---|---|---|
| v2   | 1,668 | 209 | 211 | 42 exact-duplicate train rows |
| v2.1 | 1,671 | 209 | 211 | v2 train de-duplicated (−42) + terminology anchor (+45 new, 1 already present) |

v2 validation/test were byte-identical to v2.1 (same SHA-256), so only `v2/train.jsonl` is kept.

### v2.1 train composition

| Category | Rows | Distinct outputs |
|---|---|---|
| claim_summary  | 800 | 800 |
| claim_review   | 758 | **1** |
| rcm_knowledge  |  46 |  46 |
| kpi_analysis   |  22 |  22 |
| rcm_general    |  21 |  21 |
| comparison     |  17 |  17 |
| rcm_reasoning  |   7 |   7 |

## Adapter: `rcm_qwen3_1.7b_v2_1_lora`

- PEFT 0.21.2, LoRA `r=16`, `alpha=32`, `dropout=0.05`
- Target modules: `q_proj`, `k_proj`, `v_proj`, `o_proj` (attention only)
- Zip also bundles the Qwen3 tokenizer files and chat template
- `training_args.bin` is a pickle — load it only with trusted tooling
- The bundled model card is the unfilled Hugging Face template; no metrics are recorded

The served GGUF (`backend/models/rcm_qwen3_1.7b_q4_k_m.gguf`, dated 2026-10-07) predates
these datasets, so it was **not** built from this adapter. To serve v2.1: merge the
adapter into `Qwen/Qwen3-1.7B`, convert to GGUF with llama.cpp, quantize to Q4_K_M, and
point `MODEL_PATH` at the result.

## Known data-quality issues (v2.1)

1. **ID hallucination in `claim_summary`** — all 800 train and 100 test rows mask IDs in
   the input (`<CLAIM_ID>`, `<PROVIDER_ID>`) but the target output contains the real
   claim and provider IDs. The model is trained to output identifiers it cannot see.
   The outputs should use the same placeholders as the inputs.
2. **`claim_review` is a single answer** — 758 train rows share one instruction and one
   identical output. It is 45% of the training set and teaches nothing input-dependent;
   test accuracy on this category (100 rows) is trivially perfect.
3. **Train/test leakage** — 9 test rows share an exact `(instruction, input)` pair with
   train (7 `claim_review`, plus "What is denial management?" and "What is the purpose
   of an Electronic Remittance Advice?"). One terminology-anchor prompt also appears
   in test.
4. **Small knowledge share** — only ~113 rows (7%) are open RCM knowledge/reasoning;
   claim templating dominates.
5. Validation and test each still contain 1 exact-duplicate row.

## Runtime mitigations (RAG layer)

Until the data is fixed and the model retrained, the serving pipeline compensates:

| Issue | Mitigation | Code |
|---|---|---|
| 1. ID hallucination | Answers may only state claim / payer / provider IDs (and 9+ digit numbers) that appear in the question, data or references; leaked `<..._ID>` placeholders are rejected too. Violations trigger regeneration, and IDs still unsupported are masked as `[unverified ID removed]`. | `backend/app/ai/validators.py`, `ChatService._mask_identifiers` |
| 2. Canned `claim_review` | Chat retrieves on the claim's own facts (CARC, status, category) instead of the question wording, and uses the claim answer layout. | `DataContext.retrieval_query`, `chat_service._format_for` |
| 4. Thin knowledge coverage | The knowledge Q&A is published to RAG as `knowledge/curated_qa.md`. At most one curated pair enters the context, and term definitions always come from the reference documents. | `scripts/build_curated_qa.py`, `backend/app/ai/rag.py` |

`curated_qa.md` excludes questions that appear in validation/test (so evaluation is not
contaminated) and every answer that fails the validated-terms checks. Rebuild it and the
index whenever the datasets change:

```powershell
backend\.venv\Scripts\python scripts\build_curated_qa.py
backend\.venv\Scripts\python scripts\ingest_knowledge.py
```
