from dataclasses import dataclass
from datetime import date
from html import escape
from pathlib import Path
from typing import List, Sequence, Tuple

import resvg_py

from .companies import get_adapter
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
LABEL_TITLE_FONT_SIZE = 16
LABEL_VALUE_FONT_SIZE = 14
AMAZON_LABEL_TITLE_FONT_SIZE = 18
AMAZON_LABEL_VALUE_FONT_SIZE = 16
# Company-agnostic aliases for the larger label cards (opt in via the adapter's
# large_label_fonts flag).
LARGE_LABEL_TITLE_FONT_SIZE = AMAZON_LABEL_TITLE_FONT_SIZE
LARGE_LABEL_VALUE_FONT_SIZE = AMAZON_LABEL_VALUE_FONT_SIZE
ABOVE_LABEL_DEFAULT_OFFSET = -56
GEOMETRY_EPSILON = 0.01
CANVAS_MARGIN = 16
SIDE_LABEL_MARGIN = 8


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


def h_of(facts, key: str, scale: float = 0.8 / 1000.0) -> float:
    return max(1.2, abs(facts[key].value_millions) * scale)


def _packed_flows(
    nodes: dict,
    source_values: dict,
    target_values: dict,
    income_key: str,
    width_value,
    income_target: bool = True,
) -> List["Ribbon"]:
    """Greedily route balanced source amounts into ordered targets.

    Sources and targets are positive magnitudes that sum to the same total.
    Each target is filled from the running source list, splitting a source
    across targets when needed. Flows into ``income_key`` are green when
    ``income_target`` is set; everything else is pink.
    """
    source_offsets = {key: 0.0 for key in source_values}
    target_offsets = {key: 0.0 for key in target_values}
    source_remaining = dict(source_values)
    source_keys = list(source_values)
    source_index = 0
    ribbons: List[Ribbon] = []
    for target_key, target_value in target_values.items():
        remaining = target_value
        while remaining > 0 and source_index < len(source_keys):
            source_key = source_keys[source_index]
            amount = min(source_remaining[source_key], remaining)
            ribbon_width = width_value(amount)
            ribbons.append(
                Ribbon(
                    source_key,
                    target_key,
                    nodes[source_key].right,
                    nodes[source_key].y + source_offsets[source_key],
                    nodes[target_key].x,
                    nodes[target_key].y + target_offsets[target_key],
                    ribbon_width,
                    GREEN_FLOW if target_key == income_key and income_target else PINK_FLOW,
                )
            )
            source_offsets[source_key] += ribbon_width
            target_offsets[target_key] += ribbon_width
            source_remaining[source_key] -= amount
            remaining -= amount
            if source_remaining[source_key] <= 0:
                source_index += 1
    return ribbons


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
    return get_adapter(quarter.ticker).layout(quarter)


ABOVE_LABEL_OFFSETS = {}


def _below_terminals(quarter: Quarter) -> frozenset:
    return frozenset(get_adapter(quarter.ticker).below_terminals)


def _label_position(
    key: str,
    node: Node,
    ribbons: Sequence[Ribbon],
    below_terminals: frozenset = frozenset(),
) -> Tuple[float, float, str, str, str]:
    round_left, round_right = _node_rounding(node, ribbons)
    if key == "pretax_income":
        return node.x + 11, node.y + ABOVE_LABEL_OFFSETS.get(key, ABOVE_LABEL_DEFAULT_OFFSET), "middle", "internal", "above"
    if key == "nonoperating_income_expense" and not round_left and not round_right:
        return node.right + 12, node.y + node.height / 2 - 2.5, "start", "output", "right"
    if round_left and round_right:
        return node.right + 12, node.y + node.height / 2 - 2.5, "start", "output", "right"
    if round_left and not round_right:
        if key in below_terminals:
            return node.x + 11, node.y + node.height + 30, "middle", "input", "below"
        return node.x - 12, node.y + node.height / 2 - 2.5, "end", "input", "left"
    if round_right and not round_left:
        if key in below_terminals:
            return node.x + 11, node.y + node.height + 30, "middle", "output", "below"
        return node.right + 12, node.y + node.height / 2 - 2.5, "start", "output", "right"
    return (
        node.x + 11,
        node.y + ABOVE_LABEL_OFFSETS.get(key, ABOVE_LABEL_DEFAULT_OFFSET),
        "middle",
        "internal",
        "above",
    )


def _label_font_sizes(quarter: Quarter) -> Tuple[int, int]:
    if get_adapter(quarter.ticker).large_label_fonts:
        return LARGE_LABEL_TITLE_FONT_SIZE, LARGE_LABEL_VALUE_FONT_SIZE
    return LABEL_TITLE_FONT_SIZE, LABEL_VALUE_FONT_SIZE


def _label_card_width(
    fact: FinancialFact,
    title_font_size: int = LABEL_TITLE_FONT_SIZE,
    value_font_size: int = LABEL_VALUE_FONT_SIZE,
) -> float:
    title_width = len(fact.label) * 8.75 * title_font_size / LABEL_TITLE_FONT_SIZE
    value_width = len(_format_fact(fact)) * 7.55 * value_font_size / LABEL_VALUE_FONT_SIZE
    return max(title_width, value_width) + LABEL_CARD_PADDING_X * 2


def _label_left(x: float, anchor: str, width: float) -> float:
    if anchor == "middle":
        return x - width / 2
    if anchor == "end":
        return x - width + LABEL_CARD_PADDING_X
    return x - LABEL_CARD_PADDING_X


def _fit_label_to_canvas(
    fact: FinancialFact,
    position: Tuple[float, float, str, str, str],
    title_font_size: int = LABEL_TITLE_FONT_SIZE,
    value_font_size: int = LABEL_VALUE_FONT_SIZE,
    node: "Node | None" = None,
) -> Tuple[float, float, str, str, str]:
    x, y, anchor, _, _ = position
    width = _label_card_width(fact, title_font_size, value_font_size)
    desired_left = _label_left(x, anchor, width)
    fitted_left = max(CANVAS_MARGIN, min(desired_left, WIDTH - width - CANVAS_MARGIN))
    # Keep a side-placed card beside its node rather than covering it. A
    # right-anchored (start) card must start at or after the node's right edge;
    # a left-anchored (end) card must end at or before the node's left edge.
    # When honouring that would push the card past the wider canvas margin, we
    # fall back to a tighter side margin so the card can sit fully beside the
    # rightmost/leftmost terminal instead of covering it, while staying
    # on-canvas.
    if node is not None:
        if anchor == "start":
            floor_left = node.right + LABEL_CARD_GAP - LABEL_CARD_PADDING_X
            candidate = max(fitted_left, floor_left)
            fitted_left = min(candidate, WIDTH - width - SIDE_LABEL_MARGIN)
            fitted_left = max(fitted_left, CANVAS_MARGIN)
        elif anchor == "end":
            ceil_left = node.x - LABEL_CARD_GAP - width + LABEL_CARD_PADDING_X
            candidate = min(fitted_left, ceil_left)
            fitted_left = max(candidate, SIDE_LABEL_MARGIN)
    return x + fitted_left - desired_left, y, anchor, position[3], position[4]


def _label_card_bounds(
    fact: FinancialFact,
    position: Tuple[float, float, str, str, str],
    title_font_size: int = LABEL_TITLE_FONT_SIZE,
    value_font_size: int = LABEL_VALUE_FONT_SIZE,
) -> Tuple[float, float, float, float]:
    x, y, anchor, _, _ = position
    width = _label_card_width(fact, title_font_size, value_font_size)
    left = _label_left(x, anchor, width)
    size_delta = max(0, title_font_size - LABEL_TITLE_FONT_SIZE)
    return left, y - 22 - size_delta, width, 49 + size_delta * 2


def _label_card(
    key: str,
    fact: FinancialFact,
    position: Tuple[float, float, str, str, str],
    title_font_size: int,
    value_font_size: int,
) -> str:
    """Return a translucent backing card sized for a two-line fact label."""
    _, _, _, role, placement = position
    left, top, width, height = _label_card_bounds(
        fact, position, title_font_size, value_font_size
    )
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
    title_font_size, value_font_size = _label_font_sizes(quarter)
    widths = {
        key: _label_card_width(
            quarter.facts[key], title_font_size, value_font_size
        )
        for key in keys
    }
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
        # Prefer perfect centering over the node, but when the row is too tight
        # (e.g. derived Q4 quarters with wide YoY strings) allow the card and its
        # text to shift together by a small amount so they stay on one row and
        # never overlap. The text is anchored to the card centre, so it remains
        # inside the card and visually attached to the node.
        packed_x = lefts[key] + widths[key] / 2
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
    title_font_size, value_font_size = _label_font_sizes(quarter)
    bounds = {
        key: _label_card_bounds(
            quarter.facts[key], position, title_font_size, value_font_size
        )
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
    adapter = get_adapter(quarter.ticker)
    label_keys = adapter.label_keys
    # Only label facts that are present and actually drawn as nodes. Alphabet's
    # optional segment revenue lines are omitted from filings that do not tag
    # them, so their label cards must be skipped too.
    label_keys = tuple(
        key for key in label_keys if key in quarter.facts and key in nodes_by_key
    )
    below_terminals = frozenset(adapter.below_terminals)
    title_font_size, value_font_size = _label_font_sizes(quarter)
    positions = {
        key: _fit_label_to_canvas(
            quarter.facts[key],
            _label_position(key, nodes_by_key[key], ribbons, below_terminals),
            title_font_size,
            value_font_size,
            nodes_by_key[key],
        )
        for key in label_keys
    }
    positions = _pack_above_labels(quarter, positions)
    positions = _resolve_label_spacing(quarter, positions)
    _validate_label_spacing(quarter, positions)
    for key in label_keys:
        fact = quarter.facts[key]
        position = positions[key]
        x, y, anchor, _, _ = position
        lines.append(
            _label_card(
                key, fact, position, title_font_size, value_font_size
            )
        )
        lines.append(f'<text x="{x}" y="{y - 1}" text-anchor="{anchor}" font-family="Arial,sans-serif" font-size="{title_font_size}" font-weight="700" fill="{INK}">{escape(fact.label)}</text>')
        lines.append(f'<text x="{x}" y="{y + 21}" text-anchor="{anchor}" font-family="Arial,sans-serif" font-size="{value_font_size}" fill="{MUTED}">{escape(_format_fact(fact))}</text>')
    lines.extend(
        [
            f'<line x1="42" y1="950" x2="1038" y2="950" stroke="#d7dbe0"/>',
            f'<text x="42" y="980" font-family="Arial,sans-serif" font-size="14" fill="{INK}">Source: {escape(quarter.company)} SEC filing dated {_display_date(source.filing_date)} • accession {escape(source.accession)}</text>',
            f'<text x="42" y="1004" font-family="Arial,sans-serif" font-size="13" fill="{MUTED}">Rounded for display. * values are derived. Segment labels use {escape(quarter.ticker)}-specific XBRL dimensions.</text>',
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
