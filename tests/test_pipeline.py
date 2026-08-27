import argparse
import inspect
import json
import struct
import time
from copy import deepcopy
from pathlib import Path

import pytest

import stankey.render as render_module
import stankey.cli as cli_module
from stankey.cli import (
    DEFAULT_CONFIG,
    DEFAULT_FIXTURE,
    generate,
    generate_series,
    quarter_sequence,
)
from stankey.normalize import normalize_meta, normalize_meta_q4
from stankey.sec import load_json
from stankey.validate import ReconciliationError, validate_quarter


@pytest.fixture
def quarter():
    return normalize_meta(load_json(DEFAULT_CONFIG), load_json(DEFAULT_FIXTURE), "2026Q2")


def test_official_fixture_normalizes_with_provenance(quarter):
    assert quarter.facts["revenue"].value_millions == 60_801
    assert quarter.facts["advertising_revenue"].value_millions == 59_363
    assert quarter.facts["net_income"].value_millions == 15_848
    assert quarter.facts["gross_profit"].value_millions == 49_471
    assert quarter.facts["gross_profit"].status == "derived"
    assert quarter.facts["revenue"].provenance[0].context_id == "c-10"
    assert quarter.facts["advertising_revenue"].provenance[0].dimensions[
        "srt:ProductOrServiceAxis"
    ] == "us-gaap:AdvertisingMember"
    assert round(quarter.facts["revenue"].yoy_percent) == 28


def test_all_accounting_identities_pass(quarter):
    checks = validate_quarter(quarter)
    assert len(checks) == 7
    assert all(check.passed for check in checks)


def test_q4_normalization_derives_annual_less_nine_months(quarter):
    config = deepcopy(load_json(DEFAULT_CONFIG))
    config["quarters"]["2025Q4"] = {
        "start_date": "2025-10-01",
        "end_date": "2025-12-31",
        "prior_start_date": "2024-10-01",
        "prior_end_date": "2024-12-31",
    }
    annual_facts = []
    nine_month_facts = []
    for index, (key, selector) in enumerate(config["selectors"].items()):
        current_value = quarter.facts[key].value_millions
        prior_value = quarter.facts[key].prior_value_millions
        for facts, start, end, value, context_suffix in (
            (annual_facts, "2025-01-01", "2025-12-31", current_value + 100_000, "ac"),
            (annual_facts, "2024-01-01", "2024-12-31", prior_value + 90_000, "ap"),
            (nine_month_facts, "2025-01-01", "2025-09-30", 100_000, "nc"),
            (nine_month_facts, "2024-01-01", "2024-09-30", 90_000, "np"),
        ):
            facts.append(
                {
                    "concept": selector["concept"],
                    "value": str(value * 1_000_000),
                    "unit": "usd",
                    "decimals": "-6",
                    "context_id": f"{index}-{context_suffix}",
                    "start_date": start,
                    "end_date": end,
                    "dimensions": selector["dimensions"],
                }
            )
    source = {
        "url": "https://www.sec.gov/example.xml",
        "accession": "example",
        "document": "example.xml",
        "filing_date": "2026-01-01",
    }
    annual = {"source": source, "facts": annual_facts}
    nine_month = {"source": source, "facts": nine_month_facts}

    q4 = normalize_meta_q4(config, annual, nine_month, nine_month, "2025Q4")

    assert q4.facts["revenue"].value_millions == quarter.facts["revenue"].value_millions
    assert q4.facts["revenue"].prior_value_millions == quarter.facts["revenue"].prior_value_millions
    assert q4.facts["revenue"].status == "derived"
    assert len(q4.facts["revenue"].provenance) == 2
    assert all(check.passed for check in validate_quarter(q4))


def test_labels_follow_node_positions_and_center_when_vertical(quarter):
    from stankey.companies import get_adapter

    nodes, ribbons = render_module._layout(quarter)
    below = frozenset(get_adapter(quarter.ticker).below_terminals)
    for node in nodes:
        x, y, anchor, _, placement = render_module._label_position(node.key, node, ribbons, below)
        if placement == "above":
            assert x == node.x + 11
            assert y == node.y + render_module.ABOVE_LABEL_OFFSETS.get(
                node.key, render_module.ABOVE_LABEL_DEFAULT_OFFSET
            )
            assert anchor == "middle"
        elif placement == "below":
            assert x == node.x + 11
            assert y == node.y + node.height + 30
            assert anchor == "middle"


def test_above_labels_pack_horizontally_without_vertical_stacking(quarter):
    from stankey.companies import get_adapter

    nodes, ribbons = render_module._layout(quarter)
    nodes_by_key = {node.key: node for node in nodes}
    label_keys = get_adapter(quarter.ticker).label_keys
    below = frozenset(get_adapter(quarter.ticker).below_terminals)
    positions = {
        key: render_module._fit_label_to_canvas(
            quarter.facts[key],
            render_module._label_position(key, nodes_by_key[key], ribbons, below),
        )
        for key in label_keys
    }
    initial_positions = dict(positions)
    positions = render_module._pack_above_labels(quarter, positions)
    positions = render_module._resolve_label_spacing(quarter, positions)
    top_positions = [position for position in positions.values() if position[4] == "above"]

    assert len({position[1] for position in top_positions}) == 1
    for key, position in positions.items():
        if position[4] == "above":
            assert position[0] == pytest.approx(nodes_by_key[key].x + 11)
    assert positions == initial_positions
    render_module._validate_label_spacing(quarter, positions)


def test_profit_bridge_ribbons_follow_income_and_benefit_signs(quarter):
    positive_nonoperating = deepcopy(quarter)
    positive_nonoperating.facts["nonoperating_income_expense"].value_millions = 100
    _, ribbons = render_module._layout(positive_nonoperating)
    assert any(
        ribbon.source_key == "nonoperating_income_expense"
        and ribbon.target_key == "pretax_income"
        for ribbon in ribbons
    )

    tax_benefit = deepcopy(quarter)
    tax_benefit.facts["income_tax"].value_millions = -100
    _, ribbons = render_module._layout(tax_benefit)
    assert any(
        ribbon.source_key == "income_tax" and ribbon.target_key == "net_income"
        for ribbon in ribbons
    )


def test_primary_profit_spine_stays_horizontal(quarter):
    _, ribbons = render_module._layout(quarter)
    primary_edges = {
        ("advertising_revenue", "family_of_apps_revenue"),
        ("family_of_apps_revenue", "revenue"),
        ("revenue", "gross_profit"),
        ("gross_profit", "operating_income"),
        ("operating_income", "pretax_income"),
        ("pretax_income", "net_income"),
    }
    for ribbon in ribbons:
        if (ribbon.source_key, ribbon.target_key) in primary_edges:
            assert ribbon.source_y == ribbon.target_y


def test_net_income_is_rightmost_terminal_and_label_groups_fit_canvas(quarter):
    nodes, ribbons = render_module._layout(quarter)
    render_module._validate_terminal_order(nodes, ribbons)
    terminals = [
        node for node in nodes
        if not any(ribbon.source_key == node.key for ribbon in ribbons)
    ]
    net_income = next(node for node in terminals if node.key == "net_income")
    assert net_income.x == max(node.x for node in terminals)

    for node in terminals:
        _, _, _, role, placement = render_module._label_position(
            node.key, node, ribbons
        )
        assert role == "output"
        assert placement == "right"

    for node in nodes:
        raw_position = render_module._label_position(node.key, node, ribbons)
        position = render_module._fit_label_to_canvas(
            quarter.facts[node.key], raw_position
        )
        left, _, width, _ = render_module._label_card_bounds(
            quarter.facts[node.key], position
        )
        assert left >= 16
        assert left + width <= render_module.WIDTH - 16


def test_material_reconciliation_failure_blocks_render(quarter):
    broken = deepcopy(quarter)
    broken.facts["net_income"].value_millions += 10
    with pytest.raises(ReconciliationError, match="pre-tax less income tax"):
        validate_quarter(broken)


def test_generate_writes_square_assets_and_auditable_manifest(tmp_path: Path):
    args = argparse.Namespace(
        ticker="META",
        quarter="2026Q2",
        output_dir=tmp_path,
        fetch_sec=False,
        user_agent=None,
        config=DEFAULT_CONFIG,
        png_size=3240,
    )
    manifest_path = generate(args)
    svg_path = tmp_path / "01_META_2026_Q2.svg"
    png_path = tmp_path / "01_META_2026_Q2.png"
    svg = svg_path.read_text(encoding="utf-8")
    assert svg.count('class="ribbon"') == 14
    assert svg.count('class="node"') == 15
    assert "stroke-dasharray" not in svg
    assert "* values are derived." in svg
    assert 'data-key="advertising_revenue" data-round-left="true" data-round-right="false"' in svg
    assert 'data-key="revenue" data-round-left="false" data-round-right="false"' in svg
    assert 'data-key="net_income" data-round-left="false" data-round-right="true"' in svg
    assert svg.count('class="label-card"') == 15
    assert 'fill-opacity="0.82"' in svg
    assert svg.count('data-role="input"') == 3
    assert svg.count('data-role="output"') == 7
    assert 'data-key="advertising_revenue" data-role="input" data-placement="left"' in svg
    assert 'data-key="reality_labs_revenue" data-role="input" data-placement="below"' in svg
    assert 'data-key="cost_of_revenue" data-role="output" data-placement="right"' in svg
    assert 'data-key="net_income" data-role="output" data-placement="right"' in svg
    assert 'viewBox="0 0 1080 1080"' in svg
    assert "See adjacent JSON manifest" not in svg
    png_header = png_path.read_bytes()[:24]
    assert png_header[:8] == b"\x89PNG\r\n\x1a\n"
    assert struct.unpack(">II", png_header[16:24]) == (3240, 3240)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["validation"]["status"] == "passed"
    assert all(item["passed"] for item in manifest["validation"]["checks"])
    assert manifest["source"]["accession"] == "0001628280-26-050705"
    assert manifest["quarter"]["facts"]["gross_profit"]["derivation"] == "revenue - cost_of_revenue"
    assert manifest["outputs"]["svg"]["sha256"]
    assert manifest["outputs"]["png"]["width"] == 3240
    assert manifest["outputs"]["png"]["rasterized_from"] == svg_path.name
    assert manifest["outputs"]["png"]["renderer"] == "resvg"


def test_png_has_no_parallel_geometry_renderer():
    source = inspect.getsource(render_module)
    assert "ImageDraw" not in source
    assert "_ribbon_polygon" not in source
    assert not hasattr(render_module, "render_png")
    assert hasattr(render_module, "rasterize_svg")


def test_rasterizer_consumes_the_exact_saved_svg(tmp_path: Path, monkeypatch):
    svg_path = tmp_path / "canonical.svg"
    png_path = tmp_path / "master.png"
    svg_path.write_text('<svg xmlns="http://www.w3.org/2000/svg"/>', encoding="utf-8")
    call = {}

    def fake_svg_to_bytes(**kwargs):
        call.update(kwargs)
        return b"rendered-from-canonical-svg"

    monkeypatch.setattr(render_module.resvg_py, "svg_to_bytes", fake_svg_to_bytes)
    render_module.rasterize_svg(svg_path, png_path, pixel_size=2048)

    assert call["svg_path"] == str(svg_path)
    assert "svg_string" not in call
    assert call["width"] == call["height"] == 2048
    assert png_path.read_bytes() == b"rendered-from-canonical-svg"


def test_quarter_sequence_runs_newest_first_across_years():
    assert quarter_sequence("2026Q2", 5) == [
        "2026Q2",
        "2026Q1",
        "2025Q4",
        "2025Q3",
        "2025Q2",
    ]


def test_generate_series_uses_one_subdirectory_per_quarter(tmp_path: Path):
    args = argparse.Namespace(
        ticker="META",
        quarters=1,
        from_quarter=None,
        output_dir=tmp_path,
        fetch_sec=False,
        user_agent=None,
        config=DEFAULT_CONFIG,
        png_size=3240,
    )
    series_manifest = generate_series(args)
    quarter_dir = tmp_path / "2026Q2"
    assert (quarter_dir / "01_META_2026_Q2.png").is_file()
    assert (quarter_dir / "01_META_2026_Q2.svg").is_file()
    assert (quarter_dir / "01_META_2026_Q2.json").is_file()
    assert (tmp_path / "png" / "01_META_2026_Q2.png").is_file()
    payload = json.loads(series_manifest.read_text(encoding="utf-8"))
    assert payload["quarters"] == [
        {
            "quarter": "2026Q2",
            "directory": "2026Q2",
            "manifest": "2026Q2/01_META_2026_Q2.json",
            "png": "png/01_META_2026_Q2.png",
        }
    ]


def test_generate_series_sets_chronological_mtime_on_flat_png_copies(tmp_path: Path):
    before = time.time()
    args = argparse.Namespace(
        ticker="META",
        quarters=1,
        from_quarter=None,
        output_dir=tmp_path,
        fetch_sec=False,
        user_agent=None,
        config=DEFAULT_CONFIG,
        png_size=3240,
    )
    generate_series(args)
    after = time.time()

    flat_png = tmp_path / "png" / "01_META_2026_Q2.png"
    original_png = tmp_path / "2026Q2" / "01_META_2026_Q2.png"
    assert flat_png.is_file()
    assert original_png.is_file()

    # Index 01 (newest quarter) is anchored at now - 1*60s.
    flat_mtime = flat_png.stat().st_mtime
    assert before - 60 - 2 <= flat_mtime <= after - 60 + 2
    assert flat_mtime < before

    # The per-quarter original is left untouched, not forced to the flat value.
    assert original_png.stat().st_mtime != flat_mtime


def test_generate_series_preflights_missing_quarters_before_writing(tmp_path: Path):
    args = argparse.Namespace(
        ticker="META",
        quarters=2,
        from_quarter=None,
        output_dir=tmp_path,
        fetch_sec=False,
        user_agent=None,
        config=DEFAULT_CONFIG,
        png_size=3240,
    )
    with pytest.raises(ValueError, match="2026Q1"):
        generate_series(args)
    assert list(tmp_path.iterdir()) == []


def test_generate_series_discovers_missing_fetch_sec_quarters(tmp_path: Path, monkeypatch):
    config_path = tmp_path / "meta.json"
    config_path.write_text(
        json.dumps(
            {
                "company": "Meta Platforms, Inc.",
                "ticker": "META",
                "cik": "0001326801",
                "quarters": {"2026Q2": {}},
            }
        ),
        encoding="utf-8",
    )
    discovered_q1 = {
        "start_date": "2026-01-01",
        "end_date": "2026-03-31",
        "prior_start_date": "2025-01-01",
        "prior_end_date": "2025-03-31",
        "fixture": "unused.json",
        "source": {},
    }
    monkeypatch.setattr(
        cli_module,
        "discover_filings",
        lambda *args, **kwargs: {
            "quarters": {"2026Q1": discovered_q1},
            "warnings": [],
        },
    )
    generated = []

    def fake_generate(args):
        assert "2026Q1" in args.config_data["quarters"]
        generated.append(args.quarter)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        manifest = args.output_dir / f"{args.quarter}.json"
        manifest.with_suffix(".png").write_bytes(b"png")
        return manifest

    monkeypatch.setattr(cli_module, "generate", fake_generate)
    args = argparse.Namespace(
        ticker="META",
        quarters=2,
        from_quarter="2026Q2",
        output_dir=tmp_path / "outputs",
        fetch_sec=True,
        user_agent="Test Person test@example.com",
        config=config_path,
        png_size=1080,
    )

    generate_series(args)

    assert generated == ["2026Q2", "2026Q1"]


def test_generate_series_discovers_q3_dependency_when_oldest_output_is_q4(
    tmp_path: Path, monkeypatch
):
    config_path = tmp_path / "meta.json"
    config_path.write_text(
        json.dumps(
            {
                "company": "Meta Platforms, Inc.",
                "ticker": "META",
                "cik": "0001326801",
                "quarters": {},
            }
        ),
        encoding="utf-8",
    )
    discovered_calls = []

    def fake_discover(config, quarters, user_agent, from_quarter=None):
        discovered_calls.append((quarters, from_quarter))
        return {
            "quarters": {"2025Q4": {}, "2025Q3": {}},
            "warnings": [],
        }

    def fake_generate(args):
        assert "2025Q3" in args.config_data["quarters"]
        args.output_dir.mkdir(parents=True, exist_ok=True)
        manifest = args.output_dir / f"{args.quarter}.json"
        manifest.with_suffix(".png").write_bytes(b"png")
        return manifest

    monkeypatch.setattr(cli_module, "discover_filings", fake_discover)
    monkeypatch.setattr(cli_module, "generate", fake_generate)
    args = argparse.Namespace(
        ticker="META",
        quarters=1,
        from_quarter="2025Q4",
        output_dir=tmp_path / "outputs",
        fetch_sec=True,
        user_agent="Test Person test@example.com",
        config=config_path,
        png_size=1080,
    )

    generate_series(args)

    assert discovered_calls == [(2, "2025Q4")]
