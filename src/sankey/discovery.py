"""Discover configuration-ready quarterly filing metadata from EDGAR."""

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Dict, Iterable, Optional

from .sec import fetch_sec_json


SUBMISSIONS_BASE_URL = "https://data.sec.gov/submissions"
ARCHIVES_BASE_URL = "https://www.sec.gov/Archives/edgar/data"
def quarter_sequence(start: str, count: int) -> list:
    if count <= 0:
        raise ValueError("--quarters must be a positive integer")
    normalized = start.upper()
    if (
        len(normalized) != 6
        or normalized[4] != "Q"
        or not normalized[:4].isdigit()
        or normalized[5] not in "1234"
    ):
        raise ValueError(f"Invalid fiscal quarter: {start}; expected YYYYQ1 through YYYYQ4")
    year = int(normalized[:4])
    quarter = int(normalized[5])
    result = []
    for _ in range(count):
        result.append(f"{year}Q{quarter}")
        quarter -= 1
        if quarter == 0:
            year -= 1
            quarter = 4
    return result


def _quarter_key(report_date: str, fiscal_year_end_month: int = 12) -> str:
    try:
        period_end = date.fromisoformat(report_date)
    except ValueError as exc:
        raise ValueError(f"Invalid SEC report date: {report_date}") from exc
    if fiscal_year_end_month not in range(1, 13):
        raise ValueError("fiscal_year_end_month must be between 1 and 12")
    expected_months = {
        quarter: (fiscal_year_end_month + quarter * 3 - 1) % 12 + 1
        for quarter in range(1, 5)
    }
    distances = {
        quarter: min(
            (period_end.month - expected_month) % 12,
            (expected_month - period_end.month) % 12,
        )
        for quarter, expected_month in expected_months.items()
    }
    nearest_distance = min(distances.values())
    nearest_quarters = [
        quarter for quarter, distance in distances.items() if distance == nearest_distance
    ]
    if nearest_distance > 1 or len(nearest_quarters) != 1:
        raise ValueError(
            f"Unsupported fiscal period end {report_date} for fiscal year ending "
            f"in month {fiscal_year_end_month}"
        )
    quarter = nearest_quarters[0]
    expected_month = expected_months[quarter]
    fiscal_year = period_end.year + (
        1 if expected_month > fiscal_year_end_month else 0
    )
    return f"{fiscal_year}Q{quarter}"


def _submission_rows(block: dict) -> Iterable[dict]:
    required = (
        "accessionNumber",
        "filingDate",
        "form",
        "primaryDocument",
        "reportDate",
    )
    missing = [key for key in required if key not in block]
    if missing:
        raise ValueError("SEC submissions response is missing field(s): " + ", ".join(missing))
    row_count = len(block["accessionNumber"])
    if any(len(block[key]) != row_count for key in required):
        raise ValueError("SEC submissions response contains misaligned filing arrays")
    for index in range(row_count):
        yield {key: block[key][index] for key in required}


def _quarterly_filings(
    rows: Iterable[dict],
    fiscal_year_end_month: int = 12,
    quarterly_form: str = "10-Q",
    annual_form: str = "10-K",
    primary_document_contains: Optional[str] = None,
) -> Dict[str, dict]:
    filings: Dict[str, dict] = {}
    for row in rows:
        if row["form"] not in {quarterly_form, annual_form} or not row["reportDate"]:
            continue
        if (
            primary_document_contains
            and primary_document_contains.lower() not in row["primaryDocument"].lower()
        ):
            continue
        quarter = _quarter_key(row["reportDate"], fiscal_year_end_month)
        expected_form = annual_form if quarter.endswith("Q4") else quarterly_form
        if row["form"] != expected_form:
            continue
        existing = filings.get(quarter)
        if existing is None or row["filingDate"] > existing["filingDate"]:
            filings[quarter] = row
    return filings


def _select_xbrl_document(index_payload: dict, primary_document: str) -> str:
    items = index_payload.get("directory", {}).get("item", [])
    names = [item.get("name", "") for item in items]
    expected = f"{Path(primary_document).stem}_htm.xml"
    for name in names:
        if name.lower() == expected.lower():
            return name
    candidates = [name for name in names if name.lower().endswith("_htm.xml")]
    if len(candidates) == 1:
        return candidates[0]
    if not candidates and any(name.lower().endswith("-xbrl.zip") for name in names):
        # Some SEC directory indexes expose only the filing package even though
        # the conventional extracted Inline XBRL instance is addressable.
        return expected
    if not candidates:
        raise ValueError(
            f"No extracted XBRL instance ending in _htm.xml for {primary_document}"
        )
    raise ValueError(
        f"Multiple extracted XBRL instances for {primary_document}: " + ", ".join(candidates)
    )


def _select_html_document(index_payload: dict, name_contains: str) -> str:
    items = index_payload.get("directory", {}).get("item", [])
    candidates = [
        item.get("name", "")
        for item in items
        if name_contains.lower() in item.get("name", "").lower()
        and item.get("name", "").lower().endswith((".htm", ".html"))
    ]
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise ValueError(f"No HTML filing document containing {name_contains!r}")
    raise ValueError(
        f"Multiple HTML filing documents contain {name_contains!r}: "
        + ", ".join(candidates)
    )


def _period_dates(quarter: str, report_date: str, fiscal_week_based: bool = False) -> dict:
    period_end = date.fromisoformat(report_date)
    if fiscal_week_based:
        # A standalone 13-week quarter contains 91 inclusive days. Comparable
        # periods for a 52/53-week filer normally end exactly 52 weeks earlier.
        period_start = period_end - timedelta(days=90)
        prior_start = period_start - timedelta(days=364)
        prior_end = period_end - timedelta(days=364)
    else:
        start_month = (period_end.month - 3) % 12 + 1
        start_year = period_end.year - (1 if start_month > period_end.month else 0)
        period_start = date(start_year, start_month, 1)
        prior_start = date(start_year - 1, start_month, 1)
        prior_end = date(period_end.year - 1, period_end.month, period_end.day)
    return {
        "start_date": period_start.isoformat(),
        "end_date": report_date,
        "prior_start_date": prior_start.isoformat(),
        "prior_end_date": prior_end.isoformat(),
    }


def discover_filings(
    config: dict,
    quarters: int,
    user_agent: str,
    from_quarter: Optional[str] = None,
    fetch_json: Optional[Callable[[str, str], dict]] = None,
) -> dict:
    """Return SEC filing metadata shaped for the company's ``quarters`` config."""
    if quarters <= 0:
        raise ValueError("--quarters must be a positive integer")
    if not config.get("ticker") or not config.get("cik"):
        raise ValueError("Company config must define ticker and cik")
    fetch = fetch_json or fetch_sec_json
    cik = str(config["cik"]).zfill(10)
    submissions_url = f"{SUBMISSIONS_BASE_URL}/CIK{cik}.json"
    submissions = fetch(submissions_url, user_agent)
    try:
        recent = submissions["filings"]["recent"]
        historical_files = submissions["filings"].get("files", [])
    except (KeyError, TypeError) as exc:
        raise ValueError("SEC submissions response does not contain filing metadata") from exc

    fiscal_year_end_month = int(config.get("fiscal_year_end_month", 12))
    fiscal_week_based = bool(config.get("fiscal_week_based", False))
    quarterly_form = config.get("quarterly_form", "10-Q")
    annual_form = config.get("annual_form", "10-K")
    primary_document_contains = config.get("primary_document_contains")
    available = _quarterly_filings(
        _submission_rows(recent),
        fiscal_year_end_month,
        quarterly_form,
        annual_form,
        primary_document_contains,
    )
    requested = quarter_sequence(from_quarter, quarters) if from_quarter else None

    def enough_filings() -> bool:
        if requested is not None:
            return all(quarter in available for quarter in requested)
        return len(available) >= quarters

    for historical in historical_files:
        if enough_filings():
            break
        name = historical.get("name")
        if not name:
            continue
        payload = fetch(f"{SUBMISSIONS_BASE_URL}/{name}", user_agent)
        available.update(
            _quarterly_filings(
                _submission_rows(payload),
                fiscal_year_end_month,
                quarterly_form,
                annual_form,
                primary_document_contains,
            )
        )

    if requested is None:
        requested = sorted(
            available,
            key=lambda key: (int(key[:4]), int(key[5])),
            reverse=True,
        )[:quarters]
    missing = [quarter for quarter in requested if quarter not in available]
    if missing:
        raise ValueError("SEC submissions data is missing requested quarter(s): " + ", ".join(missing))

    cik_for_archive = str(int(cik))
    slug = config.get("slug", config["ticker"].lower())
    source_type = config.get("source_type", "xbrl")
    discovered = {}
    for quarter in requested:
        filing = available[quarter]
        accession = filing["accessionNumber"]
        accession_path = accession.replace("-", "")
        filing_base_url = f"{ARCHIVES_BASE_URL}/{cik_for_archive}/{accession_path}"
        index_payload = fetch(f"{filing_base_url}/index.json", user_agent)
        if source_type == "quarterly_html":
            document = _select_html_document(
                index_payload, config["source_document_contains"]
            )
        else:
            document = _select_xbrl_document(index_payload, filing["primaryDocument"])
        period_dates = _period_dates(
            quarter, filing["reportDate"], fiscal_week_based
        )
        if config.get("period_starts_from_previous_quarter"):
            year = int(quarter[:4])
            quarter_number = int(quarter[5])
            previous_key = (
                f"{year - 1}Q4" if quarter_number == 1 else f"{year}Q{quarter_number - 1}"
            )
            prior_previous_key = (
                f"{year - 2}Q4"
                if quarter_number == 1
                else f"{year - 1}Q{quarter_number - 1}"
            )
            if previous_key in available:
                period_dates["start_date"] = (
                    date.fromisoformat(available[previous_key]["reportDate"])
                    + timedelta(days=1)
                ).isoformat()
            if prior_previous_key in available:
                period_dates["prior_start_date"] = (
                    date.fromisoformat(available[prior_previous_key]["reportDate"])
                    + timedelta(days=1)
                ).isoformat()
        fixture_suffix = "sec_html" if source_type == "quarterly_html" else "sec_xbrl"
        discovered[quarter] = {
            **period_dates,
            "fixture": f"data/fixtures/{slug}_{quarter[:4]}_q{quarter[5]}_{fixture_suffix}.json",
            "source": {
                "form": filing["form"],
                "accession": accession,
                "document": document,
                "filing_date": filing["filingDate"],
                "url": f"{filing_base_url}/{document}",
            },
        }

    q4_quarters = [quarter for quarter in requested if quarter.endswith("Q4")]
    warnings = []
    if q4_quarters and annual_form != quarterly_form:
        warnings.append(
            f"{annual_form} filings generally lack standalone three-month Q4 facts; generate-series "
            "derives annual minus nine-month values for: " + ", ".join(q4_quarters)
        )
    return {
        "schema_version": 1,
        "discovered_at": datetime.now(timezone.utc).isoformat(),
        "company": config["company"],
        "ticker": config["ticker"],
        "cik": cik,
        "quarter_count": len(discovered),
        "quarters": discovered,
        "warnings": warnings,
    }
