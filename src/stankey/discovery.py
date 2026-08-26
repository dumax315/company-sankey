"""Discover configuration-ready quarterly filing metadata from EDGAR."""

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable, Dict, Iterable, Optional

from .sec import fetch_sec_json


SUBMISSIONS_BASE_URL = "https://data.sec.gov/submissions"
ARCHIVES_BASE_URL = "https://www.sec.gov/Archives/edgar/data"
SUPPORTED_FORMS = {"10-Q", "10-K"}


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


def _quarter_key(report_date: str) -> str:
    try:
        period_end = date.fromisoformat(report_date)
    except ValueError as exc:
        raise ValueError(f"Invalid SEC report date: {report_date}") from exc
    quarter_by_month = {3: 1, 6: 2, 9: 3, 12: 4}
    quarter = quarter_by_month.get(period_end.month)
    if quarter is None:
        raise ValueError(
            f"Unsupported fiscal period end {report_date}; META discovery expects calendar quarters"
        )
    return f"{period_end.year}Q{quarter}"


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


def _quarterly_filings(rows: Iterable[dict]) -> Dict[str, dict]:
    filings: Dict[str, dict] = {}
    for row in rows:
        if row["form"] not in SUPPORTED_FORMS or not row["reportDate"]:
            continue
        quarter = _quarter_key(row["reportDate"])
        expected_form = "10-K" if quarter.endswith("Q4") else "10-Q"
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


def _period_dates(quarter: str, report_date: str) -> dict:
    year = int(quarter[:4])
    quarter_number = int(quarter[5])
    start_month = (quarter_number - 1) * 3 + 1
    period_end = date.fromisoformat(report_date)
    return {
        "start_date": date(year, start_month, 1).isoformat(),
        "end_date": report_date,
        "prior_start_date": date(year - 1, start_month, 1).isoformat(),
        "prior_end_date": date(year - 1, period_end.month, period_end.day).isoformat(),
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
    if config.get("ticker", "").upper() != "META":
        raise ValueError("The current discovery workflow supports only META")
    fetch = fetch_json or fetch_sec_json
    cik = str(config["cik"]).zfill(10)
    submissions_url = f"{SUBMISSIONS_BASE_URL}/CIK{cik}.json"
    submissions = fetch(submissions_url, user_agent)
    try:
        recent = submissions["filings"]["recent"]
        historical_files = submissions["filings"].get("files", [])
    except (KeyError, TypeError) as exc:
        raise ValueError("SEC submissions response does not contain filing metadata") from exc

    available = _quarterly_filings(_submission_rows(recent))
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
        available.update(_quarterly_filings(_submission_rows(payload)))

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
    discovered = {}
    for quarter in requested:
        filing = available[quarter]
        accession = filing["accessionNumber"]
        accession_path = accession.replace("-", "")
        filing_base_url = f"{ARCHIVES_BASE_URL}/{cik_for_archive}/{accession_path}"
        index_payload = fetch(f"{filing_base_url}/index.json", user_agent)
        document = _select_xbrl_document(index_payload, filing["primaryDocument"])
        discovered[quarter] = {
            **_period_dates(quarter, filing["reportDate"]),
            "fixture": f"data/fixtures/meta_{quarter[:4]}_q{quarter[5]}_sec_xbrl.json",
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
    if q4_quarters:
        warnings.append(
            "10-K filings generally lack standalone three-month Q4 facts; generate-series "
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
