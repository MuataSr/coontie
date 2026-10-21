"""DH5058: the inventory list a new MMTC submits with its integration plan.

Form DH5058-OMMU-1/2024, "Usable Product and Marijuana Delivery Device Inventory and
Unique Product ID", incorporated in Rule 64-4.221(5)(a). The form is explicit: submit
an .xlsx or .csv carrying **only** the columns below, one row per product type.

Source (fetched 2026-10-21):
https://knowthefactsmmj.com/wp-content/uploads/2026/01/
64ER24-1-MMTC-Usable-Product-and-Marijuana-Delivery-Device-Inventory-and-Unique-Product-ID.pdf

The enumerations are transcribed from the form, including its own spelling. Do not
"clean them up": the department reads these strings.
"""

from __future__ import annotations

import csv
import io
from datetime import date
from decimal import Decimal

FORM_ID = "DH5058-OMMU-1/2024"
SUBMIT_TO = "ommu_seedtosale@flhealth.gov"

# The exact column order on the form's "Inventory List: Required Information" page.
COLUMNS = (
    "MMTC Name",
    "Product Type",
    "Route of Administration",
    "Marijuana Delivery Device",
    "Product Name",
    "Product Brand",
    "Unique Product ID",
    "Tetrahydrocannabinol (THC) Weight",
    "Cannabidiol (CBD) Weight",
    "Product Weight",
    "Product Formulation",
    "Cultivar or Strain Name",
    "Flavor Name",
    "Approval Date",
    "Reference Number",
)

PRODUCT_TYPES = (
    "Capsule/Tablet",
    "Concentrate",
    "Vape",
    "Tincture",
    "Topical",
    "Suppository",
    "Whole Flower",
    "Ground Whole Flower",
    "Gelatin",
    "Chocolate",
    "Lozenge",
    "Pre-rolled marijuana cigarette",
    "Baked Good",
    "Drink Powder",
    "Marijuana Delivery Device",
)

ROUTES = (
    "Edible",
    "Inhalation",
    "Oral",
    "Sublingual",
    "Suppository",
    "Topical",
    "Smoking",
)

# Loose input, canonical output. Incumbents spell things their own way; the form does not
# accept their spelling. Order matters: the first match wins.
_PRODUCT_ALIASES = {
    "capsule": "Capsule/Tablet",
    "tablet": "Capsule/Tablet",
    "pill": "Capsule/Tablet",
    "concentrate": "Concentrate",
    "extract": "Concentrate",
    "live resin": "Concentrate",
    "rosin": "Concentrate",
    "vape": "Vape",
    "cartridge": "Vape",
    "cart": "Vape",
    "disposable": "Vape",
    "tincture": "Tincture",
    "drops": "Tincture",
    "topical": "Topical",
    "cream": "Topical",
    "lotion": "Topical",
    "salve": "Topical",
    "suppository": "Suppository",
    "flower": "Whole Flower",
    "whole flower": "Whole Flower",
    "ground": "Ground Whole Flower",
    "ground flower": "Ground Whole Flower",
    "ground whole flower": "Ground Whole Flower",
    "gummy": "Gelatin",
    "gummies": "Gelatin",
    "gelatin": "Gelatin",
    "chocolate": "Chocolate",
    "lozenge": "Lozenge",
    "mint": "Lozenge",
    "preroll": "Pre-rolled marijuana cigarette",
    "pre-roll": "Pre-rolled marijuana cigarette",
    "pre rolled": "Pre-rolled marijuana cigarette",
    "joint": "Pre-rolled marijuana cigarette",
    "baked good": "Baked Good",
    "cookie": "Baked Good",
    "brownie": "Baked Good",
    "drink powder": "Drink Powder",
    "device": "Marijuana Delivery Device",
    "delivery device": "Marijuana Delivery Device",
    "hardware": "Marijuana Delivery Device",
}

_ROUTE_ALIASES = {
    "edible": "Edible",
    "eat": "Edible",
    "inhalation": "Inhalation",
    "inhale": "Inhalation",
    "inhaled": "Inhalation",
    "vapor": "Inhalation",
    "oral": "Oral",
    "sublingual": "Sublingual",
    "under tongue": "Sublingual",
    "suppository": "Suppository",
    "rectal": "Suppository",
    "topical": "Topical",
    "smoking": "Smoking",
    "smoke": "Smoking",
    "combustion": "Smoking",
}


def canon_product_type(raw: str) -> str:
    key = (raw or "").strip().lower()
    if key in _PRODUCT_ALIASES:
        return _PRODUCT_ALIASES[key]
    for alias, value in _PRODUCT_ALIASES.items():
        if alias in key:
            return value
    raise ValueError(f"unrecognised product type {raw!r}; the form accepts: {', '.join(PRODUCT_TYPES)}")


def canon_route(raw: str) -> str:
    key = (raw or "").strip().lower()
    if key in _ROUTE_ALIASES:
        return _ROUTE_ALIASES[key]
    for alias, value in _ROUTE_ALIASES.items():
        if alias in key:
            return value
    raise ValueError(f"unrecognised route {raw!r}; the form accepts: {', '.join(ROUTES)}")


def _num(value) -> str:
    """Print numbers the way a spreadsheet reader expects: no trailing zeros, no 'None'."""
    if value is None or value == "":
        return ""
    d = Decimal(str(value))
    if d == d.to_integral_value():
        return str(int(d))
    return format(d.normalize(), "f")


def _date(value) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, date):
        return value.isoformat()
    return str(value)[:10]


def row_for(product, mmtc_name: str) -> dict:
    """One DH5058 row from a product record. Extra fields on the product are ignored."""
    return {
        "MMTC Name": mmtc_name,
        "Product Type": product.product_type,
        "Route of Administration": product.route,
        "Marijuana Delivery Device": "Yes" if product.is_delivery_device else "No",
        "Product Name": product.name,
        "Product Brand": product.brand or "",
        "Unique Product ID": product.upid,
        "Tetrahydrocannabinol (THC) Weight": _num(product.thc_mg),
        "Cannabidiol (CBD) Weight": _num(product.cbd_mg),
        "Product Weight": _num(product.weight_g),
        "Product Formulation": product.formulation or "",
        "Cultivar or Strain Name": product.cultivar or "",
        "Flavor Name": product.flavor or "",
        "Approval Date": _date(product.approval_date),
        "Reference Number": product.reference_number or "",
    }


def render_csv(products, mmtc_name: str) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=COLUMNS, extrasaction="raise", lineterminator="\n")
    writer.writeheader()
    for p in sorted(products, key=lambda p: (p.product_type, p.name, p.upid)):
        writer.writerow(row_for(p, mmtc_name))
    return buf.getvalue()
