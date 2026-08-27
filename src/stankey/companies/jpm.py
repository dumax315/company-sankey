"""JPMorgan Chase (JPM) adapter: a bank income statement.

Unlike the tech companies, a bank has no cost-of-revenue / gross-profit bridge.
Its income statement is:

    interest income - interest expense = net interest income
    net interest income + noninterest revenue = total net revenue
    total net revenue - provision for credit losses - noninterest expense
        = pre-tax income
    pre-tax income - income tax = net income

The layout mirrors that structure left to right:

    interest income --> net interest income (with interest expense split off)
    net interest income + noninterest revenue --> total net revenue
    total net revenue --> {provision, noninterest expense, pre-tax income}
    pre-tax income --> {income tax, net income}
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
    h_of,
)
from . import CompanyAdapter, register


LABEL_KEYS = (
    "interest_income",
    "interest_expense",
    "net_interest_income",
    "noninterest_income",
    "revenue",
    "provision_for_credit_losses",
    "noninterest_expense",
    "pretax_income",
    "income_tax",
    "net_income",
)


def layout(quarter: Quarter) -> Tuple[List[Node], List[Ribbon]]:
    f = quarter.facts
    scale = 0.8 / 1000.0

    def width_value(value: float) -> float:
        return max(1.2, abs(value) * scale)

    def width(key: str) -> float:
        return width_value(f[key].value_millions)

    # This layout targets profitable quarters (JPM's normal case). A pre-tax or
    # net loss would need sign-aware flows like the Amazon/Alphabet adapters.
    if f["pretax_income"].value_millions < 0 or f["net_income"].value_millions < 0:
        raise ValueError("JPM layout does not yet support loss quarters")

    # Side-placed label cards are ~53px tall and centred on their node, so
    # vertically stacked nodes in a column must have their centres at least a
    # card-height-plus-gap apart or the cards collide. Space the stacked cost /
    # revenue nodes by centre using this stride, independent of the (often tiny)
    # node bar heights.
    STACK_STRIDE = 62.0
    TOP = 300.0

    def stacked(x: float, keys: list[str], top: float) -> dict:
        """Place ``keys`` down a column, spacing their centres by STACK_STRIDE."""
        placed = {}
        center = top + h_of(f, keys[0]) / 2
        for key in keys:
            node_height = h_of(f, key)
            placed[key] = Node(key, x, center - node_height / 2, node_height, _color(key))
            center += STACK_STRIDE
        return placed

    def _color(key: str) -> str:
        pink_keys = {
            "interest_expense",
            "provision_for_credit_losses",
            "noninterest_expense",
            "income_tax",
        }
        return PINK if key in pink_keys else (GREEN if key in {"pretax_income", "net_income"} else BLUE)

    nodes: dict = {}
    # Column 1: gross interest income.
    nodes["interest_income"] = Node("interest_income", 150, TOP, h_of(f, "interest_income"), BLUE)
    # Column 2: net interest income, interest expense, noninterest revenue.
    nodes.update(
        stacked(320, ["net_interest_income", "interest_expense", "noninterest_income"], TOP)
    )
    # Column 3: total net revenue.
    nodes["revenue"] = Node("revenue", 500, TOP, h_of(f, "revenue"), BLUE)
    # Column 4: pre-tax income (top band) and the two expense lines. The expense
    # cards are wide and right-placed, so they start well below the terminal
    # column's cards to avoid horizontal competition with income tax / net
    # income; the vertical separation keeps every card clear.
    nodes["pretax_income"] = Node("pretax_income", 690, TOP, h_of(f, "pretax_income"), GREEN)
    nodes.update(
        stacked(690, ["provision_for_credit_losses", "noninterest_expense"], 470.0)
    )
    # Column 5: net income (terminal, top band) with income tax just to its left
    # and below so net income remains the rightmost terminal node.
    nodes["net_income"] = Node("net_income", 880, TOP, h_of(f, "net_income"), GREEN)
    nodes["income_tax"] = Node(
        "income_tax",
        826,
        TOP + h_of(f, "net_income") / 2 + STACK_STRIDE - h_of(f, "income_tax") / 2,
        h_of(f, "income_tax"),
        PINK,
    )

    ribbons: List[Ribbon] = []

    # interest_income -> net_interest_income (green net) and interest_expense (pink cost).
    ribbons.append(
        Ribbon(
            "interest_income",
            "net_interest_income",
            nodes["interest_income"].right,
            nodes["interest_income"].y,
            nodes["net_interest_income"].x,
            nodes["net_interest_income"].y,
            width("net_interest_income"),
            BLUE_FLOW,
        )
    )
    ribbons.append(
        Ribbon(
            "interest_income",
            "interest_expense",
            nodes["interest_income"].right,
            nodes["interest_income"].y + width("net_interest_income"),
            nodes["interest_expense"].x,
            nodes["interest_expense"].y,
            width("interest_expense"),
            PINK_FLOW,
        )
    )

    # net_interest_income + noninterest_income -> revenue (total net revenue).
    ribbons.append(
        Ribbon(
            "net_interest_income",
            "revenue",
            nodes["net_interest_income"].right,
            nodes["net_interest_income"].y,
            nodes["revenue"].x,
            nodes["revenue"].y,
            width("net_interest_income"),
            BLUE_FLOW,
        )
    )
    ribbons.append(
        Ribbon(
            "noninterest_income",
            "revenue",
            nodes["noninterest_income"].right,
            nodes["noninterest_income"].y,
            nodes["revenue"].x,
            nodes["revenue"].y + width("net_interest_income"),
            width("noninterest_income"),
            BLUE_FLOW,
        )
    )

    # revenue -> pre-tax income (green), provision + noninterest expense (pink).
    revenue_sources = {"revenue": f["revenue"].value_millions}
    revenue_targets = {
        "pretax_income": f["pretax_income"].value_millions,
        "provision_for_credit_losses": f["provision_for_credit_losses"].value_millions,
        "noninterest_expense": f["noninterest_expense"].value_millions,
    }
    ribbons.extend(
        _packed_flows(nodes, revenue_sources, revenue_targets, "pretax_income", width_value)
    )

    # pre-tax income -> net income (green) and income tax (pink).
    pretax_sources = {"pretax_income": f["pretax_income"].value_millions}
    pretax_targets = {
        "net_income": f["net_income"].value_millions,
        "income_tax": f["income_tax"].value_millions,
    }
    ribbons.extend(
        _packed_flows(nodes, pretax_sources, pretax_targets, "net_income", width_value)
    )

    return list(nodes.values()), ribbons


def build_checks(f: dict, tolerance_millions: int, check) -> list:
    return [
        check(
            "interest income less interest expense equals net interest income",
            f["net_interest_income"].value_millions,
            f["interest_income"].value_millions - f["interest_expense"].value_millions,
            tolerance_millions,
        ),
        check(
            "net interest income plus noninterest revenue equals total net revenue",
            f["revenue"].value_millions,
            f["net_interest_income"].value_millions
            + f["noninterest_income"].value_millions,
            tolerance_millions,
        ),
        check(
            "total net revenue less provision less noninterest expense equals pre-tax income",
            f["pretax_income"].value_millions,
            f["revenue"].value_millions
            - f["provision_for_credit_losses"].value_millions
            - f["noninterest_expense"].value_millions,
            tolerance_millions,
        ),
        check(
            "pre-tax income less income tax equals net income",
            f["net_income"].value_millions,
            f["pretax_income"].value_millions - f["income_tax"].value_millions,
            tolerance_millions,
        ),
    ]


register(
    CompanyAdapter(
        ticker="JPM",
        slug="jpm",
        config_filename="jpm.json",
        layout=layout,
        label_keys=LABEL_KEYS,
        build_checks=build_checks,
    )
)
