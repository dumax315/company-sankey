"""Per-company adapters.

Each company that the generator supports contributes a :class:`CompanyAdapter`
describing everything that varies between companies: the Sankey layout, the
label-card ordering, the font-size preference, the reconciliation identities,
the config file location, and any filing-specific quirks the CLI must apply.

The core modules (``render``, ``validate``, ``cli``) are generic and dispatch to
the registered adapter for a ticker. Adding a company therefore means adding one
module under this package and registering an adapter — the important core files
no longer grow per company.

To add a company:

1. Create ``companies/<slug>.py`` that builds a :class:`CompanyAdapter` and calls
   :func:`register` at import time.
2. Add the module to :data:`_ADAPTER_MODULES` below so it is imported (and thus
   self-registers) when the package loads.

See ``ADDING_COMPANIES_GUIDE.md`` for the full walkthrough.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Sequence, Tuple

if TYPE_CHECKING:  # Avoid import cycles at runtime; only needed for type hints.
    from ..models import Quarter
    from ..render import Node, Ribbon
    from ..validate import Check


# A layout takes a Quarter and returns the drawable nodes and ribbons.
LayoutFn = Callable[["Quarter"], Tuple[List["Node"], List["Ribbon"]]]

# A check factory receives the quarter's facts, the tolerance, and the shared
# ``_check`` helper, and returns the ordered list of reconciliation checks.
CheckFn = Callable[[dict, int, Callable[..., "Check"]], List["Check"]]


@dataclass(frozen=True)
class CompanyAdapter:
    """Everything the generic pipeline needs to know about one company."""

    ticker: str
    slug: str
    config_filename: str
    layout: LayoutFn
    label_keys: Tuple[str, ...]
    build_checks: CheckFn
    # Larger label cards (18/16pt) are the default. Set this False for the
    # smaller 16/14pt cards.
    large_label_fonts: bool = True
    # Keys whose left-side terminal label should sit below rather than beside
    # the node (e.g. Meta's Reality Labs revenue).
    below_terminals: Tuple[str, ...] = ()
    # Optional CLI quirks (Meta-style recast / Q4 derivation specials).
    quirks: "CompanyQuirks | None" = None


@dataclass(frozen=True)
class CompanyQuirks:
    """Filing-specific hooks the CLI honours for a company.

    Most companies need none of these. Meta needs them because a couple of its
    early quarters were recast in later filings.
    """

    # Selector keys allowed to be missing in the prior period for early quarters.
    historical_revenue_breakdowns: Tuple[str, ...] = ()
    # Given a Q4 key, return the nine-month "current" key to subtract. Return
    # None to use the default ``{year}Q3``.
    q4_nine_month_current_key: Optional[Callable[[str], Optional[str]]] = None
    # Given a quarter key, return a recast spec or None. The spec tells the CLI
    # to re-fetch a later filing and re-normalize with a subsequent recast.
    recast: Optional[Callable[[str], "Optional[RecastSpec]"]] = None


@dataclass(frozen=True)
class RecastSpec:
    """Instructs the CLI to normalize a quarter using a later recast filing."""

    recast_quarter_key: str
    input_mode: str


_REGISTRY: Dict[str, CompanyAdapter] = {}

# Company modules imported (and thus self-registered) when this package loads.
_ADAPTER_MODULES: Tuple[str, ...] = (
    "meta",
    "amazon",
    "alphabet",
    "jpm",
    "exxon",
    "micron",
    "palantir",
)


def register(adapter: CompanyAdapter) -> None:
    """Register a company adapter under its (upper-cased) ticker."""
    _REGISTRY[adapter.ticker.upper()] = adapter


def get_adapter(ticker: str) -> CompanyAdapter:
    _ensure_loaded()
    try:
        return _REGISTRY[ticker.upper()]
    except KeyError as exc:
        raise ValueError(f"Unsupported ticker: {ticker.upper()}") from exc


def has_adapter(ticker: str) -> bool:
    _ensure_loaded()
    return ticker.upper() in _REGISTRY


def all_adapters() -> Dict[str, CompanyAdapter]:
    _ensure_loaded()
    return dict(_REGISTRY)


_loaded = False


def _ensure_loaded() -> None:
    global _loaded
    if _loaded:
        return
    # Import each company module so its module-level register() call runs. This
    # is done lazily so importing this package does not eagerly pull in
    # ``render`` (which imports this package) before its primitives exist.
    #
    # A module may be listed here before its file exists (e.g. while another
    # contributor is still adding it). Tolerate only that specific case — a
    # missing top-level company module — and re-raise every other import error
    # (including a ModuleNotFoundError raised from *within* a module that does
    # exist) so genuine bugs are not masked.
    for name in _ADAPTER_MODULES:
        try:
            import_module(f"{__name__}.{name}")
        except ModuleNotFoundError as exc:
            if exc.name == f"{__name__}.{name}":
                continue
            raise
    _loaded = True
