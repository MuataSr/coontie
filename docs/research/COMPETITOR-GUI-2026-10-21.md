# Competitor GUIs: what the incumbent MMTC and dispensary systems actually look like

Recon for the Coontie interface increment. Run 2026-10-21. Every claim below is either a
screenshot I looked at, a help-centre article I fetched, or a quote from our own operator-pain
corpus (`docs/research/PAIN-POINTS-2026-10-21.md`). Coverage is uneven and the gaps are listed
rather than smoothed over.

## 1. Method, and what I could not see

I did not log into any competitor system, and I did not bypass a login wall. What follows comes
from four surfaces that are public by design: their help centres (which document the GUI
screen by screen), their marketing screenshots (which show the GUI, though sometimes only a
staged version of it), their product documentation trees (which reveal the module structure),
and our existing corpus of 393 operator comments.

| Vendor | Help centre | GUI seen directly | Verdict on coverage |
|---|---|---|---|
| **Canix** | 309 public articles, 18 categories, 70 sections | **Yes**, 2 real product screenshots from their own docs | Strong: navigation, table columns, bulk actions, status vocabulary |
| **Dutchie** | 949 public articles, 3 categories, 100 sections | No screenshot reviewed; structure only | Strong on structure, thin on pixels |
| **Treez** | Public Intercom help centre, collections with per-collection article counts | **Yes**, one real home-dashboard screenshot | Good on landing screen, no back-office screen |
| **Cova** | Salesforce-backed support portal (hard to enumerate) | **Yes**, one POS screenshot | Good on the register, nothing on back office |
| **Flowhub** | Public Intercom help hub | Image URL returned 401 | Structure only |
| **Flourish** | Public docs tree, 20 collections | No | Good on modules, no pixels |
| **Sweed** | Help centre **login-gated**: "You must be signed into the Sweed Portal to view help articles" | No | Closed; nothing verified |
| **Alleaves** | "Knowledge Center" of demos and walkthroughs, no article tree | No | Nothing verified beyond the fact that it exists |
| **BioTrack** | Help API answers **401 Unauthorized** | No | Closed to anonymous readers |

Two honesty notes on the screenshots. Cova's "Analytics" marketing image is a **generic
Google-Analytics-style dashboard** (Top Channels, Sessions, Conversions, Organic Search,
Direct) and is not their product UI, so I did not use it as evidence about their interface. One
Treez image labelled "POS" turned out to be an isometric illustration of a card terminal, not
software. Marketing pages stage their product; only the help-centre screenshots are the real
thing.

## 2. The shape they all share

Five patterns repeat across the systems I could see, and they define what "an MMTC system"
looks like to a Florida operator today.

1. **A persistent left rail, grouped by verb.** Canix groups its navigation as *Operate*
   (Dashboard, Cultivation, Inventory Management, Production & Forecast, Audits, Task
   Management), *Transact* (Procurement, Sales Management, Marketplace) and *Analyze & Support*
   (Business Intelligence). Treez uses an icon-only rail with no text labels at all.
2. **A facility or licence switcher at the top of the rail.** Canix shows *"Viewing
   License/Facility: Canix AZ Standalone"*. Multi-site operators live in this control.
3. **The screen is an enterprise grid, not a form.** Canix's Cannabis Inventory screen carries
   columns `Tag`, `Facility`, `Status`, `Item`, `Type`, a kebab menu per row, a column chooser
   on the right edge, filters rendered as removable chips (`Facility`, `2 Rows Selected`,
   `Clear All`), and a footer reading *"Showing 4978 of 4978 records • 2 selected"*. One demo
   dataset showed **36,609 records**.
4. **Bulk actions are where the product lives.** Selecting rows opens an Actions menu with
   *Combine Packages, Unpack into Plantings, Create Sales Order, Create Transfer, Change
   Location, **Adjust Packages**, Change Items, Deactivate Packages, Update Availability
   Status, Assign Lot IDs, Assign Package Owner, Assign Non-Cannabis Inventory*. Everything an
   operator actually does to inventory is a bulk operation on a selection.
5. **Status is a coloured pill with a lot of vocabulary.** Canix uses *Available To Sell*
   (green), *Allocated* (peach), *Sell ASAP* (pink), *In Quarantine* (pink), *In Progress*
   (blue), *Ready for Production*. A status pill is the interface's way of telling an operator
   where a package stands with the state.

## 3. Vendor by vendor

### Canix (the closest thing to our lane)

**Navigation** is the three-group rail above, with a per-licence selector and a
`Favorites` section that pins frequently used screens. The register is not their centre of
gravity; inventory is.

**What it gets right.** The inventory table is genuinely good at its job: scan-or-type search
on the tag column, per-column filters, saved views, a column chooser, and a footer that tells
you what you are looking at. Status pills carry department meaning. The bulk Actions menu
means an operator can adjust forty packages in one motion, which is what a cultivation or
processing day actually looks like.

**What it costs the operator.** The vocabulary is enormous. Their own documentation template
for every feature runs *Glossary → Prerequisites & Setup → Step-by-Step Instructions →
Important Considerations → System Impacts & Dependencies → Troubleshooting Common Issues*,
which is an honest description of how much a user has to hold in their head to do one thing.
Their inventory article opens by listing the confusions the screen is meant to resolve
("Investigating quantity discrepancies", "Understanding COGS data", "Executing recalls").

**The number that matters most:** **142 of their 309 help articles (46%) are titled "(old user
interface)"**. Nearly half their documentation describes a UI they no longer ship. That is a
self-reported measure of how expensive a redesign is when the product is a set of screens
operators were trained on.

**They ship an AI category.** Six articles sit under *AI Tools & MCP* (four AI Tools, two MCP).

**They document Florida specifically.** 35 articles mention BioTrack in the title and one of
the BioTrack sections is Florida (27 articles in the full section listing), covering
*Create Plants from Mother Plants (BioTrack FL)*, *Apply Ingredients to Package Inventory
(BioTrack FL)*, *Destroy Packages (BioTrack FL)*, *Manage Incoming BioTrack Transfers*, *Create
Lab Sample*, *Schedule Plant Destruction*, *Apply Plant Additives*.

### Dutchie (the largest corpus, and the most support-shaped)

949 articles in three categories: **Dutchie Point of Sale** (417), **Dutchie E-Commerce** (126),
and Product Announcements (6). Twenty-three US states appear by name, plus 46 Metrc articles
and 23 BioTrack articles.

The shape of the documentation is the finding: **52 articles carry "troubleshooting" in the
title**, and the POS category has separate troubleshooting sections for discounts (22),
inventory (9), reports (8), delivery (8), traceability (8), user permissions (7), loyalty (6),
hardware (3), settings (3) and the register (1). A knowledge base that large, organised that
way, is a product where things break often enough that the vendor staffed a library for it.

### Treez

Six visible collections: *Treez Ecommerce* (102 articles), *Loyalty* (34), *Taxes* (24), *Users
& Permissions* (26), *Hardware* (27), *Integrations & API* (38), plus *Getting Started &
Training* and *Sell Treez POS*.

The **home screen** is the most striking thing I saw all day. On the landing page after login
there are: a dark green header, an icon-only vertical rail with no labels, a *"Welcome David,
Last updated 9:45 am"* banner, *"Register 4"* in the top right, a **Content Hub** of
vendor-marketing articles ("How to Empower Budtenders with Data"), an **Events** block with
*RSVP* buttons for a webinar on California excise tax, a **Resource Hub**, and a card with the
operator's named customer success manager. **No inventory, no compliance fields, no work
queue.** The first screen after login is a marketing surface.

### Cova

The register is a two-pane touch interface: product browser on the left with a category row
(*All Products, Medical, Recreational, Merchandise, Concentrates, Edibles*) and a count in the
header (*"Recreational (139)"*), cart on the right with the customer's name, loyalty points
(*"960 Points"*, *"Rewards Available"*), a green progress bar toward a reward threshold, tax
and total, *"Save as Order"* and a blue *Pay*. Blue accents, generous touch targets, designed
for a tablet in a budtender's hand. No purchase-limit warning or compliance modal was visible
on that screen.

### Flowhub, Flourish, Sweed, Alleaves, BioTrack

- **Flowhub** documents *Cashier / Sales*, *Hardware* (one collection is described only as
  "Hardware resources for Maui", a name I did not chase down), *Marketing / Loyalty* and *Billing*. Documentation only; their product images sit behind a
  signed CDN URL that returned 401.
- **Flourish** publishes the cleanest module tree of the group: *Getting Started,
  Configuration & Setup, Cultivation, Flourish Analytics, Android Mobile App, eCommerce,
  Inbound, Inventory, Manufacturing, Outbound, Retail/POS, External API, Integrations,
  BioTrack, Metrc, New Mexico, Accounting, Release Notes, **AI & MCP***. Their top articles
  include *"Connecting to Flourish with an LLM Using Our MCP Server"*.
- **Sweed** gates its entire help centre behind a portal login, so a prospective customer
  cannot read how the product works before buying.
- **Alleaves** runs a "Knowledge Center" of demos, feature walkthroughs and best practices
  rather than a searchable article base.
- **BioTrack** serves 401 to anonymous readers of its help API, which is consistent with its
  position as the state's vendor rather than a customer-facing product.

## 4. What operators say about these screens

From our corpus of 393 substantive comments, the usability cluster is smaller than cost or
churn, and it is specific:

- *"too many screens to finish a sale, no useful sorting"* (cluster 10, *Usability: screens and
  clicks*, 22 hits).
- A Florida dispensary employee, on the whole stack: *"There are like 10 systems all mandated
  and regulated by the state, built independently and not designed to work together, that have
  to be bandaid'd together: Biotrack, MMUR database, ERP/..."*
- On the state/internal split: *"Basically Dutchie is the POS and the shop's record and Metrc
  is the state's copy of the legal ledger. Biggest thing that pops up is that these two don't
  sync at times and then it breaks. So you need to see where the drift happened."*
- On reporting: *"They charge you to have any reporting function."*

The complaint is not that the screens are ugly. It is that there are too many of them, that
sorting and search do not do what the operator needs, and that the record and the state
disagree without telling anyone where.

## 5. What Coontie's GUI should do differently

Ten calls, each tied to what the incumbents do.

1. **Today, not a content hub.** The first screen after login is the work queue: breaches,
   exposures, manifests still out, corrections waiting on a notice, the disconnect clock. Treez
   opens on marketing; we open on what will hurt first.
2. **Text labels on navigation, always.** Treez's icon-only rail is guesswork for a new hire.
3. **One job per screen, and the job is a form.** The incumbents' grids are powerful and
   expert-shaped. We keep grids only where the job is scanning inventory; everywhere else the
   screen is the shape of the record being written.
4. **No bulk-action menu until there is a bulk job.** "Adjust Packages" on a multi-select is
   how an operator changes forty lots without reading any of them, and 64-4.222(12) follows
   every one of those adjustments with a 12-hour notice. Our correction screen is one lot, one
   cause, one drafted notice, deliberately.
5. **Refusals in place, with the citation.** None of the visible screens had a compliance
   warning surface; the rule lives in a training deck. Ours refuses in the write path and says
   which rule.
6. **Status vocabulary that matches the department's, and nothing extra.** Canix's six pills
   are useful but they are their own language. Ours: what the DH5059 event says, plus "needs
   your decision".
7. **Drift gets a permanent tab, not a troubleshooting article.** Dutchie has eight
   traceability-troubleshooting articles. We have a page that names the difference and lets the
   operator decide.
8. **The command bar stays.** No competitor has one; typing `send 200 g blue dream to tampa`
   is faster than any grid, and the parse is auditable.
9. **Print is a first-class output.** The manifest and the audit report end up on paper. None of
   the screenshots show a document anyone would hand to an inspector.
10. **One UI, and it replaces rather than accumulates.** Canix's 46% "(old user interface)"
    articles are the cautionary number. We ship one set of screens, and the docs are generated
    from the same source as the screens.

### Where we can be structurally different, not just prettier

The incumbents' GUIs are built around the **package**: a grid of tags, statuses and bulk
actions. Florida's rule is built around the **event**: 33 record types with timings, and a
12-hour window on most of them. A GUI organised around *what needs recording before the clock
runs out* is a different product from one organised around *what is in the building*, and the
first is what 64-4.222 actually asks for. That is the wedge: Today is a compliance queue, not
an inventory table, and the inventory table is one tab inside it.

## 6. Verification notes

- Screenshots reviewed: Treez home dashboard (marketing page, real UI); Cova POS (marketing
  page, real UI on a tablet); Canix Cannabis Inventory and Canix package-status list (both
  from their own help articles, i.e. the real product).
- Rejected as evidence: Cova "Analytics" tile (generic stock dashboard), Treez `pos.png`
  (illustration of a card terminal), Flowhub product image (401).
- Article counts are from each vendor's public Zendesk API on 2026-10-21: Canix 309, Dutchie
  949. The "(old user interface)" count (142) and the troubleshooting count (52) are title
  regex counts over those two corpora, not vendor statements.
- Sweed, Alleaves and BioTrack were not verified beyond their access posture. I did not
  attempt to defeat a login wall.
- Nothing here is a copy instruction. Names and labels are quoted for identification; the
  design calls in section 5 are independent, which is what keeps the work clear of both
  copyright and trade dress.

## 7. Sources

- Canix help centre and API: `https://help.canix.com/hc/en-us`, `help.canix.com/api/v2/help_center/`
- Dutchie help centre and API: `https://support.dutchie.com/hc/en-us`, `support.dutchie.com/api/v2/help_center/`
- Treez help centre: `https://support.treez.io/en/` · Treez marketing: `https://www.treez.io/`
- Cova marketing: `https://www.covasoftware.com/` · Cova support: `https://support.covasoftware.com/`
- Flowhub help hub: `https://help.flowhub.com/en/`
- Flourish docs: `https://docs.flourishsoftware.com/`
- Sweed help centre (gated): `https://help.sweedpos.com/en/`
- Alleaves knowledge centre: `https://alleaves.com/resources/knowledge-center/index.html`
- Operator corpus: `docs/research/PAIN-POINTS-2026-10-21.md` (393 comments, PullPush archive and
  OMMU workshop transcripts)
