# Facility records: people, moves and inventory disposal

Five DH5059 events that a real facility writes every week, and that the record did not carry until
now: `employee_record`, `api_user`, `inventory_move`, `disposal_schedule_inventory`,
`disposal_inventory`.

Written before the code, per the standing ruling. Each section is one job on one screen.

## The jobs

| Job | Screen | What it writes |
|---|---|---|
| Record an employee | Setup | `employee_record` |
| Record an API user | Setup | `api_user` |
| Move a lot between rooms | Inventory | `inventory_move` |
| Schedule a lot's destruction | Inventory | `disposal_schedule_inventory` |
| Destroy a lot | Inventory | `disposal_inventory` |

## Screen: Setup, "Record an employee"

Fields in the order a payroll file has them: **full name**, **date of birth**, **hire date**,
**email**. The catalogue requires all four.

- A duplicate email is refused: two employee records for one person is how a manifest names a
  stranger.
- Date of birth is collected once and **not shown again** on any screen. It is in the record because
  the department asks for it, not because an operator needs to read it twice.
- Hire date may not be after today.

## Screen: Setup, "Record an API user"

Fields: **email**, **password**, **permissions** (a comma-separated list, e.g.
`inventory.read, transport.write`).

The catalogue asks for the password. This record **stores a verifier, never the password**:

- The form takes the password and immediately derives PBKDF2-HMAC-SHA256 (300 000 iterations,
  16-byte salt) with `hashlib.pbkdf2_hmac`.
- The ledger event carries `email`, `permissions`, `password_verifier`, `password_kdf` and a note
  saying the plaintext is not held. The plaintext exists only for the lifetime of the request.
- Reason: the ledger is append-only and hash-chained, and it is printed, backed up and exported. A
  secret written there can never be removed, not by a correction and not by a year of corrections.
  A department form asking for a password is asking about a *credential that exists in the STS*, and
  the defensible thing for this record to hold is proof that the credential was set, not the
  credential.
- This is a deliberate deviation from the field list and it is recorded as one: `events.py` keeps
  the catalogue's `password` field untouched, and the payload test names the exception with its
  reason rather than quietly skipping it. If the department's STS vendor integration later needs
  the credential itself, that value belongs in a secret store the record *references*, never in the
  ledger.

## Screen: Inventory, "Move a lot"

Fields: **lot** (prefilled when a lot is selected), **to room** (a list of the rooms that exist).

- A lot already in that room is refused: a move to where it already sits writes an event that says
  nothing happened.
- A lot on hold is refused. A hold is an instruction not to move the material, and the record
  should not let an operator satisfy the form and break the hold in the same gesture.
- A lot with no quantity left is refused.
- The event carries `facility_location` (where it came from), `inventory_ids` and `to_room`.

## Screen: Inventory, "Destroy a lot"

Two steps, because the rule has two:

1. **Schedule** with a reason (`disposal_schedule_inventory`). The clock starts.
2. **Destroy** (`disposal_inventory`), which is refused inside the 72-hour wait with the hours
   remaining in the message, exactly as plant disposal already is.

- The weight destroyed is written onto the disposal row, so the loss is a number rather than a
  disappeared lot.
- The lot's quantity goes to zero and the row stays: deleting it would take the history with it.
- A destroyed lot cannot be moved, processed or transported afterwards; every one of those paths
  refuses on a zero balance.

## What these screens do not do

- They do not edit an employee record. A changed hire date is a correction with a cause, like every
  other change to a record, and the corrections path already exists.
- They do not transmit anything. Nothing here reaches the department; the queue for that is a later
  increment and would say so on its own screen.
