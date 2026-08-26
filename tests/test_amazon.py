from pathlib import Path

import stankey.render as render_module
from stankey.models import FinancialFact, Provenance, Quarter
from stankey.normalize import _select
from stankey.validate import validate_quarter


def _amazon_quarter(values: dict, quarter: int = 1) -> Quarter:
    labels = {
        "north_america_revenue": "North America",
        "international_revenue": "International",
        "aws_revenue": "AWS",
        "revenue": "Net sales",
        "cost_of_revenue": "Cost of sales",
        "gross_profit": "Gross profit",
        "fulfillment": "Fulfillment",
        "technology_infrastructure": "Technology & infrastructure",
        "marketing": "Sales & marketing",
        "general_and_administrative": "G&A",
        "other_operating_expense": "Other operating",
        "costs_and_expenses": "Costs & expenses",
        "operating_income": "Operating income",
        "nonoperating_income_expense": "Net non-operating",
        "pretax_income": "Pre-tax income",
        "income_tax": "Income tax",
        "equity_method_investment": "Equity-method activity",
        "net_income": "Net income",
    }
    provenance = Provenance(
        source_url="https://www.sec.gov/example.xml",
        accession="example",
        document="example.xml",
        filing_date="2022-04-29",
        concept="Example",
        context_id="current",
        period_start="2022-01-01",
        period_end="2022-03-31",
        unit="usd",
        decimals="-6",
    )
    return Quarter(
        company="Amazon.com, Inc.",
        ticker="AMZN",
        fiscal_year=2022,
        fiscal_quarter=quarter,
        start_date="2022-01-01",
        end_date="2022-03-31",
        currency="USD",
        scale="millions",
        facts={
            key: FinancialFact(
                key=key,
                label=labels[key],
                value_millions=value,
                status="derived" if key == "gross_profit" else "reported",
                provenance=[provenance],
            )
            for key, value in values.items()
        },
    )


def test_amazon_loss_quarter_reconciles_and_renders(tmp_path: Path):
    quarter = _amazon_quarter(
        {
            "north_america_revenue": 69_244,
            "international_revenue": 28_759,
            "aws_revenue": 18_441,
            "revenue": 116_444,
            "cost_of_revenue": 66_499,
            "gross_profit": 49_945,
            "fulfillment": 20_271,
            "technology_infrastructure": 14_842,
            "marketing": 8_320,
            "general_and_administrative": 2_594,
            "other_operating_expense": 249,
            "costs_and_expenses": 112_775,
            "operating_income": 3_669,
            "nonoperating_income_expense": -8_955,
            "pretax_income": -5_286,
            "income_tax": -1_422,
            "equity_method_investment": -1,
            "net_income": -3_865,
        }
    )
    assert all(check.passed for check in validate_quarter(quarter))
    destination = tmp_path / "amazon-loss.svg"
    render_module.render_svg(quarter, destination)
    svg = destination.read_text(encoding="utf-8")
    assert svg.count('class="label-card"') == 17
    assert 'font-size="18" font-weight="700"' in svg
    assert 'font-size="16" font-weight="700" fill=' in svg
    assert "−$5.3B" in svg
    assert "−$3.9B" in svg


def test_amazon_operating_income_offset_reconciles_and_renders(tmp_path: Path):
    quarter = _amazon_quarter(
        {
            "north_america_revenue": 65_557,
            "international_revenue": 29_145,
            "aws_revenue": 16_110,
            "revenue": 110_812,
            "cost_of_revenue": 62_930,
            "gross_profit": 47_882,
            "fulfillment": 18_498,
            "technology_infrastructure": 14_380,
            "marketing": 8_010,
            "general_and_administrative": 2_153,
            "other_operating_expense": -11,
            "costs_and_expenses": 105_960,
            "operating_income": 4_852,
            "nonoperating_income_expense": -537,
            "pretax_income": 4_315,
            "income_tax": 1_155,
            "equity_method_investment": -4,
            "net_income": 3_156,
        },
        quarter=3,
    )
    assert all(check.passed for check in validate_quarter(quarter))
    destination = tmp_path / "amazon-offset.svg"
    render_module.render_svg(quarter, destination)
    svg = destination.read_text(encoding="utf-8")
    assert 'data-key="other_operating_expense" data-round-left="true"' in svg
    assert "−$11M" in svg


def test_selector_prefers_the_most_precise_duplicate_fact():
    selector = {"concept": "IncomeTaxExpenseBenefit", "dimensions": {}}
    base = {
        "concept": "IncomeTaxExpenseBenefit",
        "unit": "usd",
        "context_id": "current",
        "start_date": "2026-01-01",
        "end_date": "2026-03-31",
        "dimensions": {},
    }
    selected = _select(
        [
            {**base, "value": "9600000000", "decimals": "-8"},
            {**base, "value": "9560000000", "decimals": "-6"},
        ],
        selector,
        "2026-01-01",
        "2026-03-31",
    )
    assert selected["value"] == "9560000000"
