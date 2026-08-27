"""Exxon Mobil (XOM) adapter: an integrated oil & gas income statement.

ExxonMobil reports a single "revenues and other income" total (there is no
cost-of-revenue / gross-profit bridge, like a bank), then a long list of costs
and other deductions, then the tax and noncontrolling-interest waterfall:

    sales & operating revenue + equity affiliates income + other income
        = total revenues & other income                    (optional; see below)
    sum(eight cost lines) = total costs & other deductions
    total revenues - total costs = income before income taxes
    income before income taxes - income tax = net income incl. noncontrolling
    net income incl. noncontrolling - noncontrolling interests = net income

The revenue product/service breakdown (sales, equity affiliates, other income)
is only tagged in the standalone-quarter 10-Qs from mid-2023 on. Older 10-Qs and
every cumulative period (nine-month and annual, so derived Q4 quarters) omit it,
so those three lines are optional: their cards and the segment identity are only
drawn/checked when all three are present.

The layout mirrors that structure left to right:

    revenue components --> revenue                          (when present)
    revenue --> {income before taxes, eight cost lines}
    income before taxes --> {net income, income tax, noncontrolling interests}
"""

from __future__ import annotations

from typing import List, Tuple

from ..models import Quarter
from ..render import (
    BLUE,
    BLUE_FLOW,
    GREEN,
    GREEN_FLOW,
    PINK,
    PINK_FLOW,
    Node,
    Ribbon,
    _packed_flows,
)
from . import CompanyAdapter, register


# Ordered revenue components (all optional — only some periods tag them).
REVENUE_COMPONENT_KEYS = (
    "sales_revenue",
    "equity_affiliates_income",
    "other_income",
)

# Ordered cost lines that sum to total costs & other deductions.
COST_KEYS = (
    "crude_oil_purchases",
    "production_manufacturing",
    "sga",
    "depreciation",
    "exploration",
    "pension_nonservice",
    "interest_expense",
    "taxes_other",
)

LABEL_KEYS = (
    "sales_revenue",
    "equity_affiliates_income",
    "other_income",
    "revenue",
    "pretax_income",
    *COST_KEYS,
    "net_income",
    "income_tax",
    "noncontrolling_interest",
)


def _has_revenue_components(f: dict) -> bool:
    return all(key in f for key in REVENUE_COMPONENT_KEYS)


def layout(quarter: Quarter) -> Tuple[List[Node], List[Ribbon]]:
    f = quarter.facts

    # Single series-wide scale sized so XOM's tallest column fits the vertical
    # band once the eight cost lines each reserve a card's worth of height. All
    # quarters share it, so bar thickness stays comparable across the series.
    scale = 1.9 / 1000.0

    def width_value(value: float) -> float:
        return max(1.2, abs(value) * scale)

    def h(key: str) -> float:
        return width_value(f[key].value_millions)

    # This layout targets profitable quarters (XOM's case across this window).
    # A pre-tax or net loss would need sign-aware flows like the Amazon adapter.
    if f["pretax_income"].value_millions < 0 or f["net_income"].value_millions < 0:
        raise ValueError("XOM layout does not yet support loss quarters")

    TOP = 250.0
    GAP = 4.0

    nodes: dict = {}

    # Column 1 (optional): the three revenue components. Their side labels are
    # ~50px tall cards, but the equity-affiliates and other-income bars are tiny
    # (well under $1B), so a purely contiguous stack would let their cards
    # collide. Stack them by bar height but never advance less than a card's
    # worth of vertical room, so each component's left-placed card clears the
    # next one.
    draw_components = _has_revenue_components(f)
    COMPONENT_MIN_STRIDE = 60.0
    if draw_components:
        y = TOP
        for key in REVENUE_COMPONENT_KEYS:
            node_height = h(key)
            nodes[key] = Node(key, 230, y, node_height, BLUE)
            y += max(node_height, COMPONENT_MIN_STRIDE) + GAP

    # Column 2: total revenues & other income.
    nodes["revenue"] = Node("revenue", 430, TOP, h("revenue"), BLUE)

    # Column 3: income before taxes on top (green), then the eight cost lines
    # stacked below (pink). Several cost lines are tiny ($30M-$250M for
    # non-service pension, exploration and interest), so — like the revenue
    # components — the stack advances by at least a card's worth of vertical
    # room, keeping each right-placed cost card clear of its neighbour.
    COST_MIN_STRIDE = 60.0
    y = TOP
    for key in ["pretax_income", *COST_KEYS]:
        node_height = h(key)
        color = GREEN if key == "pretax_income" else PINK
        nodes[key] = Node(key, 560, y, node_height, color)
        y += max(node_height, COST_MIN_STRIDE) + GAP

    # Column 4: net income (terminal, green) with income tax and noncontrolling
    # interests below and just left of it (pink). Keeping them left of net
    # income makes net income the unambiguous rightmost terminal node. Their
    # right-placed cards are centred on each bar, so — as in the cost column —
    # advance by at least a card's worth of height between them.
    COLUMN4_MIN_STRIDE = 60.0
    nodes["net_income"] = Node("net_income", 880, TOP, h("net_income"), GREEN)
    tax_top = TOP + max(h("net_income"), COLUMN4_MIN_STRIDE) + GAP
    nodes["income_tax"] = Node("income_tax", 800, tax_top, h("income_tax"), PINK)
    nci_top = tax_top + max(h("income_tax"), COLUMN4_MIN_STRIDE) + GAP
    nodes["noncontrolling_interest"] = Node(
        "noncontrolling_interest", 800, nci_top, h("noncontrolling_interest"), PINK
    )

    ribbons: List[Ribbon] = []

    # Revenue components -> revenue (blue). Only drawn when all three present.
    if draw_components:
        target_y = nodes["revenue"].y
        for key in REVENUE_COMPONENT_KEYS:
            component_width = width_value(f[key].value_millions)
            ribbons.append(
                Ribbon(
                    key,
                    "revenue",
                    nodes[key].right,
                    nodes[key].y,
                    nodes["revenue"].x,
                    target_y,
                    component_width,
                    BLUE_FLOW,
                )
            )
            target_y += component_width

    # revenue -> income before taxes (green) + the eight cost lines (pink).
    revenue_sources = {"revenue": f["revenue"].value_millions}
    revenue_targets = {"pretax_income": f["pretax_income"].value_millions}
    for key in COST_KEYS:
        revenue_targets[key] = f[key].value_millions
    ribbons.extend(
        _packed_flows(nodes, revenue_sources, revenue_targets, "pretax_income", width_value)
    )

    # income before taxes -> net income (green) + income tax + noncontrolling
    # interests (pink). pretax - tax - NCI = net income.
    pretax_sources = {"pretax_income": f["pretax_income"].value_millions}
    pretax_targets = {
        "net_income": f["net_income"].value_millions,
        "income_tax": f["income_tax"].value_millions,
        "noncontrolling_interest": f["noncontrolling_interest"].value_millions,
    }
    ribbons.extend(
        _packed_flows(nodes, pretax_sources, pretax_targets, "net_income", width_value)
    )

    return list(nodes.values()), ribbons


def build_checks(f: dict, tolerance_millions: int, check) -> list:
    checks = []

    # Optional: revenue product/service components sum to total revenue. Only
    # enforced when all three are tagged (older/cumulative periods omit them).
    if _has_revenue_components(f):
        checks.append(
            check(
                "revenue components equal total revenues and other income",
                f["revenue"].value_millions,
                f["sales_revenue"].value_millions
                + f["equity_affiliates_income"].value_millions
                + f["other_income"].value_millions,
                tolerance_millions,
            )
        )

    checks.append(
        check(
            "cost components equal total costs and other deductions",
            f["costs_and_expenses"].value_millions,
            sum(f[key].value_millions for key in COST_KEYS),
            tolerance_millions,
        )
    )
    checks.append(
        check(
            "revenue less total costs equals income before income taxes",
            f["pretax_income"].value_millions,
            f["revenue"].value_millions - f["costs_and_expenses"].value_millions,
            tolerance_millions,
        )
    )
    checks.append(
        check(
            "income before taxes less income tax equals net income incl. noncontrolling",
            f["profit_loss"].value_millions,
            f["pretax_income"].value_millions - f["income_tax"].value_millions,
            tolerance_millions,
        )
    )
    checks.append(
        check(
            "net income incl. noncontrolling less noncontrolling interests equals net income",
            f["net_income"].value_millions,
            f["profit_loss"].value_millions
            - f["noncontrolling_interest"].value_millions,
            tolerance_millions,
        )
    )
    return checks


register(
    CompanyAdapter(
        ticker="XOM",
        slug="exxon",
        config_filename="exxon.json",
        layout=layout,
        label_keys=LABEL_KEYS,
        build_checks=build_checks,
        # The eight cost lines plus the revenue components make for a dense
        # column, so use the smaller 16/14pt cards (like Meta) to fit them.
        large_label_fonts=False,
    )
)
