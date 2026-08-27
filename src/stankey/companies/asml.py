"""ASML (ASML) adapter for its quarterly US-GAAP income statement."""

from __future__ import annotations

from typing import List, Tuple

from ..models import Quarter
from ..render import (
    BLUE,
    BLUE_FLOW,
    GREEN,
    PINK,
    Node,
    Ribbon,
    _packed_flows,
)
from . import CompanyAdapter, register


LABEL_KEYS = (
    "system_sales",
    "service_sales",
    "revenue",
    "gross_profit",
    "cost_of_revenue",
    "operating_income",
    "research_and_development",
    "selling_general_administrative",
    "nonoperating_income_expense",
    "pretax_income",
    "income_after_tax",
    "income_tax",
    "equity_method_investment",
    "net_income",
)


def layout(quarter: Quarter) -> Tuple[List[Node], List[Ribbon]]:
    f = quarter.facts
    scale = 0.052

    def width_value(value: float) -> float:
        return max(1.2, abs(value) * scale)

    def h(key: str) -> float:
        return width_value(f[key].value_millions)

    def contribution_flows(contributions: dict, result_key: str) -> List[Ribbon]:
        result = f[result_key].value_millions
        if result >= 0:
            sources = {key: value for key, value in contributions.items() if value >= 0}
            targets = {key: -value for key, value in contributions.items() if value < 0}
        else:
            sources = {key: -value for key, value in contributions.items() if value < 0}
            targets = {key: value for key, value in contributions.items() if value >= 0}
        targets[result_key] = abs(result)
        return _packed_flows(
            nodes,
            sources,
            targets,
            result_key,
            width_value,
            income_target=result >= 0,
        )

    TOP = 300.0
    GAP = 8.0
    MIN_STRIDE = 62.0

    nodes = {
        "system_sales": Node("system_sales", 150, TOP, h("system_sales"), BLUE),
        "service_sales": Node(
            "service_sales",
            150,
            TOP + h("system_sales") + GAP,
            h("service_sales"),
            BLUE,
        ),
        "revenue": Node("revenue", 300, TOP, h("revenue"), BLUE),
        "gross_profit": Node("gross_profit", 470, TOP, h("gross_profit"), GREEN),
        "cost_of_revenue": Node(
            "cost_of_revenue",
            470,
            TOP + h("gross_profit") + GAP,
            h("cost_of_revenue"),
            PINK,
        ),
        "operating_income": Node(
            "operating_income", 630, TOP, h("operating_income"), GREEN
        ),
    }
    rd_y = TOP + max(h("operating_income"), MIN_STRIDE) + GAP
    nodes["research_and_development"] = Node(
        "research_and_development", 630, rd_y, h("research_and_development"), PINK
    )
    sga_y = rd_y + max(h("research_and_development"), MIN_STRIDE) + GAP
    nodes["selling_general_administrative"] = Node(
        "selling_general_administrative",
        630,
        sga_y,
        h("selling_general_administrative"),
        PINK,
    )

    pretax_color = GREEN if f["pretax_income"].value_millions >= 0 else PINK
    nonop_color = (
        GREEN if f["nonoperating_income_expense"].value_millions >= 0 else PINK
    )
    nodes["pretax_income"] = Node(
        "pretax_income", 760, TOP, h("pretax_income"), pretax_color
    )
    nodes["nonoperating_income_expense"] = Node(
        "nonoperating_income_expense",
        700,
        max(sga_y + MIN_STRIDE + GAP, TOP + 300),
        h("nonoperating_income_expense"),
        nonop_color,
    )

    after_tax_color = GREEN if f["income_after_tax"].value_millions >= 0 else PINK
    tax_color = GREEN if f["income_tax"].value_millions < 0 else PINK
    nodes["income_after_tax"] = Node(
        "income_after_tax", 850, TOP, h("income_after_tax"), after_tax_color
    )
    nodes["income_tax"] = Node(
        "income_tax",
        850,
        TOP + max(h("income_after_tax"), MIN_STRIDE) + GAP,
        h("income_tax"),
        tax_color,
    )

    equity_color = GREEN if f["equity_method_investment"].value_millions >= 0 else PINK
    nodes["equity_method_investment"] = Node(
        "equity_method_investment",
        850,
        TOP + max(h("income_after_tax"), MIN_STRIDE) + max(h("income_tax"), MIN_STRIDE) + 2 * GAP,
        h("equity_method_investment"),
        equity_color,
    )
    net_color = GREEN if f["net_income"].value_millions >= 0 else PINK
    nodes["net_income"] = Node("net_income", 960, TOP, h("net_income"), net_color)

    ribbons: List[Ribbon] = []
    target_y = nodes["revenue"].y
    for key in ("system_sales", "service_sales"):
        ribbons.append(
            Ribbon(
                key,
                "revenue",
                nodes[key].right,
                nodes[key].y,
                nodes["revenue"].x,
                target_y,
                h(key),
                BLUE_FLOW,
            )
        )
        target_y += h(key)

    ribbons.extend(
        _packed_flows(
            nodes,
            {"revenue": f["revenue"].value_millions},
            {
                "gross_profit": f["gross_profit"].value_millions,
                "cost_of_revenue": f["cost_of_revenue"].value_millions,
            },
            "gross_profit",
            width_value,
        )
    )
    ribbons.extend(
        _packed_flows(
            nodes,
            {"gross_profit": f["gross_profit"].value_millions},
            {
                "operating_income": f["operating_income"].value_millions,
                "research_and_development": f["research_and_development"].value_millions,
                "selling_general_administrative": f[
                    "selling_general_administrative"
                ].value_millions,
            },
            "operating_income",
            width_value,
        )
    )
    ribbons.extend(
        contribution_flows(
            {
                "operating_income": f["operating_income"].value_millions,
                "nonoperating_income_expense": f[
                    "nonoperating_income_expense"
                ].value_millions,
            },
            "pretax_income",
        )
    )
    ribbons.extend(
        contribution_flows(
            {
                "pretax_income": f["pretax_income"].value_millions,
                "income_tax": -f["income_tax"].value_millions,
            },
            "income_after_tax",
        )
    )
    ribbons.extend(
        contribution_flows(
            {
                "income_after_tax": f["income_after_tax"].value_millions,
                "equity_method_investment": f[
                    "equity_method_investment"
                ].value_millions,
            },
            "net_income",
        )
    )
    return list(nodes.values()), ribbons


def build_checks(f: dict, tolerance_millions: int, check) -> list:
    return [
        check(
            "system plus service sales equal total net sales",
            f["revenue"].value_millions,
            f["system_sales"].value_millions + f["service_sales"].value_millions,
            tolerance_millions,
        ),
        check(
            "net sales less cost of sales equals gross profit",
            f["gross_profit"].value_millions,
            f["revenue"].value_millions - f["cost_of_revenue"].value_millions,
            tolerance_millions,
        ),
        check(
            "gross profit less operating expenses equals operating income",
            f["operating_income"].value_millions,
            f["gross_profit"].value_millions
            - f["research_and_development"].value_millions
            - f["selling_general_administrative"].value_millions,
            tolerance_millions,
        ),
        check(
            "operating income plus interest and other equals pre-tax income",
            f["pretax_income"].value_millions,
            f["operating_income"].value_millions
            + f["nonoperating_income_expense"].value_millions,
            tolerance_millions,
        ),
        check(
            "pre-tax income less tax equals income after tax",
            f["income_after_tax"].value_millions,
            f["pretax_income"].value_millions - f["income_tax"].value_millions,
            tolerance_millions,
        ),
        check(
            "income after tax plus equity-method profit equals net income",
            f["net_income"].value_millions,
            f["income_after_tax"].value_millions
            + f["equity_method_investment"].value_millions,
            tolerance_millions,
        ),
    ]


register(
    CompanyAdapter(
        ticker="ASML",
        slug="asml",
        config_filename="asml.json",
        layout=layout,
        label_keys=LABEL_KEYS,
        build_checks=build_checks,
        large_label_fonts=False,
    )
)
