# Prompt: Extend META history by supporting older segment disclosures

## Goal
Extend the Meta (META) SEC-XBRL Sankey series further back than its current
ceiling of **20 quarters (2021Q3 → 2026Q2)** by making the adapter tolerate the
segment-revenue disclosures Meta used in older filings, the way the Alphabet
(GOOGL) adapter was made to tolerate optional segment lines.

## Why META currently stops at 2021Q3
When `generate-series META --quarters N --from-quarter 2026Q2 --fetch-sec`
requests more than 20 quarters, generation aborts at **2021Q2** with:

```
error: No fact for ['RevenueFromContractWithCustomerExcludingAssessedTax'] in
2021-04-01..2021-06-30 with dimensions
[{'srt:ProductOrServiceAxis': 'us-gaap:AdvertisingMember',
  'us-gaap:StatementBusinessSegmentsAxis': 'meta:FamilyOfAppsMember'}]
```

Two distinct walls exist, discovered by single-quarter probes
(`generate-series META --quarters 1 --from-quarter <Q> --fetch-sec`):

1. **2021Q2 and older (down to ~2016): segment dimension mismatch.** The
   required selector asks for advertising revenue dimensioned by
   `us-gaap:StatementBusinessSegmentsAxis = meta:FamilyOfAppsMember`. Meta did
   not report the "Family of Apps" (FoA) / "Reality Labs" (RL) two-segment
   structure until FY2021 (first disclosed in the Q4 2021 10-K, recast for
   2021). Before that, Meta reported a **single reportable segment** and broke
   revenue down only by *product/service* (Advertising vs. Other revenue) using
   `srt:ProductOrServiceAxis`, without the `StatementBusinessSegmentsAxis`
   segment member. So the FoA-dimensioned fact simply does not exist in
   pre-2021Q2 instances.

2. **Pre-2016 (roughly 2015 and earlier): XBRL instance URL 404.** Example:
   `https://www.sec.gov/Archives/edgar/data/1326801/000132680116000043/fb-12312015x10k_htm.xml`
   returns HTTP 404. This is a hard data-availability wall (the extracted
   `_htm.xml` instance does not exist at the path the discovery step derives).
   **This wall is NOT fixable by segment changes** — do not spend time on it.
   The realistic reachable floor for this task is therefore ~2016, i.e. roughly
   40+ quarters, not the full history.

## What to change (mirror the GOOGL fix pattern)
The GOOGL adapter already demonstrates the pattern for tolerating segment
disclosure drift. See how it was done for the EU fine and segment optionality:
- `configs/companies/alphabet.json`: `optional_selectors`, plus selectors that
  use `dimension_options` (a list of alternative dimension dicts) and
  `concepts` (a list of alternative concept names) so one selector matches
  several filing vintages.
- `src/sankey/companies/alphabet.py`: `layout()` draws the segment column only
  when `all(key in f for key in _ALL_SEGMENT_KEYS)`, and `build_checks()` only
  asserts the segment identity when the segment facts are present. Optional
  lines are skipped gracefully when absent.
- Normalization support already exists in `src/sankey/normalize.py`: any key
  listed in a config's `optional_selectors` is skipped (rather than raising)
  when its fact is missing for a period. Selectors also support `concepts`
  (alternative concept names) and `dimension_options` (alternative dimension
  dicts) — use these to absorb drift without new code.

### Concrete steps
1. Inspect `configs/companies/meta.json` and `src/sankey/companies/meta.py` to
   see how Meta's segment/product revenue selectors are currently defined
   (the FoA/RL segment keys and the advertising selector that carries the
   `meta:FamilyOfAppsMember` dimension).
2. Add `dimension_options` to the affected revenue selector(s) so they match
   BOTH the modern FoA-segment-dimensioned facts AND the older product-only
   facts (advertising revenue dimensioned by `srt:ProductOrServiceAxis`
   advertising member with NO `StatementBusinessSegmentsAxis`). Confirm the
   exact older dimension members by dumping raw facts from a pre-2021 instance
   (e.g. 2020Q4, 2019Q4) — a `LossContingencyLossInPeriod`-style raw dump like
   the GOOGL diagnosis is the reliable way to read the actual tagged
   dimensions.
3. Make any segment breakdown that only exists post-2021 **optional** (add its
   keys to `optional_selectors`), and guard both the layout and the
   segment-identity check on the presence of all segment keys — exactly as the
   Alphabet adapter does with `_ALL_SEGMENT_KEYS`.
4. Ensure the non-segment income-statement identities (revenue → gross profit →
   operating income → pre-tax → net income) still reconcile for the older
   quarters; those tags are standard and should be present. If an older quarter
   fails on a DIFFERENT missing/uncaptured line (like Amazon's 2019Q4
   `OtherOperatingIncomeExpenseNet` or GOOGL's 2019Q1 EU fine), handle it the
   same optional-selector way, but only if it is genuinely an income-statement
   line item Meta reported separately.

## Verification
- Run the test suite (must stay green):
  `uv run --with pytest python -m pytest -q`  (expected: all pass; currently 68).
- Probe the new floor with single-quarter runs before doing a full series:
  `uv run sankey generate-series META --quarters 1 --from-quarter 2020Q4 --fetch-sec`
  (SEC_USER_AGENT must be set — see AGENTS.md:
  `export SEC_USER_AGENT='Theodore Halpern theomhalpern@gmail.com'`).
- Once single quarters pass down to the ~2016 floor, run the full series ONCE
  at the count that reaches the oldest working quarter (do NOT loop the full
  series with decreasing counts — it re-downloads and re-renders everything and
  is very slow). `generate-series` walks newest→oldest and aborts at the first
  failing quarter, naming it, so: run once at the max, read the failing quarter
  from the error, then run once more at (its index − 1).
- Add/extend a test in `tests/test_meta.py` (or the existing Meta test) that
  asserts an older product-only quarter reconciles and that the segment column
  is omitted when segment facts are absent — mirror `tests/test_alphabet.py`.

## Guardrails / scope
- Do NOT attempt to defeat the pre-2016 404 wall (category 2 above).
- Keep every value provenance-backed and let reconciliation stay authoritative:
  never fabricate or plug a segment figure to force a check to pass.
- Preserve the existing 20-quarter output and behavior for 2021Q3→2026Q2.
- Match existing code style; the change should be mostly config
  (`dimension_options` / `optional_selectors`) plus small guarded layout/check
  edits, not a rewrite.
