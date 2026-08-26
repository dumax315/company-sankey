import math
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import List, Sequence, Tuple

import resvg_py

from .models import FinancialFact, Quarter


WIDTH = HEIGHT = 1080
BACKGROUND = "#f7f5fb"
INK = "#14212b"
BLUE = "#0879c9"
BLUE_FLOW = "#68a9d2"
GREEN = "#00a650"
GREEN_FLOW = "#75c5a0"
PINK = "#db0050"
PINK_FLOW = "#dc6792"
MUTED = "#5c6872"
LABEL_CARD = "#ffffff"
LABEL_CARD_OPACITY = 0.82


@dataclass(frozen=True)
class Node:
    key: str
    x: float
    y: float
    height: float
    color: str

    @property
    def right(self) -> float:
        return self.x + 22


@dataclass(frozen=True)
class Ribbon:
    source_x: float
    source_y: float
    target_x: float
    target_y: float
    width: float
    color: str


def _format_fact(fact: FinancialFact) -> str:
    if abs(fact.value_millions) < 1000:
        value = f"${abs(fact.value_millions):,}M"
    else:
        value = f"${abs(fact.value_millions) / 1000:.1f}B"
    if fact.value_millions < 0:
        value = "−" + value
    yoy = fact.yoy_percent
    suffix = "" if yoy is None else f" • {yoy:+.0f}% Y/Y"
    marker = "*" if fact.status == "derived" else ""
    return value + suffix + marker


def _ribbon_path(ribbon: Ribbon) -> str:
    sx, sy, tx, ty, width = (
        ribbon.source_x,
        ribbon.source_y,
        ribbon.target_x,
        ribbon.target_y,
        ribbon.width,
    )
    bend = (tx - sx) * 0.52
    return (
        f"M {sx:.2f},{sy:.2f} "
        f"C {sx + bend:.2f},{sy:.2f} {tx - bend:.2f},{ty:.2f} {tx:.2f},{ty:.2f} "
        f"L {tx:.2f},{ty + width:.2f} "
        f"C {tx - bend:.2f},{ty + width:.2f} {sx + bend:.2f},{sy + width:.2f} {sx:.2f},{sy + width:.2f} Z"
    )


def _node_path(node: Node, round_left: bool, round_right: bool) -> str:
    """Draw a node with rounding only on sides that have no attached flow."""
    bottom = node.y + node.height
    radius = min(6.0, node.height / 2, (node.right - node.x) / 2)
    left_radius = radius if round_left else 0.0
    right_radius = radius if round_right else 0.0
    parts = [
        f"M {node.x + left_radius:.2f},{node.y:.2f}",
        f"H {node.right - right_radius:.2f}",
    ]
    if round_right:
        parts.append(f"Q {node.right:.2f},{node.y:.2f} {node.right:.2f},{node.y + right_radius:.2f}")
    else:
        parts.append(f"H {node.right:.2f}")
    parts.append(f"V {bottom - right_radius:.2f}")
    if round_right:
        parts.append(f"Q {node.right:.2f},{bottom:.2f} {node.right - right_radius:.2f},{bottom:.2f}")
    else:
        parts.append(f"V {bottom:.2f}")
    parts.append(f"H {node.x + left_radius:.2f}")
    if round_left:
        parts.append(f"Q {node.x:.2f},{bottom:.2f} {node.x:.2f},{bottom - left_radius:.2f}")
    else:
        parts.append(f"H {node.x:.2f}")
    parts.append(f"V {node.y + left_radius:.2f}")
    if round_left:
        parts.append(f"Q {node.x:.2f},{node.y:.2f} {node.x + left_radius:.2f},{node.y:.2f}")
    else:
        parts.append(f"V {node.y:.2f}")
    parts.append("Z")
    return " ".join(parts)


def _node_rounding(node: Node, ribbons: Sequence[Ribbon]) -> Tuple[bool, bool]:
    has_incoming = any(math.isclose(ribbon.target_x, node.x, abs_tol=0.01) for ribbon in ribbons)
    has_outgoing = any(math.isclose(ribbon.source_x, node.right, abs_tol=0.01) for ribbon in ribbons)
    return not has_incoming, not has_outgoing


def _layout(quarter: Quarter) -> Tuple[List[Node], List[Ribbon]]:
    f = quarter.facts
    scale = 3.3 / 1000.0
    h = lambda key: max(1.2, f[key].value_millions * scale)
    nodes = {
        "advertising_revenue": Node("advertising_revenue", 32, 340, h("advertising_revenue"), BLUE),
        "other_foa_revenue": Node("other_foa_revenue", 32, 575, h("other_foa_revenue"), BLUE),
        "family_of_apps_revenue": Node("family_of_apps_revenue", 230, 340, h("family_of_apps_revenue"), BLUE),
        "reality_labs_revenue": Node("reality_labs_revenue", 230, 630, h("reality_labs_revenue"), BLUE),
        "revenue": Node("revenue", 410, 340, h("revenue"), BLUE),
        "gross_profit": Node("gross_profit", 600, 320, h("gross_profit"), GREEN),
        "cost_of_revenue": Node("cost_of_revenue", 600, 560, h("cost_of_revenue"), PINK),
        "operating_income": Node("operating_income", 770, 300, h("operating_income"), GREEN),
        "research_and_development": Node("research_and_development", 770, 500, h("research_and_development"), PINK),
        "general_and_administrative": Node("general_and_administrative", 770, 620, h("general_and_administrative"), PINK),
        "marketing_and_sales": Node("marketing_and_sales", 770, 700, h("marketing_and_sales"), PINK),
        "pretax_income": Node("pretax_income", 875, 300, h("pretax_income"), GREEN),
        "nonoperating_income_expense": Node("nonoperating_income_expense", 875, 420, max(2, abs(h("nonoperating_income_expense"))), PINK),
        "net_income": Node("net_income", 980, 290, h("net_income"), GREEN),
        "income_tax": Node("income_tax", 980, 400, h("income_tax"), PINK),
    }

    def width(key: str) -> float:
        return max(1.2, abs(f[key].value_millions) * scale)

    ribbons: List[Ribbon] = []
    # Product revenue -> FoA -> consolidated revenue.
    ribbons.append(Ribbon(nodes["advertising_revenue"].right, 340, 230, 340, width("advertising_revenue"), BLUE_FLOW))
    ribbons.append(Ribbon(nodes["other_foa_revenue"].right, 575, 230, 340 + width("advertising_revenue"), width("other_foa_revenue"), BLUE_FLOW))
    ribbons.append(Ribbon(nodes["family_of_apps_revenue"].right, 340, 410, 340, width("family_of_apps_revenue"), BLUE_FLOW))
    ribbons.append(Ribbon(nodes["reality_labs_revenue"].right, 630, 410, 340 + width("family_of_apps_revenue"), width("reality_labs_revenue"), BLUE_FLOW))
    # Consolidated revenue -> gross profit and cost of revenue.
    ribbons.append(Ribbon(nodes["revenue"].right, 340, 600, 320, width("gross_profit"), GREEN_FLOW))
    ribbons.append(Ribbon(nodes["revenue"].right, 340 + width("gross_profit"), 600, 560, width("cost_of_revenue"), PINK_FLOW))
    # Gross profit -> operating result and period expenses.
    source_y = 320.0
    for key, target_y, color in (
        ("operating_income", 300, GREEN_FLOW),
        ("research_and_development", 500, PINK_FLOW),
        ("general_and_administrative", 620, PINK_FLOW),
        ("marketing_and_sales", 700, PINK_FLOW),
    ):
        ribbons.append(Ribbon(nodes["gross_profit"].right, source_y, 770, target_y, width(key), color))
        source_y += width(key)
    # Profit bridge; the negative non-operating value is an outflow.
    ribbons.append(Ribbon(nodes["operating_income"].right, 300, 875, 300, width("pretax_income"), GREEN_FLOW))
    ribbons.append(Ribbon(nodes["operating_income"].right, 300 + width("pretax_income"), 875, 420, width("nonoperating_income_expense"), PINK_FLOW))
    ribbons.append(Ribbon(nodes["pretax_income"].right, 300, 980, 290, width("net_income"), GREEN_FLOW))
    ribbons.append(Ribbon(nodes["pretax_income"].right, 300 + width("net_income"), 980, 400, width("income_tax"), PINK_FLOW))
    return list(nodes.values()), ribbons


LABELS = {
    "advertising_revenue": (32, 312, "start"),
    "other_foa_revenue": (32, 625, "start"),
    "family_of_apps_revenue": (241, 312, "middle"),
    "reality_labs_revenue": (241, 680, "middle"),
    "revenue": (421, 312, "middle"),
    "gross_profit": (611, 292, "middle"),
    "cost_of_revenue": (611, 635, "middle"),
    "operating_income": (781, 272, "middle"),
    "research_and_development": (781, 485, "middle"),
    "general_and_administrative": (781, 605, "middle"),
    "marketing_and_sales": (781, 770, "middle"),
    "pretax_income": (886, 225, "middle"),
    "nonoperating_income_expense": (860, 400, "end"),
    "net_income": (991, 272, "middle"),
    "income_tax": (1030, 470, "end"),
}


def _label_card(key: str, fact: FinancialFact) -> str:
    """Return a translucent backing card sized for a two-line fact label."""
    x, y, anchor = LABELS[key]
    title_width = len(fact.label) * 8.2
    value_width = len(_format_fact(fact)) * 7.0
    width = max(title_width, value_width) + 16
    if anchor == "middle":
        left = x - width / 2
    elif anchor == "end":
        left = x - width - 8
    else:
        left = x - 8
    return (
        f'<rect class="label-card" x="{left:.1f}" y="{y - 19:.1f}" '
        f'width="{width:.1f}" height="47" rx="5" fill="{LABEL_CARD}" '
        f'fill-opacity="{LABEL_CARD_OPACITY}"/>'
    )


def render_svg(quarter: Quarter, destination: Path) -> None:
    nodes, ribbons = _layout(quarter)
    lines: List[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-labelledby="title desc">',
        "<title id=\"title\">Meta Q2 2026 income statement Sankey</title>",
        "<desc id=\"desc\">Revenue and expense flows in USD billions based on Meta's SEC Form 10-Q.</desc>",
        f'<rect width="1080" height="1080" rx="28" fill="{BACKGROUND}"/>',
        f'<text x="42" y="82" font-family="Arial,sans-serif" font-weight="700" font-size="58" fill="{INK}">META</text>',
        f'<text x="42" y="128" font-family="Arial,sans-serif" font-weight="700" font-size="28" fill="{GREEN}">Q2 FY2026</text>',
        f'<text x="204" y="128" font-family="Arial,sans-serif" font-size="28" fill="{INK}">Income statement</text>',
        f'<text x="42" y="164" font-family="Arial,sans-serif" font-size="17" fill="{MUTED}">Quarter ended Jun 30, 2026 • USD billions • GAAP • unaudited</text>',
    ]
    for ribbon in ribbons:
        lines.append(f'<path class="ribbon" d="{_ribbon_path(ribbon)}" fill="{ribbon.color}" fill-opacity="0.78"/>')
    for node in nodes:
        fact = quarter.facts[node.key]
        dash = ' stroke-dasharray="5 3" stroke-width="3" stroke="#12683d"' if fact.status == "derived" else ""
        round_left, round_right = _node_rounding(node, ribbons)
        lines.append(
            f'<path class="node" data-key="{node.key}" data-round-left="{str(round_left).lower()}" '
            f'data-round-right="{str(round_right).lower()}" d="{_node_path(node, round_left, round_right)}" '
            f'fill="{node.color}"{dash}/>'
        )
    for key, (x, y, anchor) in LABELS.items():
        fact = quarter.facts[key]
        lines.append(_label_card(key, fact))
        lines.append(f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-family="Arial,sans-serif" font-size="15" font-weight="700" fill="{INK}">{escape(fact.label)}</text>')
        lines.append(f'<text x="{x}" y="{y + 20}" text-anchor="{anchor}" font-family="Arial,sans-serif" font-size="13" fill="{MUTED}">{escape(_format_fact(fact))}</text>')
    lines.extend(
        [
            f'<line x1="42" y1="950" x2="1038" y2="950" stroke="#d7dbe0"/>',
            f'<text x="42" y="980" font-family="Arial,sans-serif" font-size="14" fill="{INK}">Source: Meta Form 10-Q filed Jul 30, 2026 • SEC accession 0001628280-26-050705</text>',
            f'<text x="42" y="1004" font-family="Arial,sans-serif" font-size="13" fill="{MUTED}">Rounded for display. Gross profit* is derived. Segment labels use Meta-specific XBRL dimensions.</text>',
            f'<text x="42" y="1028" font-family="Arial,sans-serif" font-size="13" fill="{MUTED}">Values mapped from filing XBRL; flows may omit disclosures outside this income-statement bridge.</text>',
            "</svg>",
        ]
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(lines), encoding="utf-8")


def rasterize_svg(svg_path: Path, destination: Path, pixel_size: int = 3240) -> None:
    """Rasterize the exact saved SVG; no parallel PNG layout implementation exists."""
    if pixel_size <= 0:
        raise ValueError("PNG pixel size must be a positive integer")
    if not svg_path.is_file():
        raise FileNotFoundError(f"Canonical SVG does not exist: {svg_path}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(
        resvg_py.svg_to_bytes(
            svg_path=str(svg_path),
            width=pixel_size,
            height=pixel_size,
            shape_rendering="geometric_precision",
            text_rendering="optimize_legibility",
        )
    )
