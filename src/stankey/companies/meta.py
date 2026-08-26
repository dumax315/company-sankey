"""Meta (META) adapter: product/segment revenue reference implementation."""

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
)
from . import (
    CompanyAdapter,
    CompanyQuirks,
    RecastSpec,
    register,
)


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

HISTORICAL_REVENUE_BREAKDOWNS = (
    "advertising_revenue",
    "other_foa_revenue",
    "family_of_apps_revenue",
    "reality_labs_revenue",
)


def layout(quarter: Quarter) -> Tuple[List[Node], List[Ribbon]]:
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


def build_checks(f: dict, tolerance_millions: int, check) -> list:
    return [
        check(
            "product revenue equals Family of Apps revenue",
            f["family_of_apps_revenue"].value_millions,
            f["advertising_revenue"].value_millions + f["other_foa_revenue"].value_millions,
            tolerance_millions,
        ),
        check(
            "segment revenue equals consolidated revenue",
            f["revenue"].value_millions,
            f["family_of_apps_revenue"].value_millions + f["reality_labs_revenue"].value_millions,
            tolerance_millions,
        ),
        check(
            "revenue less cost of revenue equals gross profit",
            f["gross_profit"].value_millions,
            f["revenue"].value_millions - f["cost_of_revenue"].value_millions,
            tolerance_millions,
        ),
        check(
            "gross profit less operating expenses equals operating income",
            f["operating_income"].value_millions,
            f["gross_profit"].value_millions
            - f["research_and_development"].value_millions
            - f["marketing_and_sales"].value_millions
            - f["general_and_administrative"].value_millions,
            tolerance_millions,
        ),
        check(
            "expense components equal total costs and expenses",
            f["costs_and_expenses"].value_millions,
            f["cost_of_revenue"].value_millions
            + f["research_and_development"].value_millions
            + f["marketing_and_sales"].value_millions
            + f["general_and_administrative"].value_millions,
            tolerance_millions,
        ),
        check(
            "operating plus non-operating equals pre-tax income",
            f["pretax_income"].value_millions,
            f["operating_income"].value_millions + f["nonoperating_income_expense"].value_millions,
            tolerance_millions,
        ),
        check(
            "pre-tax less income tax equals net income",
            f["net_income"].value_millions,
            f["pretax_income"].value_millions - f["income_tax"].value_millions,
            tolerance_millions,
        ),
    ]


def _q4_nine_month_current_key(quarter_key: str) -> str | None:
    # Meta's 2021 Q3 nine-month figures were recast in the 2022 Q3 10-Q, so the
    # 2021 Q4 derivation subtracts the recast nine-month period.
    if quarter_key == "2021Q4":
        return "2022Q3"
    return None


def _recast(quarter_key: str):
    # Meta recast its 2021 Q3 segment breakdown in the subsequent 2022 Q3 filing.
    if quarter_key == "2021Q3":
        return RecastSpec(
            recast_quarter_key="2022Q3",
            input_mode="downloaded SEC XBRL instance with subsequent-filing recast",
        )
    return None


register(
    CompanyAdapter(
        ticker="META",
        slug="meta",
        config_filename="meta.json",
        layout=layout,
        label_keys=LABEL_KEYS,
        build_checks=build_checks,
        # Meta's layout uses a 4x larger vertical scale and a tightly packed
        # top row; the 18/16pt default cards collide, so Meta keeps 16/14pt.
        large_label_fonts=False,
        below_terminals=("reality_labs_revenue",),
        quirks=CompanyQuirks(
            historical_revenue_breakdowns=HISTORICAL_REVENUE_BREAKDOWNS,
            q4_nine_month_current_key=_q4_nine_month_current_key,
            recast=_recast,
        ),
    )
)
