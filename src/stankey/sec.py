import hashlib
import json
import re
import time
import urllib.request
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, List


XBRL_NS = "http://www.xbrl.org/2003/instance"
XBRLDI_NS = "http://xbrl.org/2006/xbrldi"


def _validate_user_agent(user_agent: str) -> None:
    if "@" not in user_agent or len(user_agent) < 8:
        raise ValueError("SEC User-Agent must identify a person or organization and email")


def fetch_sec_json(url: str, user_agent: str) -> dict:
    """Fetch a JSON response from an SEC endpoint under fair-access pacing."""
    _validate_user_agent(user_agent)
    retryable_statuses = {429, 500, 502, 503, 504}
    last_error = None
    for attempt in range(4):
        request = urllib.request.Request(url, headers={"User-Agent": user_agent})
        time.sleep(0.12 if attempt == 0 else 0.5 * (2 ** (attempt - 1)))
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except HTTPError as exc:
            last_error = exc
            if exc.code not in retryable_statuses:
                break
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
    raise ValueError(f"Could not fetch SEC JSON {url}: {last_error}") from last_error


def download_sec_file(url: str, destination: Path, user_agent: str) -> Path:
    """Download an SEC filing document into an immutable-by-convention cache."""
    _validate_user_agent(user_agent)
    if destination.exists():
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    retryable_statuses = {429, 500, 502, 503, 504}
    last_error = None
    payload = None
    for attempt in range(4):
        request = urllib.request.Request(url, headers={"User-Agent": user_agent})
        time.sleep(0.12 if attempt == 0 else 0.5 * (2 ** (attempt - 1)))
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = response.read()
            break
        except HTTPError as exc:
            last_error = exc
            if exc.code not in retryable_statuses:
                break
        except (URLError, TimeoutError) as exc:
            last_error = exc
    if payload is None:
        raise ValueError(f"Could not download SEC filing document {url}: {last_error}") from last_error
    temp = destination.with_suffix(destination.suffix + ".tmp")
    temp.write_bytes(payload)
    temp.replace(destination)
    return destination


def download_xbrl(url: str, destination: Path, user_agent: str) -> Path:
    """Backward-compatible name for downloading an SEC XBRL instance."""
    return download_sec_file(url, destination, user_agent)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_xbrl(path: Path, source: Dict[str, str]) -> dict:
    """Extract duration USD facts without interpreting their accounting meaning."""
    root = ET.parse(path).getroot()
    ns = {"x": XBRL_NS, "xbrldi": XBRLDI_NS}
    usd_unit_ids = {
        unit.attrib["id"]
        for unit in root.findall("x:unit", ns)
        if any(
            (measure.text or "").rsplit(":", 1)[-1].upper() == "USD"
            for measure in unit.findall("x:measure", ns)
        )
    }
    contexts: Dict[str, dict] = {}
    for context in root.findall("x:context", ns):
        start = context.find(".//x:startDate", ns)
        end = context.find(".//x:endDate", ns)
        if start is None or end is None:
            continue
        dimensions = {
            member.attrib["dimension"]: (member.text or "")
            for member in context.findall(".//xbrldi:explicitMember", ns)
        }
        contexts[context.attrib["id"]] = {
            "start_date": start.text,
            "end_date": end.text,
            "dimensions": dimensions,
        }

    facts: List[dict] = []
    seen = set()
    for element in root:
        context_id = element.attrib.get("contextRef")
        if context_id not in contexts or element.attrib.get("unitRef") not in usd_unit_ids:
            continue
        raw_value = (element.text or "").strip()
        if not raw_value:
            continue
        context = contexts[context_id]
        concept = element.tag.rsplit("}", 1)[-1]
        identity = (concept, context_id, raw_value)
        if identity in seen:
            continue
        seen.add(identity)
        facts.append(
            {
                "concept": concept,
                "value": raw_value,
                "unit": "usd",
                "decimals": element.attrib.get("decimals", ""),
                "context_id": context_id,
                **context,
            }
        )
    return {
        "fixture_version": 1,
        "description": "Facts parsed directly from the downloaded SEC XBRL instance.",
        "source": {**source, "sha256": sha256_file(path)},
        "facts": facts,
    }


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: List[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data)


_HTML_NUMBER = r"(?:\([\d,]+(?:\.\d+)?\)|-?[\d,]+(?:\.\d+)?)"


def _statement_text(path: Path) -> str:
    parser = _TextExtractor()
    parser.feed(path.read_text(encoding="utf-8", errors="replace"))
    text = re.sub(r"\s+", " ", " ".join(parser.parts)).strip()
    markers = (
        "ASML - Summary US GAAP Consolidated Statements of Operations",
        "Three months ended",
    )
    starts = [text.find(marker) for marker in markers if text.find(marker) >= 0]
    if not starts:
        raise ValueError("Could not find a quarterly statement of operations in SEC HTML")
    return text[min(starts):]


def _reported_millions_to_base_units(value: str) -> str:
    normalized = value.replace(",", "").strip()
    negative = normalized.startswith("(") and normalized.endswith(")")
    if negative:
        normalized = normalized[1:-1]
    try:
        millions = Decimal(normalized)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid reported monetary value: {value}") from exc
    if negative:
        millions = -millions
    base_units = millions * Decimal(1_000_000)
    if base_units != base_units.to_integral_value():
        raise ValueError(f"Reported value has sub-unit precision: {value} million")
    return str(int(base_units))


def parse_quarterly_html(
    path: Path,
    source: Dict[str, str],
    quarter_config: dict,
    selectors: dict,
    unit: str,
) -> dict:
    """Extract two-column quarterly facts from a filed HTML statement.

    ASML's quarterly 6-K exhibits are not XBRL. They do, however, consistently
    include a US-GAAP statement of operations with prior-year and current-year
    standalone-quarter columns. Selectors provide the exact filed row labels so
    this parser stays deterministic and auditable rather than guessing at table
    semantics.
    """
    text = _statement_text(path)
    facts: List[dict] = []
    for concept, selector in selectors.items():
        labels = selector.get("html_labels", [selector.get("html_label")])
        labels = [label for label in labels if label]
        if not labels:
            raise ValueError(f"HTML selector {concept} must define html_label(s)")
        match = None
        matched_label = None
        for label in labels:
            candidate = re.search(
                rf"{re.escape(label)}\s+({_HTML_NUMBER})\s+({_HTML_NUMBER})",
                text,
                flags=re.IGNORECASE,
            )
            if candidate is not None and (match is None or candidate.start() < match.start()):
                match = candidate
                matched_label = label
        if match is None:
            raise ValueError(
                f"Could not find HTML row for {concept}; expected one of {labels}"
            )
        prior_value, current_value = match.group(1), match.group(2)
        for context_id, value, start, end in (
            (
                "prior-quarter",
                prior_value,
                quarter_config["prior_start_date"],
                quarter_config["prior_end_date"],
            ),
            (
                "current-quarter",
                current_value,
                quarter_config["start_date"],
                quarter_config["end_date"],
            ),
        ):
            facts.append(
                {
                    "concept": concept,
                    "value": _reported_millions_to_base_units(value),
                    "unit": unit,
                    "decimals": "-5",
                    "context_id": context_id,
                    "start_date": start,
                    "end_date": end,
                    "dimensions": {},
                    "reported_label": matched_label,
                }
            )
    return {
        "fixture_version": 1,
        "description": "Facts parsed from a filed quarterly HTML statement of operations.",
        "source": {**source, "sha256": sha256_file(path)},
        "facts": facts,
    }


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)
