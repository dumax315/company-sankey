from typing import Dict, Iterable, List

from .models import FinancialFact, Provenance, Quarter


class FactSelectionError(ValueError):
    pass


def _matches(raw: dict, concept: str, start: str, end: str, dimensions: dict) -> bool:
    return (
        raw["concept"] == concept
        and raw["start_date"] == start
        and raw["end_date"] == end
        and raw.get("dimensions", {}) == dimensions
        and raw.get("unit") == "usd"
    )

def _select(facts: Iterable[dict], selector: dict, start: str, end: str) -> dict:
    matches = [
        fact
        for fact in facts
        if _matches(fact, selector["concept"], start, end, selector["dimensions"])
    ]
    values = {match["value"] for match in matches}
    if not matches:
        raise FactSelectionError(
            f"No fact for {selector['concept']} in {start}..{end} with dimensions "
            f"{selector['dimensions']}"
        )
    if len(values) != 1:
        raise FactSelectionError(f"Conflicting values for {selector['concept']}: {values}")
    return matches[0]


def _millions(raw_value: str) -> int:
    value = int(raw_value)
    if value % 1_000_000:
        raise FactSelectionError(f"Expected whole USD millions, received {value}")
    return value // 1_000_000


def _provenance(raw: dict, source: dict) -> Provenance:
    return Provenance(
        source_url=source["url"],
        accession=source["accession"],
        document=source["document"],
        filing_date=source["filing_date"],
        concept=raw["concept"],
        context_id=raw["context_id"],
        period_start=raw["start_date"],
        period_end=raw["end_date"],
        unit=raw["unit"],
        decimals=raw["decimals"],
        dimensions=raw.get("dimensions", {}),
    )


def normalize_meta(config: dict, extracted: dict, quarter_key: str) -> Quarter:
    quarter_config = config["quarters"][quarter_key]
    source = extracted["source"]
    facts: Dict[str, FinancialFact] = {}
    for key, selector in config["selectors"].items():
        current = _select(
            extracted["facts"],
            selector,
            quarter_config["start_date"],
            quarter_config["end_date"],
        )
        prior = _select(
            extracted["facts"],
            selector,
            quarter_config["prior_start_date"],
            quarter_config["prior_end_date"],
        )
        facts[key] = FinancialFact(
            key=key,
            label=selector["label"],
            value_millions=_millions(current["value"]),
            prior_value_millions=_millions(prior["value"]),
            status=selector["status"],
            provenance=[_provenance(current, source)],
        )

    revenue = facts["revenue"]
    cost = facts["cost_of_revenue"]
    prior_gross = revenue.prior_value_millions - cost.prior_value_millions
    facts["gross_profit"] = FinancialFact(
        key="gross_profit",
        label="Gross profit",
        value_millions=revenue.value_millions - cost.value_millions,
        prior_value_millions=prior_gross,
        status="derived",
        provenance=revenue.provenance + cost.provenance,
        derivation="revenue - cost_of_revenue",
    )
    year, q = quarter_key.split("Q")
    return Quarter(
        company=config["company"],
        ticker=config["ticker"],
        fiscal_year=int(year),
        fiscal_quarter=int(q),
        start_date=quarter_config["start_date"],
        end_date=quarter_config["end_date"],
        currency="USD",
        scale="millions",
        facts=facts,
    )
