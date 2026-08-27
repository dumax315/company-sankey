"""Micron (MU) adapter: product revenue and a sign-aware chipmaker P&L."""

from __future__ import annotations

from typing import Dict, List, Tuple

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


PRODUCT_KEYS = ("dram_revenue", "nand_revenue", "other_product_revenue")
OPERATING_EXPENSE_KEYS = (
    "research_and_development",
    "selling_general_and_administrative",
    "restructuring",
    "other_operating_expense",
)
LABEL_KEYS = (
    *PRODUCT_KEYS,
    "revenue",
    "gross_profit",
    "cost_of_revenue",
    "operating_income",
    *OPERATING_EXPENSE_KEYS,
    "pretax_income",
    "investment_income",
    "interest_expense",
    "other_nonoperating_income_expense",
    "income_tax",
    "equity_method_investment",
    "net_income",
)


def _groups_with_primary_source(
    contributions: Dict[str, int], outcome_key: str, outcome: int, primary_key: str
) -> Tuple[Dict[str, int], Dict[str, int]]:
    """Balance ``sum(contributions) = outcome`` while keeping the primary flowing right."""
    positive = {key: value for key, value in contributions.items() if value > 0}
    negative = {key: -value for key, value in contributions.items() if value < 0}
    if contributions[primary_key] >= 0:
        sources, targets = positive, negative
        (targets if outcome >= 0 else sources)[outcome_key] = abs(outcome)
    else:
        sources, targets = negative, positive
        (targets if outcome <= 0 else sources)[outcome_key] = abs(outcome)
    return sources, targets


def layout(quarter: Quarter) -> Tuple[List[Node], List[Ribbon]]:
    f = quarter.facts
    scale = 3.0 / 1000.0

    def width_value(value: float) -> float:
        return max(1.2, abs(value) * scale)

    def width(key: str) -> float:
        return width_value(f[key].value_millions)

    gross = f["gross_profit"].value_millions
    operating = f["operating_income"].value_millions
    pretax = f["pretax_income"].value_millions
    net = f["net_income"].value_millions

    operating_contributions = {"gross_profit": gross}
    for key in OPERATING_EXPENSE_KEYS:
        if key in f:
            operating_contributions[key] = -f[key].value_millions
    operating_sources, operating_targets = _groups_with_primary_source(
        operating_contributions, "operating_income", operating, "gross_profit"
    )

    nonoperating_contributions = {
        "operating_income": operating,
        "investment_income": f["investment_income"].value_millions,
        "interest_expense": -f["interest_expense"].value_millions,
        "other_nonoperating_income_expense": f[
            "other_nonoperating_income_expense"
        ].value_millions,
    }
    nonoperating_sources, nonoperating_targets = _groups_with_primary_source(
        nonoperating_contributions, "pretax_income", pretax, "operating_income"
    )

    tax_contribution = -f["income_tax"].value_millions
    equity_contribution = f["equity_method_investment"].value_millions
    post_tax_contributions = {
        "pretax_income": pretax,
        "income_tax": tax_contribution,
        "equity_method_investment": equity_contribution,
    }
    if net >= 0:
        post_tax_sources = {
            key: value for key, value in post_tax_contributions.items() if value > 0
        }
        post_tax_targets = {
            key: -value for key, value in post_tax_contributions.items() if value < 0
        }
    else:
        post_tax_sources = {
            key: -value for key, value in post_tax_contributions.items() if value < 0
        }
        post_tax_targets = {
            key: value for key, value in post_tax_contributions.items() if value > 0
        }
    post_tax_targets["net_income"] = abs(net)

    operating_y = 330.0 if "operating_income" in operating_sources else 260.0
    nodes: Dict[str, Node] = {
        "revenue": Node("revenue", 300, 260, width("revenue"), BLUE),
        "gross_profit": Node(
            "gross_profit", 486, 260, width("gross_profit"), GREEN if gross >= 0 else PINK
        ),
        "cost_of_revenue": Node(
            "cost_of_revenue", 486 if gross >= 0 else 540, 420, width("cost_of_revenue"), PINK
        ),
        "operating_income": Node(
            "operating_income",
            609 if "operating_income" in operating_sources else 663,
            operating_y,
            width("operating_income"),
            GREEN if operating >= 0 else PINK,
        ),
        "pretax_income": Node(
            "pretax_income",
            797 if "pretax_income" in nonoperating_sources else 851,
            260,
            width("pretax_income"),
            GREEN if pretax >= 0 else PINK,
        ),
        "net_income": Node(
            "net_income", 873, 260, width("net_income"), GREEN if net >= 0 else PINK
        ),
    }

    product_stride = 74.0
    revenue_center = nodes["revenue"].y + nodes["revenue"].height / 2
    product_center = revenue_center - product_stride
    for key in PRODUCT_KEYS:
        node_height = width(key)
        nodes[key] = Node(key, 190, product_center - node_height / 2, node_height, BLUE)
        product_center += product_stride

    expense_y = {
        "research_and_development": 540.0,
        "selling_general_and_administrative": 620.0,
        "restructuring": 700.0,
        "other_operating_expense": 780.0,
    }
    for key in OPERATING_EXPENSE_KEYS:
        if key not in f:
            continue
        value = f[key].value_millions
        nodes[key] = Node(
            key,
            609 if key in operating_sources else 663,
            expense_y[key],
            width(key),
            PINK if value >= 0 else GREEN,
        )

    nonoperating_y = {
        "investment_income": 480.0,
        "interest_expense": 370.0,
        "other_nonoperating_income_expense": 560.0,
    }
    for key in nonoperating_y:
        contribution = nonoperating_contributions[key]
        if key == "interest_expense" and key in nonoperating_sources:
            y = 310.0
        elif key == "other_nonoperating_income_expense" and key in nonoperating_sources:
            y = 370.0
        else:
            y = nonoperating_y[key]
        nodes[key] = Node(
            key,
            797 if key in nonoperating_sources else 851,
            y,
            width(key),
            GREEN if contribution >= 0 else PINK,
        )

    post_tax_y = {"income_tax": 850.0, "equity_method_investment": 920.0}
    for key, y in post_tax_y.items():
        contribution = post_tax_contributions[key]
        nodes[key] = Node(
            key,
            744 if key in post_tax_sources else 851,
            y,
            width(key),
            GREEN if contribution >= 0 else PINK,
        )

    ribbons: List[Ribbon] = []
    target_y = nodes["revenue"].y
    for key in PRODUCT_KEYS:
        ribbons.append(
            Ribbon(
                key,
                "revenue",
                nodes[key].right,
                nodes[key].y,
                nodes["revenue"].x,
                target_y,
                width(key),
                BLUE_FLOW,
            )
        )
        target_y += width(key)

    if gross >= 0:
        ribbons.append(
            Ribbon("revenue", "gross_profit", nodes["revenue"].right, nodes["revenue"].y,
                   nodes["gross_profit"].x, nodes["gross_profit"].y, width("gross_profit"), GREEN_FLOW)
        )
        ribbons.append(
            Ribbon("revenue", "cost_of_revenue", nodes["revenue"].right,
                   nodes["revenue"].y + width("gross_profit"), nodes["cost_of_revenue"].x,
                   nodes["cost_of_revenue"].y, width("cost_of_revenue"), PINK_FLOW)
        )
    else:
        ribbons.append(
            Ribbon("revenue", "cost_of_revenue", nodes["revenue"].right, nodes["revenue"].y,
                   nodes["cost_of_revenue"].x, nodes["cost_of_revenue"].y, width("revenue"), PINK_FLOW)
        )
        ribbons.append(
            Ribbon("gross_profit", "cost_of_revenue", nodes["gross_profit"].right,
                   nodes["gross_profit"].y, nodes["cost_of_revenue"].x,
                   nodes["cost_of_revenue"].y + width("revenue"), width("gross_profit"), PINK_FLOW)
        )

    ribbons.extend(
        _packed_flows(
            nodes, operating_sources, operating_targets, "operating_income", width_value,
            income_target=operating >= 0,
        )
    )
    ribbons.extend(
        _packed_flows(
            nodes, nonoperating_sources, nonoperating_targets, "pretax_income", width_value,
            income_target=pretax >= 0,
        )
    )
    ribbons.extend(
        _packed_flows(
            nodes, post_tax_sources, post_tax_targets, "net_income", width_value,
            income_target=net >= 0,
        )
    )
    return list(nodes.values()), ribbons


def build_checks(f: dict, tolerance_millions: int, check) -> list:
    operating_expenses = sum(
        f[key].value_millions for key in OPERATING_EXPENSE_KEYS if key in f
    )
    return [
        check(
            "product revenue equals consolidated revenue",
            f["revenue"].value_millions,
            sum(f[key].value_millions for key in PRODUCT_KEYS),
            tolerance_millions,
        ),
        check(
            "revenue less cost of goods sold equals gross profit",
            f["gross_profit"].value_millions,
            f["revenue"].value_millions - f["cost_of_revenue"].value_millions,
            tolerance_millions,
        ),
        check(
            "gross profit less operating expenses equals operating income",
            f["operating_income"].value_millions,
            f["gross_profit"].value_millions - operating_expenses,
            tolerance_millions,
        ),
        check(
            "operating and non-operating activity equals pre-tax income",
            f["pretax_income"].value_millions,
            f["operating_income"].value_millions
            + f["investment_income"].value_millions
            - f["interest_expense"].value_millions
            + f["other_nonoperating_income_expense"].value_millions,
            tolerance_millions,
        ),
        check(
            "pre-tax less tax plus equity-method activity equals net income",
            f["net_income"].value_millions,
            f["pretax_income"].value_millions
            - f["income_tax"].value_millions
            + f["equity_method_investment"].value_millions,
            tolerance_millions,
        ),
    ]


register(
    CompanyAdapter(
        ticker="MU",
        slug="micron",
        config_filename="micron.json",
        layout=layout,
        label_keys=LABEL_KEYS,
        build_checks=build_checks,
        large_label_fonts=False,
    )
)
