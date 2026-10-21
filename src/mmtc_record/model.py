"""Minimal domain model for a Florida MMTC's own seed-to-sale system.

Deliberately small: the entities below are the ones the DH5059 record set forces
into existence. Anything that does not appear in a DH5059 event, or in the
integration rules, is not modelled yet.

Vocabulary comes from the department, not from us:
facility, room, cultivar, seed/clone batch, plant, harvest batch, inventory lot,
sublot, final product, delivery device, retail batch, manifest, vehicle, employee,
unique product ID.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import NewType

FacilityId = NewType("FacilityId", str)
RoomId = NewType("RoomId", str)
LotId = NewType("LotId", str)
PlantId = NewType("PlantId", str)
ProductId = NewType("ProductId", str)
UniqueProductId = NewType("UniqueProductId", str)


class Route(str, Enum):
    """Routes of administration. The physician approves one or more per patient."""

    INHALATION = "inhalation"
    ORAL = "oral"
    SUBLINGUAL = "sublingual"
    TOPICAL = "topical"
    RECTAL = "rectal"
    OTHER = "other"


class RoomKind(str, Enum):
    GROW = "grow"
    INVENTORY = "inventory"


@dataclass(frozen=True)
class Room:
    id: RoomId
    facility_id: FacilityId
    kind: RoomKind
    name: str
    number: str
    is_quarantine: bool = False

    def __post_init__(self) -> None:
        if not self.name or not self.number:
            raise ValueError("a room needs a unique name and number (Rule 64-4.222(11))")


@dataclass(frozen=True)
class Cultivar:
    name: str


@dataclass
class Batch:
    """Seeds or clones grouped into one tracked batch."""

    id: str
    cultivar: Cultivar
    count: int
    room_id: RoomId
    mother_plant_id: str | None = None

    def __post_init__(self) -> None:
        if self.count <= 0:
            raise ValueError("a seed or clone batch has a positive count")


@dataclass(frozen=True)
class Plant:
    id: PlantId
    cultivar: Cultivar
    room_id: RoomId
    is_mother: bool
    planted_at: datetime
    origin_batch_id: str


@dataclass
class Lot:
    """An inventory lot, or a sublot split from one."""

    id: LotId
    inventory_type: str
    cultivar: Cultivar
    quantity: Decimal
    unit: str
    room_id: RoomId
    source_lot_id: LotId | None = None
    harvest_batch_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError("an inventory lot has a positive quantity")


@dataclass(frozen=True)
class FinalProduct:
    """Final product inventory, per the DH5059 final product section.

    The expiration date is frozen at construction on purpose: the form says a
    recorded expiration date cannot be changed, so the model makes changing it a
    type-level impossibility rather than a validation someone can forget.
    """

    id: ProductId
    product_type: str
    approved_product_name: str
    unique_product_id: UniqueProductId
    net_quantity: Decimal
    unit: str
    expiration_date: datetime
    packaged_at: datetime
    room_id: RoomId
    cultivar: Cultivar | None = None
    unit_count: int | None = None

    def weight_per_unit(self) -> Decimal | None:
        if not self.unit_count:
            return None
        return self.net_quantity / Decimal(self.unit_count)


@dataclass(frozen=True)
class Dispensation:
    """One dispensation line. Recorded in real time; never edited, only voided."""

    sale_id: str
    product_id: ProductId
    unique_product_id: UniqueProductId
    product_class: str
    route: Route
    unit_count: int
    facility_id: FacilityId
    patient_mmurnumber: str
    patient_dob: datetime
    price: Decimal
    occurred_at: datetime
    caregiver_mmurnumber: str | None = None


@dataclass(frozen=True)
class Transfer:
    manifest_id: str
    item_ids: tuple[str, ...]
    quantity: Decimal
    unit: str
    from_facility: FacilityId
    to_facility: FacilityId
    occurred_at: datetime


@dataclass(frozen=True)
class Manifest:
    """A transportation manifest generated from the internal STS (PROC-11)."""

    id: str
    creating_facility: FacilityId
    vehicle_id: str
    driver_employee_ids: tuple[str, ...]
    stops: tuple[dict, ...]
    route_directions: str
    item_ids: tuple[str, ...]
    invoice_id: str | None = None

    def __post_init__(self) -> None:
        if not self.stops:
            raise ValueError("a manifest needs at least one intended stop")
        if not self.driver_employee_ids:
            raise ValueError("a manifest needs at least one driver employee ID")


@dataclass
class Adjustment:
    inventory_id: LotId
    adjustment_type: str
    reason: str
    quantity: Decimal
    unit: str
    facility_id: FacilityId
    occurred_at: datetime
    cause: str = "unexplained"
    justification_sent_at: datetime | None = None
    justification_text: str | None = None
