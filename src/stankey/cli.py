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
    return parser


def generate(args: argparse.Namespace) -> Path:
    if args.ticker.upper() != "META" or args.quarter.upper() != "2026Q2":
        raise ValueError("Phase 1 supports only: META --quarter 2026Q2")
    config = load_json(args.config)
    input_mode = "checked-in SEC XBRL fact fixture"
    if args.fetch_sec:
        if not args.user_agent:
            raise ValueError("--fetch-sec requires --user-agent or SEC_USER_AGENT")
        raw_path = (
            PROJECT_ROOT
            / "data"
            / "raw"
            / "meta"
            / config["accession"]
            / config["document"]
        )
        download_xbrl(config["source_url"], raw_path, args.user_agent)
        source = {
            "url": config["source_url"],
            "accession": config["accession"],
            "document": config["document"],
            "filing_date": config["filing_date"],
        }
        extracted = parse_xbrl(raw_path, source)
        input_mode = "downloaded SEC XBRL instance"
    else:
        extracted = load_json(DEFAULT_FIXTURE)

    quarter = normalize_meta(config, extracted, args.quarter.upper())
    checks = validate_quarter(quarter)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    stem = "01_META_2026_Q2"
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


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        manifest = generate(args)
    except (ValueError, ReconciliationError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"Generated {manifest.parent / (manifest.stem + '.svg')}")
    print(f"Generated {manifest.parent / (manifest.stem + '.png')}")
    print(f"Generated {manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
