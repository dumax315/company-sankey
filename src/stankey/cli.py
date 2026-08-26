import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Sequence

from .normalize import normalize_meta
from .render import rasterize_svg, render_svg
from .sec import download_xbrl, load_json, parse_xbrl
from .validate import ReconciliationError, checks_to_dict, validate_quarter


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "companies" / "meta.json"
DEFAULT_FIXTURE = PROJECT_ROOT / "data" / "fixtures" / "meta_2026_q2_sec_xbrl.json"


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="stankey")
    subparsers = parser.add_subparsers(dest="command", required=True)
    generate = subparsers.add_parser("generate", help="generate quarterly Sankey assets")
    generate.add_argument("ticker", help="company ticker (MVP: META)")
    generate.add_argument("--quarter", required=True, help="fiscal quarter, e.g. 2026Q2")
    generate.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "outputs" / "meta")
    generate.add_argument("--fetch-sec", action="store_true", help="download and parse the official SEC XBRL instance")
    generate.add_argument("--user-agent", default=os.environ.get("SEC_USER_AGENT"), help="SEC-compliant identity with email")
    generate.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    generate.add_argument(
        "--png-size",
        type=int,
        default=3240,
        help="square PNG master size in pixels (default: 3240)",
    )
    series = subparsers.add_parser(
        "generate-series",
        help="generate the latest reported quarter and N-1 preceding quarters",
    )
    series.add_argument("ticker", help="company ticker (MVP: META)")
    series.add_argument("--quarters", type=int, required=True, help="number of quarters to generate")
    series.add_argument(
        "--from-quarter",
        help="newest fiscal quarter, e.g. 2026Q2 (default: latest configured quarter)",
    )
    series.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "outputs" / "meta")
    series.add_argument("--fetch-sec", action="store_true", help="download and parse each official SEC XBRL instance")
    series.add_argument("--user-agent", default=os.environ.get("SEC_USER_AGENT"), help="SEC-compliant identity with email")
    series.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    series.add_argument(
        "--png-size",
        type=int,
        default=3240,
        help="square PNG master size in pixels (default: 3240)",
    )
    return parser


def quarter_sequence(start: str, count: int) -> list:
    if count <= 0:
        raise ValueError("--quarters must be a positive integer")
    normalized = start.upper()
    if len(normalized) != 6 or normalized[4] != "Q" or not normalized[:4].isdigit() or normalized[5] not in "1234":
        raise ValueError(f"Invalid fiscal quarter: {start}; expected YYYYQ1 through YYYYQ4")
    year = int(normalized[:4])
    quarter = int(normalized[5])
    result = []
    for _ in range(count):
        result.append(f"{year}Q{quarter}")
        quarter -= 1
        if quarter == 0:
            year -= 1
            quarter = 4
    return result


def _latest_configured_quarter(config: dict) -> str:
    return max(config["quarters"], key=lambda key: (int(key[:4]), int(key[5])))


def generate(args: argparse.Namespace) -> Path:
    if args.ticker.upper() != "META":
        raise ValueError("The current generator supports only META")
    config = load_json(args.config)
    quarter_key = args.quarter.upper()
    if quarter_key not in config["quarters"]:
        raise ValueError(f"No configured source data for {args.ticker.upper()} {quarter_key}")
    quarter_config = config["quarters"][quarter_key]
    source_config = quarter_config["source"]
    input_mode = "checked-in SEC XBRL fact fixture"
    if args.fetch_sec:
        if not args.user_agent:
            raise ValueError("--fetch-sec requires --user-agent or SEC_USER_AGENT")
        raw_path = (
            PROJECT_ROOT
            / "data"
            / "raw"
            / "meta"
            / source_config["accession"]
            / source_config["document"]
        )
        download_xbrl(source_config["url"], raw_path, args.user_agent)
        source = {
            "url": source_config["url"],
            "accession": source_config["accession"],
            "document": source_config["document"],
            "filing_date": source_config["filing_date"],
        }
        extracted = parse_xbrl(raw_path, source)
        input_mode = "downloaded SEC XBRL instance"
    else:
        fixture_path = PROJECT_ROOT / quarter_config["fixture"]
        if not fixture_path.is_file():
            raise ValueError(f"Configured fixture does not exist for {quarter_key}: {fixture_path}")
        extracted = load_json(fixture_path)

    quarter = normalize_meta(config, extracted, quarter_key)
    checks = validate_quarter(quarter)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    year, fiscal_quarter = quarter_key.split("Q")
    sequence_index = getattr(args, "sequence_index", 1)
    stem = f"{sequence_index:02d}_{args.ticker.upper()}_{year}_Q{fiscal_quarter}"
    svg_path = args.output_dir / f"{stem}.svg"
    png_path = args.output_dir / f"{stem}.png"
    manifest_path = args.output_dir / f"{stem}.json"
    png_size = getattr(args, "png_size", 3240)
    if png_size <= 0:
        raise ValueError("--png-size must be a positive integer")
    render_svg(quarter, svg_path)
    rasterize_svg(svg_path, png_path, pixel_size=png_size)
    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generator": "company-stankey 0.1.0",
        "input_mode": input_mode,
        "source": extracted["source"],
        "quarter": quarter.to_dict(),
        "validation": {
            "status": "passed",
            "tolerance_millions": 1,
            "checks": checks_to_dict(checks),
        },
        "outputs": {
            "svg": {
                "filename": svg_path.name,
                "sha256": _hash(svg_path),
                "viewbox_width": 1080,
                "viewbox_height": 1080,
            },
            "png": {
                "filename": png_path.name,
                "sha256": _hash(png_path),
                "width": png_size,
                "height": png_size,
                "rasterized_from": svg_path.name,
                "renderer": "resvg",
            },
        },
        "limitations": [
            "Form 10-Q figures are unaudited.",
            "The offline fixture contains selected filed facts, not the complete filing.",
            "Gross profit is derived as revenue minus cost of revenue.",
            "Segment/product mappings are reviewed Meta-specific XBRL dimension mappings.",
            "Displayed billions and year-over-year percentages are rounded; the manifest retains USD millions.",
        ],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest_path


def generate_series(args: argparse.Namespace) -> Path:
    if args.ticker.upper() != "META":
        raise ValueError("The current generator supports only META")
    config = load_json(args.config)
    start = args.from_quarter.upper() if args.from_quarter else _latest_configured_quarter(config)
    quarters = quarter_sequence(start, args.quarters)
    missing = [quarter for quarter in quarters if quarter not in config["quarters"]]
    if missing:
        raise ValueError(
            "Missing configured source data for requested quarter(s): " + ", ".join(missing)
        )

    manifests = []
    for index, quarter_key in enumerate(quarters, start=1):
        quarter_args = argparse.Namespace(**vars(args))
        quarter_args.command = "generate"
        quarter_args.quarter = quarter_key
        quarter_args.sequence_index = index
        quarter_args.output_dir = args.output_dir / quarter_key
        manifests.append(generate(quarter_args))

    series_manifest = args.output_dir / f"{args.ticker.upper()}_{start}_{len(quarters)}_quarters.json"
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ticker": args.ticker.upper(),
        "newest_quarter": start,
        "quarter_count": len(quarters),
        "quarters": [
            {
                "quarter": quarter,
                "directory": quarter,
                "manifest": str(manifest.relative_to(args.output_dir)),
            }
            for quarter, manifest in zip(quarters, manifests)
        ],
    }
    series_manifest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return series_manifest


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        manifest = generate_series(args) if args.command == "generate-series" else generate(args)
    except (ValueError, ReconciliationError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.command == "generate":
        print(f"Generated {manifest.parent / (manifest.stem + '.svg')}")
        print(f"Generated {manifest.parent / (manifest.stem + '.png')}")
    print(f"Generated {manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
