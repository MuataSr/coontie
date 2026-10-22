# Backup, restore and the drill

Spec written before code, like every other increment. This one is CLI-first on purpose and the
reason is stated below rather than left to taste.

## What a backup is

The record is **one SQLite file** plus a `reports/` directory of artifacts (outage CSVs, manifest
pages, drafted notices). A backup is both, copied at one instant, with enough information to prove
the copy is the same record and not a plausible-looking one.

```
backup/
  coontie-backup-20261022T170500Z-8f2c1d4a-412.sqlite3
  coontie-backup-20261022T170500Z-8f2c1d4a-412.manifest.json
  reports/
    outage-out-1b2c.csv
    man-9f8e-manifest.txt
```

The filename carries the chain head's first eight characters and the event count, so an operator
holding two files can tell which is later without opening either.

## Four guarantees, and how each is proven

| Guarantee | How |
|---|---|
| **Consistent** | `sqlite3.Connection.backup()` copies pages under SQLite's own lock, so a backup taken while the appliance is serving is a real instant, not a torn file. `cp` is refused by implementation choice, not by hope |
| **Verifiable** | the manifest records a sha256 per file, the event count, the chain head, the facility, the licence, the tool version and the time; `coontie backup --verify` recomputes every one |
| **Restorable** | `coontie restore --from <backup> --db <target>` verifies first, then copies, then **verifies the chain in the restored file**, then appends one `restore_performed` event to the restored record |
| **Prunable** | `--keep N` deletes the oldest verified backups beyond N, never the newest, never one that fails verification |

## The manifest

```json
{
  "format": "coontie-backup/1",
  "created_at": "2026-10-22T17:05:00+00:00",
  "tool": "coontie 0.1",
  "facility": "Nature's Grace FL, LLC",
  "license": "MMTC-2026-0030",
  "events": 412,
  "chain_head": "8f2c1d4a…",
  "database": {"name": "…sqlite3", "bytes": 528384, "sha256": "…"},
  "reports": [{"name": "outage-out-1b2c.csv", "bytes": 611, "sha256": "…"}]
}
```

The chain head is the same value the printed audit carries. A reader who kept yesterday's audit can
compare it with a backup's manifest and know whether the file is the record that audit described.

## Restore, step by step

1. **Verify the backup.** A manifest hash mismatch, a truncated database, or a chain that does not
   verify stops here with the reason named.
2. **Refuse to overwrite.** An existing target database is refused unless `--force`. A restore is
   destructive and must not be the consequence of a mistyped command.
3. **Copy** the database and merge `reports/` into the target's directory, never deleting an artifact
   the target already holds.
4. **Verify the restored chain** and compare the restored event count and head against the manifest.
   A restore that cannot prove it restored the same record has failed, whatever the file size says.
5. **Append `restore_performed`** with the backup's name, its chain head as recorded, the head found
   on restore, and who ran it. `appearance_chosen` is excluded from operational counts; this one is
   **not**, because a restore is an event in the life of the record and an inspector may ask.
6. **Print what changed**: table by table, the counts before and after, so a restore onto a newer
   record does not silently discard a day.

## Why restore is not a screen

A backup form is safe: it writes a file and changes nothing. **Restore is not**, so it stays on the
command line where it takes an explicit `--from` and an explicit `--db`, and where a stray POST from
any page in the operator's browser cannot reach it. That is a deliberate limit on the "every screen
shows its command" rule: the rule exists so the interface cannot drift from the record, not so every
command gets a button.

## The drill

`coontie drill` runs the whole thing against a scratch directory and prints every step:

1. back up the live record
2. verify the backup
3. restore into a fresh path
4. compare every table's row count
5. compare the chain head
6. **tamper** with a copy (flip one byte in the database) and assert the verify refuses it
7. **truncate** a copy and assert the verify refuses it

A backup nobody has restored is a belief. The drill is the thing that turns it into a control, and it
is what an operator runs the morning before an inspection.

## Refusals

- free space below twice the database size (the copy plus its temporary manifest write)
- target database exists without `--force`
- a report file missing from the backup while the manifest lists it
- any hash mismatch, any truncated file, any chain that does not verify
- `--keep` below 1, or a prune that would remove the newest backup

## What this does not do

- **No off-machine copy.** `--to` is a directory the operator names, because uploading a record that
  contains employee dates of birth to a third party is exactly what 64-4.222(5) restricts. The guide
  says where to put the directory (an external disk, not a shared drive).
- **No encryption at rest.** The database holds employee names and dates of birth, so a backup
  inherits the access rule of the record. Encryption is a later increment with its own spec, and
  claiming it now would be worse than saying plainly that it is absent.
- **No incremental or cloud backups.** One file, one command, one directory.
