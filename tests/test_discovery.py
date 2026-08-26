import argparse
import json
from pathlib import Path

import pytest

import stankey.cli as cli_module
from stankey.discovery import _select_xbrl_document, discover_filings


@pytest.fixture
def meta_config():
    return {
        "company": "Meta Platforms, Inc.",
        "ticker": "META",
        "cik": "0001326801",
    }


def _submission_block(rows):
    keys = (
        "accessionNumber",
        "filingDate",
        "form",
        "primaryDocument",
        "reportDate",
    )
    return {key: [row[key] for row in rows] for key in keys}


def test_discovery_follows_historical_pages_and_builds_config_entries(meta_config):
    recent_rows = [
        {
            "accessionNumber": "0001628280-26-050705",
            "filingDate": "2026-07-30",
            "form": "10-Q",
            "primaryDocument": "meta-20260630.htm",
            "reportDate": "2026-06-30",
        },
        {
            "accessionNumber": "0001628280-26-028526",
            "filingDate": "2026-04-30",
            "form": "10-Q",
            "primaryDocument": "meta-20260331.htm",
            "reportDate": "2026-03-31",
        },
    ]
    historical_rows = [
        {
            "accessionNumber": "0001628280-26-003942",
            "filingDate": "2026-01-29",
            "form": "10-K",
            "primaryDocument": "meta-20251231.htm",
            "reportDate": "2025-12-31",
        }
    ]
    submissions_url = "https://data.sec.gov/submissions/CIK0001326801.json"
    history_url = "https://data.sec.gov/submissions/CIK0001326801-submissions-001.json"
    responses = {
        submissions_url: {
            "filings": {
                "recent": _submission_block(recent_rows),
                "files": [{"name": "CIK0001326801-submissions-001.json"}],
            }
        },
        history_url: _submission_block(historical_rows),
    }
    for row in recent_rows + historical_rows:
        accession_path = row["accessionNumber"].replace("-", "")
        index_url = f"https://www.sec.gov/Archives/edgar/data/1326801/{accession_path}/index.json"
        document = f"{Path(row['primaryDocument']).stem}_htm.xml"
        responses[index_url] = {
            "directory": {
                "item": [
                    {"name": "FilingSummary.xml"},
                    {"name": document},
                    {"name": "meta-20251231_cal.xml"},
                ]
            }
        }
    calls = []

    def fake_fetch(url, user_agent):
        calls.append((url, user_agent))
        return responses[url]

    result = discover_filings(
        meta_config,
        quarters=3,
        user_agent="Test Person test@example.com",
        fetch_json=fake_fetch,
    )

    assert list(result["quarters"]) == ["2026Q2", "2026Q1", "2025Q4"]
    assert result["quarter_count"] == 3
    assert result["quarters"]["2026Q2"] == {
        "start_date": "2026-04-01",
        "end_date": "2026-06-30",
        "prior_start_date": "2025-04-01",
        "prior_end_date": "2025-06-30",
        "fixture": "data/fixtures/meta_2026_q2_sec_xbrl.json",
        "source": {
            "form": "10-Q",
            "accession": "0001628280-26-050705",
            "document": "meta-20260630_htm.xml",
            "filing_date": "2026-07-30",
            "url": "https://www.sec.gov/Archives/edgar/data/1326801/000162828026050705/meta-20260630_htm.xml",
        },
    }
    assert "2025Q4" in result["warnings"][0]
    assert history_url in [url for url, _ in calls]
    assert all(user_agent == "Test Person test@example.com" for _, user_agent in calls)


def test_discovery_reports_missing_requested_quarters(meta_config):
    submissions = {
        "filings": {
            "recent": _submission_block(
                [
                    {
                        "accessionNumber": "0001628280-26-050705",
                        "filingDate": "2026-07-30",
                        "form": "10-Q",
                        "primaryDocument": "meta-20260630.htm",
                        "reportDate": "2026-06-30",
                    }
                ]
            ),
            "files": [],
        }
    }

    with pytest.raises(ValueError, match="2026Q1"):
        discover_filings(
            meta_config,
            quarters=2,
            from_quarter="2026Q2",
            user_agent="Test Person test@example.com",
            fetch_json=lambda url, user_agent: submissions,
        )


def test_xbrl_document_falls_back_only_when_unambiguous():
    assert _select_xbrl_document(
        {"directory": {"item": [{"name": "renamed-instance_htm.xml"}]}},
        "meta-20260331.htm",
    ) == "renamed-instance_htm.xml"
    assert _select_xbrl_document(
        {
            "directory": {
                "item": [{"name": "0001628280-25-047240-xbrl.zip"}]
            }
        },
        "meta-20250930.htm",
    ) == "meta-20250930_htm.xml"
    with pytest.raises(ValueError, match="Multiple extracted XBRL instances"):
        _select_xbrl_document(
            {
                "directory": {
                    "item": [
                        {"name": "first_htm.xml"},
                        {"name": "second_htm.xml"},
                    ]
                }
            },
            "meta-20260331.htm",
        )


def test_discover_cli_writes_json_output(tmp_path: Path, monkeypatch, meta_config):
    config_path = tmp_path / "meta.json"
    config_path.write_text(json.dumps(meta_config), encoding="utf-8")
    output_path = tmp_path / "discovered.json"
    expected = {"ticker": "META", "quarters": {"2026Q2": {}}}
    call = {}

    def fake_discover(config, quarters, user_agent, from_quarter=None):
        call.update(
            config=config,
            quarters=quarters,
            user_agent=user_agent,
            from_quarter=from_quarter,
        )
        return expected

    monkeypatch.setattr(cli_module, "discover_filings", fake_discover)
    args = argparse.Namespace(
        ticker="meta",
        quarters=1,
        from_quarter="2026q2",
        user_agent="Test Person test@example.com",
        config=config_path,
        output=output_path,
    )

    assert cli_module.discover(args) == output_path
    assert json.loads(output_path.read_text(encoding="utf-8")) == expected
    assert call["from_quarter"] == "2026Q2"
