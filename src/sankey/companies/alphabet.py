"""Alphabet (GOOGL) adapter: optional segment disclosure and concept/dimension
drift across periods, with sign-aware flows."""

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
    "rev_search_other",
    "rev_youtube_ads",
    "rev_network",
    "rev_google_properties",
    "rev_subscriptions",
    "rev_google_other",
    "google_cloud_revenue",
    "other_bets_revenue",
    "revenue",
    "gross_profit",
    "cost_of_revenue",
    "operating_income",
    "research_and_development",
    "sales_and_marketing",
    "general_and_administrative",
    "european_commission_fine",
    "pretax_income",
    "nonoperating_income_expense",
    "income_tax",
    "net_income",
)

_ALL_SEGMENT_KEYS = (
    "google_services_revenue",
    "google_cloud_revenue",
    "other_bets_revenue",
)

# Product-level revenue leaves, in top-to-bottom display order. Alphabet's
# filed revenue detail drifts by era, so each quarter presents a different
# subset: 2019 splits Google ads into Properties + Network (no Search/YouTube,
# no Cloud line); 2020 adds Search & other, YouTube, and a Cloud product line;
# 2021 introduces reportable segments and an "Other" services line; 2022+
# replaces "Other" with Subscriptions, platforms & devices. We draw whichever
# leaves are tagged, so the revenue column always mirrors that quarter's filing.
_REVENUE_LEAF_ORDER = (
    "rev_search_other",
    "rev_youtube_ads",
    "rev_network",
    "rev_google_properties",
    "rev_subscriptions",
    "rev_google_other",
    "google_cloud_revenue",
    "other_bets_revenue",
)


def _revenue_leaf_keys(f: dict) -> list:
    """Return the present, non-overlapping revenue leaves for this quarter.

    ``rev_google_properties`` is a 2019 leaf, but in 2020 filings the same
    ``GooglePropertiesMember`` fact is a *subtotal* of Search & other + YouTube
    ads. Whenever the finer Search & other split is present we therefore drop
    Properties to avoid double-counting.

    A few filings tag the breakdown incompletely — e.g. 2019Q1 does not give
    "Google other" its own product dimension, so the tagged leaves alone do not
    add up. We only return a leaf set when it plus the hedging adjustment
    reconciles to consolidated revenue; otherwise we return no leaves so the
    chart omits the revenue column rather than showing a set that does not sum.
    """
    keys = [key for key in _REVENUE_LEAF_ORDER if key in f]
    if "rev_search_other" in keys and "rev_google_properties" in keys:
        keys.remove("rev_google_properties")
    if not keys:
        return []
    leaf_total = sum(f[key].value_millions for key in keys)
    hedging = f["hedging_revenue"].value_millions if "hedging_revenue" in f else 0
    if "revenue" in f and abs(leaf_total + hedging - f["revenue"].value_millions) > 1:
        return []
    return keys


def layout(quarter: Quarter) -> Tuple[List[Node], List[Ribbon]]:
    f = quarter.facts
    scale = 0.8 / 1000.0

    def width_value(value: float) -> float:
        return max(1.2, abs(value) * scale)

    def width(key: str) -> float:
        return width_value(f[key].value_millions)

    # Draw whichever product-level revenue leaves this quarter's filing tags, so
    # the revenue column mirrors the report. Falls back to no column when a
    # nine-month or annual instance omits the breakdown entirely.
    segment_keys = _revenue_leaf_keys(f)
    expense_keys = (
        "research_and_development",
        "sales_and_marketing",
        "general_and_administrative",
    )
    # Alphabet's one-off European Commission fine (e.g. 2019Q1) is an extra
    # operating-expense line. Alphabet tags LossContingencyLossInPeriod as 0 in
    # quarters without a fine, so draw the line only when it is actually
    # non-zero — otherwise a zero-height node and empty card would render.
    has_fine = (
        "european_commission_fine" in f
        and f["european_commission_fine"].value_millions != 0
    )
    if has_fine:
        expense_keys = expense_keys + ("european_commission_fine",)

    operating = f["operating_income"].value_millions
    nonoperating = f["nonoperating_income_expense"].value_millions
    pretax = f["pretax_income"].value_millions
    operating_is_income = operating >= 0
    nonoperating_is_income = nonoperating >= 0
    pretax_is_income = pretax >= 0
    net_is_income = f["net_income"].value_millions >= 0
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
        "revenue": Node("revenue", 300, 340, h_of(f, "revenue"), BLUE),
        "gross_profit": Node("gross_profit", 486, 340, h_of(f, "gross_profit"), GREEN),
        "cost_of_revenue": Node("cost_of_revenue", 486, 505, h_of(f, "cost_of_revenue"), PINK),
        "operating_income": Node(
            "operating_income",
            663,
            340,
            h_of(f, "operating_income"),
            GREEN if operating_is_income else PINK,
        ),
        "research_and_development": Node("research_and_development", 663, 600, h_of(f, "research_and_development"), PINK),
        "sales_and_marketing": Node("sales_and_marketing", 663, 695, h_of(f, "sales_and_marketing"), PINK),
        "general_and_administrative": Node("general_and_administrative", 663, 785, h_of(f, "general_and_administrative"), PINK),
        "pretax_income": Node("pretax_income", 851, 340, h_of(f, "pretax_income"), GREEN if pretax_is_income else PINK),
        "nonoperating_income_expense": Node(
            "nonoperating_income_expense",
            797 if nonoperating_is_income else 851,
            455,
            h_of(f, "nonoperating_income_expense"),
            GREEN if nonoperating_is_income else PINK,
        ),
        "income_tax": Node(
            "income_tax",
            744 if "income_tax" in post_tax_sources else 851,
            455 if "income_tax" in post_tax_sources else 545,
            h_of(f, "income_tax"),
            GREEN if tax_contribution >= 0 else PINK,
        ),
        "net_income": Node("net_income", 873, 340, h_of(f, "net_income"), GREEN if net_is_income else PINK),
    }
    # Optional extra operating-expense node for the European Commission fine.
    if has_fine:
        nodes["european_commission_fine"] = Node(
            "european_commission_fine", 663, 875, h_of(f, "european_commission_fine"), PINK
        )
    # Segment revenue nodes stack to the left of consolidated revenue. Left-side
    # label cards are anchored to each node's vertical centre, so we space the
    # centres by a fixed stride (larger than a label card's height) and derive
    # each node's top from its own height. This keeps cards from colliding even
    # when a leaf (Other Bets) is only a few pixels tall. The leaves extend
    # downward from the revenue node's top — matching the flow direction of the
    # rest of the diagram — rather than straddling the revenue node's centre.
    segment_stride = 72.0
    first_center = nodes["revenue"].y + h_of(f, "revenue") / 2 if len(segment_keys) <= 1 else nodes["revenue"].y + segment_stride / 2
    center_y = first_center
    for key in segment_keys:
        node_height = width(key)
        nodes[key] = Node(key, 190, center_y - node_height / 2, node_height, BLUE)
        center_y += segment_stride

    ribbons: List[Ribbon] = []
    # Segment revenue -> consolidated revenue (when segment facts are present).
    target_y = nodes["revenue"].y
    for key in segment_keys:
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

    # Consolidated revenue -> gross profit and cost of revenue.
    ribbons.append(Ribbon("revenue", "gross_profit", nodes["revenue"].right, nodes["revenue"].y, nodes["gross_profit"].x, nodes["gross_profit"].y, width("gross_profit"), GREEN_FLOW))
    ribbons.append(Ribbon("revenue", "cost_of_revenue", nodes["revenue"].right, nodes["revenue"].y + width("gross_profit"), nodes["cost_of_revenue"].x, nodes["cost_of_revenue"].y, width("cost_of_revenue"), PINK_FLOW))

    # Gross profit (and any expense credits) fund operating income and operating
    # expenses. Splitting by sign keeps expense reversals honest.
    operating_sources = {"gross_profit": f["gross_profit"].value_millions}
    operating_targets = {}
    if operating_is_income:
        operating_targets["operating_income"] = operating
    else:
        operating_sources["operating_income"] = -operating
    for key in expense_keys:
        value = f[key].value_millions
        if value < 0:
            operating_sources[key] = -value
        else:
            operating_targets[key] = value
    ribbons.extend(
        _packed_flows(nodes, operating_sources, operating_targets, "operating_income", width_value)
    )

    # Operating income + non-operating income = pre-tax income (sign-aware).
    if nonoperating_is_income and operating_is_income:
        ribbons.append(Ribbon("operating_income", "pretax_income", nodes["operating_income"].right, nodes["operating_income"].y, nodes["pretax_income"].x, nodes["pretax_income"].y, width_value(operating), GREEN_FLOW))
        ribbons.append(Ribbon("nonoperating_income_expense", "pretax_income", nodes["nonoperating_income_expense"].right, nodes["nonoperating_income_expense"].y, nodes["pretax_income"].x, nodes["pretax_income"].y + width_value(operating), width_value(nonoperating), GREEN_FLOW))
    elif operating_is_income and pretax_is_income:
        ribbons.append(Ribbon("operating_income", "pretax_income", nodes["operating_income"].right, nodes["operating_income"].y, nodes["pretax_income"].x, nodes["pretax_income"].y, width_value(pretax), GREEN_FLOW))
        ribbons.append(Ribbon("operating_income", "nonoperating_income_expense", nodes["operating_income"].right, nodes["operating_income"].y + width_value(pretax), nodes["nonoperating_income_expense"].x, nodes["nonoperating_income_expense"].y, width_value(nonoperating), PINK_FLOW))
    elif operating_is_income and not pretax_is_income:
        ribbons.append(Ribbon("operating_income", "nonoperating_income_expense", nodes["operating_income"].right, nodes["operating_income"].y, nodes["nonoperating_income_expense"].x, nodes["nonoperating_income_expense"].y, width_value(operating), PINK_FLOW))
        ribbons.append(Ribbon("nonoperating_income_expense", "pretax_income", nodes["nonoperating_income_expense"].right, nodes["nonoperating_income_expense"].y + width_value(operating), nodes["pretax_income"].x, nodes["pretax_income"].y, width_value(pretax), PINK_FLOW))
    else:
        # Operating loss: non-operating income offsets it toward pre-tax.
        ribbons.append(Ribbon("nonoperating_income_expense", "operating_income", nodes["nonoperating_income_expense"].right, nodes["nonoperating_income_expense"].y, nodes["operating_income"].x, nodes["operating_income"].y, width_value(operating), PINK_FLOW))
        if pretax_is_income:
            ribbons.append(Ribbon("nonoperating_income_expense", "pretax_income", nodes["nonoperating_income_expense"].right, nodes["nonoperating_income_expense"].y + width_value(operating), nodes["pretax_income"].x, nodes["pretax_income"].y, width_value(pretax), GREEN_FLOW))

    # Pre-tax income - income tax = net income (sign-aware, no equity-method line).
    if net_is_income:
        source_values = {key: value for key, value in post_tax_contributions.items() if value >= 0}
        target_values = {key: -value for key, value in post_tax_contributions.items() if value < 0}
    else:
        source_values = {key: -value for key, value in post_tax_contributions.items() if value < 0}
        target_values = {key: value for key, value in post_tax_contributions.items() if value >= 0}
    target_values["net_income"] = abs(f["net_income"].value_millions)
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
    checks = []
    # Alphabet booked a one-off European Commission antitrust fine as a
    # separate operating-expense line in a few quarters (e.g. 2019Q1). When
    # tagged, it is part of total costs and expenses, so fold it into the
    # operating-expense identities; otherwise it is zero.
    fine = (
        f["european_commission_fine"].value_millions
        if "european_commission_fine" in f
        else 0
    )
    # The product-level revenue leaves this quarter tags, plus the intercompany
    # hedging adjustment, reconcile to consolidated revenue. The leaf set drifts
    # by era (see _revenue_leaf_keys); nine-month and annual instances omit the
    # breakdown entirely. Check the identity only when leaves are present.
    leaf_keys = _revenue_leaf_keys(f)
    if leaf_keys:
        leaf_total = sum(f[key].value_millions for key in leaf_keys)
        hedging = f["hedging_revenue"].value_millions if "hedging_revenue" in f else 0
        checks.append(
            check(
                "revenue lines plus hedging equal consolidated revenue",
                f["revenue"].value_millions,
                leaf_total + hedging,
                tolerance_millions,
            )
        )
    checks.extend(
        [
            check(
                "revenue less cost of revenues equals gross profit",
                f["gross_profit"].value_millions,
                f["revenue"].value_millions - f["cost_of_revenue"].value_millions,
                tolerance_millions,
            ),
            check(
                "gross profit less operating expenses equals operating income",
                f["operating_income"].value_millions,
                f["gross_profit"].value_millions
                - f["research_and_development"].value_millions
                - f["sales_and_marketing"].value_millions
                - f["general_and_administrative"].value_millions
                - fine,
                tolerance_millions,
            ),
            check(
                "expense components equal total costs and expenses",
                f["costs_and_expenses"].value_millions,
                f["cost_of_revenue"].value_millions
                + f["research_and_development"].value_millions
                + f["sales_and_marketing"].value_millions
                + f["general_and_administrative"].value_millions
                + fine,
                tolerance_millions,
            ),
            check(
                "revenue less total costs and expenses equals operating income",
                f["operating_income"].value_millions,
                f["revenue"].value_millions - f["costs_and_expenses"].value_millions,
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
    )
    return checks


register(
    CompanyAdapter(
        ticker="GOOGL",
        slug="alphabet",
        config_filename="alphabet.json",
        layout=layout,
        label_keys=LABEL_KEYS,
        build_checks=build_checks,
    )
)
