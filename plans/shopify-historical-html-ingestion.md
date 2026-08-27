# Shopify Historical HTML Ingestion Plan

## Goal

Extend the SHOP series from the six standard-XBRL quarters currently supported
(`2025Q1` through `2026Q2`) to 20 quarters (`2021Q3` through `2026Q2`) without
weakening the pipeline's reconciliation or provenance guarantees.

Shopify filed quarterly financial statements on Form 6-K before 2025. Those
filings are ordinary HTML, not Inline XBRL. The current `parse_xbrl` path cannot
read them, but each results filing includes an HTML financial-statements exhibit
(typically Exhibit 99.1) containing the required current and comparative income
statement tables.

## Filing coverage

The target 20-quarter sequence is:

- Existing XBRL path: `2025Q1` through `2026Q2`.
- Historical HTML 6-K path: Q1, Q2, and Q3 of 2021 through 2024, beginning with
  `2021Q3` for this series.
- Q4 derivation: annual XBRL Form 40-F/10-K facts minus the corresponding
  nine-month facts parsed from the Q3 HTML 6-K.

Confirmed historical filing pattern:

- Quarterly results use a results Form 6-K plus a separate press-release Form
  6-K with the same report date. Discovery must select the results filing, not
  the press release.
- The results filing is a wrapper. Its filing-directory index identifies the
  financial-statements exhibit, such as
  `exhibit991financialstateme.htm` for 2024Q3.
- Annual Forms 40-F are Inline XBRL and can continue through the existing XBRL
  parser. Shopify's 2024 annual report is a Form 10-K and is already supported.

## Design

### 1. Make discovery source-format aware

Add narrowly scoped configuration for alternate filing forms rather than
changing the global `10-Q`/`10-K` assumptions for every company.

For SHOP:

- Treat results Forms 6-K as Q1-Q3 sources before 2025.
- Prefer primary-document names containing the quarter and `results`; reject
  press-release and AGM-results filings.
- Treat Forms 40-F as annual Q4 sources before 2025.
- Resolve the financial-statements exhibit from `index.json` and store its URL
  and document name in the discovered source metadata.
- Add a source-format marker such as `"format": "shopify_html"`; retain
  `"format": "xbrl"` as the default for existing configurations.

Discovery tests must cover duplicate same-date 6-K candidates, exhibit
selection, 40-F Q4 selection, and an uninterrupted 20-quarter manifest.

### 2. Add a Shopify HTML financial-statement parser

Implement the parser with Python's standard-library `html.parser`; avoid a new
runtime dependency unless the real filings demonstrate that the standard
library cannot preserve the required table structure reliably.

The parser should:

- Locate the condensed consolidated statement of operations and comprehensive
  income/loss.
- Preserve row labels, column headings, signs, and units.
- Extract both three-month and nine-month columns, plus comparative prior-year
  columns where present.
- Extract the subscription-solutions and merchant-solutions revenue breakdown
  from the revenue note when it is not present on the face statement.
- Emit the same neutral extracted-fact shape as `parse_xbrl`: concept/key,
  integer USD value, start/end dates, context identifier, dimensions, unit, and
  precision metadata.
- Use stable synthetic concepts and dimensions only for facts sourced from HTML
  rows. Keep their names explicit (for example,
  `shop-html:SubscriptionSolutionsRevenue`) so they cannot be mistaken for
  filed XBRL concepts.
- Include the exact SEC exhibit URL, accession, document, filing date, table
  title, row label, and column heading in provenance. Extend the provenance
  model only where necessary to retain that evidence.

The parser must fail on ambiguous tables, duplicate conflicting rows, missing
units, unrecognized periods, or values that are not whole USD millions.

### 3. Dispatch fetching by source format

Replace the XBRL-only CLI fetch helper with a generic filing-source fetch:

- XBRL source: existing download and `parse_xbrl` behavior.
- `shopify_html` source: download the resolved Exhibit 99.1 document and run the
  Shopify HTML parser.

Keep SEC caching, fair-access pacing, and the required identifying User-Agent
for both paths. Manifests should describe whether a quarter used downloaded SEC
XBRL, downloaded SEC HTML, or a mixed annual-XBRL-minus-nine-month-HTML Q4
derivation.

### 4. Normalize through the existing selectors

Prefer translating HTML rows into the existing fact-selection contract so the
normalizer, adapter, checks, and renderer remain shared.

- Add HTML concept fallbacks to the SHOP selectors.
- Use product/service dimensions compatible with the current subscription and
  merchant selectors, or add explicit HTML dimension fallbacks if required.
- Verify revenue and pre-tax concept drift across every filing year.
- Continue deriving gross profit from revenue minus cost of revenue.
- Continue deriving Q4 as annual minus nine months, allowing the annual input
  to be XBRL and the nine-month input to be HTML.

### 5. Build filing-backed regression fixtures

Check in compact extracted fixtures, not entire SEC filings, for representative
cases:

- A 2024 quarter using the newest HTML structure.
- A 2021 quarter using the oldest structure in the target series.
- A historical Q3 nine-month input paired with a 40-F annual input for Q4.
- At least one pre-tax/net loss and one tax-benefit period.

Tests should assert exact values, periods, signs, comparative values, source
documents, table/row provenance, all reconciliation identities, and successful
rendering.

### 6. Verify all 20 quarters

Run:

```bash
uv run pytest
uv run stankey discover-filings SHOP --quarters 20 --from-quarter 2026Q2 \
  --user-agent 'Theodore Halpern theomhalpern@gmail.com'
uv run stankey generate-series SHOP --quarters 20 --from-quarter 2026Q2 \
  --fetch-sec --user-agent 'Theodore Halpern theomhalpern@gmail.com'
```

For every generated quarter:

- Require every accounting reconciliation to pass within USD 1 million.
- Audit label-card bounds and node obstruction using authoritative node
  rectangles.
- Visually inspect the newest quarter, oldest quarter, each Q4 derivation, and
  all loss/tax-benefit outliers.
- Confirm 20 numbered 3240×3240 PNG masters exist under
  `outputs/shopify/png/`.
- Copy the final PNG masters into the main checkout's output directory only
  after the full series passes.

## Accounting identities

Historical HTML inputs must satisfy the same adapter checks as current XBRL
inputs:

1. Subscription solutions + merchant solutions = revenue.
2. Revenue − cost of revenues = gross profit.
3. Sales and marketing + R&D + G&A + transaction and loan losses = operating
   expenses.
4. Gross profit − operating expenses = operating income/loss.
5. Operating income/loss + non-operating income/expense = pre-tax income/loss.
6. Pre-tax income/loss − income-tax expense/benefit = net income/loss.

Any historical filing that does not reconcile should stop generation for manual
review; the parser must not invent balancing adjustments.

## Risks and mitigations

- **HTML structure drift:** use table titles and semantic row labels rather than
  fixed table indexes or CSS classes; cover oldest and newest structures.
- **Duplicate 6-K filings:** filter on the results-document naming pattern and
  confirm the financial-statements exhibit exists.
- **Sign loss from parentheses:** parse displayed accounting notation before
  stripping markup and test negative investment gains/losses and tax benefits.
- **Three-month versus nine-month confusion:** derive periods from table headers
  and filing report date; reject ambiguous column sets.
- **Non-XBRL provenance:** label HTML-derived facts explicitly and retain filing,
  exhibit, table, row, and column evidence in the manifest.
- **Q4 mixed inputs:** test annual-XBRL-minus-nine-month-HTML normalization as a
  first-class case rather than assuming both inputs share a parser.

## Completion criteria

The historical extension is complete only when discovery returns all 20
quarters, live generation produces all 20 validated PNGs, representative HTML
fixtures make the path reproducibly testable offline, provenance distinguishes
HTML facts from XBRL facts, and the README no longer describes six quarters as
SHOP's maximum supported history.
