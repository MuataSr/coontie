# DH5059 event catalog

Generated from `src/coontie/events.py`. Do not edit by hand.

Source: Form DH5059-OMMU-05/2026, "MMTC Seed-to-Sale Required Data Collection
Document" (Eff. 05/26), incorporated by reference in Rule 64-4.222(3), F.A.C.

Timing: 12 hours by default; **real time** for dispensation, refund, void and
both sides of a transfer. A `*` marks an optional field.


## Cultivation tracking

### `seed_clone_batch` - Enter Marijuana Clones and Seeds as New Inventory

Timing: 12 h. Fields: 5.

| Field | Required | Note |
|---|---|---|
| `facility_location` | yes |  |
| `room` | yes |  |
| `cultivar` | yes |  |
| `count` | yes | number of seeds or clones in the batch |
| `mother_plant_id` | no `*` | if applicable |

Note: Tracked as inventory until the seed or clone becomes an immature plant.

### `immature_plant` - Marijuana Plants

Timing: 12 h. Fields: 6.

| Field | Required | Note |
|---|---|---|
| `facility_location` | yes |  |
| `room` | yes |  |
| `cultivar` | yes |  |
| `is_mother_plant` | yes |  |
| `planted_at` | yes | date and time the plant was planted |
| `origin_batch_id` | yes | seed or clone batch the plant came from |

Note: Immature plant means a rooted plant in vegetation, no taller than 8 in and no wider than 8 in, in a growing container.

### `additive_application` - Application of Additives to a Plant

Timing: 12 h. Fields: 5.

| Field | Required | Note |
|---|---|---|
| `facility_location` | yes |  |
| `additive_description` | yes | active ingredient, concentration, manufacturer lot, EPA reg where applicable |
| `amount` | yes |  |
| `unit` | yes |  |
| `plant_ids` | yes |  |

### `harvest_schedule` - Scheduling Plant Harvests

Timing: 12 h. Fields: 2.

| Field | Required | Note |
|---|---|---|
| `facility_location` | yes |  |
| `plant_ids` | yes |  |

Note: A harvest must be scheduled before the plants are harvested.

### `harvest` - Harvesting Plants

Timing: 12 h. Fields: 9.

| Field | Required | Note |
|---|---|---|
| `facility_location` | yes |  |
| `plant_ids` | yes |  |
| `wet_flower_weight` | yes |  |
| `wet_flower_unit` | yes |  |
| `waste_weight` | yes |  |
| `waste_unit` | yes |  |
| `other_material_weight` | yes |  |
| `other_material_unit` | yes |  |
| `post_harvest_room` | yes |  |


## Processing tracking

### `cure_dry` - Curing/Drying Plants

Timing: 12 h. Fields: 8.

| Field | Required | Note |
|---|---|---|
| `facility_location` | yes |  |
| `harvest_batch_id` | yes |  |
| `plant_ids` | yes |  |
| `post_cure_weight` | yes |  |
| `post_cure_unit` | yes |  |
| `waste_weight` | yes |  |
| `waste_unit` | yes |  |
| `post_cure_room` | yes |  |

### `inventory_lot_create` - Creation of New Inventory Lot

Timing: 12 h. Fields: 7.

| Field | Required | Note |
|---|---|---|
| `weight_or_volume` | yes |  |
| `unit` | yes |  |
| `inventory_type` | yes | cured and dried flower, dried flower, wet flower, etc. |
| `cultivar` | yes |  |
| `facility_location` | yes |  |
| `room` | yes |  |
| `harvest_batch_ids` | yes |  |

### `lot_split` - Splitting an Existing Inventory Lot into a Sublot

Timing: 12 h. Fields: 5.

| Field | Required | Note |
|---|---|---|
| `source_lot_id` | yes |  |
| `facility_location` | yes |  |
| `new_room` | yes |  |
| `removed_weight_or_volume` | yes |  |
| `unit` | yes |  |

### `conversion` - Conversion of Inventory through Processing

Timing: 12 h. Fields: 11.

| Field | Required | Note |
|---|---|---|
| `source_inventory_id` | yes |  |
| `removed_weight_or_volume` | yes |  |
| `removed_unit` | yes |  |
| `resulting_inventory_type` | yes | flower, extract, etc. |
| `cultivar` | yes |  |
| `resulting_weight_or_volume` | yes |  |
| `resulting_unit` | yes |  |
| `waste_weight` | yes |  |
| `waste_unit` | yes |  |
| `facility_location` | yes |  |
| `post_conversion_room` | yes |  |

### `ingredient_add` - Addition of Ingredients to Inventory

Timing: 12 h. Fields: 5.

| Field | Required | Note |
|---|---|---|
| `inventory_id` | yes |  |
| `ingredient_names` | yes |  |
| `ingredient_amounts` | yes |  |
| `units` | yes |  |
| `facility_location` | yes |  |

Note: Ingredient means any substance added to inventory after extraction.

### `inventory_adjustment` - Inventory Adjustments

Timing: 12 h. Fields: 7.

| Field | Required | Note |
|---|---|---|
| `inventory_id` | yes |  |
| `adjustment_type` | yes |  |
| `reason` | yes |  |
| `removed_weight_or_volume` | yes |  |
| `unit` | yes |  |
| `facility_location` | yes |  |
| `cause` | no `*` | our addition: drives the 64-4.222(12) exemption test |

Note: Rule 64-4.222(12) separately requires a written justification to ommu_seedtosale@flhealth.gov within 12 hours for adjustments that do not result from processing, dispensation, wholesale purchase or distribution, or disposal of waste.

### `final_product` - Final Product Inventory

Timing: 12 h. Fields: 12.

| Field | Required | Note |
|---|---|---|
| `cultivar` | no `*` |  |
| `product_type` | yes | whole flower, vape, etc. |
| `unit_count` | yes | units assigned, for unit-based inventory |
| `expiration_date` | yes | immutable once recorded |
| `net_weight_or_volume` | yes | inclusive of the receptacle |
| `unit` | yes |  |
| `approved_product_name` | yes | department-approved product name |
| `weight_per_unit` | yes | for unit-based final product |
| `packaged_at` | yes | date the final product was placed in its receptacle |
| `unique_product_id` | yes |  |
| `facility_location` | yes |  |
| `room` | yes |  |

### `lab_sample_create` - Creation of New Lab Sample

Timing: 12 h. Fields: 6.

| Field | Required | Note |
|---|---|---|
| `is_research_and_development` | yes |  |
| `source_ids` | yes | plants, harvest batch, inventory, or retail batch |
| `removed_weight_or_volume` | yes |  |
| `unit` | yes |  |
| `cmtl_id` | yes | identity of the certified marijuana testing laboratory |
| `facility_location` | yes |  |

### `delivery_device_inventory` - Create New Delivery Device Inventory Record

Timing: 12 h. Fields: 5.

| Field | Required | Note |
|---|---|---|
| `unique_product_id` | no `*` |  |
| `inventory_type` | yes |  |
| `unit_count` | yes |  |
| `facility_location` | yes |  |
| `room` | yes |  |


## Dispensing tracking (real time)

### `dispensation` - Sale/Dispensation of Final Products and Delivery Devices

Timing: real time. Fields: 11.

| Field | Required | Note |
|---|---|---|
| `item_id` | yes |  |
| `sale_id` | yes | unique MMTC-assigned identification number for the sale |
| `product_class` | yes | low-THC, whole flower, etc. |
| `unique_product_id` | yes |  |
| `route_of_administration` | yes |  |
| `unit_count` | yes |  |
| `dispensing_facility_location` | yes |  |
| `patient_mmurnumber` | yes |  |
| `caregiver_mmurnumber` | no `*` |  |
| `patient_dob` | yes |  |
| `price` | yes |  |

Note: The department STS updates the medical marijuana use registry on receipt.

### `refund` - Refund the Sale/Dispensation of Final Product and Delivery Devices

Timing: real time. Fields: 6.

| Field | Required | Note |
|---|---|---|
| `sale_id` | yes |  |
| `item_id` | yes |  |
| `refund_amount` | yes |  |
| `unit_count` | yes | units returned or refunded |
| `dispensing_facility_location` | yes |  |
| `disposition` | yes | a refund does not return the item to inventory |

### `void_sale` - Void the Sale/Dispensation of Usable Product / Delivery Device

Timing: real time. Fields: 2.

| Field | Required | Note |
|---|---|---|
| `dispensing_facility_location` | yes |  |
| `sale_id` | yes |  |

Note: A voided sale returns the item to inventory in the department STS.


## Storage location

### `grow_room_create` - Create New Grow Room

Timing: 12 h. Fields: 3.

| Field | Required | Note |
|---|---|---|
| `facility_location` | yes |  |
| `room_name` | yes |  |
| `room_number` | yes |  |

### `plant_move` - Move Plants

Timing: 12 h. Fields: 3.

| Field | Required | Note |
|---|---|---|
| `facility_location` | yes |  |
| `plant_ids` | yes |  |
| `to_room` | yes |  |

### `inventory_room_create` - Create New Inventory Room

Timing: 12 h. Fields: 4.

| Field | Required | Note |
|---|---|---|
| `facility_location` | yes |  |
| `room_name` | yes |  |
| `room_number` | yes |  |
| `is_quarantine` | yes |  |

### `inventory_move` - Move Inventory

Timing: 12 h. Fields: 3.

| Field | Required | Note |
|---|---|---|
| `facility_location` | yes |  |
| `inventory_ids` | yes |  |
| `to_room` | yes |  |


## Waste destruction

### `disposal_schedule_inventory` - Schedule Inventory Disposal

Timing: 12 h. Fields: 2. Wait 72 h before the next step.

| Field | Required | Note |
|---|---|---|
| `inventory_id` | yes |  |
| `reason` | yes |  |

Note: The MMTC must wait 72 hours after scheduling before disposing.

### `disposal_inventory` - Dispose of Inventory

Timing: 12 h. Fields: 1.

| Field | Required | Note |
|---|---|---|
| `inventory_id` | yes |  |

### `disposal_schedule_plants` - Schedule Plant Disposal

Timing: 12 h. Fields: 2. Wait 72 h before the next step.

| Field | Required | Note |
|---|---|---|
| `plant_ids` | yes |  |
| `reason` | yes |  |

Note: The MMTC must wait 72 hours after scheduling before disposing.

### `disposal_plants` - Dispose of Plants

Timing: 12 h. Fields: 1.

| Field | Required | Note |
|---|---|---|
| `plant_ids` | yes |  |

### `plant_matter_disposal` - Dispose of Marijuana Plant Matter

Timing: 12 h. Fields: 4.

| Field | Required | Note |
|---|---|---|
| `facility_location` | yes |  |
| `collected_at` | yes |  |
| `weight` | yes |  |
| `unit` | yes |  |

Note: Post-defoliation matter where the plant ID is unknown.


## Plant and inventory transfer (real time)

### `transfer_out` - Transfer of Plants/Inventory Between MMTC Facilities (transferring)

Timing: real time. Fields: 6.

| Field | Required | Note |
|---|---|---|
| `item_ids` | yes |  |
| `manifest_id` | yes |  |
| `unit_count` | no `*` |  |
| `quantity` | yes |  |
| `unit` | yes |  |
| `transferring_facility_location` | yes |  |

### `transfer_in` - Transfer of Plants/Inventory Between MMTC Facilities (receiving)

Timing: real time. Fields: 9.

| Field | Required | Note |
|---|---|---|
| `item_ids` | yes |  |
| `manifest_id` | yes |  |
| `units_received` | no `*` |  |
| `units_rejected` | no `*` |  |
| `quantity_received` | yes |  |
| `unit_received` | yes |  |
| `quantity_rejected` | no `*` |  |
| `unit_rejected` | no `*` |  |
| `receiving_facility_location` | yes |  |

### `wholesale_invoice` - Creation of New Invoice for Wholesale Transaction

Timing: 12 h. Fields: 6.

| Field | Required | Note |
|---|---|---|
| `item_ids` | yes |  |
| `buyer_facility_location` | yes |  |
| `seller_facility_location` | yes |  |
| `price` | yes |  |
| `quantity` | yes |  |
| `unit` | yes |  |


## Transport

### `vehicle_register` - Department-Approved Vehicles Used to Transport Marijuana

Timing: 12 h. Fields: 7.

| Field | Required | Note |
|---|---|---|
| `vin` | yes |  |
| `license_plate` | yes |  |
| `make` | yes |  |
| `model` | yes |  |
| `year` | yes |  |
| `color` | yes |  |
| `vehicle_name` | yes | name selected by the MMTC |

### `manifest` - Transportation Manifest

Timing: 12 h. Fields: 9.

| Field | Required | Note |
|---|---|---|
| `driver_employee_ids` | yes |  |
| `stops` | yes | order of intended stops and the location of each |
| `arrival_times` | yes |  |
| `departure_times` | yes |  |
| `route_directions` | yes |  |
| `item_ids` | yes |  |
| `invoice_id` | no `*` | when the manifest documents a wholesale transfer |
| `creating_facility_location` | yes |  |
| `vehicle_id` | yes |  |


## Employees and API users

### `employee_record` - MMTC Employees

Timing: 12 h. Fields: 4.

| Field | Required | Note |
|---|---|---|
| `full_name` | yes |  |
| `dob` | yes |  |
| `hire_date` | yes |  |
| `email` | yes |  |

Note: For each employee that transports marijuana.

### `api_user` - Authorized API Users

Timing: 12 h. Fields: 3.

| Field | Required | Note |
|---|---|---|
| `email` | yes |  |
| `password` | yes |  |
| `permissions` | yes |  |

Note: Access is limited by Rule 64-4.222(5) to MMTC people, the MMTC's internal STS vendor, and the department STS vendor.
