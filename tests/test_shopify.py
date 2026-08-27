import re
from pathlib import Path

import pytest

import sankey.render as render_module
from sankey.models import FinancialFact, Provenance, Quarter
from sankey.validate import ReconciliationError, validate_quarter


SHOP_LABELS = {
    "subscription_solutions_revenue": "Subscription solutions",
    "merchant_solutions_revenue": "Merchant solutions",
    "revenue": "Revenue",
    "cost_of_revenue": "Cost of revenues",
    "gross_profit": "Gross profit",
    "sales_and_marketing": "Sales & marketing",
    "research_and_development": "R&D",
    "general_and_administrative": "G&A",
    "transaction_and_loan_losses": "Transaction & loan losses",
    "operating_expenses": "Operating expenses",
    "operating_income": "Operating income",
    "nonoperating_income_expense": "Net other income",
    "pretax_income": "Pre-tax income",
    "income_tax": "Income tax",
    "net_income": "Net income",
}


def _shop_quarter(values: dict, quarter: int, year: int) -> Quarter:
    provenance = Provenance(
        source_url="https://www.sec.gov/example.xml",
        accession="example",
        document="example.xml",
        filing_date=f"{year}-08-05",
        concept="Example",
        context_id="current",
        period_start=f"{year}-01-01",
        period_end=f"{year}-03-31",
        unit="usd",
        decimals="-6",
    )
    return Quarter(
        company="Shopify Inc.",
        ticker="SHOP",
        fiscal_year=year,
        fiscal_quarter=quarter,
        start_date=f"{year}-01-01",
        end_date=f"{year}-03-31",
        currency="USD",
        scale="millions",
        facts={
            key: FinancialFact(
                key=key,
                label=SHOP_LABELS[key],
                value_millions=value,
                status="derived" if key == "gross_profit" else "reported",
                provenance=[provenance],
            )
            for key, value in values.items()
        },
    )


def _q2_2026_values() -> dict:
    # Shopify 2026 Q2 10-Q, USD millions.
    return {
        "subscription_solutions_revenue": 802,
        "merchant_solutions_revenue": 2_781,
        "revenue": 3_583,
        "cost_of_revenue": 1_875,
        "gross_profit": 1_708,
        "sales_and_marketing": 498,
        "research_and_development": 445,
        "general_and_administrative": 136,
        "transaction_and_loan_losses": 141,
        "operating_expenses": 1_220,
        "operating_income": 488,
        "nonoperating_income_expense": 1_287,
        "pretax_income": 1_775,
        "income_tax": 273,
        "net_income": 1_502,
    }


def _q1_2025_loss_values() -> dict:
    # Shopify 2025 Q1 10-Q: a real pre-tax/net loss and income-tax benefit.
    return {
        "subscription_solutions_revenue": 620,
        "merchant_solutions_revenue": 1_740,
        "revenue": 2_360,
        "cost_of_revenue": 1_191,
        "gross_profit": 1_169,
        "sales_and_marketing": 405,
        "research_and_development": 377,
        "general_and_administrative": 109,
        "transaction_and_loan_losses": 75,
        "operating_expenses": 966,
        "operating_income": 203,
        "nonoperating_income_expense": -973,
        "pretax_income": -770,
        "income_tax": -88,
        "net_income": -682,
    }


@pytest.mark.parametrize("values,quarter,year", [
    (_q2_2026_values(), 2, 2026),
    (_q1_2025_loss_values(), 1, 2025),
])
def test_shop_reconciles_real_profit_and_loss_quarters(values, quarter, year):
    checks = validate_quarter(_shop_quarter(values, quarter, year))
    assert len(checks) == 6
    assert all(check.passed for check in checks)


def test_shop_reconciliation_detects_broken_identity():
    values = _q2_2026_values()
    values["net_income"] += 100
    with pytest.raises(ReconciliationError):
        validate_quarter(_shop_quarter(values, 2, 2026))


@pytest.mark.parametrize("values,quarter,year", [
    (_q2_2026_values(), 2, 2026),
    (_q1_2025_loss_values(), 1, 2025),
])
def test_shop_renders_profit_loss_and_tax_benefit(
    values, quarter, year, tmp_path: Path
):
    destination = tmp_path / f"shop-{year}q{quarter}.svg"
    render_module.render_svg(_shop_quarter(values, quarter, year), destination)
    svg = destination.read_text(encoding="utf-8")
    assert svg.count('class="label-card"') == 14
    assert "Subscription solutions" in svg
    assert "Merchant solutions" in svg
    assert "Transaction &amp; loan losses" in svg
    assert "SHOP" in svg

    for match in re.finditer(
        r'<rect class="label-card"[^>]*x="([-\d.]+)"[^>]*y="([-\d.]+)"[^>]*width="([-\d.]+)"[^>]*height="([-\d.]+)"',
        svg,
    ):
        x, y, width, height = (float(group) for group in match.groups())
        assert x >= 0
        assert x + width <= render_module.WIDTH
        assert y >= 0
        assert y + height <= render_module.HEIGHT
