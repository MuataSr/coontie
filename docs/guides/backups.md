# Backups: the operator's page

One page. Print it and tape it inside the cupboard where the record lives.

## Every day, at closing

```bash
coontie backup --to /media/usb/coontie --keep 14
```

That copies the whole record and its documents, checks the copy against the record before writing the
manifest, and deletes the oldest copies beyond fourteen. It takes a second and prints what it did.

If the machine runs all day and nobody remembers, put that line in cron once:

```bash
crontab -e
# 0 18 * * * cd /path/to/record && coontie backup --to /media/usb/coontie --keep 14
```

**The copy goes to a disk you can unplug.** Not a shared network drive: the record holds employee
names and dates of birth, and a copy inherits the record's access rule, which is you and your staff.

## Once, before you need it

```bash
coontie drill
```

It backs up, restores into a scratch folder, compares every table, then flips a byte and truncates a
copy to prove the checks catch both. If the drill passes, you know the backup works. **A backup nobody
has restored is a belief.**

Run it again the morning before an inspection, and after any change to the machine.

## When something is lost

```bash
coontie backup --verify /media/usb/coontie          # which copy is good, and what is wrong with it
coontie restore --from /media/usb/coontie --db record.sqlite3 --actor "Your Name"
coontie audit
```

`restore` refuses to overwrite a record unless you add `--force`, verifies the backup first, verifies
the chain in the restored file, and only then records `restore_performed` with the backup's name, the
head it expected and the head it found.

Restoring is a command and not a button, on purpose. It overwrites a record.

## What a good copy looks like on the Setup page

Setup lists the last five copies in the record's own `backups/` folder:

- **Copy** — the stamp, the part of the name `--from` takes
- **Made** — your clock, with the zone written out
- **Records** — how many events the copy holds
- **Ends at** — the chain head, the same value the printed audit carries, so a copy can be matched to
  a piece of paper
- **State** — `Verified`, or `Does not verify` with the first problem named

A copy that does not verify is **shown, not deleted**. It might be the only copy of something.

## The three failures, and what they mean

| What you see | What happened | What to do |
|---|---|---|
| `does not hash to the value in the manifest` | the file changed after it was written: a bad disk, a half-copied file, or someone edited it | use another copy; if it is the only one, the record on the machine is still the authority |
| `is 4096 bytes, the manifest says 360448` | the copy was cut short: the disk filled or the cable came out | copy again |
| `the chain in … does not verify` | the copy is internally inconsistent | do not restore from it; restore the previous day and name the gap in writing |

## What is not here yet, so nobody assumes it

- **No encryption.** A copy is a plain SQLite file. Treat the disk like the record itself.
- **No cloud or off-site upload.** Deliberate: uploading a record with employee dates of birth to a
  third party is the access rule this product exists to keep.
- **No restore from the browser.** See above.
