# Company Stankey

This project generates auditable quarterly income-statement Sankeys for Meta,
Amazon, and Alphabet. It
emits a canonical SVG with a 1080×1080 viewBox, a matching 3240×3240 PNG master,
and a JSON manifest containing each value's SEC XBRL provenance and all
reconciliation results.

## Run

Python 3.10+ and [uv](https://docs.astral.sh/uv/) are required. `uv sync`
creates an isolated `.venv` from the checked-in lockfile.

```bash
uv sync
uv run stankey generate META --quarter 2026Q2
uv run stankey generate-series META --quarters 20 --from-quarter 2026Q2 \
  --fetch-sec --user-agent 'Your Name your.email@example.com'
uv run stankey discover-filings META --quarters 20 \
  --user-agent 'Your Name your.email@example.com' \
  --output outputs/meta/META_discovered_filings.json
uv run pytest
```

Amazon uses the same workflow and resolves its company config automatically:

```bash
uv run stankey discover-filings AMZN --quarters 20 --from-quarter 2026Q2 \
  --user-agent 'Your Name your.email@example.com' \
  --output outputs/amazon/AMZN_discovered_filings.json
uv run stankey generate-series AMZN --quarters 20 --from-quarter 2026Q2 \
  --fetch-sec --user-agent 'Your Name your.email@example.com'
```

Amazon assets are written under `outputs/amazon/`, including the flat set of
all masters in `outputs/amazon/png/`. Amazon's adapter reconciles North America,
International, and AWS sales; its six operating-cost lines; non-operating
income or expense; income-tax benefits or expense; and equity-method activity.
Profit and loss quarters are rendered with sign-aware flows.

Alphabet uses the same workflow and resolves its company config automatically:

```bash
uv run stankey discover-filings GOOGL --quarters 20 --from-quarter 2025Q4 \
  --user-agent 'Your Name your.email@example.com' \
  --output outputs/alphabet/GOOGL_discovered_filings.json
uv run stankey generate-series GOOGL --quarters 4 --from-quarter 2025Q4 \
  --fetch-sec --user-agent 'Your Name your.email@example.com'
```

Alphabet assets are written under `outputs/alphabet/`, including the flat set of
all masters in `outputs/alphabet/png/`. Alphabet's adapter reconciles Google
Services, Google Cloud, and Other Bets revenue against consolidated revenues
(including the intercompany hedging adjustment when Alphabet tags it as a
separate line); its cost of revenues and R&D, sales & marketing, and G&A
operating expenses against total costs and expenses; operating income;
non-operating income or expense; income-tax benefits or expense; and net income.
Gross profit is derived. Profit, loss, and tax-benefit quarters render with
sign-aware flows.

Alphabet tags segment revenue only in some extracted instances, and older
filings tag only a subset. The Google Services, Google Cloud, and Other Bets
cards are drawn only when all three are present; otherwise they are skipped and
the remaining income-statement identities still reconcile. The consolidated
revenue concept also varies by period (older filings use
`RevenueFromContractWithCustomerExcludingAssessedTax`, newer ones use
`Revenues`), as does the pre-tax income concept, and each variant is matched
automatically.

`discover-filings` reads the company's SEC submissions history, follows historical
submission pages when the recent feed is not deep enough, resolves each filing's
extracted XBRL instance, and emits configuration-ready entries under `quarters`.
It does not modify the company config. Use `--from-quarter 2026Q2` to
pin the newest requested quarter, or omit it to start at the latest reported
filing. Discovered Q4 entries include a warning because 10-K filings generally
require annual-minus-nine-month derivation; `generate-series` performs that
derivation automatically.

`generate-series` starts at the latest configured reported quarter and walks
backward in fiscal-quarter order. With `--fetch-sec`, missing quarter metadata
is discovered automatically. Q4 values are derived as the annual 10-K value
minus the corresponding nine-month 10-Q value, with both sources retained in
provenance. Each quarter gets an isolated output folder:

```text
outputs/meta/
  png/
    01_META_2026_Q2.png
    02_META_2026_Q1.png
    ...
    20_META_2021_Q3.png
  2026Q2/
    01_META_2026_Q2.svg
    01_META_2026_Q2.png
    01_META_2026_Q2.json
  2026Q1/
    02_META_2026_Q1.svg
    02_META_2026_Q1.png
    02_META_2026_Q1.json
  ...
  META_2026Q2_20_quarters.json
```

Use `--from-quarter 2025Q4` to reproduce a range from a specific point. The
command validates that every requested quarter has source metadata before
starting generation.

The PNG is rasterized from the exact saved SVG with resvg, so there is only
one layout implementation. Override the square master size when needed, for
example `--png-size 2160`. resvg supports the SVG features used here:
paths, fills and opacity, rectangles, strokes/dashes, and text. Font metrics can
still vary when a different system font is selected from the SVG's fallback
list.

The default is reproducible and offline: it reads the checked-in subset of
facts extracted from Meta's SEC XBRL instance. To re-download and parse the
official instance, identify yourself to the SEC:

```bash
uv run stankey generate META --quarter 2026Q2 --fetch-sec \
  --user-agent 'Your Name your.email@example.com'
```

Outputs are written to `outputs/meta/01_META_2026_Q2.{svg,png,json}`. Downloads
are cached under `data/raw/meta/0001628280-26-050705/` and are not committed.

## MVP limitations

- The checked-in offline fixture covers only `META 2026Q2`; Amazon, Alphabet, and historical
  series generation requires live SEC access with `--fetch-sec`.
- Values are GAAP and normalized to USD millions. Form 10-Q figures are
  unaudited, and Q4 values are derived as annual minus nine months.
- Gross profit is derived because Meta does not report it as a separate fact.
- Segment/product revenue comes from company-specific XBRL dimensions. Mapping
  it is deterministic but company-specific.
- The layout uses reviewed company-specific flow columns with deterministic
  label lanes. Amazon profit/loss and income/expense sign changes are supported;
  negative consolidated operating-profit quarters are not yet supported.
- The PNG is derived directly from the SVG; text rasterization can still vary
  by platform font availability.
