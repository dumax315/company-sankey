# Company Stankey

This MVP generates auditable quarterly income-statement Sankeys for Meta. It
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

`discover-filings` reads Meta's SEC submissions history, follows historical
submission pages when the recent feed is not deep enough, resolves each filing's
extracted XBRL instance, and emits configuration-ready entries under `quarters`.
It does not modify `configs/companies/meta.json`. Use `--from-quarter 2026Q2` to
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

- The checked-in offline fixture covers only `META 2026Q2`; historical series
  generation requires live SEC access with `--fetch-sec`.
- Values are GAAP and normalized to USD millions. Form 10-Q figures are
  unaudited, and Q4 values are derived as annual minus nine months.
- Gross profit is derived because Meta does not report it as a separate fact.
- Segment/product revenue comes from company-specific XBRL dimensions. Mapping
  it is deterministic but company-specific.
- The layout uses fixed flow columns with deterministic label lanes. It does not
  yet generalize automatically across companies or negative operating-profit
  quarters.
- The PNG is derived directly from the SVG; text rasterization can still vary
  by platform font availability.
