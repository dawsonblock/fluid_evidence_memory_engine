# Extraction Baseline - FEME v0.8.2

## Fixture

- Fixture name: `tests/fixtures/extraction/project_decisions.jsonl`
- Extractor mode: `heuristic`
- Extractor provider: `None` (default heuristic path)

## Command

```bash
feme eval-extraction --fixture tests/fixtures/extraction/project_decisions.jsonl
```

Equivalent Python helper used for the current baseline:

```bash
PYTHONPATH=$PWD:src .venv/bin/python - <<'PY'
from feme.eval import evaluate_extraction_fixture
print(evaluate_extraction_fixture(
    'tests/fixtures/extraction/project_decisions.jsonl',
    extractor_mode='heuristic',
))
PY
```

## Current Output Metrics

```json
{
  "case_count": 2,
  "claim_count_accuracy": 1.0,
  "support_span_exact_match": 0.0,
  "quote_exact_match": 1.0,
  "fallback_rate": 1.0,
  "strict_rejection_rate": 0.0
}
```

## Interpretation

The default heuristic extractor is still not suitable for serious legal or court-record extraction without review. On the current fixture, claim-count and quote-match behavior improved, but exact support-span boundaries still miss because sentence-level spans include trailing punctuation while fixture spans currently do not.

## Known Weakness

- Exact support spans are not yet reliable on the baseline fixture.
- High-quality structured extraction depends on the configured LLM or local provider plus schema validation and repair behavior.

## Next Improvement Target

- Use `feme eval-extraction --fixture tests/fixtures/extraction/project_decisions.jsonl --verbose` to inspect miss reasons case by case.
- Improve the low-risk heuristic patterns for `must use`, `should use`, `uses`, `configured to use`, `stores`, `links`, `requires`, `replaces`, and `contradicts`.
- Keep strict structured extraction fail-closed and expand mocked provider coverage before relying on real external LLM responses.
