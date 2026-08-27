import re
from pathlib import Path

import pytest

import sankey.render as render_module
from sankey.models import FinancialFact, Provenance, Quarter
from sankey.normalize import normalize_meta
from sankey.validate import validate_quarter


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "jpm" / "_test_samples"

JPM_LABELS = {
    "interest_income": "Interest income",
    "interest_expense": "Interest expense",
    "net_interest_income": "Net interest income",
    "noninterest_income": "Noninterest revenue",
    "revenue": "Total net revenue",
    "provision_for_credit_losses": "Provision for credit losses",
    "noninterest_expense": "Noninterest expense",
    "pretax_income": "Pre-tax income",
    "income_tax": "Income tax",
    "net_income": "Net income",
}


def _jpm_quarter(values: dict, quarter: int = 2, year: int = 2026) -> Quarter:
    provenance = Provenance(
        source_url="https://www.sec.gov/example.xml",
        accession="example",
        document="example.xml",
        filing_date="2026-07-15",
        concept="Example",
        context_id="current",
        period_start=f"{year}-04-01",
        period_end=f"{year}-06-30",
        unit="usd",
        decimals="-6",
    )
    return Quarter(
        company="JPMorgan Chase & Co.",
        ticker="JPM",
        fiscal_year=year,
        fiscal_quarter=quarter,
        start_date=f"{year}-04-01",
        end_date=f"{year}-06-30",
        currency="USD",
        scale="millions",
        facts={
            key: FinancialFact(
                key=key,
                label=JPM_LABELS[key],
                value_millions=value,
                status="reported",
                provenance=[provenance],
            )
            for key, value in values.items()
        },
    )


def _q2_2026_values() -> dict:
    # JPMorgan Chase 2026 Q2 10-Q (USD millions), verified against the filed
    # XBRL instance. Every reconciliation identity holds exactly.
    return {
        "interest_income": 50_624,
        "interest_expense": 25_113,
        "net_interest_income": 25_511,
        "noninterest_income": 31_836,
        "revenue": 57_347,
        "provision_for_credit_losses": 2_515,
        "noninterest_expense": 27_316,
        "pretax_income": 27_516,
        "income_tax": 6_361,
        "net_income": 21_155,
    }


def test_jpm_reconciles_all_identities():
    quarter = _jpm_quarter(_q2_2026_values())
    checks = validate_quarter(quarter)
    assert all(check.passed for check in checks)
    names = {check.name for check in checks}
    assert "interest income less interest expense equals net interest income" in names
    assert "net interest income plus noninterest revenue equals total net revenue" in names
    assert (
        "total net revenue less provision less noninterest expense equals pre-tax income"
        in names
    )
    assert "pre-tax income less income tax equals net income" in names


def test_jpm_reconciliation_detects_broken_identity():
    values = _q2_2026_values()
    values["net_income"] = values["net_income"] + 500
    quarter = _jpm_quarter(values)
    with pytest.raises(Exception):
        validate_quarter(quarter)


def test_jpm_renders_expected_cards(tmp_path: Path):
    quarter = _jpm_quarter(_q2_2026_values())
    destination = tmp_path / "jpm-q2.svg"
    # render_svg validates label spacing and terminal order; it raises on any
    # collision, so reaching the assertions proves a clean layout.
    render_module.render_svg(quarter, destination)
    svg = destination.read_text(encoding="utf-8")
    # 10 income-statement lines, one label card each (no gross-profit bridge).
    assert svg.count('class="label-card"') == 10
    assert "Total net revenue" in svg
    assert "Net interest income" in svg
    assert "Provision for credit losses" in svg
    # Secondary value text is bold like the other companies.
    assert 'font-size="16" font-weight="700"' in svg
    assert "JPM" in svg


def test_jpm_layout_rejects_loss_quarter():
    # The bank layout targets profitable quarters; a pre-tax/net loss is not yet
    # supported and must fail loudly rather than render a misleading chart.
    values = _q2_2026_values()
    values["pretax_income"] = -1_000
    values["income_tax"] = -300
    values["net_income"] = -700
    # Keep the revenue/expense identity consistent so the failure is the layout,
    # not reconciliation: revenue - provision - noninterest_expense = pretax.
    values["noninterest_expense"] = (
        values["revenue"] - values["provision_for_credit_losses"] - values["pretax_income"]
    )
    quarter = _jpm_quarter(values)
    assert all(check.passed for check in validate_quarter(quarter))
    with pytest.raises(ValueError, match="loss quarters"):
        render_module.render_svg(quarter, Path("/tmp/should-not-write.svg"))


def test_jpm_normalize_does_not_derive_gross_profit():
    # Banks have no cost-of-revenue line, so the generic gross-profit derivation
    # must be skipped (it previously ran unconditionally).
    config = {
        "company": "JPMorgan Chase & Co.",
        "ticker": "JPM",
        "slug": "jpm",
        "quarters": {
            "2026Q2": {
                "start_date": "2026-04-01",
                "end_date": "2026-06-30",
                "prior_start_date": "2025-04-01",
                "prior_end_date": "2025-06-30",
            }
        },
        "selectors": {
            "revenue": {
                "label": "Total net revenue",
                "concept": "RevenuesNetOfInterestExpense",
                "dimensions": {},
                "status": "reported",
            },
            "net_income": {
                "label": "Net income",
                "concept": "NetIncomeLoss",
                "dimensions": {},
                "status": "reported",
            },
        },
    }

    def fact(concept, value, start, end):
        return {
            "concept": concept,
            "value": value,
            "unit": "usd",
            "decimals": "-6",
            "context_id": "c",
            "start_date": start,
            "end_date": end,
            "dimensions": {},
        }

    extracted = {
        "source": {"url": "u", "accession": "a", "document": "d.xml", "filing_date": "2026-07-15"},
        "facts": [
            fact("RevenuesNetOfInterestExpense", "57347000000", "2026-04-01", "2026-06-30"),
            fact("NetIncomeLoss", "21155000000", "2026-04-01", "2026-06-30"),
            fact("RevenuesNetOfInterestExpense", "44912000000", "2025-04-01", "2025-06-30"),
            fact("NetIncomeLoss", "14987000000", "2025-04-01", "2025-06-30"),
        ],
    }
    quarter = normalize_meta(config, extracted, "2026Q2")
    assert "gross_profit" not in quarter.facts
    assert quarter.facts["revenue"].value_millions == 57_347


def test_jpm_sample_svg_has_no_overlap_and_fits_canvas():
    quarter = _jpm_quarter(_q2_2026_values())
    SAMPLE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    svg_path = SAMPLE_OUTPUT_DIR / "JPM_2026Q2_sample.svg"
    render_module.render_svg(quarter, svg_path)
    svg = svg_path.read_text(encoding="utf-8")
    assert svg.count('class="label-card"') == 10
    for match in re.finditer(
        r'<rect class="label-card"[^>]*x="([-\d.]+)"[^>]*y="([-\d.]+)"[^>]*width="([-\d.]+)"[^>]*height="([-\d.]+)"',
        svg,
    ):
        x, y, w, h = (float(g) for g in match.groups())
        assert x >= 0, f"card overflows left edge: x={x}"
        assert x + w <= render_module.WIDTH, f"card overflows right edge: {x + w}"
        assert y >= 0, f"card overflows top edge: y={y}"
        assert y + h <= render_module.HEIGHT, f"card overflows bottom edge: {y + h}"
