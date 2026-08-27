from typing import Dict, Iterable, List, Optional, Sequence

from .models import FinancialFact, Provenance, Quarter


class FactSelectionError(ValueError):
    pass


def _canonical_dimensions(dimensions: dict) -> dict:
    """Treat Meta's pre-rename ``fb`` taxonomy prefix as its ``meta`` successor."""
    return {
        key.replace("fb:", "meta:", 1): value.replace("fb:", "meta:", 1)
        for key, value in dimensions.items()
    }


def _matches(raw: dict, concept: str, start: str, end: str, dimensions: dict) -> bool:
    return (
        raw["concept"] == concept
        and raw["start_date"] == start
        and raw["end_date"] == end
        and _canonical_dimensions(raw.get("dimensions", {}))
        == _canonical_dimensions(dimensions)
        and raw.get("unit") == "usd"
    )

def _select(facts: Iterable[dict], selector: dict, start: str, end: str) -> dict:
    concepts = selector.get("concepts", [selector["concept"]])
    dimension_options = selector.get("dimension_options", [selector["dimensions"]])
    matches = [
        fact
        for fact in facts
        if any(
            _matches(fact, concept, start, end, dimensions)
            for concept in concepts
            for dimensions in dimension_options
        )
    ]
    if not matches:
        raise FactSelectionError(
            f"No fact for {concepts} in {start}..{end} with dimensions "
            f"{dimension_options}"
        )
    numeric_decimals = [
        int(match["decimals"])
        for match in matches
        if str(match.get("decimals", "")).lstrip("-").isdigit()
    ]
    if numeric_decimals:
        most_precise = max(numeric_decimals)
        matches = [
            match
            for match in matches
            if str(match.get("decimals", "")).lstrip("-").isdigit()
            and int(match["decimals"]) == most_precise
        ]
    values = {match["value"] for match in matches}
    if len(values) != 1:
        raise FactSelectionError(f"Conflicting values for {selector['concept']}: {values}")
    return matches[0]


def _millions(raw_value: str, multiplier: int = 1) -> int:
    value = int(raw_value)
    if value % 1_000_000:
        raise FactSelectionError(f"Expected whole USD millions, received {value}")
    return value // 1_000_000 * multiplier


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


def normalize_meta(
    config: dict,
    extracted: dict,
    quarter_key: str,
    *,
    current_extracted: Optional[dict] = None,
    prior_extracted: Optional[dict] = None,
    allow_missing_prior: Sequence[str] = (),
) -> Quarter:
    quarter_config = config["quarters"][quarter_key]
    current_input = current_extracted or extracted
    prior_input = prior_extracted or extracted
    optional_selectors = set(config.get("optional_selectors", ()))
    facts: Dict[str, FinancialFact] = {}
    for key, selector in config["selectors"].items():
        try:
            current = _select(
                current_input["facts"],
                selector,
                quarter_config["start_date"],
                quarter_config["end_date"],
            )
        except FactSelectionError:
            # Some disclosures (e.g. Alphabet's segment revenue and hedging
            # adjustment) are not tagged in every extracted instance. Skip an
            # optional selector when the current period is unavailable rather
            # than failing the whole quarter.
            if key in optional_selectors:
                continue
            raise
        try:
            prior = _select(
                prior_input["facts"],
                selector,
                quarter_config["prior_start_date"],
                quarter_config["prior_end_date"],
            )
        except FactSelectionError:
            if key not in allow_missing_prior:
                raise
            prior = None
        facts[key] = FinancialFact(
            key=key,
            label=selector["label"],
            value_millions=_millions(current["value"], selector.get("multiplier", 1)),
            prior_value_millions=(
                _millions(prior["value"], selector.get("multiplier", 1))
                if prior
                else None
            ),
            status=selector["status"],
            provenance=[_provenance(current, current_input["source"])],
        )

    # Gross profit is a derived tech-company convenience (revenue minus cost of
    # revenue). Banks and other companies without a cost-of-revenue line do not
    # report it, so only derive it when both keys are present.
    if "revenue" in facts and "cost_of_revenue" in facts:
        revenue = facts["revenue"]
        cost = facts["cost_of_revenue"]
        prior_gross = None
        if (
            revenue.prior_value_millions is not None
            and cost.prior_value_millions is not None
        ):
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


def normalize_meta_q4(
    config: dict,
    annual_extracted: dict,
    nine_month_current_extracted: dict,
    nine_month_prior_extracted: dict,
    quarter_key: str,
    *,
    allow_missing_prior: Sequence[str] = (),
) -> Quarter:
    """Derive standalone Q4 values as annual reported facts minus nine months."""
    year = int(quarter_key[:4])
    quarter_config = config["quarters"][quarter_key]
    current_annual_period = (f"{year}-01-01", f"{year}-12-31")
    prior_annual_period = (f"{year - 1}-01-01", f"{year - 1}-12-31")
    current_nine_period = (f"{year}-01-01", f"{year}-09-30")
    prior_nine_period = (f"{year - 1}-01-01", f"{year - 1}-09-30")
    optional_selectors = set(config.get("optional_selectors", ()))
    facts: Dict[str, FinancialFact] = {}
    for key, selector in config["selectors"].items():
        try:
            annual_current = _select(
                annual_extracted["facts"], selector, *current_annual_period
            )
            nine_current = _select(
                nine_month_current_extracted["facts"], selector, *current_nine_period
            )
        except FactSelectionError:
            # Optional disclosures may be absent from the annual or nine-month
            # instance (Alphabet does not tag segment revenue cumulatively);
            # skip deriving a standalone Q4 value for them.
            if key in optional_selectors:
                continue
            raise
        try:
            annual_prior = _select(
                annual_extracted["facts"], selector, *prior_annual_period
            )
            nine_prior = _select(
                nine_month_prior_extracted["facts"], selector, *prior_nine_period
            )
        except FactSelectionError:
            if key not in allow_missing_prior:
                raise
            annual_prior = None
            nine_prior = None
        prior_value = None
        if annual_prior is not None and nine_prior is not None:
            prior_value = (
                _millions(annual_prior["value"], selector.get("multiplier", 1))
                - _millions(nine_prior["value"], selector.get("multiplier", 1))
            )
        facts[key] = FinancialFact(
            key=key,
            label=selector["label"],
            value_millions=(
                _millions(annual_current["value"], selector.get("multiplier", 1))
                - _millions(nine_current["value"], selector.get("multiplier", 1))
            ),
            prior_value_millions=prior_value,
            status="derived",
            provenance=[
                _provenance(annual_current, annual_extracted["source"]),
                _provenance(nine_current, nine_month_current_extracted["source"]),
            ],
            derivation="annual reported value - nine-month reported value",
        )

    # Only derive gross profit for companies that report a cost-of-revenue line
    # (see normalize_meta). Banks omit both keys.
    if "revenue" in facts and "cost_of_revenue" in facts:
        revenue = facts["revenue"]
        cost = facts["cost_of_revenue"]
        prior_gross = None
        if revenue.prior_value_millions is not None and cost.prior_value_millions is not None:
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
    return Quarter(
        company=config["company"],
        ticker=config["ticker"],
        fiscal_year=year,
        fiscal_quarter=4,
        start_date=quarter_config["start_date"],
        end_date=quarter_config["end_date"],
        currency="USD",
        scale="millions",
        facts=facts,
    )
