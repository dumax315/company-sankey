import argparse
import inspect
import json
import struct
from copy import deepcopy
from pathlib import Path

import pytest

import stankey.render as render_module
from stankey.cli import DEFAULT_CONFIG, DEFAULT_FIXTURE, generate
from stankey.normalize import normalize_meta
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
    assert 'data-key="advertising_revenue" data-round-left="true" data-round-right="false"' in svg
    assert 'data-key="revenue" data-round-left="false" data-round-right="false"' in svg
    assert 'data-key="net_income" data-round-left="false" data-round-right="true"' in svg
    assert svg.count('class="label-card"') == 15
    assert 'fill-opacity="0.82"' in svg
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
