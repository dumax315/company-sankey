# Adding a Company

This guide walks through adding a new company to the quarterly income-statement
Sankey generator. It reflects the patterns used to add Amazon (`AMZN`) and
Alphabet (`GOOGL`) on top of the original Meta (`META`) implementation. Follow it
in order; each step builds on the last.

Meta is the reference for a company with **product/segment revenue**, Amazon for
**many operating-cost lines + equity-method activity + sign-aware flows**, and
Alphabet for **optional segment disclosure + concept/dimension drift across
periods**. Pick whichever existing adapter is closest to your target and copy it.

## Mental model

The pipeline is config-driven end to end:

```
SEC XBRL instance ──parse_xbrl──▶ flat list of USD facts
        │
        ▼
configs/companies/<slug>.json  (selectors map fact keys ──▶ concept + dimensions)
        │
        ▼
normalize_meta / normalize_meta_q4  ──▶ Quarter(facts={key: FinancialFact})
        │
        ▼
validate_quarter  (per-ticker reconciliation identities)
        │
        ▼
render_svg → _layout_<company> → SVG → resvg → PNG + JSON manifest
```

`normalize_meta`, `normalize_meta_q4`, `discover_filings`, and the CLI are all
**generic** and rarely need per-company changes. The three places you almost
always touch are the **config**, the **validator branch**, and the **layout
function**.

## Step 0 — Investigate the real XBRL first (do not skip)

Concept names, dimension members, and even which line items are tagged **vary by
company and drift over time**. Always inspect the actual filings before writing
the config. Use the project's own parser so you see exactly what the pipeline
will see (`parse_xbrl` keeps only `unitRef == "usd"` duration facts):

```bash
# 1. Find recent filings + accession numbers
curl -s -H 'User-Agent: You you@example.com' \
  'https://data.sec.gov/submissions/CIK0000000000.json' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); r=d['filings']['recent']; \
    [print(r['form'][i], r['accessionNumber'][i], r['reportDate'][i], r['primaryDocument'][i]) \
     for i in range(len(r['accessionNumber'])) if r['form'][i] in ('10-Q','10-K')][:8]"

# 2. Download an XBRL instance (document is <primaryDocument stem>_htm.xml)
curl -s -H 'User-Agent: You you@example.com' \
  'https://www.sec.gov/Archives/edgar/data/<CIK-no-zeros>/<ACCESSION-no-dashes>/<doc>_htm.xml' \
  -o /tmp/inst.xml

# 3. Inventory the income-statement facts for a single 3-month period
uv run python -c "
from src.stankey.sec import parse_xbrl
from pathlib import Path
d = parse_xbrl(Path('/tmp/inst.xml'), {'url':'','accession':'','document':'','filing_date':''})
per = ('2025-04-01','2025-06-30')  # the quarter's start/end
for f in d['facts']:
    if (f['start_date'], f['end_date']) == per:
        print(f['concept'], '|', f['value'], '|', f['dimensions'])
"
```

Confirm, for **several periods across several years** (recent 10-Q, an older
10-Q, and a 10-K):

- The **consolidated revenue** concept (often `Revenues` or
  `RevenueFromContractWithCustomerExcludingAssessedTax`).
- Every **expense** concept and the **total costs & expenses** concept.
- **Operating income**, **non-operating**, **pre-tax**, **income tax**,
  **net income** concepts.
- **Segment/product revenue** concepts and their exact **dimension members**.
- Which lines are **missing** in some periods (very common).

Then hand-verify the reconciliation identities with a calculator before trusting
them (e.g. `sum(segments) + hedging == revenue`, `revenue - cost == gross`,
`gross - opex == operating`, `operating + nonop == pretax`,
`pretax - tax == net`). If an identity does not hold, you have the wrong concept
or a missing adjustment line.

## Step 1 — Create `configs/companies/<slug>.json`

Copy `configs/companies/amazon.json` (or `meta.json`) and edit. Required top-level
keys: `company`, `ticker`, `slug`, `cik` (10 digits, zero-padded), `quarters`
(leave `{}` — discovery fills it), and `selectors`.

Each selector maps a **fact key** to how it is found:

```json
"operating_income": {
  "label": "Operating income",
  "concept": "OperatingIncomeLoss",
  "dimensions": {},
  "status": "reported"
}
```

Selector fields:

- `label` — text shown on the card.
- `concept` — primary XBRL concept (local name, no namespace prefix).
- `dimensions` — exact dimension map, keys are **prefixed** raw attributes
  (`us-gaap:StatementBusinessSegmentsAxis`, `srt:ProductOrServiceAxis`, ...).
  Use `{}` for undimensioned totals.
- `status` — `"reported"`, `"mapped"` (segment/dimension-derived), or
  `"derived"`. `derived` values get a `*` marker on the card.
- `concept`**s** (optional list) — alternate concepts tried in order. Use when a
  line's concept **changes across periods** (see Pitfall A).
- `dimension_options` (optional list) — alternate dimension maps tried in order.
  Use when a **member name changes across periods** (see Pitfall B).
- `multiplier` (optional int, e.g. `-1`) — flip sign for concepts reported with
  the opposite polarity (Amazon's `other_operating_expense`).
- `optional_selectors` (optional top-level array of keys) — see Pitfall C.

Notes:

- `gross_profit` is **derived automatically** by `normalize_meta` as
  `revenue - cost_of_revenue`. Do **not** add a `gross_profit` selector; just
  ensure `revenue` and `cost_of_revenue` exist.
- Fact **keys** are the contract between config, validator, and layout. Whatever
  keys you define here are exactly what you reference in `validate.py` and
  `_layout_<company>`.
- `_select` matches on concept **and** period **and** dimensions **and**
  `unit == usd`, prefers the most precise `decimals`, and errors if the surviving
  matches disagree in value. Duplicate identical values (same number under two
  concept aliases) are fine — they dedupe.

## Step 2 — Add the reconciliation branch in `src/stankey/validate.py`

`validate_quarter` branches on `quarter.ticker.upper()`. Add a branch for your
ticker before the final (Meta) fallback:

```python
if quarter.ticker.upper() == "TICKER":
    checks = [
        _check("revenue less cost equals gross profit",
               f["gross_profit"].value_millions,
               f["revenue"].value_millions - f["cost_of_revenue"].value_millions,
               tolerance_millions),
        # ...one _check per accounting identity...
    ]
    if any(not c.passed for c in checks):
        raise ReconciliationError(checks)
    return checks
```

Guidelines:

- One `_check(name, expected, actual, tolerance)` per identity. `expected` is the
  reported figure; `actual` is what you compute from components.
- Default tolerance is `1` (USD million) to absorb rounding.
- **Gate optional identities on fact presence.** If a line (e.g. segment revenue,
  hedging adjustment) is not tagged in every period, only add its `_check` when
  the required keys are in `f`:

  ```python
  if all(k in f for k in segment_keys) and "hedging_revenue" in f:
      checks.append(_check("segments plus hedging equals revenue", ...))
  ```

  This is why Alphabet's segment check is conditional — see Pitfall C/D.

## Step 3 — Add the layout in `src/stankey/render.py`

Copy `_layout_amazon` (richest example) or `_layout_alphabet` (optional segments)
into a new `_layout_<company>` and adjust. A layout returns
`(list[Node], list[Ribbon])`.

- `Node(key, x, y, height, color)` — a bar; `right == x + 22`. Heights scale from
  values via `h_of(f, key)` (default `scale = 0.8/1000` USD-millions→px). Colors:
  `BLUE` revenue, `GREEN` profit, `PINK` cost/expense.
- `Ribbon(source_key, target_key, source_x, source_y, target_x, target_y, width, color)`
  — a flow. Widths must **balance**: the sum of a node's incoming widths equals
  its height, likewise outgoing.
- Use `_packed_flows(nodes, source_values, target_values, income_key, width_value,
  income_target=...)` to route a set of balanced sources into ordered targets
  (used for the operating and post-tax bridges). Split contributions by sign so
  losses and tax **benefits** render as honest flows (see the Amazon/Alphabet
  post-tax blocks).
- Keep `net_income` the **rightmost** terminal node — `_validate_terminal_order`
  enforces this.
- Column x-positions used so far: revenue segments ~190–210, revenue ~289–300,
  gross/cost ~479–486, operating + opex ~663, pre-tax/non-op/tax ~851, net ~873.

Then wire the ticker into the four dispatchers (search for the existing tickers):

1. `_layout(quarter)` — add `if quarter.ticker.upper() == "TICKER": return _layout_<company>(quarter)`.
2. `_label_font_sizes(quarter)` — add your ticker to the larger-font tuple if you
   want 18/16pt cards (`("AMZN", "GOOGL", "TICKER")`) or leave it on the 16/14 default.
3. Add a `TICKER_LABEL_KEYS` tuple listing every card key in draw order.
4. In `render_svg`, extend the `label_keys` selection to pick `TICKER_LABEL_KEYS`
   for your ticker. The existing code already filters to keys that are **both**
   in `quarter.facts` **and** in the built nodes, so optional lines that you did
   not draw are skipped automatically.

## Step 4 — Wire the CLI in `src/stankey/cli.py`

Add one line to `COMPANY_CONFIGS`:

```python
COMPANY_CONFIGS = {
    "META": DEFAULT_CONFIG,
    "AMZN": PROJECT_ROOT / "configs" / "companies" / "amazon.json",
    "GOOGL": PROJECT_ROOT / "configs" / "companies" / "alphabet.json",
    "TICKER": PROJECT_ROOT / "configs" / "companies" / "<slug>.json",
}
```

Outputs land under `outputs/<slug>/` automatically (via the config `slug`).
Discovery, series generation, and Q4 derivation are generic and need no changes
unless your company has Meta-style recast quirks (see `generate()` in `cli.py`).

## Step 5 — Add `tests/test_<company>.py`

Copy `tests/test_amazon.py` or `tests/test_alphabet.py`. Build `Quarter` objects
directly from real filing numbers (no network) and assert:

- Every reconciliation identity passes (`all(c.passed for c in validate_quarter(q))`).
- A deliberately broken figure raises `ReconciliationError`.
- Rendering succeeds and produces the expected label-card count.
- A **loss / tax-benefit** quarter reconciles and renders (exercises sign-aware
  flows), even if you have to construct a hypothetical one.
- If any line is optional, test both the present and absent cases.

Write any sample artifacts under `outputs/<slug>/` (not `/tmp`), so they are
inspectable.

## Step 6 — Verify

```bash
uv run pytest
uv run stankey generate-series TICKER --quarters 4 --from-quarter 2025Q4 \
  --fetch-sec --user-agent 'You you@example.com'
```

Then confirm the SVGs are clean. `render_svg` already raises on card-vs-card
collisions and bad terminal order, so successful generation covers a lot. For an
independent check of **edge overflow** and **cards obscuring nodes**, audit
against the authoritative node rectangles `(x, y, x+22, y+height)` — not the raw
SVG path extents, which include bezier control points and will produce false
positives. See the audit snippet pattern used during the Alphabet work:
render each quarter's layout, compute card bounds via `_label_card_bounds`, and
assert no card falls outside `0..WIDTH/HEIGHT` and no card covers >50% of any
other node's rectangle.

Finally, render 20 quarters (`--quarters 20`) to shake out historical concept and
member drift, and eyeball a few PNGs — including the **oldest** quarter, which is
most likely to use legacy concepts.

Update `README.md` with a usage block for the new company.

## Pitfalls learned the hard way

**A. The consolidated revenue (or pre-tax) concept changes across periods.**
Alphabet's total revenue is `RevenueFromContractWithCustomerExcludingAssessedTax`
in early-2025 and older filings but `Revenues` in mid-2025+. Its pre-tax concept
is `...ExtraordinaryItemsNoncontrollingInterest` in recent filings and
`...MinorityInterestAndIncomeLossFromEquityMethodInvestments` in 2021–2022. Handle
with a `concepts: [...]` fallback list (primary first). Only one variant is
present per period, so `_select` dedupes cleanly.

**B. Dimension member names change across periods.**
Alphabet renamed segment members between 2022 and 2023:
`goog:GoogleServicesSegmentMember` → `goog:GoogleServicesMember` (same for Cloud;
Other Bets stayed `us-gaap:AllOtherSegmentsMember`). Handle with
`dimension_options: [...]`. If you only map the new names, older filings silently
drop those lines.

**C. Some lines are not tagged in every filing → make them optional.**
Add their keys to a top-level `optional_selectors` array in the config.
`normalize_meta`/`normalize_meta_q4` then **skip** (rather than fail on) an
optional selector whose current-period fact is absent, and the key simply won't
appear in `quarter.facts`. Cumulative periods in 10-Ks/10-Ks may omit
single-axis segment revenue even when the standalone quarter tags it.

**D. Reconciliation and layout must both handle absent optional lines.**
- Validator: gate the optional identity's `_check` on the keys being present
  (Step 2). Alphabet's segment identity also requires the separately-tagged
  hedging line, because some quarters fold the hedging adjustment into the
  consolidated total instead of tagging it — without the tagged line the sum
  legitimately will not match, so do not enforce it.
- Layout: only draw a group when it is **complete**. Alphabet draws the segment
  column only when **all three** segments are present; otherwise a lone tiny
  segment (Other Bets kept its member name) would appear to feed the entire
  revenue node. Suppress partial groups.

**E. Sign-aware flows.**
Losses (negative operating/pre-tax/net) and tax **benefits** (negative income
tax) must render as flows in the correct direction. Reuse the sign-splitting
pattern: partition contributions into positive "sources" and negative "targets"
(recast by whether the destination is itself income or loss), then route them
with `_packed_flows`. Do not assume every quarter is profitable.

**F. `parse_xbrl` only keeps `unitRef == "usd"` duration facts.**
Per-share values, shares outstanding, and instant (balance-sheet) facts are not
in the parsed set. Everything you map must be a USD duration fact.

**G. Verify against the real data, not assumptions.**
Every surprise above was found by parsing actual instances across multiple
periods. A config that reconciles for one quarter can fail three years back.
Always run the 20-quarter series before declaring done.
