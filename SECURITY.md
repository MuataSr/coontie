# Security

Coontie holds a facility's operational record: inventory, manifests, corrections, employee names and
dates of birth, and the API users a facility's own systems authenticate as. Treat a copy of the database
as you would treat the record itself.

## Reporting a vulnerability

Open a private security advisory on the repository (Security → Advisories → New draft) rather than a
public issue. If that is not possible, contact the maintainers through the address on the repository
profile. Expect an acknowledgment within a week; this is a small project, not a vendor with a
24-hour contract, and saying so is more useful than promising a service level it does not have.

Please include: what you ran, what happened, what you expected, and the smallest record that shows it.
Do not include real licence numbers, patient information, or credentials.

## What this system's security model is

- **It runs on the facility's own machine, bound to loopback.** `coontie serve` refuses any bind
  outside `127.0.0.1`; there is no hosted mode and no telemetry.
- **Any page in the operator's browser can POST to loopback**, so the server mints a session token at
  startup, requires it as a hidden field, compares it with `compare_digest`, and checks `Origin` and
  `Host` on every request. The CSP forbids scripts. Tests assert each of these.
- **No JavaScript, no build step, no CDN, no network fetch from a screen.** A skin that smuggles in a
  `<script>`, a `javascript:` URL or an `@import` is refused by `theme.check_skin`.
- **Secrets are never written to the ledger.** The record is append-only, hashed, printed, backed up and
  exported, so an API user's password is recorded as a PBKDF2-HMAC-SHA256 verifier and never as
  plaintext; two tests enforce it, one of them reading the raw database bytes.
- **Restores are commands, not buttons.** A restore overwrites a record; it takes an explicit `--from`
  and `--db` and cannot be reached from a page.

## Known and deliberate limits

- **No encryption at rest.** The database and its backups are plain SQLite files. Disk encryption is the
  operator's job, and the guide says so rather than implying otherwise.
- **No authentication of the person at the keyboard.** The operator name is a claim, not a credential,
  because Rule 64-4.222(5) restricts *who may touch the record* and the appliance assumes one
  authenticated OS session. Whether staff share that session is still an open question in
  `docs/flows/gui.md`.
- **No department adapter.** Nothing is transmitted, so no credential exists here to leak.
- **Files under `reports/`** (outage CSVs, manifest pages, envelopes) are evidence and are not
  encrypted either.

## Supported versions

The `main` branch. There are no release branches, and the project is pre-1.0: a fix lands on `main` and
the version moves.
