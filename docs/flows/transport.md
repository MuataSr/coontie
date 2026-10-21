# Flow 2c: transport, screen by screen

Rule basis: Rule 64-4.222(10), F.A.C. requires a transportation manifest **generated from the
Internal STS** every time marijuana is transported, complying with s. 381.986(8)(g), F.S.

The statute's own list, fetched from flsenate.gov on 2026-10-21 (2025 Florida Statutes), is the
field contract for the manifest. It requires the manifest to include:

| | Required item | Our field |
|---|---|---|
| a | Departure date and approximate time of departure | `departure_at` |
| b | Name, location address, and license number of the originating MMTC | facility record |
| c | Name and address of the recipient of the delivery | `recipient_name`, `recipient_address` |
| d | Quantity and form of any marijuana or delivery device transported | manifest items |
| e | Arrival date and estimated time of arrival | `arrival_at` |
| f | Delivery vehicle make and model and license plate number | vehicle record |
| g | Name and signature of the MMTC employees delivering the product | `employee_ids` + signature block |

Beyond the manifest itself, the same subsection requires: a copy to each recipient who signs
acknowledging receipt (`1.(I)`), retention of copies for at least three years (`1.(III)`), that
only vehicles in good working order are used (`2.`), and that **at least two persons are in the
vehicle**, one of whom remains in it during a delivery (`5.`).

---

## Screen 1: Register a vehicle

*Job:* "The white Transit, plate FL-MMTC-12."

| # | Field | Notes |
|---|---|---|
| 1 | Vehicle name | What the staff call it |
| 2 | VIN (`vin`), license plate (`license_plate`), make, model, year, color | |
| 3 | In service? | Off when the vehicle is in the shop; an out-of-service vehicle cannot be dispatched |

**Records:** `vehicle_register`.

## Screen 2: Build a manifest

*Job:* "Two hundred grams to the Tampa dispensary tomorrow morning."

| # | Field | Notes |
|---|---|---|
| 1 | Recipient name and address (`recipient_name`, `recipient_address`) | A dispensary, a testing laboratory, or a patient address |
| 2 | Items | Each line: a lot, a quantity, a unit, and the form |
| 3 | Vehicle | Must be registered and in service |
| 4 | Employees delivering (`driver_employee_ids`) | **At least two**, per the statute |
| 5 | Departure date and time (`departure_at`) | |
| 6 | Arrival date and estimated time (`arrival_at`) | |
| 7 | Route directions and stops | Stops are the intended addresses in order |
| 8 | Wholesale invoice | Optional; required when the transfer is a wholesale sale |

**Blocks:** fewer than two employees; an unregistered or out-of-service vehicle; no items; no
recipient; no departure or arrival time; a quantity larger than the lot holds.

**Records:** `manifest`, and the printable artifact under `reports/`.

## Screen 3: Dispatch

*Job:* "It left the building."

| # | Field | Notes |
|---|---|---|
| 1 | Manifest | |
| 2 | Actual departure time | Defaults to now |

**Blocks:** dispatching a manifest twice, and dispatching more than the lot holds.

**Records:** `transfer_out` (real time), plus a weight move out of each source lot.

## Screen 4: Receive

*Job:* "Tampa signed for 198 grams and rejected 2."

| # | Field | Notes |
|---|---|---|
| 1 | Manifest | |
| 2 | Received and rejected quantities per item | Rejected quantities are recorded, not discarded |
| 3 | Receiver name | The signature on the paper copy; recorded here as acknowledgment |
| 4 | Room | Where the received stock lands |

**Blocks:** receiving more than was dispatched; receiving a manifest that was never dispatched;
receiving the same manifest twice.

**Records:** `transfer_in` (real time), a new lot for the received quantity.

## Screen 5: The manifest artifact

One printable page containing every item the statute lists, with a signature block for the
receiving party, generated from the record and written to `reports/`. It is the thing the driver
carries and the thing an officer asks for, so it is plain text rather than a dashboard.

---

## What transport does not do

- No route optimisation, no vehicle telematics, no GPS, no driver scheduling. The statute asks
  for a manifest and a crew, not a logistics platform.
- No e-signature capture. The paper copy is signed as the statute describes; the system records
  who signed and when, which is the part the record can hold honestly.
