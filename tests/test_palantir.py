import json
from pathlib import Path

import pytest

import stankey.render as render_module
from stankey.models import FinancialFact, Provenance, Quarter
from stankey.normalize import _millions, _select, normalize_meta_q4
from stankey.sec import parse_xbrl
from stankey.validate import ReconciliationError, validate_quarter


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PALANTIR_CONFIG = json.loads(
    (PROJECT_ROOT / "configs" / "companies" / "palantir.json").read_text()
)

LABELS = {
    key: selector["label"] for key, selector in PALANTIR_CONFIG["selectors"].items()
}
LABELS["gross_profit"] = "Gross profit"


def _palantir_quarter(values: dict, year: int = 2026, quarter: int = 2) -> Quarter:
    provenance = Provenance(
        source_url="https://www.sec.gov/example.xml",
        accession="example",
        document="example.xml",
        filing_date="2026-08-04",
        concept="Example",
        context_id="current",
        period_start=f"{year}-04-01",
        period_end=f"{year}-06-30",
        unit="usd",
        decimals="-3",
    )
    return Quarter(
        company="Palantir Technologies Inc.",
        ticker="PLTR",
        fiscal_year=year,
        fiscal_quarter=quarter,
        start_date=f"{year}-04-01",
        end_date=f"{year}-06-30",
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


def _q2_2026_values() -> dict:
    # Palantir 2026 Q2 10-Q (USD millions, preserving filed $000 precision).
    return {
        "government_revenue": 990.032,
        "commercial_revenue": 945.432,
        "revenue": 1_935.464,
        "cost_of_revenue": 296.870,
        "gross_profit": 1_638.594,
        "sales_and_marketing": 339.500,
        "research_and_development": 192.513,
        "general_and_administrative": 194.577,
        "operating_expenses": 726.590,
        "operating_income": 912.004,
        "investment_income": 77.505,
        "other_nonoperating_income_expense": 91.836,
        "pretax_income": 1_081.345,
        "income_tax": 15.383,
        "profit_loss": 1_065.962,
        "noncontrolling_interest": 4.072,
        "net_income": 1_061.890,
    }


def _q3_2021_values() -> dict:
    # Palantir 2021 Q3 10-Q: operating, pre-tax, and net losses with no NCI.
    return {
        "government_revenue": 217.836,
        "commercial_revenue": 174.310,
        "revenue": 392.146,
        "cost_of_revenue": 86.804,
        "gross_profit": 305.342,
        "sales_and_marketing": 153.443,
        "research_and_development": 94.316,
        "general_and_administrative": 149.524,
        "operating_expenses": 397.283,
        "operating_income": -91.941,
        "investment_income": 0.379,
        "interest_expense": 0.609,
        "other_nonoperating_income_expense": -8.528,
        "pretax_income": -100.699,
        "income_tax": 1.438,
        "net_income": -102.137,
    }


def test_palantir_profitable_quarter_reconciles_and_renders(tmp_path: Path):
    quarter = _palantir_quarter(_q2_2026_values())
    assert all(check.passed for check in validate_quarter(quarter))

    destination = tmp_path / "palantir-profit.svg"
    render_module.render_svg(quarter, destination)
    svg = destination.read_text(encoding="utf-8")
    assert svg.count('class="label-card"') == 15
    assert "Government" in svg
    assert "Commercial" in svg
    assert "$990.032M" in svg
    assert "PLTR" in svg


def test_palantir_loss_quarter_without_nci_reconciles_and_renders(tmp_path: Path):
    quarter = _palantir_quarter(_q3_2021_values(), year=2021, quarter=3)
    assert all(check.passed for check in validate_quarter(quarter))

    destination = tmp_path / "palantir-loss.svg"
    render_module.render_svg(quarter, destination)
    svg = destination.read_text(encoding="utf-8")
    assert svg.count('class="label-card"') == 15
    assert "−$91.941M" in svg
    assert "−$102.137M" in svg
    assert "Noncontrolling int." not in svg


def test_palantir_tax_benefit_loss_reconciles_and_renders(tmp_path: Path):
    values = _q3_2021_values()
    values["income_tax"] = -20.000
    values["net_income"] = values["pretax_income"] - values["income_tax"]
    quarter = _palantir_quarter(values, year=2021, quarter=3)

    assert all(check.passed for check in validate_quarter(quarter))
    destination = tmp_path / "palantir-tax-benefit.svg"
    render_module.render_svg(quarter, destination)
    assert destination.is_file()


def test_palantir_reconciliation_detects_broken_identity():
    values = _q2_2026_values()
    values["net_income"] += 10
    with pytest.raises(ReconciliationError):
        validate_quarter(_palantir_quarter(values))


@pytest.mark.parametrize(
    ("selector_key", "concept", "dimensions"),
    [
        (
            "government_revenue",
            "RevenueFromContractWithCustomerIncludingAssessedTax",
            {
                "srt:ConsolidationItemsAxis": "us-gaap:OperatingSegmentsMember",
                "us-gaap:AccountsNotesLoansAndFinancingReceivablesByLegalEntityOfCounterpartyTypeAxis": "us-gaap:GovernmentMember",
            },
        ),
        (
            "commercial_revenue",
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            {
                "srt:ConsolidationItemsAxis": "us-gaap:OperatingSegmentsMember",
                "us-gaap:StatementBusinessSegmentsAxis": "pltr:CommercialSegmentMember",
            },
        ),
        (
            "commercial_revenue",
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            {
                "srt:ConsolidationItemsAxis": "us-gaap:OperatingSegmentsMember",
                "us-gaap:StatementBusinessSegmentsAxis": "pltr:CommercialOperatingSegmentMember",
            },
        ),
    ],
)
def test_palantir_segment_selectors_cover_historical_drift(
    selector_key: str, concept: str, dimensions: dict
):
    fact = {
        "concept": concept,
        "value": "1000000",
        "unit": "usd",
        "decimals": "-3",
        "context_id": "current",
        "start_date": "2026-04-01",
        "end_date": "2026-06-30",
        "dimensions": dimensions,
    }
    assert _select(
        [fact],
        PALANTIR_CONFIG["selectors"][selector_key],
        "2026-04-01",
        "2026-06-30",
    ) == fact


def test_q4_treats_new_noncontrolling_interest_as_zero_before_acquisition():
    config = {
        "company": "Palantir Technologies Inc.",
        "ticker": "PLTR",
        "allow_fractional_millions": True,
        "quarters": {
            "2022Q4": {
                "start_date": "2022-10-01",
                "end_date": "2022-12-31",
                "prior_start_date": "2021-10-01",
                "prior_end_date": "2021-12-31",
            }
        },
        "optional_selectors": ["noncontrolling_interest"],
        "selectors": {
            "revenue": {
                "label": "Revenue",
                "concept": "Revenue",
                "dimensions": {},
                "status": "reported",
            },
            "noncontrolling_interest": {
                "label": "Noncontrolling int.",
                "concept": "NCI",
                "dimensions": {},
                "q4_missing_nine_as_zero": True,
                "status": "reported",
            },
        },
    }

    def fact(concept, value, start, end):
        return {
            "concept": concept,
            "value": str(value),
            "unit": "usd",
            "decimals": "-3",
            "context_id": f"{concept}-{end}",
            "start_date": start,
            "end_date": end,
            "dimensions": {},
        }

    source = {
        "url": "https://www.sec.gov/example.xml",
        "accession": "example",
        "document": "example.xml",
        "filing_date": "2023-02-21",
    }
    annual = {
        "source": source,
        "facts": [
            fact("Revenue", 1_905_871_000, "2022-01-01", "2022-12-31"),
            fact("Revenue", 1_541_889_000, "2021-01-01", "2021-12-31"),
            fact("NCI", 2_611_000, "2022-01-01", "2022-12-31"),
        ],
    }
    nine_month = {
        "source": source,
        "facts": [
            fact("Revenue", 1_397_247_000, "2022-01-01", "2022-09-30"),
            fact("Revenue", 1_108_000_000, "2021-01-01", "2021-09-30"),
        ],
    }

    quarter = normalize_meta_q4(config, annual, nine_month, nine_month, "2022Q4")
    nci = quarter.facts["noncontrolling_interest"]
    assert nci.value_millions == 2.611
    assert nci.prior_value_millions is None
    assert len(nci.provenance) == 1


def test_parser_resolves_usd_measure_when_unit_id_is_not_lowercase_usd(
    tmp_path: Path,
):
    instance = tmp_path / "instance.xml"
    instance.write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<xbrl xmlns="http://www.xbrl.org/2003/instance"
      xmlns:iso4217="http://www.xbrl.org/2003/iso4217"
      xmlns:us-gaap="http://fasb.org/us-gaap/2021-01-31">
  <unit id="Unit_USD"><measure>iso4217:USD</measure></unit>
  <context id="quarter">
    <entity><identifier scheme="example">PLTR</identifier></entity>
    <period><startDate>2021-07-01</startDate><endDate>2021-09-30</endDate></period>
  </context>
  <us-gaap:Revenues contextRef="quarter" unitRef="Unit_USD" decimals="-3">392146000</us-gaap:Revenues>
</xbrl>
""",
        encoding="utf-8",
    )

    extracted = parse_xbrl(
        instance,
        {"url": "", "accession": "", "document": "", "filing_date": ""},
    )
    assert extracted["facts"][0]["value"] == "392146000"
    assert _millions(extracted["facts"][0]["value"], allow_fractional=True) == 392.146
