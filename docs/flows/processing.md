# Flow 2b: processing, screen by screen

Written before the module, same as cultivation. Nine DH5059 events, and one idea underneath
all of them: **weight is conserved**. Whatever leaves a lot goes somewhere, and a lot cannot
give up more than it holds.

Rule basis: DH5059-OMMU-05/2026 processing section; Rule 64-4.222(12) for adjustments;
Rule 64-4.221(1)(c) for unique product IDs; Rule 64-4.222(6) for the ounce conversion.

---

## Screen 1: Cure and dry a harvest

*Job:* "The Blue Dream came off the rack at 620."

| # | Field | Notes |
|---|---|---|
| 1 | Harvest (`harvest_batch_id`) | The harvest it came from |
| 2 | Plants | Carried from the harvest record |
| 3 | Post-cure weight (`post_cure_weight`) and unit | The dry weight |
| 4 | Waste weight (`waste_weight`) and unit | Stems, trim lost in the process |
| 5 | Room (`post_cure_room`) | |

**Blocks:** no cure for a harvest that has not been harvested.

**Records:** `cure_dry`.

## Screen 2: Create the inventory lot

*Job:* "600 g of cured flower into INV1."

| # | Field | Notes |
|---|---|---|
| 1 | Weight (`weight_or_volume`) and unit | Cannot exceed what the cure left available |
| 2 | Inventory type (`inventory_type`) | cured and dried flower, dried flower, wet flower |
| 3 | Cultivar (`cultivar`) | |
| 4 | Room (`room`) | |
| 5 | Harvest batches (`harvest_batch_ids`) | What it came from |

**Records:** `inventory_lot_create`.

## Screen 3: Split a lot

*Job:* "Take 200 g of that into INV2."

| # | Field | Notes |
|---|---|---|
| 1 | Source lot (`source_lot_id`) | |
| 2 | How much (`removed_weight_or_volume`) and unit | Cannot exceed the lot's remaining weight |
| 3 | New room (`new_room`) | |

**Records:** `lot_split`. The sublot is a new lot with its own id, and the source keeps its
history.

## Screen 4: Convert through processing

*Job:* "300 g of flower into extract, 90 g out, 15 g waste."

| # | Field | Notes |
|---|---|---|
| 1 | Source lot (`source_inventory_id`) | |
| 2 | Removed weight and unit | Cannot exceed remaining |
| 3 | Resulting type (`resulting_inventory_type`) | extract, concentrate, edible, and so on |
| 4 | Cultivar | |
| 5 | Resulting weight and unit | Resulting plus waste cannot exceed what was removed |
| 6 | Waste weight and unit | |
| 7 | Post-conversion room | |

**Records:** `conversion`, plus a new lot for the result.

## Screen 5: Add ingredients

*Job:* "250 ml of MCT oil and 5 ml of flavor into the extract lot."

| # | Field | Notes |
|---|---|---|
| 1 | Lot (`inventory_id`) | |
| 2 | Ingredient names (`ingredient_names`) | Any substance added after extraction |
| 3 | Amounts (`ingredient_amounts`) and units (`units`) | One per ingredient |

**Records:** `ingredient_add`. Ingredients add to the lot; they are not a weight movement,
so the lot's remaining weight is unchanged. That is the rule's own model, and the screen says
so rather than inventing a mass balance the department does not ask for.

## Screen 6: Take a lab sample

*Job:* "Five grams to ACS for testing."

| # | Field | Notes |
|---|---|---|
| 1 | Source (`source_ids`) | The lot, or the plants or harvest |
| 2 | Weight and unit | Comes out of the lot |
| 3 | Lab (`cmtl_id`) | Certified marijuana testing laboratory |
| 4 | Research and development? (`is_research_and_development`) | |

**Records:** `lab_sample_create`.

## Screen 7: Final product

*Job:* "100 jars of 3.5 g, expires April 1."

| # | Field | Notes |
|---|---|---|
| 1 | Unique product ID (`unique_product_id`) | Must already exist in the DH5058 catalogue |
| 2 | Product type (`product_type`) | whole flower, vape, and so on |
| 3 | Units (`unit_count`), net weight, unit, weight per unit | |
| 4 | Approved product name (`approved_product_name`) | Department-approved name |
| 5 | Packaged at (`packaged_at`) | |
| 6 | Expiration date (`expiration_date`) | **Immutable once recorded** |
| 7 | Room | |

**Blocks:** an unknown unique product ID, and any attempt to change a recorded expiration.
The refusal quotes the catalog's own word: immutable.

**Records:** `final_product`.

## Screen 8: Delivery device inventory

*Job:* "50 batteries into INV2."

| # | Field | Notes |
|---|---|---|
| 1 | Unique product ID or device type | |
| 2 | Inventory type (`inventory_type`) | |
| 3 | Units (`unit_count`) | |
| 4 | Room | |

**Records:** `delivery_device_inventory`.

## Screen 9: Correct a lot

The S2 flow, unchanged, now usable on a processing lot: a cause is mandatory, a non-exempt
cause drafts the 12-hour justification, and the original weight stays on the ledger.

---

## What processing does not do

- No recipes, no potency calculations, no yield forecasting, no batch costing. The catalog
  records what moved, not what it was worth.
- No automatic mass balance correction. If the numbers do not add up the record refuses and
  says which two numbers disagree; it never invents the missing grams.
