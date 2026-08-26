from dataclasses import dataclass
from datetime import date
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
LABEL_CARD_PADDING_X = 6
LABEL_CARD_GAP = 8
LABEL_CARD_VERTICAL_GAP = 1
GEOMETRY_EPSILON = 0.01


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
    source_key: str
    target_key: str
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


def _display_date(iso_date: str) -> str:
    return date.fromisoformat(iso_date).strftime("%b %d, %Y").replace(" 0", " ")


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
    has_incoming = any(ribbon.target_key == node.key for ribbon in ribbons)
    has_outgoing = any(ribbon.source_key == node.key for ribbon in ribbons)
    return not has_incoming, not has_outgoing


def _layout(quarter: Quarter) -> Tuple[List[Node], List[Ribbon]]:
    f = quarter.facts
    scale = 3.3 / 1000.0
    h = lambda key: max(1.2, abs(f[key].value_millions) * scale)
    nonoperating_is_income = f["nonoperating_income_expense"].value_millions >= 0
    income_tax_is_benefit = f["income_tax"].value_millions < 0
    nodes = {
        "advertising_revenue": Node("advertising_revenue", 180, 340, h("advertising_revenue"), BLUE),
        "other_foa_revenue": Node("other_foa_revenue", 180, 575, h("other_foa_revenue"), BLUE),
        "family_of_apps_revenue": Node("family_of_apps_revenue", 249, 340, h("family_of_apps_revenue"), BLUE),
        "reality_labs_revenue": Node("reality_labs_revenue", 249, 630, h("reality_labs_revenue"), BLUE),
        "revenue": Node("revenue", 398, 340, h("revenue"), BLUE),
        "gross_profit": Node("gross_profit", 551, 340, h("gross_profit"), GREEN),
        "cost_of_revenue": Node("cost_of_revenue", 551, 560, h("cost_of_revenue"), PINK),
        "operating_income": Node("operating_income", 710, 340, h("operating_income"), GREEN),
        "research_and_development": Node("research_and_development", 710, 540, h("research_and_development"), PINK),
        "general_and_administrative": Node("general_and_administrative", 710, 650, h("general_and_administrative"), PINK),
        "marketing_and_sales": Node("marketing_and_sales", 710, 735, h("marketing_and_sales"), PINK),
        "pretax_income": Node("pretax_income", 863, 340, h("pretax_income"), GREEN),
        "nonoperating_income_expense": Node(
            "nonoperating_income_expense",
            818 if nonoperating_is_income else 863,
            450,
            h("nonoperating_income_expense"),
            GREEN if nonoperating_is_income else PINK,
        ),
        "net_income": Node("net_income", 900, 340, h("net_income"), GREEN),
        "income_tax": Node(
            "income_tax",
            800 if income_tax_is_benefit else 895,
            470 if income_tax_is_benefit else 520,
            h("income_tax"),
            GREEN if income_tax_is_benefit else PINK,
        ),
    }

    def width(key: str) -> float:
        return max(1.2, abs(f[key].value_millions) * scale)

    ribbons: List[Ribbon] = []
    # Product revenue -> FoA -> consolidated revenue.
    ribbons.append(Ribbon("advertising_revenue", "family_of_apps_revenue", nodes["advertising_revenue"].right, nodes["advertising_revenue"].y, nodes["family_of_apps_revenue"].x, nodes["family_of_apps_revenue"].y, width("advertising_revenue"), BLUE_FLOW))
    ribbons.append(Ribbon("other_foa_revenue", "family_of_apps_revenue", nodes["other_foa_revenue"].right, nodes["other_foa_revenue"].y, nodes["family_of_apps_revenue"].x, nodes["family_of_apps_revenue"].y + width("advertising_revenue"), width("other_foa_revenue"), BLUE_FLOW))
    ribbons.append(Ribbon("family_of_apps_revenue", "revenue", nodes["family_of_apps_revenue"].right, nodes["family_of_apps_revenue"].y, nodes["revenue"].x, nodes["revenue"].y, width("family_of_apps_revenue"), BLUE_FLOW))
    ribbons.append(Ribbon("reality_labs_revenue", "revenue", nodes["reality_labs_revenue"].right, nodes["reality_labs_revenue"].y, nodes["revenue"].x, nodes["revenue"].y + width("family_of_apps_revenue"), width("reality_labs_revenue"), BLUE_FLOW))
    # Consolidated revenue -> gross profit and cost of revenue.
    ribbons.append(Ribbon("revenue", "gross_profit", nodes["revenue"].right, nodes["revenue"].y, nodes["gross_profit"].x, nodes["gross_profit"].y, width("gross_profit"), GREEN_FLOW))
    ribbons.append(Ribbon("revenue", "cost_of_revenue", nodes["revenue"].right, nodes["revenue"].y + width("gross_profit"), nodes["cost_of_revenue"].x, nodes["cost_of_revenue"].y, width("cost_of_revenue"), PINK_FLOW))
    # Gross profit -> operating result and period expenses.
    source_y = nodes["gross_profit"].y
    for key, color in (
        ("operating_income", GREEN_FLOW),
        ("research_and_development", PINK_FLOW),
        ("general_and_administrative", PINK_FLOW),
        ("marketing_and_sales", PINK_FLOW),
    ):
        ribbons.append(Ribbon("gross_profit", key, nodes["gross_profit"].right, source_y, nodes[key].x, nodes[key].y, width(key), color))
        source_y += width(key)
    # Profit bridge: gains and tax benefits flow into profit; expenses flow out.
    if nonoperating_is_income:
        ribbons.append(Ribbon("operating_income", "pretax_income", nodes["operating_income"].right, nodes["operating_income"].y, nodes["pretax_income"].x, nodes["pretax_income"].y, width("operating_income"), GREEN_FLOW))
        ribbons.append(Ribbon("nonoperating_income_expense", "pretax_income", nodes["nonoperating_income_expense"].right, nodes["nonoperating_income_expense"].y, nodes["pretax_income"].x, nodes["pretax_income"].y + width("operating_income"), width("nonoperating_income_expense"), GREEN_FLOW))
    else:
        ribbons.append(Ribbon("operating_income", "pretax_income", nodes["operating_income"].right, nodes["operating_income"].y, nodes["pretax_income"].x, nodes["pretax_income"].y, width("pretax_income"), GREEN_FLOW))
        ribbons.append(Ribbon("operating_income", "nonoperating_income_expense", nodes["operating_income"].right, nodes["operating_income"].y + width("pretax_income"), nodes["nonoperating_income_expense"].x, nodes["nonoperating_income_expense"].y, width("nonoperating_income_expense"), PINK_FLOW))
    if income_tax_is_benefit:
        ribbons.append(Ribbon("pretax_income", "net_income", nodes["pretax_income"].right, nodes["pretax_income"].y, nodes["net_income"].x, nodes["net_income"].y, width("pretax_income"), GREEN_FLOW))
        ribbons.append(Ribbon("income_tax", "net_income", nodes["income_tax"].right, nodes["income_tax"].y, nodes["net_income"].x, nodes["net_income"].y + width("pretax_income"), width("income_tax"), GREEN_FLOW))
    else:
        ribbons.append(Ribbon("pretax_income", "net_income", nodes["pretax_income"].right, nodes["pretax_income"].y, nodes["net_income"].x, nodes["net_income"].y, width("net_income"), GREEN_FLOW))
        ribbons.append(Ribbon("pretax_income", "income_tax", nodes["pretax_income"].right, nodes["pretax_income"].y + width("net_income"), nodes["income_tax"].x, nodes["income_tax"].y, width("income_tax"), PINK_FLOW))
    return list(nodes.values()), ribbons


LABEL_KEYS = (
    "advertising_revenue",
    "other_foa_revenue",
    "family_of_apps_revenue",
    "reality_labs_revenue",
    "revenue",
    "gross_profit",
    "cost_of_revenue",
    "operating_income",
    "research_and_development",
    "general_and_administrative",
    "marketing_and_sales",
    "pretax_income",
    "nonoperating_income_expense",
    "net_income",
    "income_tax",
)

VERTICAL_TERMINALS = {
    "reality_labs_revenue": "below",
}

ABOVE_LABEL_OFFSETS = {}


def _label_position(key: str, node: Node, ribbons: Sequence[Ribbon]) -> Tuple[float, float, str, str, str]:
    round_left, round_right = _node_rounding(node, ribbons)
    if round_left and not round_right:
        if VERTICAL_TERMINALS.get(key) == "below":
            return node.x + 11, node.y + node.height + 30, "middle", "input", "below"
        return node.x - 12, node.y + node.height / 2 - 2.5, "end", "input", "left"
    if round_right and not round_left:
        if VERTICAL_TERMINALS.get(key) == "below":
            return node.x + 11, node.y + node.height + 30, "middle", "output", "below"
        return node.right + 12, node.y + node.height / 2 - 2.5, "start", "output", "right"
    return (
        node.x + 11,
        node.y + ABOVE_LABEL_OFFSETS.get(key, -50),
        "middle",
        "internal",
        "above",
    )


def _label_card_width(fact: FinancialFact) -> float:
    title_width = len(fact.label) * 8.2
    value_width = len(_format_fact(fact)) * 7.0
    return max(title_width, value_width) + LABEL_CARD_PADDING_X * 2


def _label_left(x: float, anchor: str, width: float) -> float:
    if anchor == "middle":
        return x - width / 2
    if anchor == "end":
        return x - width + LABEL_CARD_PADDING_X
    return x - LABEL_CARD_PADDING_X


def _fit_label_to_canvas(fact: FinancialFact, position: Tuple[float, float, str, str, str]) -> Tuple[float, float, str, str, str]:
    x, y, anchor, _, _ = position
    width = _label_card_width(fact)
    desired_left = _label_left(x, anchor, width)
    fitted_left = max(16, min(desired_left, WIDTH - width - 16))
    return x + fitted_left - desired_left, y, anchor, position[3], position[4]


def _label_card_bounds(fact: FinancialFact, position: Tuple[float, float, str, str, str]) -> Tuple[float, float, float, float]:
    x, y, anchor, _, _ = position
    width = _label_card_width(fact)
    left = _label_left(x, anchor, width)
    return left, y - 20, width, 45


def _label_card(key: str, fact: FinancialFact, position: Tuple[float, float, str, str, str]) -> str:
    """Return a translucent backing card sized for a two-line fact label."""
    _, _, _, role, placement = position
    left, top, width, height = _label_card_bounds(fact, position)
    return (
        f'<rect class="label-card" data-key="{key}" data-role="{role}" data-placement="{placement}" '
        f'x="{left:.1f}" y="{top:.1f}" '
        f'width="{width:.1f}" height="{height}" rx="5" fill="{LABEL_CARD}" '
        f'fill-opacity="{LABEL_CARD_OPACITY}"/>'
    )


def _bounds_are_separated(left: tuple, right: tuple) -> bool:
    left_x, left_y, left_width, left_height = left
    right_x, right_y, right_width, right_height = right
    return (
        left_x + left_width + LABEL_CARD_GAP <= right_x + GEOMETRY_EPSILON
        or right_x + right_width + LABEL_CARD_GAP <= left_x + GEOMETRY_EPSILON
        or left_y + left_height + LABEL_CARD_VERTICAL_GAP <= right_y + GEOMETRY_EPSILON
        or right_y + right_height + LABEL_CARD_VERTICAL_GAP <= left_y + GEOMETRY_EPSILON
    )


def _pack_above_labels(quarter: Quarter, positions: dict) -> dict:
    """Keep internal-node cards on one row and resolve collisions horizontally."""
    packed = dict(positions)
    keys = sorted(
        (key for key, position in positions.items() if position[4] == "above"),
        key=lambda key: positions[key][0],
    )
    if not keys:
        return packed
    widths = {key: _label_card_width(quarter.facts[key]) for key in keys}
    available_width = WIDTH - 32
    required_width = sum(widths.values()) + LABEL_CARD_GAP * (len(keys) - 1)
    if required_width > available_width + GEOMETRY_EPSILON:
        raise ValueError("Top label cards cannot fit on one horizontal row")

    lefts = {}
    next_left = 16.0
    for key in keys:
        desired_left = _label_left(positions[key][0], positions[key][2], widths[key])
        lefts[key] = max(desired_left, next_left)
        next_left = lefts[key] + widths[key] + LABEL_CARD_GAP
    overflow = lefts[keys[-1]] + widths[keys[-1]] - (WIDTH - 16)
    if overflow > 0:
        lefts = {key: left - overflow for key, left in lefts.items()}
    if lefts[keys[0]] < 16 - GEOMETRY_EPSILON:
        raise ValueError("Top label cards cannot fit within the canvas")

    row_y = positions[keys[0]][1]
    for key in keys:
        _, _, anchor, role, placement = positions[key]
        if anchor != "middle":
            raise ValueError(f"Top label must use a centered anchor: {key}")
        packed_x = lefts[key] + widths[key] / 2
        if abs(packed_x - positions[key][0]) > GEOMETRY_EPSILON:
            raise ValueError(
                f"Top label cannot remain centered without overlap: {key}"
            )
        packed[key] = (
            packed_x,
            row_y,
            anchor,
            role,
            placement,
        )
    return packed


def _resolve_label_spacing(quarter: Quarter, positions: dict) -> dict:
    """Reject collisions instead of detaching a label from its node."""
    _validate_label_spacing(quarter, positions)
    return dict(positions)


def _validate_label_spacing(quarter: Quarter, positions: dict) -> None:
    bounds = {
        key: _label_card_bounds(quarter.facts[key], position)
        for key, position in positions.items()
    }
    keys = list(bounds)
    for index, left_key in enumerate(keys):
        for right_key in keys[index + 1 :]:
            if not _bounds_are_separated(bounds[left_key], bounds[right_key]):
                raise ValueError(f"Label cards are too close: {left_key} and {right_key}")


def _validate_terminal_order(nodes: Sequence[Node], ribbons: Sequence[Ribbon]) -> None:
    terminals = [
        node for node in nodes
        if not any(ribbon.source_key == node.key for ribbon in ribbons)
    ]
    net_income = next(node for node in terminals if node.key == "net_income")
    if any(node.x >= net_income.x for node in terminals if node.key != "net_income"):
        raise ValueError("Net income must be the rightmost terminal node")


def render_svg(quarter: Quarter, destination: Path) -> None:
    nodes, ribbons = _layout(quarter)
    _validate_terminal_order(nodes, ribbons)
    quarter_label = f"Q{quarter.fiscal_quarter} FY{quarter.fiscal_year}"
    source = quarter.facts["revenue"].provenance[0]
    lines: List[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-labelledby="title desc">',
        f'<title id="title">{escape(quarter.ticker)} {quarter_label} income statement Sankey</title>',
        f'<desc id="desc">Revenue and expense flows in USD billions based on {escape(quarter.company)} SEC filing data.</desc>',
        f'<rect width="1080" height="1080" rx="28" fill="{BACKGROUND}"/>',
        f'<text x="42" y="82" font-family="Arial,sans-serif" font-weight="700" font-size="58" fill="{INK}">{escape(quarter.ticker)}</text>',
        f'<text x="42" y="128" font-family="Arial,sans-serif" font-weight="700" font-size="28" fill="{GREEN}">{quarter_label}</text>',
        f'<text x="204" y="128" font-family="Arial,sans-serif" font-size="28" fill="{INK}">Income statement</text>',
        f'<text x="42" y="164" font-family="Arial,sans-serif" font-size="17" fill="{MUTED}">Quarter ended {_display_date(quarter.end_date)} • USD billions • GAAP • unaudited</text>',
    ]
    for ribbon in ribbons:
        lines.append(f'<path class="ribbon" d="{_ribbon_path(ribbon)}" fill="{ribbon.color}" fill-opacity="0.78"/>')
    for node in nodes:
        round_left, round_right = _node_rounding(node, ribbons)
        lines.append(
            f'<path class="node" data-key="{node.key}" data-round-left="{str(round_left).lower()}" '
            f'data-round-right="{str(round_right).lower()}" d="{_node_path(node, round_left, round_right)}" '
            f'fill="{node.color}"/>'
        )
    nodes_by_key = {node.key: node for node in nodes}
    positions = {
        key: _fit_label_to_canvas(
            quarter.facts[key],
            _label_position(key, nodes_by_key[key], ribbons),
        )
        for key in LABEL_KEYS
    }
    positions = _pack_above_labels(quarter, positions)
    positions = _resolve_label_spacing(quarter, positions)
    _validate_label_spacing(quarter, positions)
    for key in LABEL_KEYS:
        fact = quarter.facts[key]
        position = positions[key]
        x, y, anchor, _, _ = position
        lines.append(_label_card(key, fact, position))
        lines.append(f'<text x="{x}" y="{y - 1}" text-anchor="{anchor}" font-family="Arial,sans-serif" font-size="15" font-weight="700" fill="{INK}">{escape(fact.label)}</text>')
        lines.append(f'<text x="{x}" y="{y + 19}" text-anchor="{anchor}" font-family="Arial,sans-serif" font-size="13" fill="{MUTED}">{escape(_format_fact(fact))}</text>')
    lines.extend(
        [
            f'<line x1="42" y1="950" x2="1038" y2="950" stroke="#d7dbe0"/>',
            f'<text x="42" y="980" font-family="Arial,sans-serif" font-size="14" fill="{INK}">Source: {escape(quarter.company)} SEC filing dated {_display_date(source.filing_date)} • accession {escape(source.accession)}</text>',
            f'<text x="42" y="1004" font-family="Arial,sans-serif" font-size="13" fill="{MUTED}">Rounded for display. * values are derived. Segment labels use Meta-specific XBRL dimensions.</text>',
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
