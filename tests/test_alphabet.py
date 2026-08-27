from pathlib import Path

import pytest

import sankey.render as render_module
from sankey.models import FinancialFact, Provenance, Quarter
from sankey.normalize import FactSelectionError, _select, normalize_meta
from sankey.validate import validate_quarter


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "alphabet" / "_test_samples"

ALPHABET_LABELS = {
    "google_services_revenue": "Google Services",
    "google_cloud_revenue": "Google Cloud",
    "other_bets_revenue": "Other Bets",
    "hedging_revenue": "Hedging gains (losses)",
    "revenue": "Revenues",
    "cost_of_revenue": "Cost of revenues",
    "gross_profit": "Gross profit",
    "research_and_development": "R&D",
    "sales_and_marketing": "Sales & marketing",
    "general_and_administrative": "G&A",
    "costs_and_expenses": "Costs & expenses",
    "operating_income": "Operating income",
    "nonoperating_income_expense": "Net other income",
    "pretax_income": "Pre-tax income",
    "income_tax": "Income tax",
    "net_income": "Net income",
}


def _alphabet_quarter(values: dict, quarter: int = 2, year: int = 2025) -> Quarter:
    provenance = Provenance(
        source_url="https://www.sec.gov/example.xml",
        accession="example",
        document="example.xml",
        filing_date="2025-07-24",
        concept="Example",
        context_id="current",
        period_start=f"{year}-04-01",
        period_end=f"{year}-06-30",
        unit="usd",
        decimals="-6",
    )
    return Quarter(
        company="Alphabet Inc.",
        ticker="GOOGL",
        fiscal_year=year,
        fiscal_quarter=quarter,
        start_date=f"{year}-04-01",
        end_date=f"{year}-06-30",
        currency="USD",
        scale="millions",
        facts={
            key: FinancialFact(
                key=key,
                label=ALPHABET_LABELS[key],
                value_millions=value,
                status="derived" if key == "gross_profit" else "reported",
                provenance=[provenance],
            )
            for key, value in values.items()
        },
    )


def _q2_2025_values() -> dict:
    # Alphabet 2025 Q2 10-Q (USD millions), gross profit derived.
    return {
        "google_services_revenue": 82_543,
        "google_cloud_revenue": 13_624,
        "other_bets_revenue": 373,
        "hedging_revenue": -112,
        "revenue": 96_428,
        "cost_of_revenue": 39_039,
        "gross_profit": 96_428 - 39_039,
        "research_and_development": 13_808,
        "sales_and_marketing": 7_101,
        "general_and_administrative": 5_209,
        "costs_and_expenses": 65_157,
        "operating_income": 31_271,
        "nonoperating_income_expense": 2_662,
        "pretax_income": 33_933,
        "income_tax": 5_737,
        "net_income": 28_196,
    }


def test_alphabet_q2_reconciles_all_identities():
    quarter = _alphabet_quarter(_q2_2025_values())
    checks = validate_quarter(quarter)
    assert all(check.passed for check in checks)
    names = {check.name for check in checks}
    assert "segment revenue plus hedging equals consolidated revenue" in names
    assert "revenue less cost of revenues equals gross profit" in names
    assert "gross profit less operating expenses equals operating income" in names
    assert "expense components equal total costs and expenses" in names
    assert "revenue less total costs and expenses equals operating income" in names
    assert "operating plus non-operating equals pre-tax income" in names
    assert "pre-tax less income tax equals net income" in names


def test_alphabet_reconciliation_detects_broken_identity():
    values = _q2_2025_values()
    values["net_income"] = values["net_income"] + 500
    quarter = _alphabet_quarter(values)
    with pytest.raises(Exception):
        validate_quarter(quarter)


def test_alphabet_reconciles_without_segment_disclosure():
    # Nine-month and annual instances omit segment revenue; reconciliation must
    # still pass on the remaining income-statement identities.
    values = _q2_2025_values()
    for key in ("google_services_revenue", "google_cloud_revenue", "other_bets_revenue", "hedging_revenue"):
        values.pop(key)
    quarter = _alphabet_quarter(values)
    checks = validate_quarter(quarter)
    assert all(check.passed for check in checks)
    assert "segment revenue plus hedging equals consolidated revenue" not in {
        check.name for check in checks
    }


def test_alphabet_renders_with_segments(tmp_path: Path):
    quarter = _alphabet_quarter(_q2_2025_values())
    destination = tmp_path / "alphabet-q2.svg"
    render_module.render_svg(quarter, destination)
    svg = destination.read_text(encoding="utf-8")
    # Three segment cards + revenue + gross + cost + operating + 3 opex +
    # pretax + non-operating + income tax + net income = 14 label cards.
    assert svg.count('class="label-card"') == 14
    assert "Google Services" in svg
    assert "Google Cloud" in svg
    assert "Other Bets" in svg
    assert 'font-size="18" font-weight="700"' in svg
    assert "GOOGL" in svg


def test_alphabet_renders_without_segments(tmp_path: Path):
    values = _q2_2025_values()
    for key in ("google_services_revenue", "google_cloud_revenue", "other_bets_revenue", "hedging_revenue"):
        values.pop(key)
    quarter = _alphabet_quarter(values)
    destination = tmp_path / "alphabet-no-seg.svg"
    render_module.render_svg(quarter, destination)
    svg = destination.read_text(encoding="utf-8")
    # No segment cards: revenue + gross + cost + operating + 3 opex + pretax +
    # non-operating + income tax + net income = 11 label cards.
    assert svg.count('class="label-card"') == 11
    assert "Google Services" not in svg


def test_alphabet_loss_and_tax_benefit_quarter_reconciles_and_renders(tmp_path: Path):
    # Hypothetical downturn: operating income still positive but a large
    # non-operating loss drives a pre-tax loss, a net loss, and a tax benefit
    # (negative income tax). Exercises the sign-aware post-tax packing.
    values = {
        "google_services_revenue": 70_000,
        "google_cloud_revenue": 10_000,
        "other_bets_revenue": 400,
        "hedging_revenue": -100,
        "revenue": 80_300,
        "cost_of_revenue": 35_000,
        "gross_profit": 80_300 - 35_000,
        "research_and_development": 14_000,
        "sales_and_marketing": 7_000,
        "general_and_administrative": 5_000,
        "costs_and_expenses": 61_000,
        "operating_income": 19_300,
        "nonoperating_income_expense": -24_300,
        "pretax_income": -5_000,
        "income_tax": -1_200,
        "net_income": -3_800,
    }
    quarter = _alphabet_quarter(values)
    checks = validate_quarter(quarter)
    assert all(check.passed for check in checks)
    destination = tmp_path / "alphabet-loss.svg"
    render_module.render_svg(quarter, destination)
    svg = destination.read_text(encoding="utf-8")
    assert svg.count('class="label-card"') == 14
    # Net loss and tax benefit render as signed values.
    assert "−$5.0B" in svg  # pre-tax loss
    assert "−$3.8B" in svg  # net loss


def test_alphabet_large_nonoperating_income_quarter_renders_without_collision(tmp_path: Path):
    # Regression: Alphabet 2026 Q2 reported ~$98B of non-operating income
    # (large equity-security gains), rivaling cost of revenue. The identities
    # reconcile, but the non-operating label card previously extended left into
    # the cost-of-revenue column and tripped the spacing guard. The label must
    # now sit to the right of its node so the SVG renders cleanly.
    values = {
        "google_services_revenue": 82_543,
        "google_cloud_revenue": 13_624,
        "other_bets_revenue": 373,
        "hedging_revenue": -112,
        "revenue": 96_428,
        "cost_of_revenue": 45_900,
        "gross_profit": 96_428 - 45_900,
        "research_and_development": 13_808,
        "sales_and_marketing": 7_101,
        "general_and_administrative": 5_209,
        "costs_and_expenses": 72_018,
        "operating_income": 24_410,
        "nonoperating_income_expense": 97_983,
        "pretax_income": 122_393,
        "income_tax": 12_000,
        "net_income": 110_393,
    }
    quarter = _alphabet_quarter(values, quarter=2, year=2026)
    checks = validate_quarter(quarter)
    assert all(check.passed for check in checks)
    destination = tmp_path / "alphabet-big-nonop.svg"
    # render_svg raises on any label-card collision; reaching the assertions
    # proves the oversized non-operating card no longer overlaps the cost card.
    render_module.render_svg(quarter, destination)
    svg = destination.read_text(encoding="utf-8")
    assert svg.count('class="label-card"') == 14
    _assert_cards_on_canvas(svg)


def test_alphabet_selector_matches_alternate_revenue_concept():
    # Older filings tag consolidated revenue as
    # RevenueFromContractWithCustomerExcludingAssessedTax; newer ones as Revenues.
    selector = {
        "concept": "Revenues",
        "concepts": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax"],
        "dimensions": {},
    }
    base = {
        "unit": "usd",
        "context_id": "current",
        "start_date": "2025-01-01",
        "end_date": "2025-03-31",
        "dimensions": {},
        "decimals": "-6",
    }
    selected = _select(
        [{**base, "concept": "RevenueFromContractWithCustomerExcludingAssessedTax", "value": "90234000000"}],
        selector,
        "2025-01-01",
        "2025-03-31",
    )
    assert selected["value"] == "90234000000"


def test_alphabet_normalize_skips_missing_optional_selector():
    config = {
        "company": "Alphabet Inc.",
        "ticker": "GOOGL",
        "slug": "alphabet",
        "optional_selectors": ["google_services_revenue"],
        "quarters": {
            "2025Q2": {
                "start_date": "2025-04-01",
                "end_date": "2025-06-30",
                "prior_start_date": "2024-04-01",
                "prior_end_date": "2024-06-30",
            }
        },
        "selectors": {
            "google_services_revenue": {
                "label": "Google Services",
                "concept": "RevenueFromContractWithCustomerExcludingAssessedTax",
                "dimensions": {"us-gaap:StatementBusinessSegmentsAxis": "goog:GoogleServicesMember"},
                "status": "mapped",
            },
            "revenue": {"label": "Revenues", "concept": "Revenues", "dimensions": {}, "status": "reported"},
            "cost_of_revenue": {"label": "Cost of revenues", "concept": "CostOfRevenue", "dimensions": {}, "status": "reported"},
        },
    }

    def fact(concept, value, start, end, dimensions=None):
        return {
            "concept": concept,
            "value": value,
            "unit": "usd",
            "decimals": "-6",
            "context_id": "c",
            "start_date": start,
            "end_date": end,
            "dimensions": dimensions or {},
        }

    extracted = {
        "source": {"url": "u", "accession": "a", "document": "d.xml", "filing_date": "2025-07-24"},
        "facts": [
            # No segment fact for the current period -> optional, must be skipped.
            fact("Revenues", "96428000000", "2025-04-01", "2025-06-30"),
            fact("CostOfRevenue", "39039000000", "2025-04-01", "2025-06-30"),
            fact("Revenues", "84742000000", "2024-04-01", "2024-06-30"),
            fact("CostOfRevenue", "35000000000", "2024-04-01", "2024-06-30"),
        ],
    }
    quarter = normalize_meta(config, extracted, "2025Q2")
    assert "google_services_revenue" not in quarter.facts
    assert quarter.facts["revenue"].value_millions == 96_428
    # Gross profit is still derived generically.
    assert quarter.facts["gross_profit"].value_millions == 96_428 - 39_039


def test_alphabet_sample_svg_has_no_overlap_and_fits_canvas():
    """Render a representative quarter into outputs/alphabet for inspection."""
    quarter = _alphabet_quarter(_q2_2025_values())
    SAMPLE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    svg_path = SAMPLE_OUTPUT_DIR / "GOOGL_2025Q2_sample.svg"
    # render_svg internally validates label spacing and terminal order; it
    # raises if any card overlaps another. Reaching the assertions means the
    # layout is collision-free.
    render_module.render_svg(quarter, svg_path)
    svg = svg_path.read_text(encoding="utf-8")
    assert svg.count('class="label-card"') == 14
    _assert_cards_on_canvas(svg)


def _assert_cards_on_canvas(svg: str) -> None:
    import re

    for match in re.finditer(
        r'<rect class="label-card"[^>]*x="([-\d.]+)"[^>]*y="([-\d.]+)"[^>]*width="([-\d.]+)"[^>]*height="([-\d.]+)"',
        svg,
    ):
        x, y, w, h = (float(g) for g in match.groups())
        assert x >= 0, f"card overflows left edge: x={x}"
        assert x + w <= render_module.WIDTH, f"card overflows right edge: {x + w}"
        assert y >= 0, f"card overflows top edge: y={y}"
        assert y + h <= render_module.HEIGHT, f"card overflows bottom edge: {y + h}"
