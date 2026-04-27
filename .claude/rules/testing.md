# Testing Rules

## Coverage Gates

- Unit tests: ≥ 80% line coverage required before reviewer approves.
- Integration tests: required for every external API boundary.
- No PR merges with failing tests.

## Fixture Conventions

- All fixtures in `tests/fixtures/`. Filename: `<entity>_<scenario>.json`.
- Use factory functions, not raw dicts, for complex objects.
- Fixtures must be deterministic (no `datetime.now()`, no random seeds without `seed=42`).

## Test Naming

```
test_<unit>_<scenario>_<expected_outcome>
# e.g.: test_backtest_zero_allocation_raises_value_error
```

## Monetary Test Assertions

Always assert with `Decimal`, never `float`:

```python
assert result.amount == Decimal("19.99")  # correct
assert result.amount == 19.99             # FORBIDDEN
```

## Mock Policy

- Mock at the boundary (HTTP client, DB session, IBKR connection), never inside domain logic.
- Use `responses` library for HTTP mocking in Python.
- Integration tests hit real services; no mocks.

## Root Cause Discipline

Before writing any fix, state the hypothesized root cause in one sentence. If the first fix is insufficient, re-diagnose from scratch — do not patch the patch. Symptom-level fixes (caching, retries, clamps) that leave the underlying cause intact are a FAIL.
