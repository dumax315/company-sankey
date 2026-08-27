# Company Stankey

This project generates auditable quarterly income-statement Sankeys for Meta,
Amazon, Alphabet, Shopify, JPMorgan Chase, ExxonMobil, and Micron. It
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
uv run stankey discover-filings GOOGL --quarters 20 --from-quarter 2026Q2 \
  --user-agent 'Your Name your.email@example.com' \
  --output outputs/alphabet/GOOGL_discovered_filings.json
uv run stankey generate-series GOOGL --quarters 20 --from-quarter 2026Q2 \
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

Shopify uses the same workflow for the six continuous standard-XBRL quarters
available since it began filing Forms 10-Q and 10-K in 2025:

```bash
uv run stankey discover-filings SHOP --quarters 6 --from-quarter 2026Q2 \
  --user-agent 'Your Name your.email@example.com' \
  --output outputs/shopify/SHOP_discovered_filings.json
uv run stankey generate-series SHOP --quarters 6 --from-quarter 2026Q2 \
  --fetch-sec --user-agent 'Your Name your.email@example.com'
```

Shopify assets are written under `outputs/shopify/`. The adapter reconciles
subscription-solutions and merchant-solutions revenue to total revenue; cost of
revenues to gross profit; sales and marketing, R&D, G&A, and transaction and
loan losses to operating expenses and operating income; and net other income or
expense and income tax to net income. Profit, loss, and tax-benefit quarters
render with sign-aware flows. The selectors also handle Shopify's revenue and
pre-tax concept changes across annual and quarterly filings.

Shopify's pre-2025 quarterly results were furnished on non-XBRL Forms 6-K, so
the SEC-XBRL pipeline cannot generate a continuous series before 2025Q1. Its
older annual Forms 40-F are XBRL-tagged, but they do not provide the standalone
quarterly facts needed by this project.

ExxonMobil uses the same workflow and resolves its company config automatically:

```bash
uv run stankey discover-filings XOM --quarters 20 --from-quarter 2026Q2 \
  --user-agent 'Your Name your.email@example.com' \
  --output outputs/exxon/XOM_discovered_filings.json
uv run stankey generate-series XOM --quarters 20 --from-quarter 2026Q2 \
  --fetch-sec --user-agent 'Your Name your.email@example.com'
```

ExxonMobil assets are written under `outputs/exxon/`, including the flat set of
all masters in `outputs/exxon/png/`. As an integrated oil & gas company, XOM has
no cost-of-revenue / gross-profit bridge (like a bank); its adapter reconciles a
single "total revenues and other income" line against its eight cost and other
deduction lines — crude oil & product purchases, production & manufacturing,
SG&A, depreciation & depletion, exploration, non-service pension, interest
expense, and taxes other than income — to income before income taxes, then the
income-tax and noncontrolling-interest waterfall to net income attributable to
ExxonMobil. Gross profit is not derived.

ExxonMobil tags its revenue product/service breakdown (sales & operating
revenue, income from equity affiliates, and other income) only in the
standalone-quarter 10-Qs from mid-2023 onward. Older 10-Qs omit it, so those
three revenue-component cards are drawn only when all three are present and the
segment identity is checked only then; the remaining income-statement identities
still reconcile without them. Derived Q4 quarters reconstruct the components (and
every other line) as the annual 10-K value minus the nine-month 10-Q value, so
their cards carry the derived (`*`) marker.

Micron uses the same workflow, with fiscal-quarter labels based on its
52/53-week fiscal year ending in August:

```bash
uv run stankey discover-filings MU --quarters 20 --from-quarter 2026Q3 \
  --user-agent 'Your Name your.email@example.com' \
  --output outputs/micron/MU_discovered_filings.json
uv run stankey generate-series MU --quarters 20 --from-quarter 2026Q3 \
  --fetch-sec --user-agent 'Your Name your.email@example.com'
```

Micron assets are written under `outputs/micron/`, including 20 flat PNG
masters in `outputs/micron/png/`. The adapter reconciles DRAM, NAND, and other
product sales to consolidated revenue; cost of goods sold and operating
expenses to operating income; investment income, interest expense, and other
non-operating activity to pre-tax income; and the tax and equity-method bridge
to net income. Its flows support gross losses, operating losses, tax benefits,
and signed income/expense lines. Q4 derivation also handles restructuring that
is reported in the annual filing while an omitted nine-month line represents
zero.

Palantir uses the same workflow and resolves its company config automatically:

```bash
uv run stankey discover-filings PLTR --quarters 20 --from-quarter 2026Q2 \
  --user-agent 'Your Name your.email@example.com' \
  --output outputs/palantir/PLTR_discovered_filings.json
uv run stankey generate-series PLTR --quarters 20 --from-quarter 2026Q2 \
  --fetch-sec --user-agent 'Your Name your.email@example.com'
```

Palantir assets are written under `outputs/palantir/`, including 20 flat PNG
masters in `outputs/palantir/png/`. The adapter reconciles government and
commercial segment sales to consolidated revenue; cost of revenue to gross
profit; sales & marketing, R&D, and G&A to operating expenses and operating
income; interest income, interest expense, and other non-operating activity to
pre-tax income; and the income-tax and noncontrolling-interest bridge to net
income. Gross profit is derived. Its flows are sign-aware, so the early loss
quarters (operating, pre-tax, and net losses, with and without a
noncontrolling interest) and any tax-benefit quarters render honestly. The
selectors also absorb Palantir's segment concept and dimension-member drift
across filings, and interest expense and the noncontrolling interest are
optional lines drawn only when tagged. Values preserve Palantir's filed
sub-million (`$000`) precision.

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

Use `--from-quarter 2026Q2` to reproduce a range from a specific point. The
command validates that every requested quarter has source metadata before
starting generation.

## Create MP4 videos

With [FFmpeg](https://ffmpeg.org/) installed, the 20 numbered PNG masters for
each company can be combined into a 15-second MP4. This batch command creates
one video in every company output directory:

```bash
for d in outputs/*/png; do
  company_dir=${d%/png}
  ffmpeg -hide_banner -loglevel error -y \
    -framerate 4/3 -pattern_type glob -i "$d/*.png" \
    -t 15 -r 30 -c:v libx264 -pix_fmt yuv420p \
    -movflags +faststart \
    "$company_dir/$(basename "$company_dir").mp4"
done
```

The numbered filenames are read in order, and each image remains on screen for
0.75 seconds. For example, the Amazon video is written to
`outputs/amazon/amazon.mp4`.

The flat `png/` copies get modification timestamps set to `now - N*1min`, where
`N` is the sequence number in the filename (`01` is the newest quarter and gets
the latest timestamp, higher numbers are older quarters and get earlier
timestamps). This makes the images sort chronologically in a phone's photo
gallery. The per-quarter originals under each `<quarter>/` folder are left
untouched.

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

- The checked-in offline fixture covers only `META 2026Q2`; regenerating other
  companies and historical series requires live SEC access with `--fetch-sec`.
- SHOP's continuous SEC-XBRL quarterly history begins at 2025Q1; older quarterly
  results were furnished on non-XBRL Forms 6-K.
- Values are GAAP and normalized to USD millions. Form 10-Q figures are
  unaudited, and Q4 values are derived as annual minus nine months.
- Gross profit is derived because Meta does not report it as a separate fact.
- Segment/product revenue comes from company-specific XBRL dimensions. Mapping
  it is deterministic but company-specific.
- The layout uses reviewed company-specific flow columns with deterministic
  label lanes. Sign handling varies by adapter; Micron supports gross,
  operating, pre-tax, and net losses as well as tax benefits.
- The PNG is derived directly from the SVG; text rasterization can still vary
  by platform font availability.
