from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Union


Number = Union[int, float]


@dataclass(frozen=True)
class Provenance:
    source_url: str
    accession: str
    document: str
    filing_date: str
    concept: str
    context_id: str
    period_start: str
    period_end: str
    unit: str
    decimals: str
    dimensions: Dict[str, str] = field(default_factory=dict)


@dataclass
class FinancialFact:
    key: str
    label: str
    value_millions: Number
    status: str
    provenance: List[Provenance]
    prior_value_millions: Optional[Number] = None
    derivation: Optional[str] = None

    @property
    def yoy_percent(self) -> Optional[float]:
        if self.prior_value_millions in (None, 0):
            return None
        return (self.value_millions / self.prior_value_millions - 1.0) * 100.0

    def to_dict(self) -> dict:
        value = asdict(self)
        value["yoy_percent"] = self.yoy_percent
        return value


@dataclass
class Quarter:
    company: str
    ticker: str
    fiscal_year: int
    fiscal_quarter: int
    start_date: str
    end_date: str
    currency: str
    scale: str
    facts: Dict[str, FinancialFact]

    def to_dict(self) -> dict:
        return {
            "company": self.company,
            "ticker": self.ticker,
            "fiscal_year": self.fiscal_year,
            "fiscal_quarter": self.fiscal_quarter,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "currency": self.currency,
            "scale": self.scale,
            "facts": {key: fact.to_dict() for key, fact in self.facts.items()},
        }
