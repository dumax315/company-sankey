from dataclasses import asdict, dataclass
from typing import List

from .models import Quarter


@dataclass(frozen=True)
class Check:
    name: str
    expected_millions: int
    actual_millions: int
    difference_millions: int
    tolerance_millions: int
    passed: bool


class ReconciliationError(ValueError):
    def __init__(self, checks: List[Check]):
        failures = [check.name for check in checks if not check.passed]
        super().__init__("Failed reconciliation: " + ", ".join(failures))
        self.checks = checks


def _check(name: str, expected: int, actual: int, tolerance: int) -> Check:
    difference = actual - expected
    return Check(name, expected, actual, difference, tolerance, abs(difference) <= tolerance)


def validate_quarter(quarter: Quarter, tolerance_millions: int = 1) -> List[Check]:
    f = quarter.facts
    if quarter.ticker.upper() == "AMZN":
        checks = [
            _check(
                "segment revenue equals consolidated revenue",
                f["revenue"].value_millions,
                f["north_america_revenue"].value_millions
                + f["international_revenue"].value_millions
                + f["aws_revenue"].value_millions,
                tolerance_millions,
            ),
            _check(
                "revenue less cost of sales equals gross profit",
                f["gross_profit"].value_millions,
                f["revenue"].value_millions - f["cost_of_revenue"].value_millions,
                tolerance_millions,
            ),
            _check(
                "gross profit less operating expenses equals operating income",
                f["operating_income"].value_millions,
                f["gross_profit"].value_millions
                - f["fulfillment"].value_millions
                - f["technology_infrastructure"].value_millions
                - f["marketing"].value_millions
                - f["general_and_administrative"].value_millions
                - f["other_operating_expense"].value_millions,
                tolerance_millions,
            ),
            _check(
                "expense components equal total costs and expenses",
                f["costs_and_expenses"].value_millions,
                f["cost_of_revenue"].value_millions
                + f["fulfillment"].value_millions
                + f["technology_infrastructure"].value_millions
                + f["marketing"].value_millions
                + f["general_and_administrative"].value_millions
                + f["other_operating_expense"].value_millions,
                tolerance_millions,
            ),
            _check(
                "operating plus non-operating equals pre-tax income",
                f["pretax_income"].value_millions,
                f["operating_income"].value_millions
                + f["nonoperating_income_expense"].value_millions,
                tolerance_millions,
            ),
            _check(
                "pre-tax less income tax plus equity-method activity equals net income",
                f["net_income"].value_millions,
                f["pretax_income"].value_millions
                - f["income_tax"].value_millions
                + f["equity_method_investment"].value_millions,
                tolerance_millions,
            ),
        ]
        if any(not check.passed for check in checks):
            raise ReconciliationError(checks)
        return checks
    if quarter.ticker.upper() == "GOOGL":
        checks = []
        # Segment revenue plus the intercompany hedging adjustment reconciles to
        # consolidated revenue. Alphabet does not tag segment revenue in every
        # extracted instance (nine-month and annual filings omit it), and some
        # quarters fold the hedging adjustment into the consolidated total
        # instead of tagging it separately. The identity is therefore checked
        # only when all three segments and the hedging line are present.
        segment_keys = (
            "google_services_revenue",
            "google_cloud_revenue",
            "other_bets_revenue",
        )
        if all(key in f for key in segment_keys) and "hedging_revenue" in f:
            segment_total = sum(f[key].value_millions for key in segment_keys)
            hedging = f["hedging_revenue"].value_millions
            checks.append(
                _check(
                    "segment revenue plus hedging equals consolidated revenue",
                    f["revenue"].value_millions,
                    segment_total + hedging,
                    tolerance_millions,
                )
            )
        checks.extend(
            [
                _check(
                    "revenue less cost of revenues equals gross profit",
                    f["gross_profit"].value_millions,
                    f["revenue"].value_millions - f["cost_of_revenue"].value_millions,
                    tolerance_millions,
                ),
                _check(
                    "gross profit less operating expenses equals operating income",
                    f["operating_income"].value_millions,
                    f["gross_profit"].value_millions
                    - f["research_and_development"].value_millions
                    - f["sales_and_marketing"].value_millions
                    - f["general_and_administrative"].value_millions,
                    tolerance_millions,
                ),
                _check(
                    "expense components equal total costs and expenses",
                    f["costs_and_expenses"].value_millions,
                    f["cost_of_revenue"].value_millions
                    + f["research_and_development"].value_millions
                    + f["sales_and_marketing"].value_millions
                    + f["general_and_administrative"].value_millions,
                    tolerance_millions,
                ),
                _check(
                    "revenue less total costs and expenses equals operating income",
                    f["operating_income"].value_millions,
                    f["revenue"].value_millions - f["costs_and_expenses"].value_millions,
                    tolerance_millions,
                ),
                _check(
                    "operating plus non-operating equals pre-tax income",
                    f["pretax_income"].value_millions,
                    f["operating_income"].value_millions
                    + f["nonoperating_income_expense"].value_millions,
                    tolerance_millions,
                ),
                _check(
                    "pre-tax less income tax equals net income",
                    f["net_income"].value_millions,
                    f["pretax_income"].value_millions - f["income_tax"].value_millions,
                    tolerance_millions,
                ),
            ]
        )
        if any(not check.passed for check in checks):
            raise ReconciliationError(checks)
        return checks
    checks = [
        _check(
            "product revenue equals Family of Apps revenue",
            f["family_of_apps_revenue"].value_millions,
            f["advertising_revenue"].value_millions + f["other_foa_revenue"].value_millions,
            tolerance_millions,
        ),
        _check(
            "segment revenue equals consolidated revenue",
            f["revenue"].value_millions,
            f["family_of_apps_revenue"].value_millions + f["reality_labs_revenue"].value_millions,
            tolerance_millions,
        ),
        _check(
            "revenue less cost of revenue equals gross profit",
            f["gross_profit"].value_millions,
            f["revenue"].value_millions - f["cost_of_revenue"].value_millions,
            tolerance_millions,
        ),
        _check(
            "gross profit less operating expenses equals operating income",
            f["operating_income"].value_millions,
            f["gross_profit"].value_millions
            - f["research_and_development"].value_millions
            - f["marketing_and_sales"].value_millions
            - f["general_and_administrative"].value_millions,
            tolerance_millions,
        ),
        _check(
            "expense components equal total costs and expenses",
            f["costs_and_expenses"].value_millions,
            f["cost_of_revenue"].value_millions
            + f["research_and_development"].value_millions
            + f["marketing_and_sales"].value_millions
            + f["general_and_administrative"].value_millions,
            tolerance_millions,
        ),
        _check(
            "operating plus non-operating equals pre-tax income",
            f["pretax_income"].value_millions,
            f["operating_income"].value_millions + f["nonoperating_income_expense"].value_millions,
            tolerance_millions,
        ),
        _check(
            "pre-tax less income tax equals net income",
            f["net_income"].value_millions,
            f["pretax_income"].value_millions - f["income_tax"].value_millions,
            tolerance_millions,
        ),
    ]
    if any(not check.passed for check in checks):
        raise ReconciliationError(checks)
    return checks


def checks_to_dict(checks: List[Check]) -> list:
    return [asdict(check) for check in checks]
