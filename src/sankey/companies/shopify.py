"""Shopify (SHOP) adapter with product revenue and sign-aware profit flows."""

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
    "subscription_solutions_revenue",
    "merchant_solutions_revenue",
    "revenue",
    "gross_profit",
    "cost_of_revenue",
    "operating_income",
    "sales_and_marketing",
    "research_and_development",
    "general_and_administrative",
    "transaction_and_loan_losses",
    "pretax_income",
    "nonoperating_income_expense",
    "income_tax",
    "net_income",
)

REVENUE_KEYS = (
    "subscription_solutions_revenue",
    "merchant_solutions_revenue",
)

EXPENSE_KEYS = (
    "sales_and_marketing",
    "research_and_development",
    "general_and_administrative",
    "transaction_and_loan_losses",
)


def layout(quarter: Quarter) -> Tuple[List[Node], List[Ribbon]]:
    f = quarter.facts
    # SHOP's quarterly revenue is much smaller than the mega-cap tech reference
    # adapters, so use a company-specific scale that keeps the flows legible.
    scale = 20.0 / 1000.0

    def width_value(value: float) -> float:
        return max(1.2, abs(value) * scale)

    def width(key: str) -> float:
        return width_value(f[key].value_millions)

    operating = f["operating_income"].value_millions
    nonoperating = f["nonoperating_income_expense"].value_millions
    pretax = f["pretax_income"].value_millions
    net = f["net_income"].value_millions
    operating_is_income = operating >= 0
    nonoperating_is_income = nonoperating >= 0
    pretax_is_income = pretax >= 0
    net_is_income = net >= 0
    tax_contribution = -f["income_tax"].value_millions
    post_tax_contributions = {
        "pretax_income": pretax,
        "income_tax": tax_contribution,
    }
    post_tax_sources = (
        {key for key, value in post_tax_contributions.items() if value >= 0}
        if net_is_income
        else {key for key, value in post_tax_contributions.items() if value < 0}
    )

    nodes = {
        "subscription_solutions_revenue": Node(
            "subscription_solutions_revenue", 190, 305, width("subscription_solutions_revenue"), BLUE
        ),
        "merchant_solutions_revenue": Node(
            "merchant_solutions_revenue", 190, 410, width("merchant_solutions_revenue"), BLUE
        ),
        "revenue": Node("revenue", 300, 340, width("revenue"), BLUE),
        "gross_profit": Node("gross_profit", 486, 340, width("gross_profit"), GREEN),
        "cost_of_revenue": Node("cost_of_revenue", 486, 500, width("cost_of_revenue"), PINK),
        "operating_income": Node(
            "operating_income",
            663,
            340,
            width("operating_income"),
            GREEN if operating_is_income else PINK,
        ),
        "sales_and_marketing": Node(
            "sales_and_marketing", 663, 565, width("sales_and_marketing"), PINK
        ),
        "research_and_development": Node(
            "research_and_development", 663, 645, width("research_and_development"), PINK
        ),
        "general_and_administrative": Node(
            "general_and_administrative", 663, 725, width("general_and_administrative"), PINK
        ),
        "transaction_and_loan_losses": Node(
            "transaction_and_loan_losses", 663, 805, width("transaction_and_loan_losses"), PINK
        ),
        "pretax_income": Node(
            "pretax_income", 851, 340, width("pretax_income"), GREEN if pretax_is_income else PINK
        ),
        "nonoperating_income_expense": Node(
            "nonoperating_income_expense",
            797 if nonoperating_is_income else 851,
            455,
            width("nonoperating_income_expense"),
            GREEN if nonoperating_is_income else PINK,
        ),
        "income_tax": Node(
            "income_tax",
            744 if "income_tax" in post_tax_sources else 851,
            455 if "income_tax" in post_tax_sources else 545,
            width("income_tax"),
            GREEN if tax_contribution >= 0 else PINK,
        ),
        "net_income": Node(
            "net_income", 873, 340, width("net_income"), GREEN if net_is_income else PINK
        ),
    }

    ribbons: List[Ribbon] = []
    target_y = nodes["revenue"].y
    for key in REVENUE_KEYS:
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

    ribbons.append(
        Ribbon(
            "revenue",
            "gross_profit",
            nodes["revenue"].right,
            nodes["revenue"].y,
            nodes["gross_profit"].x,
            nodes["gross_profit"].y,
            width("gross_profit"),
            GREEN_FLOW,
        )
    )
    ribbons.append(
        Ribbon(
            "revenue",
            "cost_of_revenue",
            nodes["revenue"].right,
            nodes["revenue"].y + width("gross_profit"),
            nodes["cost_of_revenue"].x,
            nodes["cost_of_revenue"].y,
            width("cost_of_revenue"),
            PINK_FLOW,
        )
    )

    operating_sources = {"gross_profit": f["gross_profit"].value_millions}
    operating_targets = {}
    if operating_is_income:
        operating_targets["operating_income"] = operating
    else:
        operating_sources["operating_income"] = -operating
    for key in EXPENSE_KEYS:
        value = f[key].value_millions
        if value < 0:
            operating_sources[key] = -value
        else:
            operating_targets[key] = value
    ribbons.extend(
        _packed_flows(
            nodes,
            operating_sources,
            operating_targets,
            "operating_income",
            width_value,
        )
    )

    # Operating income plus net other income/expense equals pre-tax income.
    if nonoperating_is_income and operating_is_income:
        ribbons.append(
            Ribbon(
                "operating_income", "pretax_income",
                nodes["operating_income"].right, nodes["operating_income"].y,
                nodes["pretax_income"].x, nodes["pretax_income"].y,
                width_value(operating), GREEN_FLOW,
            )
        )
        ribbons.append(
            Ribbon(
                "nonoperating_income_expense", "pretax_income",
                nodes["nonoperating_income_expense"].right,
                nodes["nonoperating_income_expense"].y,
                nodes["pretax_income"].x,
                nodes["pretax_income"].y + width_value(operating),
                width_value(nonoperating), GREEN_FLOW,
            )
        )
    elif operating_is_income and pretax_is_income:
        ribbons.append(
            Ribbon(
                "operating_income", "pretax_income",
                nodes["operating_income"].right, nodes["operating_income"].y,
                nodes["pretax_income"].x, nodes["pretax_income"].y,
                width_value(pretax), GREEN_FLOW,
            )
        )
        ribbons.append(
            Ribbon(
                "operating_income", "nonoperating_income_expense",
                nodes["operating_income"].right,
                nodes["operating_income"].y + width_value(pretax),
                nodes["nonoperating_income_expense"].x,
                nodes["nonoperating_income_expense"].y,
                width_value(nonoperating), PINK_FLOW,
            )
        )
    elif operating_is_income and not pretax_is_income:
        ribbons.append(
            Ribbon(
                "operating_income", "nonoperating_income_expense",
                nodes["operating_income"].right, nodes["operating_income"].y,
                nodes["nonoperating_income_expense"].x,
                nodes["nonoperating_income_expense"].y,
                width_value(operating), PINK_FLOW,
            )
        )
        ribbons.append(
            Ribbon(
                "nonoperating_income_expense", "pretax_income",
                nodes["nonoperating_income_expense"].right,
                nodes["nonoperating_income_expense"].y + width_value(operating),
                nodes["pretax_income"].x, nodes["pretax_income"].y,
                width_value(pretax), PINK_FLOW,
            )
        )
    else:
        # An operating loss can be offset by non-operating income.
        ribbons.append(
            Ribbon(
                "nonoperating_income_expense", "operating_income",
                nodes["nonoperating_income_expense"].right,
                nodes["nonoperating_income_expense"].y,
                nodes["operating_income"].x, nodes["operating_income"].y,
                width_value(operating), PINK_FLOW,
            )
        )
        if pretax_is_income:
            ribbons.append(
                Ribbon(
                    "nonoperating_income_expense", "pretax_income",
                    nodes["nonoperating_income_expense"].right,
                    nodes["nonoperating_income_expense"].y + width_value(operating),
                    nodes["pretax_income"].x, nodes["pretax_income"].y,
                    width_value(pretax), GREEN_FLOW,
                )
            )

    if net_is_income:
        source_values = {
            key: value for key, value in post_tax_contributions.items() if value >= 0
        }
        target_values = {
            key: -value for key, value in post_tax_contributions.items() if value < 0
        }
    else:
        source_values = {
            key: -value for key, value in post_tax_contributions.items() if value < 0
        }
        target_values = {
            key: value for key, value in post_tax_contributions.items() if value >= 0
        }
    target_values["net_income"] = abs(net)
    ribbons.extend(
        _packed_flows(
            nodes,
            source_values,
            target_values,
            "net_income",
            width_value,
            income_target=net_is_income,
        )
    )
    return list(nodes.values()), ribbons


def build_checks(f: dict, tolerance_millions: int, check) -> list:
    return [
        check(
            "product revenue equals total revenue",
            f["revenue"].value_millions,
            sum(f[key].value_millions for key in REVENUE_KEYS),
            tolerance_millions,
        ),
        check(
            "revenue less cost of revenues equals gross profit",
            f["gross_profit"].value_millions,
            f["revenue"].value_millions - f["cost_of_revenue"].value_millions,
            tolerance_millions,
        ),
        check(
            "operating expense components equal operating expenses",
            f["operating_expenses"].value_millions,
            sum(f[key].value_millions for key in EXPENSE_KEYS),
            tolerance_millions,
        ),
        check(
            "gross profit less operating expenses equals operating income",
            f["operating_income"].value_millions,
            f["gross_profit"].value_millions - f["operating_expenses"].value_millions,
            tolerance_millions,
        ),
        check(
            "operating plus non-operating equals pre-tax income",
            f["pretax_income"].value_millions,
            f["operating_income"].value_millions
            + f["nonoperating_income_expense"].value_millions,
            tolerance_millions,
        ),
        check(
            "pre-tax less income tax equals net income",
            f["net_income"].value_millions,
            f["pretax_income"].value_millions - f["income_tax"].value_millions,
            tolerance_millions,
        ),
    ]


register(
    CompanyAdapter(
        ticker="SHOP",
        slug="shopify",
        config_filename="shopify.json",
        layout=layout,
        label_keys=LABEL_KEYS,
        build_checks=build_checks,
        large_label_fonts=False,
    )
)
