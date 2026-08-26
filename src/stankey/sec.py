import hashlib
import json
import time
import urllib.request
from urllib.error import HTTPError, URLError
import xml.etree.ElementTree as ET
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


def download_xbrl(url: str, destination: Path, user_agent: str) -> Path:
    """Download once into an immutable-by-convention cache."""
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
        raise ValueError(f"Could not download SEC XBRL {url}: {last_error}") from last_error
    temp = destination.with_suffix(destination.suffix + ".tmp")
    temp.write_bytes(payload)
    temp.replace(destination)
    return destination


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
        if context_id not in contexts or element.attrib.get("unitRef") != "usd":
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


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)
