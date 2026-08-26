# Meta Quarterly Sankey Image Generator

## Status and Scope

This plan covers the first deliverable only: generate one square income-statement Sankey image for each of Meta's latest 20 reported fiscal quarters, ordered newest first. As of August 26, 2026, the expected range is Q2 2026 through Q3 2021. Each slide is produced as canonical SVG and a 1080×1080 PNG. Posting to Instagram, scheduling, captions, and generalized support for other companies are out of scope.

Success means a reviewer can run one command, inspect the source and derivation of every displayed number, and receive 20 legible, consistently styled images whose flows reconcile to Meta's reports.

## Architecture Decision

Use a deterministic Python pipeline with reviewed Meta-specific mappings. Do not put an LLM in the first numeric extraction path.

```text
SEC submissions + filing documents
              │
              ▼
      immutable raw cache
              │
              ▼
   XBRL/table fact extraction
              │
              ▼
 Meta mapping + quarter selection
              │
              ▼
 validated canonical Quarter model
              │
              ▼
 Sankey graph → SVG → 1080px PNG
              │
              └── provenance/validation manifest
```

Python keeps ingestion, validation, layout, and CLI behavior in one toolchain. Generate SVG directly using templates or a small geometry layer; use cubic paths for flows and fixed layout columns. Rasterize that SVG for PNG so both formats remain visually identical.

### Alternatives Considered

- **SEC Company Facts only:** easiest JSON interface and useful for standard GAAP facts, but it excludes custom taxonomy concepts and facts that are not entity-wide. It is insufficient for maximum segment detail.
- **Filing-level Inline XBRL:** richer facts, dimensions, labels, and provenance. This is the primary extraction source despite greater complexity. Arelle is the preferred parser rather than hand-implementing XBRL semantics.
- **Meta investor-relations releases only:** quarter tables are convenient, especially for Q4, but HTML/PDF layouts can change and provenance is less uniform. Use them as a cross-check and as an explicit fallback for standalone Q4 facts.
- **PDF/OCR extraction:** broad but unnecessarily lossy when structured filings exist. Reserve it for future companies or missing disclosures.
- **LLM-first parsing:** flexible but difficult to reproduce and audit. A future LLM may propose mappings from unfamiliar labels to the canonical schema; it must return citations and confidence, never silently invent or alter values.
- **Plotly:** fast prototype with built-in Sankey support, but offers limited editorial control over fixed labels and dense square composition.
- **D3/browser rendering:** excellent layout control but introduces a second language and browser build pipeline.
- **Custom SVG in Python:** best fit for deterministic, branded static slides and dual SVG/PNG output; recommended for the Meta MVP.

## Data Sources and Provenance

Use Meta's SEC CIK `0001326801`.

1. Discover 10-Q, 10-K, amended filings, and relevant earnings-release 8-K exhibits through the SEC Submissions API.
2. Cache filing index metadata, primary Inline XBRL, extracted XBRL instance, and required taxonomy/linkbase files by accession number.
3. Parse facts with their concept, value, unit, period, dimensions, decimals, filing date, accession number, and source-document URL intact.
4. Select facts from the latest applicable filing, while recording if a later filing restated a prior period.
5. Prefer a true three-month context. A 10-Q can contain both quarterly and year-to-date contexts; they must never be confused.
6. A 10-K normally lacks a standalone Q4 income statement. Prefer Meta's quarterly earnings-release exhibit when it explicitly reports Q4; otherwise derive Q4 as full year minus nine months and mark every affected value as derived.

The SEC APIs are unauthenticated but require a descriptive User-Agent and fair-access throttling below 10 requests per second. Raw downloads are immutable so any image can be reproduced from the exact input.

References:

- SEC EDGAR APIs: https://www.sec.gov/search-filings/edgar-application-programming-interfaces
- SEC access guidance: https://www.sec.gov/about/webmaster-frequently-asked-questions
- Arelle Python API: https://arelle.readthedocs.io/en/latest/python_api/python_api.html
- Meta investor relations: https://investor.atmeta.com/financials/

## Canonical Financial Model

Store money as integer USD millions and preserve the unrounded source value when available. A quarter contains:

- identity: company, ticker, fiscal year/quarter, start/end dates;
- revenue: advertising, other Family of Apps, Reality Labs, and consolidated revenue;
- costs: cost of revenue, R&D, marketing and sales, G&A, and total costs/expenses;
- profit bridge: gross profit, operating income, interest/other income or expense, pretax income, tax provision or benefit, and net income;
- comparison: prior-year value and calculated year-over-year change;
- provenance per fact: reported/derived status, source locator, XBRL context, transformation, and review state.

Gross profit may be calculated as revenue minus cost of revenue and must be marked derived if Meta does not report it. Negative items remain signed in the model but become positive-width graph links with an explicit semantic direction. For example, a tax benefit flows into net income; a tax provision flows out of pretax income.

Each fact receives one status:

- `reported`: directly present in the selected source;
- `derived`: deterministic arithmetic from cited reported facts;
- `mapped`: a reported custom concept assigned through reviewed Meta configuration;
- `unresolved`: excluded from the image and surfaced for review.

## Sankey and Slide Specification

Use a fixed 1080×1080 view box. The intended flow is:

1. Advertising and other revenue feed Family of Apps; Reality Labs and Family of Apps feed total revenue.
2. Revenue splits into cost of revenue and gross profit.
3. Gross profit splits into R&D, marketing and sales, G&A, and operating profit.
4. Operating profit combines with interest/other items to reach pretax income.
5. Pretax income splits into taxes and net income, with direction reversed for a tax benefit.

The layout engine may omit the least material breakdowns when labels would overlap, but it must never merge categories without recording that decision in the manifest. Use a stable materiality/layout rule rather than manual per-quarter positioning.

Every slide includes the company/ticker, fiscal quarter and end date, values in USD billions, year-over-year changes where meaningful, and a compact limitation footer. Visual treatment distinguishes reported from derived values. The footer should state the source family, rounding basis, and whether any facts were derived; the adjacent manifest contains complete URLs and calculations.

Provisional filename order:

```text
outputs/meta/01_META_2026_Q2.svg
outputs/meta/01_META_2026_Q2.png
...
outputs/meta/20_META_2021_Q3.png
```

## Validation and Failure Policy

Validate before rendering:

- segment revenue equals consolidated revenue within reported rounding tolerance;
- revenue minus cost of revenue equals gross profit;
- gross profit minus operating expenses equals operating income;
- operating income plus net non-operating items equals pretax income;
- pretax income minus tax provision, or plus tax benefit, equals net income;
- total expense components equal reported total costs/expenses;
- quarter dates, duration, currency, scale, and prior-year comparison are correct;
- all visible values have provenance and no unresolved value reaches rendering.

Use a default tolerance of $1 million for exact source units, expanded only when display rounding requires it. A failed material reconciliation blocks image generation. Minor rounding differences render only with a recorded warning.

The validation fixture set must include Q1 2026's unusual tax benefit, at least one Q4 derived/fallback quarter, a loss/negative line item, and the oldest quarter in the 20-slide range. Add golden-image tests for geometry and SVG text plus model-level tests for every accounting identity.

## Proposed Repository Layout

```text
pyproject.toml
src/stankey/
  cli.py
  sec.py
  xbrl.py
  models.py
  normalize.py
  validate.py
  graph.py
  render_svg.py
configs/companies/meta.yaml
assets/meta/
data/raw/                 # downloaded, ignored by Git
data/normalized/          # generated, ignored except fixtures
outputs/                  # generated, ignored by Git
tests/fixtures/meta/
tests/
plans/
```

Suggested dependencies are `httpx`, `pydantic`, `arelle-release`, `PyYAML`, and an SVG-to-PNG renderer such as CairoSVG. Pin versions after a one-quarter technical spike verifies installation and rendering behavior.

## Delivery Phases

### Phase 1: One-quarter vertical slice

Implement SEC discovery/cache, extract Q2 2026, define the canonical model, hand-verify it against the filing, and render a plain SVG/PNG. This proves data correctness before visual polish.

### Phase 2: Meta design and edge cases

Implement the square branded layout, provenance footer, tax-benefit handling, Q4 policy, deterministic YoY calculations, and validation manifests. Test Q1 2026 and Q4 2025.

### Phase 3: Twenty-quarter backfill

Ingest Q3 2021 through Q2 2026, resolve taxonomy/segment changes in `meta.yaml`, review every warning, and generate the ordered image set. Produce a machine-readable run summary listing source filings, derived values, omissions, and failures.

### Phase 4: Hardening for repeat runs

Add a CLI such as `stankey generate META --quarters 20`, retries and SEC throttling, reproducible builds, unit/golden tests, and contributor documentation. Generalization to a second company begins only after the Meta set passes review.

## Deferred Product Decisions

Before visual polish, decide whether to use Meta's official logo/assets, whether the house style should closely reproduce the supplied reference or merely its information hierarchy, and how much methodology text can remain legible in a square Instagram image. These choices do not block the Phase 1 data pipeline.
