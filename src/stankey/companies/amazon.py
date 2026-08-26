"""Amazon (AMZN) adapter: many operating-cost lines, equity-method activity,
and sign-aware profit/loss flows."""

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
    h_of,
)
from . import CompanyAdapter, register


LABEL_KEYS = (
    "north_america_revenue",
    "international_revenue",
    "aws_revenue",
    "revenue",
    "gross_profit",
    "cost_of_revenue",
    "operating_income",
    "fulfillment",
    "technology_infrastructure",
    "marketing",
    "general_and_administrative",
    "other_operating_expense",
    "pretax_income",
    "nonoperating_income_expense",
    "income_tax",
    "equity_method_investment",
    "net_income",
)


def layout(quarter: Quarter) -> Tuple[List[Node], List[Ribbon]]:
    f = quarter.facts
    scale = 0.8 / 1000.0
    h = lambda key: max(1.2, abs(f[key].value_millions) * scale)
    expense_keys = (
        "fulfillment",
        "technology_infrastructure",
        "marketing",
        "general_and_administrative",
        "other_operating_expense",
    )
    if f["operating_income"].value_millions < 0:
        raise ValueError("Amazon layout does not yet support operating losses")

    nonoperating_is_income = f["nonoperating_income_expense"].value_millions >= 0
    pretax_is_income = f["pretax_income"].value_millions >= 0
    net_is_income = f["net_income"].value_millions >= 0
    tax_contribution = -f["income_tax"].value_millions
    equity_contribution = f["equity_method_investment"].value_millions
    post_tax_contributions = {
        "pretax_income": f["pretax_income"].value_millions,
        "income_tax": tax_contribution,
        "equity_method_investment": equity_contribution,
    }
    post_tax_sources = (
        {key for key, value in post_tax_contributions.items() if value >= 0}
        if net_is_income
        else {key for key, value in post_tax_contributions.items() if value < 0}
    )

    nodes = {
        "north_america_revenue": Node("north_america_revenue", 210, 340, h("north_america_revenue"), BLUE),
        "international_revenue": Node("international_revenue", 210, 535, h("international_revenue"), BLUE),
        "aws_revenue": Node("aws_revenue", 210, 625, h("aws_revenue"), BLUE),
        "revenue": Node("revenue", 289, 340, h("revenue"), BLUE),
        "gross_profit": Node("gross_profit", 479, 340, h("gross_profit"), GREEN),
        "cost_of_revenue": Node("cost_of_revenue", 479, 525, h("cost_of_revenue"), PINK),
        "operating_income": Node("operating_income", 663, 340, h("operating_income"), GREEN),
        "fulfillment": Node("fulfillment", 663, 515, h("fulfillment"), PINK),
        "technology_infrastructure": Node("technology_infrastructure", 663, 590, h("technology_infrastructure"), PINK),
        "marketing": Node("marketing", 663, 665, h("marketing"), PINK),
        "general_and_administrative": Node("general_and_administrative", 663, 735, h("general_and_administrative"), PINK),
        "other_operating_expense": Node(
            "other_operating_expense",
            609 if f["other_operating_expense"].value_millions < 0 else 663,
            800,
            h("other_operating_expense"),
            GREEN if f["other_operating_expense"].value_millions < 0 else PINK,
        ),
        "pretax_income": Node("pretax_income", 851, 340, h("pretax_income"), GREEN if pretax_is_income else PINK),
        "nonoperating_income_expense": Node(
            "nonoperating_income_expense",
            797 if nonoperating_is_income else 851,
            430,
            h("nonoperating_income_expense"),
            GREEN if nonoperating_is_income else PINK,
        ),
        "income_tax": Node(
            "income_tax",
            744 if "income_tax" in post_tax_sources else 851,
            445 if "income_tax" in post_tax_sources else 535,
            h("income_tax"),
            GREEN if tax_contribution >= 0 else PINK,
        ),
        "equity_method_investment": Node(
            "equity_method_investment",
            744 if "equity_method_investment" in post_tax_sources else 806,
            870,
            h("equity_method_investment"),
            GREEN if equity_contribution >= 0 else PINK,
        ),
        "net_income": Node("net_income", 873, 340, h("net_income"), GREEN if net_is_income else PINK),
    }

    def width_value(value: int) -> float:
        return max(1.2, abs(value) * scale)

    def width(key: str) -> float:
        return width_value(f[key].value_millions)

    ribbons: List[Ribbon] = []
    target_y = nodes["revenue"].y
    for key in ("north_america_revenue", "international_revenue", "aws_revenue"):
        ribbons.append(Ribbon(key, "revenue", nodes[key].right, nodes[key].y, nodes["revenue"].x, target_y, width(key), BLUE_FLOW))
        target_y += width(key)

    ribbons.append(Ribbon("revenue", "gross_profit", nodes["revenue"].right, nodes["revenue"].y, nodes["gross_profit"].x, nodes["gross_profit"].y, width("gross_profit"), GREEN_FLOW))
    ribbons.append(Ribbon("revenue", "cost_of_revenue", nodes["revenue"].right, nodes["revenue"].y + width("gross_profit"), nodes["cost_of_revenue"].x, nodes["cost_of_revenue"].y, width("cost_of_revenue"), PINK_FLOW))

    operating_sources = {"gross_profit": f["gross_profit"].value_millions}
    operating_targets = {"operating_income": f["operating_income"].value_millions}
    for key in expense_keys:
        value = f[key].value_millions
        if value < 0:
            operating_sources[key] = -value
        else:
            operating_targets[key] = value
    operating_source_offsets = {key: 0.0 for key in operating_sources}
    operating_target_offsets = {key: 0.0 for key in operating_targets}
    operating_remaining = dict(operating_sources)
    operating_source_keys = list(operating_sources)
    operating_source_index = 0
    for target_key, target_value in operating_targets.items():
        remaining = target_value
        while remaining > 0:
            source_key = operating_source_keys[operating_source_index]
            amount = min(operating_remaining[source_key], remaining)
            ribbon_width = width_value(amount)
            ribbons.append(
                Ribbon(
                    source_key,
                    target_key,
                    nodes[source_key].right,
                    nodes[source_key].y + operating_source_offsets[source_key],
                    nodes[target_key].x,
                    nodes[target_key].y + operating_target_offsets[target_key],
                    ribbon_width,
                    GREEN_FLOW if target_key == "operating_income" else PINK_FLOW,
                )
            )
            operating_source_offsets[source_key] += ribbon_width
            operating_target_offsets[target_key] += ribbon_width
            operating_remaining[source_key] -= amount
            remaining -= amount
            if operating_remaining[source_key] == 0:
                operating_source_index += 1

    operating = f["operating_income"].value_millions
    nonoperating = f["nonoperating_income_expense"].value_millions
    pretax = f["pretax_income"].value_millions
    if nonoperating >= 0:
        ribbons.append(Ribbon("operating_income", "pretax_income", nodes["operating_income"].right, nodes["operating_income"].y, nodes["pretax_income"].x, nodes["pretax_income"].y, width_value(operating), GREEN_FLOW))
        ribbons.append(Ribbon("nonoperating_income_expense", "pretax_income", nodes["nonoperating_income_expense"].right, nodes["nonoperating_income_expense"].y, nodes["pretax_income"].x, nodes["pretax_income"].y + width_value(operating), width_value(nonoperating), GREEN_FLOW))
    elif pretax >= 0:
        ribbons.append(Ribbon("operating_income", "pretax_income", nodes["operating_income"].right, nodes["operating_income"].y, nodes["pretax_income"].x, nodes["pretax_income"].y, width_value(pretax), GREEN_FLOW))
        ribbons.append(Ribbon("operating_income", "nonoperating_income_expense", nodes["operating_income"].right, nodes["operating_income"].y + width_value(pretax), nodes["nonoperating_income_expense"].x, nodes["nonoperating_income_expense"].y, width_value(nonoperating), PINK_FLOW))
    else:
        ribbons.append(Ribbon("operating_income", "nonoperating_income_expense", nodes["operating_income"].right, nodes["operating_income"].y, nodes["nonoperating_income_expense"].x, nodes["nonoperating_income_expense"].y, width_value(operating), PINK_FLOW))
        ribbons.append(Ribbon("nonoperating_income_expense", "pretax_income", nodes["nonoperating_income_expense"].right, nodes["nonoperating_income_expense"].y + width_value(operating), nodes["pretax_income"].x, nodes["pretax_income"].y, width_value(pretax), PINK_FLOW))

    # Balance P - tax + equity-method activity = net income. Recasting the
    # equation by sign keeps loss quarters and tax benefits as honest flows.
    if net_is_income:
        source_values = {key: value for key, value in post_tax_contributions.items() if value >= 0}
        target_values = {key: -value for key, value in post_tax_contributions.items() if value < 0}
    else:
        source_values = {key: -value for key, value in post_tax_contributions.items() if value < 0}
        target_values = {key: value for key, value in post_tax_contributions.items() if value >= 0}
    target_values["net_income"] = abs(f["net_income"].value_millions)
    source_offsets = {key: 0.0 for key in source_values}
    target_offsets = {key: 0.0 for key in target_values}
    source_remaining = dict(source_values)
    source_keys = list(source_values)
    source_index = 0
    for target_key, target_value in target_values.items():
        remaining = target_value
        while remaining > 0:
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
                    GREEN_FLOW if target_key == "net_income" and net_is_income else PINK_FLOW,
                )
            )
            source_offsets[source_key] += ribbon_width
            target_offsets[target_key] += ribbon_width
            source_remaining[source_key] -= amount
            remaining -= amount
            if source_remaining[source_key] == 0:
                source_index += 1
    return list(nodes.values()), ribbons


def build_checks(f: dict, tolerance_millions: int, check) -> list:
    return [
        check(
            "segment revenue equals consolidated revenue",
            f["revenue"].value_millions,
            f["north_america_revenue"].value_millions
            + f["international_revenue"].value_millions
            + f["aws_revenue"].value_millions,
            tolerance_millions,
        ),
        check(
            "revenue less cost of sales equals gross profit",
            f["gross_profit"].value_millions,
            f["revenue"].value_millions - f["cost_of_revenue"].value_millions,
            tolerance_millions,
        ),
        check(
            "gross profit less operating expenses equals operating income",
            f["operating_income"].value_millions,
            f["gross_profit"].value_millions
            - f["fulfillment"].value_millions
            - f["technology_infrastructure"].value_millions
            - f["marketing"].value_millions
            - f["general_and_administrative"].value_millions
            - f["other_operating_expense"].value_millions,
            tolerance_millions,
        ),
        check(
            "expense components equal total costs and expenses",
            f["costs_and_expenses"].value_millions,
            f["cost_of_revenue"].value_millions
            + f["fulfillment"].value_millions
            + f["technology_infrastructure"].value_millions
            + f["marketing"].value_millions
            + f["general_and_administrative"].value_millions
            + f["other_operating_expense"].value_millions,
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
            "pre-tax less income tax plus equity-method activity equals net income",
            f["net_income"].value_millions,
            f["pretax_income"].value_millions
            - f["income_tax"].value_millions
            + f["equity_method_investment"].value_millions,
            tolerance_millions,
        ),
    ]


register(
    CompanyAdapter(
        ticker="AMZN",
        slug="amazon",
        config_filename="amazon.json",
        layout=layout,
        label_keys=LABEL_KEYS,
        build_checks=build_checks,
    )
)
