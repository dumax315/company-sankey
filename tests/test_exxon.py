import re
from pathlib import Path

import pytest

import stankey.render as render_module
from stankey.models import FinancialFact, Provenance, Quarter
from stankey.validate import validate_quarter


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "exxon" / "_test_samples"

XOM_LABELS = {
    "sales_revenue": "Sales & operating rev.",
    "equity_affiliates_income": "Equity affiliate income",
    "other_income": "Other income",
    "revenue": "Total revenues",
    "crude_oil_purchases": "Crude & product buys",
    "production_manufacturing": "Production & mfg.",
    "sga": "SG&A",
    "depreciation": "Deprec. & depletion",
    "exploration": "Exploration",
    "pension_nonservice": "Non-service pension",
    "interest_expense": "Interest expense",
    "taxes_other": "Taxes (non-income)",
    "costs_and_expenses": "Total costs",
    "pretax_income": "Pre-tax income",
    "income_tax": "Income tax",
    "profit_loss": "Net income incl. NCI",
    "noncontrolling_interest": "Noncontrolling int.",
    "net_income": "Net income",
}


def _xom_quarter(values: dict, quarter: int = 2, year: int = 2026) -> Quarter:
    provenance = Provenance(
        source_url="https://www.sec.gov/example.xml",
        accession="example",
        document="example.xml",
        filing_date="2026-07-31",
        concept="Example",
        context_id="current",
        period_start=f"{year}-04-01",
        period_end=f"{year}-06-30",
        unit="usd",
        decimals="-6",
    )
    return Quarter(
        company="Exxon Mobil Corporation",
        ticker="XOM",
        fiscal_year=year,
        fiscal_quarter=quarter,
        start_date=f"{year}-04-01",
        end_date=f"{year}-06-30",
        currency="USD",
        scale="millions",
        facts={
            key: FinancialFact(
                key=key,
                label=XOM_LABELS[key],
                value_millions=value,
                status="reported",
                provenance=[provenance],
            )
            for key, value in values.items()
        },
    )


def _q2_2026_values() -> dict:
    # Exxon Mobil 2026 Q2 10-Q (USD millions), verified against the filed XBRL
    # instance. Every reconciliation identity holds exactly.
    return {
        "sales_revenue": 114_529,
        "equity_affiliates_income": 893,
        "other_income": 595,
        "revenue": 116_017,
        "crude_oil_purchases": 67_801,
        "production_manufacturing": 12_250,
        "sga": 2_483,
        "depreciation": 8_689,
        "exploration": 155,
        "pension_nonservice": 32,
        "interest_expense": 227,
        "taxes_other": 4_956,
        "costs_and_expenses": 96_593,
        "pretax_income": 19_424,
        "income_tax": 4_543,
        "profit_loss": 14_881,
        "noncontrolling_interest": 356,
        "net_income": 14_525,
    }


def _q3_2021_values() -> dict:
    # Exxon Mobil 2021 Q3 10-Q (USD millions), verified against the filed XBRL
    # instance. This older filing does NOT tag the revenue product breakdown, so
    # the three revenue-component lines are absent (the optional-segment case).
    return {
        "revenue": 73_786,
        "crude_oil_purchases": 39_745,
        "production_manufacturing": 8_719,
        "sga": 2_287,
        "depreciation": 4_990,
        "exploration": 190,
        "pension_nonservice": 146,
        "interest_expense": 214,
        "taxes_other": 7_889,
        "costs_and_expenses": 64_180,
        "pretax_income": 9_606,
        "income_tax": 2_664,
        "profit_loss": 6_942,
        "noncontrolling_interest": 192,
        "net_income": 6_750,
    }


def test_xom_reconciles_all_identities():
    quarter = _xom_quarter(_q2_2026_values())
    checks = validate_quarter(quarter)
    assert all(check.passed for check in checks)
    names = {check.name for check in checks}
    assert "revenue components equal total revenues and other income" in names
    assert "cost components equal total costs and other deductions" in names
    assert "revenue less total costs equals income before income taxes" in names
    assert (
        "income before taxes less income tax equals net income incl. noncontrolling"
        in names
    )
    assert (
        "net income incl. noncontrolling less noncontrolling interests equals net income"
        in names
    )


def test_xom_reconciliation_detects_broken_identity():
    values = _q2_2026_values()
    values["net_income"] = values["net_income"] + 500
    quarter = _xom_quarter(values)
    with pytest.raises(Exception):
        validate_quarter(quarter)


def test_xom_reconciles_without_revenue_components():
    # Older 10-Qs (and every derived Q4) omit the revenue product breakdown.
    # The remaining income-statement identities must still reconcile and the
    # optional segment identity must simply be skipped.
    quarter = _xom_quarter(_q3_2021_values(), quarter=3, year=2021)
    checks = validate_quarter(quarter)
    assert all(check.passed for check in checks)
    names = {check.name for check in checks}
    assert "revenue components equal total revenues and other income" not in names
    assert "cost components equal total costs and other deductions" in names


def test_xom_renders_expected_cards(tmp_path: Path):
    quarter = _xom_quarter(_q2_2026_values())
    destination = tmp_path / "xom-q2.svg"
    # render_svg validates label spacing and terminal order; it raises on any
    # collision, so reaching the assertions proves a clean layout.
    render_module.render_svg(quarter, destination)
    svg = destination.read_text(encoding="utf-8")
    # 3 revenue components + revenue + pretax + 8 costs + net + tax + NCI = 16
    # label cards (profit_loss reconciles but is not drawn as a node).
    assert svg.count('class="label-card"') == 16
    assert "Total revenues" in svg
    assert "Crude &amp; product buys" in svg
    assert "Net income" in svg
    assert "XOM" in svg


def test_xom_renders_without_revenue_components(tmp_path: Path):
    quarter = _xom_quarter(_q3_2021_values(), quarter=3, year=2021)
    destination = tmp_path / "xom-2021q3.svg"
    render_module.render_svg(quarter, destination)
    svg = destination.read_text(encoding="utf-8")
    # No revenue-component cards: revenue + pretax + 8 costs + net + tax + NCI = 13.
    assert svg.count('class="label-card"') == 13
    assert "Sales &amp; operating rev." not in svg


def test_xom_layout_rejects_loss_quarter():
    # The layout targets profitable quarters; a pre-tax/net loss is not yet
    # supported and must fail loudly rather than render a misleading chart.
    values = _q2_2026_values()
    # Force a net loss while keeping the reconciliation identities consistent so
    # the failure is the layout, not reconciliation.
    values["pretax_income"] = -1_000
    values["costs_and_expenses"] = values["revenue"] - values["pretax_income"]
    # Re-balance the eight cost lines by absorbing the change into taxes_other.
    other_costs = (
        values["crude_oil_purchases"]
        + values["production_manufacturing"]
        + values["sga"]
        + values["depreciation"]
        + values["exploration"]
        + values["pension_nonservice"]
        + values["interest_expense"]
    )
    values["taxes_other"] = values["costs_and_expenses"] - other_costs
    values["income_tax"] = -300
    values["profit_loss"] = values["pretax_income"] - values["income_tax"]
    values["noncontrolling_interest"] = 0
    values["net_income"] = values["profit_loss"] - values["noncontrolling_interest"]
    quarter = _xom_quarter(values)
    assert all(check.passed for check in validate_quarter(quarter))
    with pytest.raises(ValueError, match="loss quarters"):
        render_module.render_svg(quarter, Path("/tmp/should-not-write.svg"))


def test_xom_sample_svg_has_no_overlap_and_fits_canvas():
    quarter = _xom_quarter(_q2_2026_values())
    SAMPLE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    svg_path = SAMPLE_OUTPUT_DIR / "XOM_2026Q2_sample.svg"
    render_module.render_svg(quarter, svg_path)
    svg = svg_path.read_text(encoding="utf-8")
    assert svg.count('class="label-card"') == 16
    for match in re.finditer(
        r'<rect class="label-card"[^>]*x="([-\d.]+)"[^>]*y="([-\d.]+)"[^>]*width="([-\d.]+)"[^>]*height="([-\d.]+)"',
        svg,
    ):
        x, y, w, h = (float(g) for g in match.groups())
        assert x >= 0, f"card overflows left edge: x={x}"
        assert x + w <= render_module.WIDTH, f"card overflows right edge: {x + w}"
        assert y >= 0, f"card overflows top edge: y={y}"
        assert y + h <= render_module.HEIGHT, f"card overflows bottom edge: {y + h}"
