# Publication: what is ready, what is a decision

Lane D. Everything mechanical is done and gated. Three things below are not mine to choose, and the
repository does not go public until they are answered.

## What is done

| | |
|---|---|
| Licence | MIT, "The Coontie Authors", declared in `pyproject.toml` and stated in the README |
| Brand | `scripts/publish_check.py` fails on any company name in a tracked file; four documents were neutralised for this lane |
| Secrets | no key, token or password literal in the tree (a fixture password in a test is exempted by name, and the record's own test proves it never reaches the database) |
| Paths | no absolute home directory in any tracked file |
| Evidence | 453 tests, no third-party runtime dependency, `scripts/publish_check.py` runs them |
| Screens | six committed under `docs/screens/`, two linked from the README |
| Demo | `scripts/soak.py --keep` produces a month of one facility in under a minute, and the screenshots are that record |
| Contribution | `CONTRIBUTING.md` (the seven build rules), `SECURITY.md` (model and its honest limits) |

Reproduce the gate:

```
python3 scripts/publish_check.py
```

## Decision 1: where it lives

Handle availability, checked against GitHub on 2026-10-22:

| Handle | Status |
|---|---|
| `coontie` | **taken** (HTTP 200, an existing account) |
| `coontie-app` | free (404) |
| `coontie-record` | free (404) |
| `coontie-mmtc` | free (404) |

An organisation rather than a personal account is the better shape for a project meant to outlive one
maintainer's login. Options, with the trade-off stated:

- **A new neutral org** (`coontie-app` or similar): keeps the brand clean, one more account to run.
- **A personal account**: fastest, and puts an individual's name on a product meant to stand alone.
- **An existing company org**: worst of the three for this project. The brand decision was explicit:
  no company name on the OSS product, support sold separately and disclosed.

## Decision 2: freedom to operate

The name `Coontie` is a Florida native plant, but a defunct "Coonti CMS" existed years ago. `docs/sources.md`
records that collision. Two paths:

- **A read before publishing** (an hour of searching USPTO TESS, Florida's registry and the usual code
  hosts) and a dated note in the repository.
- **Publish with the risk documented**, which is defensible for a pre-1.0 project with no revenue, as
  long as the note exists before anyone asks.

Nobody is being misled either way; the difference is whether the check is done before or after.

## Decision 3: commit authorship

Every commit in the history is authored `ann-e@mu2.solutions`. That domain is a company name, and this
project's brand decision says the company stays out of it. The history has never been pushed, so this is
the last moment it can be changed cheaply:

```bash
git filter-branch --env-filter '
  export GIT_AUTHOR_NAME="Coontie Authors"
  export GIT_AUTHOR_EMAIL="dev@coontie.invalid"
  export GIT_COMMITTER_NAME="Coontie Authors"
  export GIT_COMMITTER_EMAIL="dev@coontie.invalid"
' -- --all
```

(`.invalid` is reserved by RFC 2606 and cannot be mistaken for a real address; a GitHub noreply address
is the alternative if authorship should point at an account.) The alternative is to leave the history
as it stands and accept the company domain on every commit.

## Decision 4: licence headers

- **Repo-level `LICENSE` only** (current state): normal for Python projects, nothing to maintain.
- **A short header in every file**: unambiguous in a file copied out of the tree, and 96 files of
  noise to keep consistent, which is exactly the kind of thing that drifts.

## The publish sequence, once the four are answered

```bash
python3 scripts/publish_check.py            # must print "publishable"
gh repo create <owner>/<name> --public --source . --remote origin --push
gh repo edit --description "An open, MIT-licensed internal seed-to-sale record for Florida MMTCs (Rule 64-4.221, Form DH5059)" \
             --add-topic cannabis --add-topic seed-to-sale --add-topic florida --add-topic compliance --add-topic python
```

Then, in order:

1. Open the repository page and confirm the six screenshots render and the two README images load.
2. Confirm the licence banner reads MIT and the description is the one above.
3. Turn on private vulnerability reporting (Settings → Security) so `SECURITY.md` is not a dead end.
4. Tag `v0.0.1` on the published commit, and note in the release that the record layer and the
   appliance are complete through a facility's ordinary day, with no department adapter.
5. Add the repository to `docs/sources.md`, so a reader can tell which revision the research describes.

## What must not be published

- Any real facility's database, export, licence number or employee list. The screenshots are a synthetic
  facility, `Soak Creek Cultivation, LLC`, `MMTC-2026-0099`, produced by the soak.
- Any credential, and there are none in the tree.
- `~/.hermes/` notes, session logs or private research: not tracked, and not to be added.
