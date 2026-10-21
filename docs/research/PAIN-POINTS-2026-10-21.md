# Coontie recon: what operators actually complain about

Date: 2026-10-21. Scope: pain points voiced by users and staff of Florida MMTCs and
of the cannabis software they run (Alleaves, Flourish, Dutchie, Flowhub, Treez, Cova,
Sweed, BioTrack).

## Coverage: what worked, what was blocked

| Source | Result |
|---|---|
| OMMU rules workshop transcripts (Oct 28 and 29, 2025) | **Full text retrieved** (6 documents from the OMMU media library). Named MMTC compliance staff speaking on the record. Strongest source in this dossier |
| Reddit, via PullPush comment archive API | **419 comments retrieved** across 4 full threads plus keyword sweeps (393 substantive after dedupe) |
| Reddit direct (HTML and .json) | **403 from this network**, old.reddit and api.reddit also 403. Jina reader returned "blocked by network security". Not archived on Wayback for these thread IDs |
| G2 | Blocked (CRAWL_UNKNOWN_ERROR) |
| Capterra | Blocked (CRAWL_NOT_FOUND on three URL shapes) |
| SoftwareAdvice | Reachable. **Flourish has 1 review**, 4.0 overall, sub-scores: ease of use 4.0, value 4.0, support 5.0, **functionality 3.0** |
| GetApp | Reachable. Dutchie: 5 reviews, 4.6 overall, 80% positive |
| TrustRadius | Reachable but empty: "We don't have enough ratings and reviews" for both Dutchie and Flowhub |
| MJBizDaily (two relevant articles) | Blocked at the fetch layer (404 from the server-side fetcher) |
| Cannabis Regulatory Monitor (NM BioTrack suit) | Full text retrieved |
| X/Twitter, LinkedIn, Facebook groups, Discord | Not attempted beyond noting they require login. Operator complaints are known to live there |

**Coverage finding in its own right:** these platforms have almost no public reviews
(1, 5, 0). The complaint discourse is not on review sites. It lives in Reddit threads,
in state rulemaking hearings, and in private operator groups.

**Vendor-specific finding:** across 393 substantive comments, **zero** genuine
discussion of Flourish or Alleaves as products. Every "flourish" hit was the verb.
Alleaves appears almost exclusively as COA-link URLs from dispensary menus. The loud
complaints are about **Dutchie, Flowhub, Treez, Sweed, Metrc and BioTrack**.

## Pain clusters, most-evidenced first

Keyword screen over 393 substantive comments (a comment can hit several tags; these
are screening counts, not a validated coding scheme).

| # | Cluster | Screen hits | Core complaint |
|---|---|---|---|
| 1 | Switching, churn, DIY replacement | 115 | Operators are actively leaving vendors, and some are building their own |
| 2 | Cost and contract lock-in | 76 | Price, auto-renewal, MSA terms, reporting paywalled |
| 3 | Compliance guardrails missing | 76 | Limits, age checks, package holds, audit exposure |
| 4 | Reporting, exports, inventory ops | 58 | Expirations, sales reports, sorting, receipts, trust in exports |
| 5 | Support collapse | 40 | Tickets never resolved, abandonment after onboarding |
| 6 | Training and implementation | 32 | "Training" that was really a failed setup |
| 7 | Outages on peak days | 28 | 4/20 specifically, repeatedly |
| 8 | Sync drift with the state system | 28 | POS and state ledger disagree, and nobody can say which is wrong |
| 9 | Vendor distrust / astroturfing | 24 | Reps in threads, posts allegedly bought or deleted |
| 10 | Usability: screens and clicks | 22 | Too many screens to finish a sale, no useful sorting |

## Verbatims

### Outages cluster on the days that matter

- "But it locks you into its ecosystem and has a poor track record of stability on high sales days like 4/20." (Dutchie, r/weedbiz `1jgsp0b/mj1vwfw`)
- "flowhub went down on 4/20 and never even talked about it" (`1veosoy/p1pjfi9`)
- "i have several clients who say flowhub was down on 4/20 for about 4-5 hours" (`1veosoy/p24tavi`)

### Support is the loudest single complaint

- "I was genuinely shocked by how poor their customer support has been. My background is in restaurants... Both their products and their customer support have been light-years ahead of Dutchie... what's the point of having more features if those features are constantly breaking?" (`1veosoy/p1j46vg`)
- "There is zero customer support. It never works." (`1khx1ge/mygb0ud`)
- "They have since abandoned all communication and we are on our own opening support tickets that never get resolved." (`1khx1ge/myhd54g`)
- "We hear from many retailers who feel abandoned after onboarding." (Meadow's CEO, `1jgsp0b/mxmcnez`)

### Sync drift: the state ledger and the shop's record disagree

- "Basically Dutchie is the POS and the shop's record and Metrc is the state's copy of the legal ledger. Biggest thing that pops up is that these two don't sync at times and then it breaks. So you need to see where the drift happened and if Metrc is outdated or Dutchie is and then you can fix it." (`1v3xg7q/ozgwbr1`)
- Florida, from a dispensary employee: "There are like 10 systems all mandated and regulated by the state, built independently and not designed to work together, that have to be bandaid'd together: Biotrack, MMUR database, ERP/cultivation system, POS, website... It's literally impossible to not have errors." (r/FLMedicalTrees `1v740t7/ozw08ok`)

### Compliance guardrails that silently are not there

- "They set it up for us and it doesn't do things its supposed to like prevent sales to minors or not allow sales over purchase limits." (`1khx1ge/mygb0ud`)
- "If a package gets put 'On Hold', it should be pulled from the sales floor immediately because it can't legally be sold until the hold is resolved... it's easy to miss if nobody is actively monitoring for it." (`1v3xg7q/p0hqsqw`)

### Cost, contracts and paywalled basics

- "It's just expensive." (`1jgsp0b/mj42gfa`)
- "check out the Master Service Agreement. That's where the meat and potatoes of their power over you begins." (`1veosoy/p1kruv7`; the thread itself is titled "Dutchie.. (AUTO)renewal BEWARE")
- "They charge you to have any reporting function." (`1khx1ge/mygb0ud`)

### Training that was really a failed install

- "We had onsite 'training' for three days, the last of which had two people. There was almost no training done in those 3 days. They were trying to set it up and make it work the entire [time], which it still doesn't." (`1khx1ge/myhd54g`)

### Operators are leaving, and some are building their own

- "Some of the bigger players are making the switch from Dutchie to Sweed. Verano and Curaleaf have both switched over all their stores which is over 300 locations." (`1veosoy/p1wgwb2`)
- "one of my clients is a rather large dispensary chain and is leaving flowhub due to the soc2 compliance issues... they just built a custom system to replace flowhub... with claude, lol. passes all compliance. they are ELATED." (`1veosoy/p24tavi`)
- "i am creating my own point of sale with ai, and its working... all dutchie does is get your data from metrc and make it look pretty on their end. use ai and stop paying them more than 1000 a month." (`1v3xg7q/pa6oxph`)
- "Pick a POS that plays nice with other vendors. Dont pick one that says they do it all." (`1khx1ge/mrb7bxi`)

### Trust in vendor voices is low

- "are you a flowhub employee? this seems like something they would post to try to try to rank on SEO." (`1veosoy/p1phi5i`)
- "i turned the ceo away after he offered me $$$ to remove my post and i declined" (`1veosoy/p1qsb7y`)

## The Florida-specific pain, on the record

Source: OMMU Rules Workshop, 2025-10-29, Tallahassee, full transcript. Named speakers
from Trulieve, Surterra, Curaleaf, AYR, The Flowery, INSA, Sunburn, Baxter Law and the
Florida Cannabis Action Network. This is testimony about rules 64-4.221 and 64-4.222,
the exact rules Coontie implements.

1. **Correcting an error is a multi-day operation, not an edit.** "At the harvest where if you make a mistake that's a very expensive and time-consuming mistake. You have to actually go engage the operator of the system and go through a lot of coding and back-end work in order to reverse the error. And you can't really move your inventory until that's done. We're talking about days or weeks sometimes to fix just a common human error." (Christine Senne)
2. **No direct control over their own data.** "We have a lot of issues with having to interface with Bio Track to get help whenever there's an issue. We'd like to be able to control things more directly through a user interface, making data corrections, compliance management." (Devin Baxter, for several MMTCs and CMTLs)
3. **They pay the state's vendor to fix the state's system.** "We spent thousands of dollars charged by Bio Track to try to fix integration issues... most contracts in other states include support for their licensees." (Tim Gunther, The Flowery)
4. **Opening a new location is an email and a multi-day wait.** A new dispensing location needs a unique identifier that requires emailing BioTrack and waiting "a day or two" before product can move.
5. **One product, several routes, several IDs.** Multiple unique product IDs for one product across approved routes "causes inventory management issues" and is "incredibly difficult to keep track of" (Baxter, Senne, Jodi James, Mike Smuts).
6. **Undefined terms drive variance churn.** "Open window" comes from BioTrack and is defined nowhere in rule; some MMTCs must file a new variance request every time they add seeds, even for previously approved strains (Senne).
7. **Integration broke returns.** Returns used to work at any store of an MMTC; after integration a patient must return to the original dispensary or the MMTC builds a workaround. Allotments are not returned to the patient promptly (Baxter).
8. **Manifests forced into separate documents.** Dispensable devices versus dosed products must go on separate manifests, which "creates delays" (Baxter).
9. **Duplicated reporting.** Operators asked to remove a voluntary email report that duplicates data the state already receives through BioTrack, or at least extend it from 12 to 48 hours.
10. **Post-integration reporting is wrong.** Low-THC dispensations are misreported in OMMU's weekly report since integration (Baxter).

## What this means for a KISS product

The complaints cluster into five things a user would actually pay to stop experiencing.
None of them is "more features".

1. **Corrections, with the paperwork built in.** The pain is that a wrong weight takes
   days and a vendor relationship. A guided amend flow, with the 12-hour justification
   generated from the same screen, is the feature.
2. **Drift visibility.** Show me the difference between my record and the state's,
   name which side is wrong, and let me fix it from one place.
3. **Guardrails that are impossible to miss.** Package holds, near-expiry, purchase
   limits, adjustment pending justification, disconnect clock. Surface them; do not
   require someone to remember to check.
4. **Exports and reports that are free and correct.** CSV on demand, in the state's
   own field names, with no paywalled reporting tier.
5. **Onboarding that is days.** Rooms, product IDs, and first lots in a guided first
   run, not a three-day install that ends with support tickets.

Explicitly **not** our pain, and therefore not in scope: e-commerce storefronts, menu
boards, loyalty, payments, AI recommendation engines. Those are what the loudest
vendors compete on, and the operators in this corpus describe them as the parts that
break.

The positioning the corpus supports: **a small, dull, correct system of record that
makes the state conversation short.** Free, readable, and no contract. Trust is the
scarce good in this market, not features.

## Limits of this research

- Reddit was reached through an archive API, not the live site. Comment scores and
  thread context are as archived; a deleted comment cannot be recovered.
- The keyword table is a screen, not a coding study. It measures how many comments
  mention a theme, not how strongly the authors feel.
- Florida's enforcement record for software failures is not public, so nothing here
  quantifies how often these pains cost money. Rule 64-4.210 sets the penalty, not
  the frequency.
- No operator was interviewed. The next tier of evidence is five conversations with
  compliance leads at new licensees, which would also double as the anchor-operator
  search.
