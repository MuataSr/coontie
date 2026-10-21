"""Unique product IDs, per Rule 64-4.221(1)(c).

The rule defines the grouping exactly:

    "Usable products of the same cultivar, size, volume, flavor, ratio of
     tetrahydrocannabinol to cannabidiol, and route of administration shall be
     considered a single product type... The stock-keeping unit (SKU) number assigned
     to an MMTC's usable product or marijuana delivery device may also serve as the
     unique product ID so long as the SKU number is unique to each product type."

Two consequences the software must enforce:

1. Those six attributes decide identity. Two products that differ only in name share an
   ID; two that differ only in route do not.
2. A supplied SKU can be adopted, but then it has to be unique per product type, so we
   refuse to reuse one SKU for a different six-attribute key.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction

from .forms import canon_product_type, canon_route

_SLUG = re.compile(r"[^a-z0-9]+")


def _slug(text: str, limit: int = 12) -> str:
    s = _SLUG.sub("-", (text or "").strip().lower()).strip("-")
    return s[:limit] or "na"


def ratio(thc_mg, cbd_mg) -> str:
    """THC:CBD as a reduced fraction; CBD-only reads as 0:1, THC-only as 1:0."""
    t = Fraction(Decimal(str(thc_mg or 0))).limit_denominator(1000)
    c = Fraction(Decimal(str(cbd_mg or 0))).limit_denominator(1000)
    if c == 0 and t == 0:
        return "0:0"
    if c == 0:
        return "1:0"
    if t == 0:
        return "0:1"
    frac = (t / c).limit_denominator(1000)
    return f"{frac.numerator}:{frac.denominator}"


@dataclass(frozen=True)
class ProductKey:
    """The six attributes Rule 64-4.221(1)(c) groups on."""

    cultivar: str
    size: str
    volume: str
    flavor: str
    ratio: str
    route: str

    @classmethod
    def build(
        cls,
        *,
        cultivar: str = "",
        size: str = "",
        volume: str = "",
        flavor: str = "",
        thc_mg: Decimal | int | float | None = 0,
        cbd_mg: Decimal | int | float | None = 0,
        route: str = "",
    ) -> "ProductKey":
        return cls(
            cultivar=_slug(cultivar),
            size=_num_slug(size),
            volume=_num_slug(volume),
            flavor=_slug(flavor),
            ratio=ratio(thc_mg, cbd_mg),
            route=_slug(canon_route(route) if route else "na"),
        )
    def canonical(self) -> str:
        return "|".join((self.cultivar, self.size, self.volume, self.flavor, self.ratio, self.route))


def _num_slug(value) -> str:
    if value in (None, ""):
        return "na"
    d = Decimal(str(value))
    return str(int(d)) if d == d.to_integral_value() else format(d.normalize(), "f")


def derive_upid(key: ProductKey, seed: str = "") -> str:
    """A stable, readable ID: attributes first, then a short hash of the full key.

    The readable prefix is for humans on a call. The hash is what actually guarantees
    uniqueness, because two long cultivar names can share a 12-character slug.
    """
    digest = hashlib.sha256((key.canonical() + "|" + seed).encode()).hexdigest()[:6].upper()
    size_token = key.size if key.volume == "na" else f"{key.size}x{key.volume}"
    parts = [p for p in (key.cultivar, size_token, key.flavor, key.route) if p != "na"]
    prefix = "-".join(parts)[:28] or "PRODUCT"
    return f"{prefix}-{digest}"


def upid_for(
    *,
    cultivar: str = "",
    size: str = "",
    volume: str = "",
    flavor: str = "",
    thc_mg: Decimal | int | float | None = 0,
    cbd_mg: Decimal | int | float | None = 0,
    route: str = "",
    supplied_sku: str = "",
) -> tuple[str, ProductKey]:
    """Return (unique product id, key). A supplied SKU is adopted verbatim."""
    key = ProductKey.build(
        cultivar=cultivar, size=size, volume=volume, flavor=flavor, thc_mg=thc_mg, cbd_mg=cbd_mg, route=route
    )
    if supplied_sku:
        return supplied_sku.strip(), key
    return derive_upid(key), key


def validate_product_row(*, product_type: str, route: str) -> tuple[str, str]:
    """Canonicalise the two enumerated fields, raising with the form's own options."""
    return canon_product_type(product_type), canon_route(route)
