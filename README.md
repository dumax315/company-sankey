# Company Stankey

This MVP generates an auditable income-statement Sankey for Meta's second
quarter of 2026. It emits a canonical SVG with a 1080×1080 viewBox, a matching
3240×3240 PNG master, and a JSON manifest containing each value's SEC XBRL
provenance and all reconciliation results.

## Run

Python 3.10+ and [uv](https://docs.astral.sh/uv/) are required. `uv sync`
creates an isolated `.venv` from the checked-in lockfile.

```bash
uv sync
uv run stankey generate META --quarter 2026Q2
uv run pytest
```

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

- Only `META 2026Q2` is configured; this is deliberately one vertical slice.
- Values are GAAP, USD millions, and from the unaudited Form 10-Q filed July 30,
  2026. The fixture is an extracted subset, not a copy of the complete filing.
- Gross profit is derived because Meta does not report it as a separate fact.
- Segment/product revenue comes from company-specific XBRL dimensions. Mapping
  it is deterministic but company-specific.
- The layout is fixed for this quarter. It does not yet solve label placement
  or materiality automatically across companies and negative-profit quarters.
- The PNG is derived directly from the SVG; text rasterization can still vary
  by platform font availability.
