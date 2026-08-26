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
    from .companies import get_adapter

    checks = get_adapter(quarter.ticker).build_checks(
        quarter.facts, tolerance_millions, _check
    )
    if any(not check.passed for check in checks):
        raise ReconciliationError(checks)
    return checks

def checks_to_dict(checks: List[Check]) -> list:
    return [asdict(check) for check in checks]
