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
    # Single series-wide scale sized so JPM's tallest column (net interest
    # income + interest expense + noninterest revenue ~= $82B stacked) nearly
    # fills the vertical band. All quarters share it, so bar thickness stays
    # comparable across the series.
    scale = 7.5 / 1000.0

    def width_value(value: float) -> float:
        return max(1.2, abs(value) * scale)

    def width(key: str) -> float:
        return width_value(f[key].value_millions)

    def h(key: str) -> float:
        return width_value(f[key].value_millions)

    # This layout targets profitable quarters (JPM's normal case). A pre-tax or
    # net loss would need sign-aware flows like the Amazon/Alphabet adapters.
    if f["pretax_income"].value_millions < 0 or f["net_income"].value_millions < 0:
        raise ValueError("JPM layout does not yet support loss quarters")

    # With thick bars, columns stack contiguously (like a real Sankey): each
    # node begins a small gap below the previous one so incoming/outgoing flows
    # line up. GAP separates logically distinct bars within a column.
    TOP = 250.0
    GAP = 24.0

    def _color(key: str) -> str:
        pink_keys = {
            "interest_expense",
            "provision_for_credit_losses",
            "noninterest_expense",
            "income_tax",
        }
        return PINK if key in pink_keys else (GREEN if key in {"pretax_income", "net_income"} else BLUE)

    def stacked(x: float, keys: list[str], top: float) -> dict:
        """Stack ``keys`` down a column by bar height, GAP apart."""
        placed = {}
        y = top
        for key in keys:
            node_height = h(key)
            placed[key] = Node(key, x, y, node_height, _color(key))
            y += node_height + GAP
        return placed

    nodes: dict = {}
    # Column 1: gross interest income.
    nodes["interest_income"] = Node("interest_income", 150, TOP, h("interest_income"), BLUE)
    # Column 2: the two revenue inputs stack contiguously so they line up with
    # the revenue node, then interest expense sits just below.
    nodes.update(
        stacked(320, ["net_interest_income", "noninterest_income", "interest_expense"], TOP)
    )
    # Column 3: total net revenue (aligned with the top of column 2's revenue
    # inputs).
    nodes["revenue"] = Node("revenue", 500, TOP, h("revenue"), BLUE)
    # Column 4: pre-tax income on top, then the two expense lines, contiguously.
    nodes.update(
        stacked(
            690,
            ["pretax_income", "provision_for_credit_losses", "noninterest_expense"],
            TOP,
        )
    )
    # Column 5: net income (terminal) on top with income tax to its left. Income
    # tax is dropped below column 4's provision card so the two right-placed
    # cards never overlap; net income stays the rightmost terminal node.
    nodes["net_income"] = Node("net_income", 880, TOP, h("net_income"), GREEN)
    nodes["income_tax"] = Node(
        "income_tax",
        826,
        nodes["noninterest_expense"].y + nodes["noninterest_expense"].height + 30.0,
        h("income_tax"),
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
