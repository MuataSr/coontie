# Primary sources

All retrieved and read on 2026-10-21. Nothing in this repo rests on a secondary
description of a rule.

| Document | Where it came from | How it was read |
|---|---|---|
| Rule 64-4.221, F.A.C., MMTC Seed-to-Sale Tracking System Integration (New 8-24-26) | `https://www.flrules.org/gateway/readFile.asp?sid=0&tid=31211416&type=1&file=64-4.221.doc` | Downloaded the adopted rule document, converted with LibreOffice, transcribed into `docs/requirements/64-4.221.md` |
| Rule 64-4.222, F.A.C., MMTC STS Tracking System Procedures (New 8-24-26) | `https://www.flrules.org/gateway/readFile.asp?sid=0&tid=31211513&type=1&file=64-4.222.doc` | Same method, transcribed into `docs/requirements/64-4.222.md` |
| Form DH5059-OMMU-05/2026, MMTC Seed-to-Sale Required Data Collection Document (Eff. 05/26) | `https://flrules.org/gateway/reference.asp?No=Ref-19592`, file `64-4.222 MMTC Seed-to-Sale Required Data Collection Document_Final.rtf` | Downloaded the incorporated RTF, converted, and transcribed every field into `src/coontie/events.py` |
| Rule 64-4.210, F.A.C., MMTC Fines, Suspension, and Revocation | `https://www.law.cornell.edu/regulations/florida/Fla-Admin-Code-Ann-R-64-4-210` | For context on penalty exposure. Not yet modelled |
| s. 381.986, F.S. (2025) | `https://www.flsenate.gov/Laws/statutes/2025/381.986` | For the enabling statute and the (8)(d)/(8)(e)/(8)(g) obligations |
| BioTrack API access process and approved integrator list | `https://biotrack.com/legislation/florida/` | The department's STS vendor states API credentials require naming the MMTC or CMTL you integrate for |
| The coontie and the atala butterfly (project name) | `https://www.floridamuseum.ufl.edu/earth-systems/blog/a-butterfly-on-the-move-the-atala-butterfly-and-its-coontie-connection/` | Read for the name's story: coontie as the atala host plant, commercial Florida Arrowroot harvesting outrunning the cycad, the butterfly believed extinct in the 1940s, and recovery after replanting |
| OMMU Rules Workshop transcripts, 2025-10-28 and 2025-10-29 | `https://knowthefactsmmj.com/wp-content/uploads/Transcripts/` (media library) | Downloaded and read in full. The October 29 session is the operator testimony on 64-4.221 and 64-4.222: named compliance staff from Trulieve, Surterra, Curaleaf, AYR, The Flowery, INSA, Sunburn, plus Baxter Law and the Florida Cannabis Action Network |
| Form DH5058-OMMU-1/2024, Usable Product and Marijuana Delivery Device Inventory and Unique Product ID | `https://knowthefactsmmj.com/wp-content/uploads/2026/01/64ER24-1-MMTC-Usable-Product-and-Marijuana-Delivery-Device-Inventory-and-Unique-Product-ID.pdf` | Downloaded and transcribed in full into `src/coontie/forms.py` and `docs/forms/dh5058.md`: 15 columns, 15 product types, 7 routes |
| Operator complaint corpus | Reddit via the PullPush archive API (`https://api.pullpush.io/reddit/search/comment/`), 393 substantive comments from four full threads plus keyword sweeps | Reddit itself returns 403 from this network on every route; the archive API is the working path. Distilled in `docs/research/PAIN-POINTS-2026-10-21.md` |

## What is deliberately not used

- No incumbent's code, bundle, or private API was read. Per vendor terms and
  because it is unnecessary: their workflows are described in public documentation
  and their data leaves with the operator.
- OpenTHC's BioTrack adapter (`openthc/cre-adapter`, GPL-3.0) was read only for
  orientation on BioTrack's endpoint grammar. No code is copied; copying it would
  force GPL-3.0 across this MIT tree.

## Known gaps

- The department API specification itself (endpoints, auth, exact payload shape)
  is available only to an integrating vendor with a sponsoring MMTC or CMTL.
  Everything here is the department's side of the contract, which is public.
- MMUR (Medical Marijuana Use Registry) access for patient verification at
  dispensing is unverified. Rule 64-4.222(2)(a) assumes the MMTC can check MMUR
  status and limits; how software performs that check is not documented publicly.
  Do not promise a dispensing module before this is answered.
