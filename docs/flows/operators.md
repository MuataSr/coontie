# Operators: from a claimed name to a person who signed in

Spec written 2026-10-23, before code. Lane F. Predecessor: `docs/flows/lan.md`, which put a tablet in
the cure room and had to say, out loud, that the name beside every one of its records was a claim.

## The problem this closes

Throughout this build the operator name has been a cookie holding whatever the last person typed,
and every screen said so. That was correct on loopback: the OS login was the boundary, one person sat
at the machine, and asking them for a password to reach a record they had already unlocked would have
been theatre.

A tablet in a cure room ends that. Two people, one shared tablet, records attributed by a first name
someone typed. That is the largest false statement the software was still willing to make, and this
increment retires it.

## What changes, in one sentence

An employee may be given a passphrase; once any employee has one, the appliance requires a person to
sign in before it will show or change anything, and the name on every record comes from that session
rather than from a text box.

## The shape of it

- **Enrolment is a facility act, done at the server, on the command line.**

  ```bash
  coontie passphrase --id emp-3f81c0 --set            # prompts twice, nothing echoed
  coontie passphrase --id emp-3f81c0 --verify         # prompts once; exit 0 or 1
  coontie passphrase --id emp-3f81c0 --forget --actor "Maria Lopez"
  ```

  An employee is a DH5059 record already (`employee_record`); a passphrase is an attribute of that
  record, not a new kind of person. The record keeps `pbkdf2_sha256`, the iteration count, the salt
  and the derived key, exactly as an API user's verifier is kept, and for the same reason: the ledger
  is printed, exported and backed up. **The passphrase itself is never stored, in any form that can
  be read back.**

- **The appliance requires sign-in only when a passphrase exists.** Enrol nobody and every screen
  behaves exactly as it does today, with the claim stated. Enrol one person and `/signin` becomes the
  only page that answers, `/health` stays open for whatever watches the process, and `/pair` still
  works so a tablet can be paired before anyone signs in. The gate is derived from the record, never
  from a flag someone must remember to set.

- **The session cookie is signed, not merely set.** A person cookie is `emp-…` plus an HMAC-SHA256 of
  that id under the server's own session token, which lives in memory and in an HttpOnly cookie no
  page can read. A cookie naming an employee the process cannot verify is dropped and treated as no
  sign-in at all. Without this, the "signed in" state would be a text box with better manners.

- **Five wrong passphrases from one address lock that address for fifteen minutes**, the same policy
  and the same limiter as terminal pairing, and the screen says how long rather than failing quietly.

- **Signing in and out are on the ledger.** `person_signed_in` carries the employee id and full name;
  `person_signed_out` carries the same. That is what makes the name on a record checkable: an
  inspector can see that Maria signed in at 09:12 and that the fourteen records after it carry her
  name. It also gives the facility the only answer it has ever had to "who had the tablet at 3 a.m.".

- **Nothing else about attribution changes.** Every writer already records the operator name it is
  given; it now receives the signed-in person's full name instead of a typed string. No payload grows
  a field, no report changes shape, and the department's `actor` field still holds a name.

## Refusals, in the words the operator sees

- A passphrase shorter than twelve characters: `a passphrase shorter than twelve characters is
  refused; this one protects a controlled-substance record`.
- A passphrase containing the person's own name: `a passphrase that contains the person's name is the
  first thing anyone would try`.
- One repeated character: `a passphrase of one repeated character is not a passphrase`.
- Signing in as an employee with no passphrase: `that person has no passphrase; enrol one at the
  server with coontie passphrase --id … --set`.
- A wrong passphrase: `that passphrase does not match; N tries left from this device`.
- A locked address: `too many wrong passphrases from this device; try again in N minutes`.
- An unknown or inactive employee: `that person is not on the payroll record, or is no longer active`.

## What this increment deliberately does not do

- **No roles and no permissions.** Every signed-in person may do everything, because every person on
  the record today may do everything. Role separation is a rule question about the facility's own
  staffing, not a guess this build should make.
- **No password reset by email.** There is no mail server, no network, and an appliance that can mail
  a reset link is an appliance that phones home.
- **No passphrase expiry.** Chasing a rotation policy adds a refusal that has nothing to do with a
  record being correct, and a forced change on a tablet in a cure room is how people write the new
  passphrase on the wall.
- **No second factor.** A token or an SMS needs a network this appliance does not have.
- **The CLI does not sign in.** The OS login is still the boundary for the person at the server, which
  is where enrolment happens; a passphrase checked at a terminal that is already unlocked adds nothing
  an attacker with that terminal does not already have.
- **The operator name is still stored as a name, not an employee id, in every event payload.** Adding
  `actor_employee` to thirty-one writers is a schema change across the whole record for attribution
  that `person_signed_in` already gives an inspector. Recorded here as the known limit rather than
  implied away.

## The screens

- **`/signin`** — the people who can sign in, one field, one button. It says what signing in does, and
  it says where a passphrase comes from when nobody has one.
- **`/signout`** — a POST from the header, because a GET that clears a session is a link a browser can
  prefetch. It appends `person_signed_out` and lands on `/signin`.
- **The header** — the signed-in person's full name and a sign-out button while signed in; the plain
  name field only while nobody is enrolled, with the sentence that this name is a claim.
- **Setup** — a row per employee saying whether a passphrase is set and when, plus the command that
  sets one. No passphrase is ever displayed, echoed back, or offered as a hint.

## What its gate asserts

`tests/test_passphrase_gate.py`, against a real server on a real socket:

1. With nobody enrolled, loopback behaves exactly as before (the regression that matters).
2. Enrolling one person makes `/signin` the only page that answers; `/health` and `/pair` still answer.
3. The right passphrase signs in, sets a verified cookie, and lands on Today with the person's name in
   the header.
4. A forged person cookie is treated as no sign-in.
5. A wrong passphrase answers with the tries left; five of them lock that address and say how long.
6. Strength refusals fire for short, name-containing and single-character passphrases.
7. Signing in and out append their ledger events with the employee id.
8. `--forget` clears the verifier and returns the appliance to the claimed-name path.
9. The passphrase is absent from the raw database bytes, and the verifier is a PBKDF2 string.
10. The commands themselves work: `passphrase --set/--verify/--forget` through the real command line.
