# Flow 2a: cultivation, screen by screen

Written before the code, on purpose. Each screen is one job an operator actually does in a
grow room, and the module is built to that shape so the interface is a wrap rather than a
redesign. Fields are listed in the order a person records them, with the department's field
name in parentheses where it differs from the plain name.

Rule basis: DH5059-OMMU-05/2026, cultivation section, plus Rule 64-4.221(4) (integration
complete before cultivation authorization) and Rule 64-4.222(2) timings.

---

## Screen 1: Start a batch

*Job:* "Twelve clones of Blue Dream arrived."

| # | Field | Notes |
|---|---|---|
| 1 | Cultivar (`cultivar`) | Free text, matched to the products you sell |
| 2 | Room (`room`) | Must be an existing grow room |
| 3 | Count (`count`) | Number of seeds or clones in the batch |
| 4 | Mother plant (`mother_plant_id`) | Optional; only when the cuttings came from one of your mothers |

**Blocks:** no batch until integration is recorded (STS-2). A batch is inventory until the
plants are planted.

**Records:** `seed_clone_batch`.

## Screen 2: Plant them

*Job:* "Twelve clones into veg."

| # | Field | Notes |
|---|---|---|
| 1 | Batch | Which batch they came from |
| 2 | How many | Cannot exceed what the batch holds |
| 3 | Planted at (`planted_at`) | Defaults to now |
| 4 | Mother plant? (`is_mother_plant`) | Yes for a plant kept for cuttings |

**Blocks:** more plants from a batch than the batch contains.

**Records:** one `immature_plant` per plant, each with its own plant ID.

## Screen 3: Move plants

*Job:* "Veg to flower room 2."

| # | Field | Notes |
|---|---|---|
| 1 | Plants (`plant_ids`) | Scan or type ranges, e.g. `PL-0001..PL-0012` |
| 2 | To room (`to_room`) | Must be an existing room |

**Blocks:** moving a plant that is harvested or disposed.

**Records:** `plant_move`.

## Screen 4: Apply an additive

*Job:* "Neem oil on the veg room, 40 ml."

| # | Field | Notes |
|---|---|---|
| 1 | What (`additive_description`) | Active ingredient, concentration, manufacturer lot, EPA registration where it applies |
| 2 | How much (`amount`) and unit (`unit`) | |
| 3 | Which plants (`plant_ids`) | |
| 4 | When | Defaults to now |

**Blocks:** a plant that is no longer growing.

**Records:** `additive_application`.

## Screen 5: Schedule the harvest

*Job:* "These twelve come down Friday."

| # | Field | Notes |
|---|---|---|
| 1 | Plants (`plant_ids`) | The exact set that will be harvested together |
| 2 | When | |

**Blocks:** nothing. This screen exists because the rule requires the schedule to exist
before the harvest, and because it gives the harvest screen a set to confirm rather than a
set to invent.

**Records:** `harvest_schedule`.

## Screen 6: Harvest

*Job:* "Chop, weigh, into the dry room."

| # | Field | Notes |
|---|---|---|
| 1 | Plants (`plant_ids`) | Must match one open schedule exactly |
| 2 | Wet flower weight (`wet_flower_weight`) and unit (`wet_flower_unit`) | |
| 3 | Waste weight (`waste_weight`) and unit (`waste_unit`) | Stems, fan leaves |
| 4 | Other material weight (`other_material_weight`) and unit (`other_material_unit`) | |
| 5 | Post-harvest room (`post_harvest_room`) | Where the flower went |

**Blocks:** no harvest without a matching open schedule. Harvested plants leave the growing
count.

**Records:** `harvest`, and the wet flower becomes the input the processing flow starts
from.

## Screen 7: Dispose

Three jobs share one shape because they share one rule: **schedule first, wait 72 hours,
then dispose.**

| Job | Fields | Records |
|---|---|---|
| Plants | plants, reason, then at least 72 hours later the disposal | `disposal_schedule_plants`, `disposal_plants` |
| Plant matter | weight, unit, collected at (plant ID unknown, post-defoliation) | `plant_matter_disposal` |

**Blocks:** disposing plants less than 72 hours after scheduling.

---

## What the screens do not do

- No yield forecasts, no strain library, no photos, no barcodes, no scheduling automation.
  Those are vendor features the research found operators paying for and not using.
- No "mature plant" state. The DH5059 catalog has immature plants, moves, additives,
  schedules, harvests and disposals; inventing a vegetation and flowering state machine
  would be our own data, not the department's.
- The 8-inch immature plant definition in the catalog is not enforced, because nothing in
  the record measures the plant. The screen says so rather than pretending to check.
