from pathlib import Path

import pytest

import stankey.render as render_module
from stankey.models import FinancialFact, Provenance, Quarter
from stankey.normalize import normalize_meta_q4
from stankey.validate import ReconciliationError, validate_quarter


LABELS = {
    "dram_revenue": "DRAM",
    "nand_revenue": "NAND",
    "other_product_revenue": "Other products",
    "revenue": "Revenue",
    "cost_of_revenue": "Cost of goods sold",
    "gross_profit": "Gross profit",
    "research_and_development": "R&D",
    "selling_general_and_administrative": "SG&A",
    "restructuring": "Restructuring",
    "other_operating_expense": "Other operating",
    "operating_income": "Operating income",
    "investment_income": "Investment income",
    "interest_expense": "Interest expense",
    "other_nonoperating_income_expense": "Other non-operating",
    "pretax_income": "Pre-tax income",
    "income_tax": "Income tax",
    "equity_method_investment": "Equity-method activity",
    "net_income": "Net income",
}


def _micron_quarter(values: dict, year: int = 2026, quarter: int = 3) -> Quarter:
    provenance = Provenance(
        source_url="https://www.sec.gov/example.xml",
        accession="example",
        document="example.xml",
        filing_date="2026-06-25",
        concept="Example",
        context_id="current",
        period_start="2026-02-27",
        period_end="2026-05-28",
        unit="usd",
        decimals="-6",
    )
    return Quarter(
        company="Micron Technology, Inc.",
        ticker="MU",
        fiscal_year=year,
        fiscal_quarter=quarter,
        start_date="2026-02-27",
        end_date="2026-05-28",
        currency="USD",
        scale="millions",
        facts={
            key: FinancialFact(
                key=key,
                label=LABELS[key],
                value_millions=value,
                status="derived" if key == "gross_profit" else "reported",
                provenance=[provenance],
            )
            for key, value in values.items()
        },
    )


def _q3_2026_values() -> dict:
    return {
        "dram_revenue": 31_328,
        "nand_revenue": 9_943,
        "other_product_revenue": 185,
        "revenue": 41_456,
        "cost_of_revenue": 6_400,
        "gross_profit": 35_056,
        "research_and_development": 1_316,
        "selling_general_and_administrative": 407,
        "other_operating_expense": 15,
        "operating_income": 33_318,
        "investment_income": 215,
        "interest_expense": 0,
        "other_nonoperating_income_expense": -321,
        "pretax_income": 33_212,
        "income_tax": 4_978,
        "equity_method_investment": 9,
        "net_income": 28_243,
    }


def test_micron_profitable_quarter_reconciles_and_renders(tmp_path: Path):
    quarter = _micron_quarter(_q3_2026_values())
    assert all(check.passed for check in validate_quarter(quarter))
    destination = tmp_path / "micron-profit.svg"
    render_module.render_svg(quarter, destination)
    svg = destination.read_text(encoding="utf-8")
    assert svg.count('class="label-card"') == 17
    assert "DRAM" in svg
    assert "NAND" in svg
    assert "MU" in svg


def test_micron_loss_quarter_reconciles_and_renders(tmp_path: Path):
    quarter = _micron_quarter(
        {
            "dram_revenue": 2_722,
            "nand_revenue": 885,
            "other_product_revenue": 86,
            "revenue": 3_693,
            "cost_of_revenue": 4_899,
            "gross_profit": -1_206,
            "research_and_development": 788,
            "selling_general_and_administrative": 231,
            "restructuring": 86,
            "other_operating_expense": -8,
            "operating_income": -2_303,
            "investment_income": 119,
            "interest_expense": 89,
            "other_nonoperating_income_expense": 2,
            "pretax_income": -2_271,
            "income_tax": 54,
            "equity_method_investment": 13,
            "net_income": -2_312,
        },
        year=2023,
        quarter=2,
    )
    assert all(check.passed for check in validate_quarter(quarter))
    destination = tmp_path / "micron-loss.svg"
    render_module.render_svg(quarter, destination)
    svg = destination.read_text(encoding="utf-8")
    assert svg.count('class="label-card"') == 18
    assert "−$1.2B" in svg
    assert "−$2.3B" in svg


def test_micron_reconciliation_detects_broken_identity():
    values = _q3_2026_values()
    values["net_income"] += 100
    with pytest.raises(ReconciliationError):
        validate_quarter(_micron_quarter(values))


def test_q4_treats_omitted_nine_month_restructuring_as_zero():
    config = {
        "company": "Micron Technology, Inc.",
        "ticker": "MU",
        "quarters": {
            "2025Q4": {
                "start_date": "2025-05-30",
                "end_date": "2025-08-28",
                "prior_start_date": "2024-05-31",
                "prior_end_date": "2024-08-29",
            }
        },
        "optional_selectors": ["restructuring"],
        "selectors": {
            "revenue": {
                "label": "Revenue",
                "concept": "Revenue",
                "dimensions": {},
                "status": "reported",
            },
            "restructuring": {
                "label": "Restructuring",
                "concept": "Restructuring",
                "dimensions": {},
                "q4_missing_nine_as_zero": True,
                "status": "reported",
            },
        },
    }

    def fact(concept, value, start, end):
        return {
            "concept": concept,
            "value": str(value * 1_000_000),
            "unit": "usd",
            "decimals": "-6",
            "context_id": f"{concept}-{end}",
            "start_date": start,
            "end_date": end,
            "dimensions": {},
        }

    source = {
        "url": "https://www.sec.gov/example.xml",
        "accession": "example",
        "document": "example.xml",
        "filing_date": "2025-10-03",
    }
    annual = {
        "source": source,
        "facts": [
            fact("Revenue", 37_000, "2024-08-30", "2025-08-28"),
            fact("Revenue", 25_000, "2023-09-01", "2024-08-29"),
            fact("Restructuring", 39, "2024-08-30", "2025-08-28"),
            fact("Restructuring", 1, "2023-09-01", "2024-08-29"),
        ],
    }
    nine_month = {
        "source": source,
        "facts": [
            fact("Revenue", 25_685, "2024-08-30", "2025-05-29"),
            fact("Revenue", 17_000, "2023-09-01", "2024-05-30"),
        ],
    }

    quarter = normalize_meta_q4(
        config, annual, nine_month, nine_month, "2025Q4"
    )

    assert quarter.facts["restructuring"].value_millions == 39
    assert quarter.facts["restructuring"].prior_value_millions == 1
    assert len(quarter.facts["restructuring"].provenance) == 1
