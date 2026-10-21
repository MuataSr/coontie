"""The DH5059 event catalog: the wire contract for a Florida MMTC internal STS.

Every record in this module is transcribed from Form DH5059-OMMU-05/2026,
"MMTC Seed-to-Sale Required Data Collection Document" (Eff. 05/26), incorporated
by reference in Rule 64-4.222(3), F.A.C.

Source of the field list: the incorporated document served at
https://flrules.org/gateway/reference.asp?No=Ref-19592 (Final RTF), retrieved
2026-10-21. Do not edit field names without re-reading the form: the department
checks the payload against the timeframes and fields stated there.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Stage(str, Enum):
    CULTIVATION = "cultivation"
    PROCESSING = "processing"
    DISPENSING = "dispensing"
    LOCATION = "location"
    WASTE = "waste"
    TRANSFER = "transfer"
    TRANSPORT = "transport"
    ADMIN = "admin"


class Timing(str, Enum):
    """How fast the department must receive the record (DH5059 preamble)."""

    DEFAULT_12H = "12h"
    REALTIME = "realtime"


@dataclass(frozen=True)
class FieldSpec:
    name: str
    required: bool = True
    note: str = ""


@dataclass(frozen=True)
class EventSpec:
    key: str
    title: str
    stage: Stage
    fields: tuple[FieldSpec, ...]
    timing: Timing = Timing.DEFAULT_12H
    wait_hours_before_next: int = 0
    citation: str = "DH5059-OMMU-05/2026"
    notes: str = ""

    @property
    def field_names(self) -> tuple[str, ...]:
        return tuple(f.name for f in self.fields)

    @property
    def required_names(self) -> tuple[str, ...]:
        return tuple(f.name for f in self.fields if f.required)


def _f(name: str, required: bool = True, note: str = "") -> FieldSpec:
    return FieldSpec(name=name, required=required, note=note)


# Cultivation Tracking Requirements -------------------------------------------------

SEED_CLONE_BATCH = EventSpec(
    key="seed_clone_batch",
    title="Enter Marijuana Clones and Seeds as New Inventory",
    stage=Stage.CULTIVATION,
    fields=(
        _f("facility_location"),
        _f("room"),
        _f("cultivar"),
        _f("count", note="number of seeds or clones in the batch"),
        _f("mother_plant_id", required=False, note="if applicable"),
    ),
    notes="Tracked as inventory until the seed or clone becomes an immature plant.",
)

IMMATURE_PLANT = EventSpec(
    key="immature_plant",
    title="Marijuana Plants",
    stage=Stage.CULTIVATION,
    fields=(
        _f("facility_location"),
        _f("room"),
        _f("cultivar"),
        _f("is_mother_plant"),
        _f("planted_at", note="date and time the plant was planted"),
        _f("origin_batch_id", note="seed or clone batch the plant came from"),
    ),
    notes=(
        "Immature plant means a rooted plant in vegetation, no taller than 8 in and "
        "no wider than 8 in, in a growing container."
    ),
)

ADDITIVE_APPLICATION = EventSpec(
    key="additive_application",
    title="Application of Additives to a Plant",
    stage=Stage.CULTIVATION,
    fields=(
        _f("facility_location"),
        _f("additive_description", note="active ingredient, concentration, manufacturer lot, EPA reg where applicable"),
        _f("amount"),
        _f("unit"),
        _f("plant_ids"),
    ),
)

HARVEST_SCHEDULE = EventSpec(
    key="harvest_schedule",
    title="Scheduling Plant Harvests",
    stage=Stage.CULTIVATION,
    fields=(
        _f("facility_location"),
        _f("plant_ids"),
    ),
    notes="A harvest must be scheduled before the plants are harvested.",
)

HARVEST = EventSpec(
    key="harvest",
    title="Harvesting Plants",
    stage=Stage.CULTIVATION,
    fields=(
        _f("facility_location"),
        _f("plant_ids"),
        _f("wet_flower_weight"),
        _f("wet_flower_unit"),
        _f("waste_weight"),
        _f("waste_unit"),
        _f("other_material_weight"),
        _f("other_material_unit"),
        _f("post_harvest_room"),
    ),
    citation="DH5059-OMMU-05/2026; waste defined in Rule 64-4.207, F.A.C.",
)

# Processing Tracking Requirements --------------------------------------------------

CURE_DRY = EventSpec(
    key="cure_dry",
    title="Curing/Drying Plants",
    stage=Stage.PROCESSING,
    fields=(
        _f("facility_location"),
        _f("harvest_batch_id"),
        _f("plant_ids"),
        _f("post_cure_weight"),
        _f("post_cure_unit"),
        _f("waste_weight"),
        _f("waste_unit"),
        _f("post_cure_room"),
    ),
)

INVENTORY_LOT_CREATE = EventSpec(
    key="inventory_lot_create",
    title="Creation of New Inventory Lot",
    stage=Stage.PROCESSING,
    fields=(
        _f("weight_or_volume"),
        _f("unit"),
        _f("inventory_type", note="cured and dried flower, dried flower, wet flower, etc."),
        _f("cultivar"),
        _f("facility_location"),
        _f("room"),
        _f("harvest_batch_ids"),
    ),
)

LOT_SPLIT = EventSpec(
    key="lot_split",
    title="Splitting an Existing Inventory Lot into a Sublot",
    stage=Stage.PROCESSING,
    fields=(
        _f("source_lot_id"),
        _f("facility_location"),
        _f("new_room"),
        _f("removed_weight_or_volume"),
        _f("unit"),
    ),
)

CONVERSION = EventSpec(
    key="conversion",
    title="Conversion of Inventory through Processing",
    stage=Stage.PROCESSING,
    fields=(
        _f("source_inventory_id"),
        _f("removed_weight_or_volume"),
        _f("removed_unit"),
        _f("resulting_inventory_type", note="flower, extract, etc."),
        _f("cultivar"),
        _f("resulting_weight_or_volume"),
        _f("resulting_unit"),
        _f("waste_weight"),
        _f("waste_unit"),
        _f("facility_location"),
        _f("post_conversion_room"),
    ),
)

INGREDIENT_ADD = EventSpec(
    key="ingredient_add",
    title="Addition of Ingredients to Inventory",
    stage=Stage.PROCESSING,
    fields=(
        _f("inventory_id"),
        _f("ingredient_names"),
        _f("ingredient_amounts"),
        _f("units"),
        _f("facility_location"),
    ),
    notes="Ingredient means any substance added to inventory after extraction.",
)

INVENTORY_ADJUSTMENT = EventSpec(
    key="inventory_adjustment",
    title="Inventory Adjustments",
    stage=Stage.PROCESSING,
    fields=(
        _f("inventory_id"),
        _f("adjustment_type"),
        _f("reason"),
        _f("removed_weight_or_volume"),
        _f("unit"),
        _f("facility_location"),
        _f("cause", required=False, note="our addition: drives the 64-4.222(12) exemption test"),
    ),
    notes=(
        "Rule 64-4.222(12) separately requires a written justification to "
        "ommu_seedtosale@flhealth.gov within 12 hours for adjustments that do not "
        "result from processing, dispensation, wholesale purchase or distribution, "
        "or disposal of waste."
    ),
)

FINAL_PRODUCT = EventSpec(
    key="final_product",
    title="Final Product Inventory",
    stage=Stage.PROCESSING,
    fields=(
        _f("cultivar", required=False),
        _f("product_type", note="whole flower, vape, etc."),
        _f("unit_count", note="units assigned, for unit-based inventory"),
        _f("expiration_date", note="immutable once recorded"),
        _f("net_weight_or_volume", note="inclusive of the receptacle"),
        _f("unit"),
        _f("approved_product_name", note="department-approved product name"),
        _f("weight_per_unit", note="for unit-based final product"),
        _f("packaged_at", note="date the final product was placed in its receptacle"),
        _f("unique_product_id"),
        _f("facility_location"),
        _f("room"),
    ),
)

LAB_SAMPLE_CREATE = EventSpec(
    key="lab_sample_create",
    title="Creation of New Lab Sample",
    stage=Stage.PROCESSING,
    fields=(
        _f("is_research_and_development"),
        _f("source_ids", note="plants, harvest batch, inventory, or retail batch"),
        _f("removed_weight_or_volume"),
        _f("unit"),
        _f("cmtl_id", note="identity of the certified marijuana testing laboratory"),
        _f("facility_location"),
    ),
)

DELIVERY_DEVICE_INVENTORY = EventSpec(
    key="delivery_device_inventory",
    title="Create New Delivery Device Inventory Record",
    stage=Stage.PROCESSING,
    fields=(
        _f("unique_product_id", required=False),
        _f("inventory_type"),
        _f("unit_count"),
        _f("facility_location"),
        _f("room"),
    ),
)

# Dispensing Tracking Requirements (real time) --------------------------------------

DISPENSATION = EventSpec(
    key="dispensation",
    title="Sale/Dispensation of Final Products and Delivery Devices",
    stage=Stage.DISPENSING,
    timing=Timing.REALTIME,
    fields=(
        _f("item_id"),
        _f("sale_id", note="unique MMTC-assigned identification number for the sale"),
        _f("product_class", note="low-THC, whole flower, etc."),
        _f("unique_product_id"),
        _f("route_of_administration"),
        _f("unit_count"),
        _f("dispensing_facility_location"),
        _f("patient_mmurnumber"),
        _f("caregiver_mmurnumber", required=False),
        _f("patient_dob"),
        _f("price"),
    ),
    notes="The department STS updates the medical marijuana use registry on receipt.",
)

REFUND = EventSpec(
    key="refund",
    title="Refund the Sale/Dispensation of Final Product and Delivery Devices",
    stage=Stage.DISPENSING,
    timing=Timing.REALTIME,
    fields=(
        _f("sale_id"),
        _f("item_id"),
        _f("refund_amount"),
        _f("unit_count", note="units returned or refunded"),
        _f("dispensing_facility_location"),
        _f("disposition", note="a refund does not return the item to inventory"),
    ),
)

VOID_SALE = EventSpec(
    key="void_sale",
    title="Void the Sale/Dispensation of Usable Product / Delivery Device",
    stage=Stage.DISPENSING,
    timing=Timing.REALTIME,
    fields=(
        _f("dispensing_facility_location"),
        _f("sale_id"),
    ),
    notes="A voided sale returns the item to inventory in the department STS.",
)

# Storage Location Requirements -----------------------------------------------------

GROW_ROOM_CREATE = EventSpec(
    key="grow_room_create",
    title="Create New Grow Room",
    stage=Stage.LOCATION,
    fields=(
        _f("facility_location"),
        _f("room_name"),
        _f("room_number"),
    ),
)

PLANT_MOVE = EventSpec(
    key="plant_move",
    title="Move Plants",
    stage=Stage.LOCATION,
    fields=(
        _f("facility_location"),
        _f("plant_ids"),
        _f("to_room"),
    ),
)

INVENTORY_ROOM_CREATE = EventSpec(
    key="inventory_room_create",
    title="Create New Inventory Room",
    stage=Stage.LOCATION,
    fields=(
        _f("facility_location"),
        _f("room_name"),
        _f("room_number"),
        _f("is_quarantine"),
    ),
)

INVENTORY_MOVE = EventSpec(
    key="inventory_move",
    title="Move Inventory",
    stage=Stage.LOCATION,
    fields=(
        _f("facility_location"),
        _f("inventory_ids"),
        _f("to_room"),
    ),
)

# Waste Destruction Requirements ----------------------------------------------------

DISPOSAL_SCHEDULE_INVENTORY = EventSpec(
    key="disposal_schedule_inventory",
    title="Schedule Inventory Disposal",
    stage=Stage.WASTE,
    wait_hours_before_next=72,
    fields=(
        _f("inventory_id"),
        _f("reason"),
    ),
    notes="The MMTC must wait 72 hours after scheduling before disposing.",
)

DISPOSAL_INVENTORY = EventSpec(
    key="disposal_inventory",
    title="Dispose of Inventory",
    stage=Stage.WASTE,
    fields=(_f("inventory_id"),),
)

DISPOSAL_SCHEDULE_PLANTS = EventSpec(
    key="disposal_schedule_plants",
    title="Schedule Plant Disposal",
    stage=Stage.WASTE,
    wait_hours_before_next=72,
    fields=(
        _f("plant_ids"),
        _f("reason"),
    ),
    notes="The MMTC must wait 72 hours after scheduling before disposing.",
)

DISPOSAL_PLANTS = EventSpec(
    key="disposal_plants",
    title="Dispose of Plants",
    stage=Stage.WASTE,
    fields=(_f("plant_ids"),),
)

PLANT_MATTER_DISPOSAL = EventSpec(
    key="plant_matter_disposal",
    title="Dispose of Marijuana Plant Matter",
    stage=Stage.WASTE,
    fields=(
        _f("facility_location"),
        _f("collected_at"),
        _f("weight"),
        _f("unit"),
    ),
    notes="Post-defoliation matter where the plant ID is unknown.",
)

# Plant and Inventory Transfer Requirements (real time) ------------------------------

TRANSFER_OUT = EventSpec(
    key="transfer_out",
    title="Transfer of Plants/Inventory Between MMTC Facilities (transferring)",
    stage=Stage.TRANSFER,
    timing=Timing.REALTIME,
    fields=(
        _f("item_ids"),
        _f("manifest_id"),
        _f("unit_count", required=False),
        _f("quantity"),
        _f("unit"),
        _f("transferring_facility_location"),
    ),
)

TRANSFER_IN = EventSpec(
    key="transfer_in",
    title="Transfer of Plants/Inventory Between MMTC Facilities (receiving)",
    stage=Stage.TRANSFER,
    timing=Timing.REALTIME,
    fields=(
        _f("item_ids"),
        _f("manifest_id"),
        _f("units_received", required=False),
        _f("units_rejected", required=False),
        _f("quantity_received"),
        _f("unit_received"),
        _f("quantity_rejected", required=False),
        _f("unit_rejected", required=False),
        _f("receiving_facility_location"),
    ),
)

WHOLESALE_INVOICE = EventSpec(
    key="wholesale_invoice",
    title="Creation of New Invoice for Wholesale Transaction",
    stage=Stage.TRANSFER,
    fields=(
        _f("item_ids"),
        _f("buyer_facility_location"),
        _f("seller_facility_location"),
        _f("price"),
        _f("quantity"),
        _f("unit"),
    ),
)

# Transport ------------------------------------------------------------------------

VEHICLE_REGISTER = EventSpec(
    key="vehicle_register",
    title="Department-Approved Vehicles Used to Transport Marijuana",
    stage=Stage.TRANSPORT,
    fields=(
        _f("vin"),
        _f("license_plate"),
        _f("make"),
        _f("model"),
        _f("year"),
        _f("color"),
        _f("vehicle_name", note="name selected by the MMTC"),
    ),
)

MANIFEST = EventSpec(
    key="manifest",
    title="Transportation Manifest",
    stage=Stage.TRANSPORT,
    fields=(
        _f("driver_employee_ids"),
        _f("stops", note="order of intended stops and the location of each"),
        _f("arrival_times"),
        _f("departure_times"),
        _f("route_directions"),
        _f("item_ids"),
        _f("invoice_id", required=False, note="when the manifest documents a wholesale transfer"),
        _f("creating_facility_location"),
        _f("vehicle_id"),
    ),
    citation="DH5059-OMMU-05/2026; Rule 64-4.222(10); s. 381.986(8)(g), F.S.",
)

# MMTC Employees and Authorized API Users -------------------------------------------

EMPLOYEE_RECORD = EventSpec(
    key="employee_record",
    title="MMTC Employees",
    stage=Stage.ADMIN,
    fields=(
        _f("full_name"),
        _f("dob"),
        _f("hire_date"),
        _f("email"),
    ),
    notes="For each employee that transports marijuana.",
)

API_USER = EventSpec(
    key="api_user",
    title="Authorized API Users",
    stage=Stage.ADMIN,
    fields=(
        _f("email"),
        _f("password"),
        _f("permissions"),
    ),
    notes=(
        "Access is limited by Rule 64-4.222(5) to MMTC people, the MMTC's internal STS "
        "vendor, and the department STS vendor."
    ),
)


EVENTS: tuple[EventSpec, ...] = (
    SEED_CLONE_BATCH,
    IMMATURE_PLANT,
    ADDITIVE_APPLICATION,
    HARVEST_SCHEDULE,
    HARVEST,
    CURE_DRY,
    INVENTORY_LOT_CREATE,
    LOT_SPLIT,
    CONVERSION,
    INGREDIENT_ADD,
    INVENTORY_ADJUSTMENT,
    FINAL_PRODUCT,
    LAB_SAMPLE_CREATE,
    DELIVERY_DEVICE_INVENTORY,
    DISPENSATION,
    REFUND,
    VOID_SALE,
    GROW_ROOM_CREATE,
    PLANT_MOVE,
    INVENTORY_ROOM_CREATE,
    INVENTORY_MOVE,
    DISPOSAL_SCHEDULE_INVENTORY,
    DISPOSAL_INVENTORY,
    DISPOSAL_SCHEDULE_PLANTS,
    DISPOSAL_PLANTS,
    PLANT_MATTER_DISPOSAL,
    TRANSFER_OUT,
    TRANSFER_IN,
    WHOLESALE_INVOICE,
    VEHICLE_REGISTER,
    MANIFEST,
    EMPLOYEE_RECORD,
    API_USER,
)

BY_KEY: dict[str, EventSpec] = {e.key: e for e in EVENTS}


def events_for_stage(stage: Stage) -> tuple[EventSpec, ...]:
    return tuple(e for e in EVENTS if e.stage is stage)


def realtime_events() -> tuple[EventSpec, ...]:
    return tuple(e for e in EVENTS if e.timing is Timing.REALTIME)
