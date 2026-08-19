# Problem Statement — AI-Powered Discovery Engine (Myntra Wishlist Conversion)

**Document status:** v1.1 — baseline for `architecture.md`, `edgecase.md`, `evals.md` and the implementation plan
**Resolved by:** `architecture.md` (all §12 open questions answered there)
**Scope of this document:** the problem *the engine* solves and what it must be able to do. It does **not** contain the answer to the user-research question — producing that answer is the engine's job.
**Product chosen:** Myntra
**Deliverable this feeds:** Part 1 of the assignment (AI Discovery Engine — publicly testable link + 1 slide explaining how it works), and by extension Parts 2–4 (metric decomposition, opportunity selection, problem definition).

---

## 1. Context

Myntra's Growth team has a stated business goal:

> **Increase the percentage of users who purchase at least one item from their wishlist within 30 days of adding it.**

A wishlist save is the strongest pre-purchase intent signal on the platform short of an add-to-bag. Users accumulate dozens to hundreds of saves; only a small fraction convert. The gap between "saved" and "bought" is therefore demand that already exists and is already paid for in acquisition terms.

Two hard constraints frame everything downstream:

- **C-1 — The underlying user problem is not given.** It must be discovered, not assumed. The assignment explicitly withholds it.
- **C-2 — No monetary incentives.** The eventual solution cannot use discounts, coupons, cashback, or price manipulation. This retroactively constrains *discovery* too: an engine that only surfaces "users want it cheaper" produces an unusable insight, so it must be capable of resolving price-adjacent complaints into their non-monetary components (price *transparency*, price *anchoring/loss framing*, *timing* signals) rather than collapsing them into "discount".

A working blueprint already exists (`Docs/Myntra Project's Current solution .pdf`): a KPI-tree decomposition of wishlist→purchase into four funnel stages (A: recall/discovery, B: wishlist-level retrieval, C: item-level decision, D: cart-level), ~13 candidate drop-off hypotheses at Stage C, three candidate wishlisting segments, and a 13-stage decision journey. That blueprint is **the hypothesis space, not the finding.** The engine's job is to populate it with evidence and rank it. Reconciled into a single addressable scheme, it becomes the engine's classification codebook (§5) — the bedrock every number in the output is computed against.

---

## 2. The problem the engine solves

**The PM cannot see the funnel.**

Choosing where to intervene requires knowing which stage (A/B/C/D) loses the most high-intent users and why. That requires Myntra's internal event data — wishlist opens, item clicks, add-to-bag rates, 30-day purchase attribution. It is not available and will not be.

The only substitute is **public user feedback at scale**: app store reviews, Reddit and fashion communities, YouTube comments and haul/unboxing discussion, social conversations, on-platform product reviews and Q&A, and published research on Indian online fashion behaviour. That corpus is large, unstructured, unevenly relevant, contaminated with unrelated complaints (delivery, refunds, app crashes, customer service), and written by people who are not describing a funnel.

So the operative problem is:

> **How does a PM turn a noisy, unstructured, publicly-available corpus of fashion-shopping conversation into a defensible, quantified, source-cited ranking of the barriers preventing wishlist→purchase conversion — reliable enough to bet a product roadmap on, and honest enough to say when the evidence does not support a conclusion?**

### 2.1 Why the obvious approaches fail

| Approach | Why it is insufficient here |
|---|---|
| Manual reading | Thousands of relevant items across 6+ source types. Not tractable in the timeline, and unauditable. |
| Sentiment analysis | Returns polarity, not causality. "Negative about sizing" does not tell you whether sizing blocks a *saved-item* purchase or a *first-discovery* purchase. |
| Review summarisation / one-shot LLM prompt | Produces fluent, unfalsifiable prose. No counts, no provenance, no way to check whether a claim rests on 3 comments or 300. Cannot be defended in a review. |
| Generic topic modelling (LDA/BERTopic alone) | Produces clusters, not decisions. Clusters do not map to funnel stages or to the no-monetary-incentives constraint without a PM framework imposed on top. |
| Off-the-shelf VoC tools | Tuned to CSAT/NPS drivers for a whole app, not to a single micro-funnel between two specific user actions. |

The assignment states this directly: *"Your workflow should go beyond summarizing reviews or performing sentiment analysis. It should enable you to identify, quantify where possible, and compare potential opportunity areas."* **Identify, quantify, compare** are the three verbs the system is accountable to.

---

## 3. Users of the engine

| # | User | Need | Success looks like |
|---|---|---|---|
| U-1 | **The PM (primary)** | Decide which funnel stage, which segment, and which hypothesis to pursue; defend that choice with evidence | Can go from "I have a business metric" to "here is my prioritised user problem, with N citations behind it" without reading raw data |
| U-2 | **Evaluators / mentors (secondary)** | Interrogate the engine live via a public link; test whether the reasoning holds | Can ask an adversarial question and get either a grounded answer or an honest refusal |
| U-3 | **Downstream artefacts** | Slide deck, survey design, interview guide, problem-framing canvas | Engine outputs are directly liftable — numbers, quotes, and charts do not need to be re-derived by hand |

---

## 4. What the engine must do

Four stages, per the blueprint. Each is a functional requirement block.

### FR-1 — Collect (Data Bank)
- **FR-1.1** Ingest public user feedback across at least these source classes: app store reviews (iOS + Play), Reddit and fashion/shopping communities, YouTube comments on hauls/unboxings/reviews, social conversations, on-platform product reviews and Q&A where accessible, and credible published research on Indian online fashion buying behaviour.
- **FR-1.2** Persist every record with provenance: source platform, URL/permalink, author handle (or pseudonymised id), timestamp, and verbatim text. **Nothing enters analysis without a traceable origin.**
- **FR-1.3** Normalise heterogeneous records into one schema so that a Play Store review and a Reddit comment are comparable units.
- **FR-1.4** Deduplicate, language-detect, and handle Hinglish/code-mixed text — a large share of the relevant Indian corpus is not standard English.
- **FR-1.5** Expose the Data Bank to the user through the app: browsable, filterable, searchable. Every downstream claim must be clickable back to its raw evidence.
- **FR-1.6** Record what was collected *and what was excluded*, with the reason. Corpus composition is itself a finding.

### FR-2 — Analyse
- **FR-2.1** Filter for relevance: separate feedback that bears on the **save→purchase decision** from general Myntra complaints (delivery delays, refunds, app performance, customer care). This filter is the single highest-leverage component in the system; a permissive filter destroys every number downstream.
- **FR-2.2** Classify each relevant record against the **hypothesis codebook of §5** — the pre-registered, closed set of every conceivable reason a wishlisted item goes unpurchased. Each record receives a canonical code, funnel stage, journey phase, Exit/Defer outcome, and inferred segment, with **explicit `unknown` wherever the text does not support a label**. The codebook is the bedrock: see FR-5 for the full requirement block.
- **FR-2.3** Multi-label by default. Real feedback carries several barriers at once ("didn't know my size and it got costlier") and forcing one label fabricates precision.
- **FR-2.4** Surface structure the codebook did not anticipate: emergent themes, barrier co-occurrence, and clusters landing in the residual bucket (FR-5.4). The codebook must be able to *grow* from the data, not merely be filled by it — but only through the governance in FR-5.6, never silently mid-run.
- **FR-2.5** Quantify: counts and shares per theme, per source, per segment; co-occurrence matrices; severity and confidence weighting; recency trend where timestamps permit.
- **FR-2.6** Visualise: theme prevalence, stage-wise distribution, segment × barrier matrix, co-occurrence, and evidence-strength per claim. Charts must be readable by a colour-blind reader (assignment guideline) and must show sample size.

### FR-3 — Insight & hypothesis generation
- **FR-3.1** Convert quantified patterns into **insights** (what is true, with numbers) and then into **hypotheses** (what is causing it, testable, falsifiable).
- **FR-3.2** Every hypothesis carries: supporting evidence count, representative verbatims, source diversity, confidence level, **contradicting evidence**, and an explicit statement of what would disprove it.
- **FR-3.3** Rank/compare opportunity areas so the PM can select one — on prevalence, severity, segment fit, solvability without monetary incentives (C-2), and evidence strength.
- **FR-3.4** Emit the artefacts the next phases need: a target-segment recommendation, a prioritised hypothesis set, and a draft interview guide + survey instrument to validate the top hypotheses with 5–6 users (Part 3).
- **FR-3.5** **Falsifiability requirement.** The engine must be able to return "the evidence does not support Stage C being the largest opportunity" if that is what the corpus says. The existing blueprint records an expectation that Stage C dominates; that is a prior, not a result, and the system must not be constructed to confirm it. If the engine cannot contradict its author, it is not a discovery engine.

### FR-4 — Grounded Q&A interface
- **FR-4.1** Answer natural-language questions about the problem statement, corpus, analysis, insights, and hypotheses.
- **FR-4.2** Answer **only** from the collected data and derived analysis. Every answer cites its evidence.
- **FR-4.3** Three-way behaviour on scope, which is the distinguishing feature:
  - **In scope + evidence exists** → answer with citations.
  - **Out of scope, or no evidence** → refuse, and state what is missing.
  - **Partially answerable** → answer the supported part, explicitly name the unsupported part.
- **FR-4.4** Must handle the assignment's canonical questions (why users wishlist; what prevents purchase; residual uncertainties; causes of postponement; how users compare shortlisted items; what they seek off-platform; the role of fit/size/styling/price/reviews/occasion/social validation; intent vs. bookmarking; segment differences; recurring unmet needs) — and hold the line on adversarial or out-of-scope ones.
- **FR-4.5** Publicly accessible, no login, stable for the evaluation window.

---
## 5. The hypothesis codebook — bedrock of the analysis

This section is the analytical core of the engine. Everything in §4 operates **on** this codebook.

### 5.1 Design principle

The engine does **not** discover its categories from the data. It classifies every relevant record against a **pre-registered, closed-set codebook** that enumerates all currently-conceivable reasons a user does not purchase a wishlisted item, plus a residual bucket for what the codebook misses.

This is deliberate, and it is what makes the output quantifiable and comparable:

- **Prevalence needs a denominator.** "34% of save-decision discussion is fit uncertainty" only means something if every record was scored against the same fixed set.
- **Comparison needs commensurability.** Ranking opportunity areas requires codes at the same level of abstraction, mapped to the same funnel.
- **Pre-registration blocks confirmation bias** (R-1). The codebook is fixed *before* the corpus is scored, so the engine cannot quietly invent categories that flatter the expected answer.
- **The residual bucket is the honesty valve.** If a large share of relevant feedback will not fit, the codebook is wrong — and that is a finding, not an error (see §5.7).

The codebook below reconciles the three overlapping hypothesis systems in the blueprint into one addressable scheme.

### 5.2 Reconciling three ID namespaces

The blueprint carries three parallel numbering systems that collide:

| System | Where it lives | Problem |
|---|---|---|
| Stage sub-themes | A1–A3, B1–B3, C1–C9, D1–D4 | Structural, but Stage C's nine sub-themes don't cover everything in the H-list |
| Barrier hypotheses | H1–H15 | Flat list; several map to more than one stage; no stage anchoring |
| Journey drop-off hypotheses | DH1–DH13 | Ordered by decision sequence, adds *phase* (Eliminator / Confidence / Trigger), overlaps H-list |

They also collide literally: **"Recall H1" (Stage A), "H1" (Stage C list), and "Cart H1" (Stage D) are three different hypotheses sharing one label.** A classifier cannot be asked to output "H1".

**Resolution:** one canonical ID per hypothesis — `<Stage><n>[.<m>]` — with every blueprint reference preserved in a crosswalk column so nothing from the original work is lost. Canonical IDs are what the engine emits; H/DH references are for reading the codebook back against your existing docs.

Each code carries four attributes that do analytical work downstream:

- **Phase** — *Eliminator* (a hard gate; fails → user leaves), *Confidence* (a doubt; fails → user defers), *Trigger* (nothing prompts action now).
- **Outcome** — *Exit* (intent destroyed) vs *Defer* (intent intact, decision postponed). **Defer is the winnable population.** Exit mostly is not.
- **Solvable without monetary incentive** — the C-2 filter, applied at the hypothesis level.
- **Observable workaround** — what users do instead. Workarounds are the strongest evidence in the corpus: a user who builds a workaround is *proving* the unmet need exists, without being asked.

---

### 5.3 Stage A — Recall / Discovery

**Metric:** % of wishlist-adders who open the wishlist within 30 days
**Population:** saved an item, never came back to the list

| Code | Sub-theme | Barrier in the user's words | Root cause | Blueprint ref | Outcome | Solvable w/o money |
|---|---|---|---|---|---|---|
| **A1.1** | No trigger to return | "I forgot I even had a wishlist" | List is write-only — it never reaches back out | Recall H1 | Defer | Yes |
| **A1.2** | No trigger to return | "Nothing told me anything had changed" | No price / stock / low-inventory signal | new | Defer | Yes |
| **A1.3** | No trigger to return | "It was one tap while scrolling" | Save never encoded as a decision | new | Defer | Yes |
| **A2.1** | Access friction | "I don't know where the wishlist lives" | Entry point buried in nav | Recall H2 | Defer | Yes |
| **A2.2** | Access friction | "I saved on phone, I shop on laptop" | Cross-device / logged-out saves | new | Defer | Yes |
| **A3.1** | No reason to return | "It's the same list as last time" | Static list, no new information since save | new | Defer | Yes |
| **A3.2** | No reason to return | "I just search for it again" | Users re-enter via feed/search instead | new | Defer | Yes |

> **Expected under-detection.** Stage A is the corpus's structural blind spot (§8): forgetting produces no complaint. Low A-counts must be reported as *plausibly artefactual*, never as evidence Stage A is small.

---

### 5.4 Stage B — Wishlist-level retrieval

**Metric:** % of wishlist-openers who click into the item they came for
**Population:** opened the list, couldn't get to the item

| Code | Sub-theme | Barrier | Root cause | Blueprint ref | Outcome | Solvable w/o money |
|---|---|---|---|---|---|---|
| **B1.1** | Retrieval failure at scale | "I can't find the kurta I saved last month" | No sort, filter, or search within wishlist | H1 | Defer | Yes |
| **B1.2** | Retrieval failure at scale | "Old stuff is at the bottom forever" | Reverse-chronological only | H1 | Defer | Yes |
| **B1.3** | Retrieval failure at scale | "It's one long undifferentiated grid" | No grouping by category, occasion, or intent | new | Defer | Yes |
| **B2.1** | Dead inventory clutter | "Half of it is sold out" | OOS items still occupy the grid | H1 | Defer | Yes |
| **B2.2** | Dead inventory clutter | "This one just vanished" | Delisted products, brand exits | new | Defer | Yes |
| **B2.3** | Dead inventory clutter | "I've saved the same thing three times" | No duplicate detection | new | Defer | Yes |
| **B3.1** | Recognition failure | "I don't remember why I saved this" | Thumbnail-only, no save context captured | new | Defer | Yes |
| **B3.2** | Recognition failure | "Which colour did I want?" | Variant not preserved on the tile | new | Defer | Yes |

---

### 5.5 Stage C — Item-level decision

**Metric:** % of item-viewers who click 'Add to Bag'
**Population:** found the item, opened it, didn't add it

The deepest stage — where sub-themes become candidate segments. C1–C9 are the blueprint's originals, preserved exactly. C10–C14 are additions, each with its provenance stated (§5.6 explains why each was needed).

| Code | Sub-theme | Phase | The unresolved question | Blueprint ref | Outcome | Solvable w/o money | Observable workaround |
|---|---|---|---|---|---|---|---|
| **C1** | Fit & size uncertainty | Confidence | "Which size, when every brand runs different?" | H6(part), H11(part), DH5 | Defer | **Yes** | Ordering two sizes; checking a garment they own; abandoning |
| **C2** | Physical-vs-digital gap (material & quality) | Confidence | "Will the fabric, colour and quality match the photos?" | H6(part), DH6 | Defer | **Yes** | Zooming images; hunting buyer photos; asking in comments |
| **C3** | Styling & self-image / wardrobe integration | Confidence | "Will it look good on *me*, with what I own?" | H4, DH9 | Defer | **Yes** | Screenshotting to compare with wardrobe; Pinterest checks |
| **C4** | Real-buyer evidence insufficient | Confidence | "What did people who actually received it say?" | H5, H13, DH7 | Defer | **Yes** | Reading reviews for on-body photos, sizing comments, complaint patterns |
| **C5** | Comparison paralysis / shortlist commitment | Confidence | "Which of these five do I actually pick?" | H2, H3, DH11 | Defer | **Yes** | Opening multiple tabs; screenshot collages; deferring |
| **C6** | Value & price uncertainty | Eliminator | "Is this the right price, and is now the right time?" | H7, H9, H10, DH2 | Exit / Defer | **Partly** — price-history transparency and loss-framing, not the price itself | Cross-platform price checks; waiting on sale calendars |
| **C7** | Fulfilment & returns trust (risk floor) | Eliminator | "If it's wrong, how painful is sending it back?" | H8, DH3 | Exit | **Partly** — return-effort disclosure, not the policy | Reading return policy; preferring COD; buying in-store |
| **C8** | Availability at decision time | Eliminator | "My size isn't there right now" | H11, DH1 | Exit | **No** — supply-side | Waiting; checking back manually; buying elsewhere |
| **C9** | Intent was never live ⚠️ | — | *(no question — no live intent)* | H12, H14 | n/a — correct behaviour | **N/A** | None |
| **C10** | Approval & permission | Confidence | "I need to check with my partner/parent" | blueprint "New C4b", DH10 | Defer | **Yes** | Sharing the link; group polls; waiting for a reply |
| **C11** | Need extinguished | — | *(bought it, or a substitute, elsewhere)* | blueprint "New C6b", H9(part), DH8(part) | Exit — lost to competitor | **Partly** | None |
| **C12** | Desire decay / impulse cooled | Confidence | "Do I still actually want this?" | H15, DH4 | Exit | **Partly** | None |
| **C13** | No trigger to act now | Trigger | "What makes today different from tomorrow?" | DH12 | Defer | **Yes** | Indefinite deferral; waiting for an unnamed prompt |
| **C14** | Off-platform verification exit | Confidence | "Let me go check this properly somewhere else" | H5(part), DH8 | Defer / lost to competitor | **Yes** — highest strategic value | Leaving for YouTube unboxings, Reddit, Instagram, price comparison |

> **C9 is a denominator control, not an opportunity.** Records coded C9 describe users whose non-purchase is *correct behaviour* — no live intent existed. Counting them inside the addressable opportunity inflates it. They must be quantified and then excluded from opportunity sizing, which is exactly why the code exists.

**Decision-journey ordering (DH1–DH13) is preserved as a separate attribute.** The journey is sequential and gated: Eliminators (C8 → C6 → C7) are evaluated before Confidence questions (C12, C1, C2, C4, C14, C3, C10, C5) and finally the Trigger (C13). This matters for prioritisation — solving a Confidence barrier for a user who already failed an Eliminator changes nothing. The engine must therefore report **where in the sequence** each user's blocking barrier sits, not just which code fired.

---

### 5.6 Stage D — Cart-level

**Metric:** % of add-to-bag users who complete purchase
**Population:** added to bag, didn't pay

| Code | Sub-theme | Barrier | Blueprint ref | Outcome | Solvable w/o money |
|---|---|---|---|---|---|
| **D1** | Cost surprise | Shipping, platform/convenience fee, COD charge, tax revealed late | Cart H1, DH13 | Exit | **Yes** — a disclosure fix, not a discount; survives C-2 cleanly |
| **D2** | Mechanical friction | Payment failure, no preferred method, OTP drop, pincode rejected at checkout | new, DH13 | Exit | **Yes** — cheapest win available anywhere in the funnel |
| **D3** | Late-revealed terms | Delivery date too late for the occasion; item turns out non-returnable | new | Exit | **Yes** — an information-timing problem |
| **D4** | Final reconsideration | Basket total triggers second thoughts; cart used as a holding pen | new | Exit | **Partly** — overlaps C6; count once, at D |

---

### 5.7 Gaps found while reconciling — and how they were closed

Merging the three systems exposed five holes. Each is closed above; each is flagged here because they are changes to your framework, not just formatting.

| # | Gap | Resolution |
|---|---|---|
| 1 | **H15 (impulse cooled off) had no home in C1–C9.** It is not C9 — C9 means intent never existed; H15 means intent existed and *decayed*. Different populations, different solves. | New **C12** |
| 2 | **DH12 (trigger to act now) had no C sub-theme.** It is also the only hypothesis the blueprint marks as spanning two stages (A / C). | New **C13**, cross-linked to A1.2 |
| 3 | **C4 conflated two different failures.** DH7 = on-platform review evidence is thin/stale/photo-less (a *content* problem). DH8 = user leaves the platform to verify and the session dies (a *retention* problem). Same trigger, opposite solves. | Split: **C4** (evidence insufficient) and **C14** (off-platform exit) |
| 4 | **Three "H1"s.** Recall H1, Stage-C H1, and Cart H1 are unrelated hypotheses sharing a label — unusable as classifier output. | Canonical stage-prefixed IDs; blueprint refs retained in a column |
| 5 | **"Solvable without monetary incentive" was defined only for Stage C** (and truncated in the source doc), despite being the binding constraint C-2 on every code. | Populated for all four stages |

**Crosswalk — H1–H15 to canonical codes** (so nothing in your existing hypothesis list goes unclassified):

| H | Canonical code(s) | | H | Canonical code(s) |
|---|---|---|---|---|
| H1 | A1.1, B1.1, B1.2, B2.1 | | H9 | C6, C11 |
| H2 | C5 | | H10 | C6 |
| H3 | C5 | | H11 | C1, C8 |
| H4 | C3 | | H12 | C9 |
| H5 | C4, C14 | | H13 | C4 |
| H6 | C1, C2 | | H14 | C9 |
| H7 | C6 | | H15 | **C12** *(newly homed)* |
| H8 | C7 | | | |

---

### 5.8 User segments — the second analytical axis

Barriers alone don't select a target. The same code means different things depending on **why the item was saved**. Segment is therefore a first-class classification dimension, not a filter applied afterwards.

| Code | Segment | Why they saved | Re-engagement (T≤30d) | Intent & urgency | Price sensitivity |
|---|---|---|---|---|---|
| **S1** | **Buying-soon** — immediate need | A live need, now | **Very high** — active re-engagers | **High** | **Low** — has a budget range and will pay inside it |
| **S2** | **Future-event / conditional** | A dated occasion, a sale, a salary cycle, or a size restock | **Moderate** — returns for price change and size checks | **Moderate** | **High** — waiting for sales, price drops, better deals |
| **S3** | **Bookmarker / taste archive / aspirational** | Collection, reference, inspiration | **Very low** — dormant, may never return | **Zero** | **N/A** |

**Inference signals the classifier looks for** (text-based, since the corpus has no user records):

| Segment | Positive signals | Typical give-away phrasing |
|---|---|---|
| S1 | Named near-term deadline; delivery-speed concern; active checking; decision language | "need it by Friday", "will it arrive before…", "should I order it or not" |
| S2 | Named future occasion; conditional waiting; explicit price/stock trigger | "saving it for the wedding", "waiting for EOSS", "after salary", "if it comes back in my size" |
| S3 | Collection/inspiration framing; no purchase language; volume-of-saves talk | "just saving for later", "my wishlist has 200 items", "window shopping", "someday" |

Three rules that keep this honest:

1. **`unknown` is the expected majority.** Public text rarely states why someone saved. Forcing every record into a segment fabricates the entire segmentation. The engine reports segment coverage explicitly and computes segment-conditional results only on the labelled subset, with n shown.
2. **S3 non-conversion is not a problem to solve.** Bookmarkers behave correctly by not buying. They must be sized and then removed from the addressable opportunity — the same discipline as C9. Leaving them in the denominator makes the opportunity look larger than it is and is one of the easiest ways to produce a wrong answer that survives review.
3. **Segment is a hypothesis about the corpus, not a fact about Myntra's base.** Relative segment sizes from public discussion reflect who posts, not who saves (§8).

**Expected barrier profiles — pre-registered predictions, to be tested rather than assumed:**

| Segment | Predicted dominant codes | Predicted outcome mix |
|---|---|---|
| S1 | C1, C2, C4, C8, C14 — confidence and availability under time pressure | Mostly **Defer**, short window → winnable |
| S2 | C6, C13, A1.2, C8 — price/timing/trigger and restock | **Defer**, long window → needs a trigger |
| S3 | C9 by definition | Not addressable |

If the corpus contradicts these predictions, that is a finding worth more than a confirmation — record it as such (FR-3.5).

---

### 5.9 FR-5 — Codebook-driven classification (requirements)

- **FR-5.1** Every relevant record is scored against the **complete** codebook of §5.3–5.6 (33 canonical codes across four stages: 7 · 8 · 14 · 4), not a subset chosen per record.
- **FR-5.2** Multi-label with confidence per label (per FR-2.3). Where a record shows a *sequence* ("price went up and then I couldn't find my size"), capture the **blocking** code — the earliest failure in journey order — as primary.
- **FR-5.3** Every record also receives: funnel stage, phase (Eliminator/Confidence/Trigger), outcome (Exit/Defer), segment (S1/S2/S3/`unknown`), and workaround-present (bool).
- **FR-5.4** **Residual bucket `Z-99`** — relevant to the save→purchase decision but not fitting any code. If Z-99 exceeds **15%** of relevant records, the codebook is treated as incomplete: cluster the residual, propose new codes, version the codebook, re-run classification.
- **FR-5.5** Required cross-tabulations, each with n and source mix:
  - code × prevalence (the headline ranking)
  - **segment × code** (the artefact that selects the target segment)
  - code × code co-occurrence (which barriers compound)
  - code × source type (triangulation — a code carried by one source only is downgraded)
  - code × solvable-without-money (the C-2 filter applied to the ranking)
  - Exit vs Defer split per stage (Defer = addressable population)
  - workaround prevalence per code (strongest unmet-need evidence)
- **FR-5.6** **Codebook governance.** The codebook is versioned and frozen before scoring. A new code requires: a minimum record count, a root cause distinct from every existing code, **and a distinct solve**. Version changes force full re-classification (NFR-3).
- **FR-5.7** The codebook is visible in the deployed app, and every code links to its supporting records (NFR-1).

---

## 6. Non-functional requirements

| # | Requirement | Rationale |
|---|---|---|
| NFR-1 | **Traceability** — every number and claim resolves to raw records | The entire credibility of the output rests on this; it is what separates the engine from a chatbot with opinions |
| NFR-2 | **Calibrated honesty** — refusals and "insufficient evidence" are correct outputs, not failures | An engine that always answers is an engine that sometimes invents |
| NFR-3 | **Reproducibility** — same corpus + same config → same classifications and counts (within stated tolerance) | Numbers that move between runs cannot be put on a slide |
| NFR-4 | **Auditability** — prompts, model versions, filter rules, and exclusions are inspectable | A mentor should be able to ask "how did you get 34%?" and be shown |
| NFR-5 | **Latency** — Q&A responses fast enough for live interrogation | The link will be tested interactively during evaluation |
| NFR-6 | **Cost** — runs within a personal-project budget; heavy analysis is batch/cached, not per-query | Full-corpus LLM classification per question is not affordable |
| NFR-7 | **Legality & ethics** — public data only, platform ToS respected, authors pseudonymised, no PII in outputs | Public availability is not consent to identify individuals |
| NFR-8 | **Deployability** — a public URL that a stranger can use unassisted | Explicit deliverable |

---

## 7. Explicit non-goals

- **NG-1** Not a general-purpose PM research assistant. Bound to one question: barriers to wishlist→purchase conversion on Myntra (C-1 constraint from the blueprint).
- **NG-2** Not a replacement for primary research. It selects and sharpens what the 5–6 interviews should test; interviews remain the validation step (Part 3).
- **NG-3** Not a source of true funnel metrics — see §8.
- **NG-4** Not the MVP. The MVP (Part 5) is a separate, user-facing product addressing the *discovered* problem. Conflating the two is a failure mode to avoid.
- **NG-5** Not a real-time monitor. Batch collection over a fixed window is sufficient.
- **NG-6** No scraping behind logins, no paywalled or private-community data.

---

## 8. Central methodological caveat — proxy data, not funnel data

The blueprint says: *"we need to know where we find the highest drop-off rate. This requires app data … you have to get online user feedback as a proxy."* This is right, and its consequence must be stated plainly and carried into every output:

**Public feedback cannot measure drop-off rates.** It measures **who talks about what, how often, and how intensely.** These differ systematically:

- People complain about what is *frustrating*, not what is *frequent*. A silent drop-off (Stage A: "I forgot the wishlist existed") is under-represented precisely because it generates no emotion worth posting about — while return-and-refund pain is loudly over-represented and sits outside the save→purchase decision entirely.
- Reddit and YouTube skew younger, more urban, more English-fluent, and more deliberate than Myntra's full base.
- App store reviews skew bimodal — one-star and five-star — and toward transactional failures.
- Volume across sources reflects platform activity, not user population.

**Therefore the engine outputs an *evidence-weighted opportunity ranking*, explicitly labelled as such — never a claimed conversion or drop-off percentage.** Mitigations to build in, not bolt on:

1. Report prevalence as *share of relevant discussion*, always with n and always per source.
2. Triangulate: a theme corroborated across three source types outranks one that dominates a single source.
3. Weight by source-bias profile and state the weighting.
4. Carry a known-blind-spots section — Stage A silence is the leading candidate.
5. Treat the ranking as a **hypothesis prioritiser** feeding interviews and a survey, which is where causal claims actually earn their status.

An engine that reports "Theme C = 47% of drop-off" is lying with a number. An engine that reports "Theme C accounts for 47% of save-decision-related discussion (n=612, across 4 source types; under-counts Stage A by construction)" is doing the job.

---

## 9. Success criteria

The engine is done when:

- **AC-1** A user with no context reaches the public URL and can, unassisted, browse the Data Bank, view the analysis, read the hypotheses, and ask questions.
- **AC-2** Every quantified claim in the output is traceable to raw records in ≤2 clicks.
- **AC-3** The engine answers all ten canonical assignment questions (FR-4.4) with cited, corpus-grounded answers.
- **AC-4** The engine correctly refuses an out-of-scope question (e.g. "what is Myntra's revenue?") and correctly partial-answers a mixed one, without being told to.
- **AC-5** It produces a ranked comparison of opportunity areas across Stages A–D with counts, confidence, and stated limitations — sufficient to justify segment/opportunity selection for Part 4.
- **AC-6** It produces ≥1 insight that is **not** already in the pre-existing hypothesis list (H1–H15 / DH1–DH13). Reproducing only the author's priors means the corpus was not actually mined.
- **AC-7** Every hypothesis states what would falsify it.
- **AC-8** The whole mechanism is explainable in one slide (deliverable requirement).
- **AC-9** A held-out sample of records, hand-labelled, shows classification agreement above a threshold set at design time (target: ≥80% on the relevance filter, ≥70% on code assignment). Numbers derived from an unvalidated classifier are decoration.
- **AC-10** Every one of the 33 canonical codes in §5 has been scored across the full corpus — including those returning zero or near-zero counts. A code with no evidence is a reportable result (especially at Stage A, per §8); a code that was never *checked* is a hole in the analysis.
- **AC-11** The residual bucket `Z-99` sits below 15% of relevant records, or the codebook has been revised and re-run (FR-5.4).
- **AC-12** The segment × code matrix is populated with n and coverage shown, C9 and S3 are sized and then excluded from opportunity sizing, and the resulting target-segment recommendation is justified against the matrix rather than asserted.

---

## 10. Assumptions

- **A-1** Sufficient public Myntra/Indian-fashion feedback exists to support meaningful counts. *Still unverified — the pilot in `architecture.md` §5.2 measures per-source yield before the full run. Corpus target is set at **2,000 relevant records**; at that scale the leading codes carry usable counts while the tail is under-evidenced by construction, handled by the minimum-n gate in `architecture.md` §9.4.*
- **A-2** LLM classification against a fixed PM framework is reliable enough to be trusted after validation (AC-9).
- **A-3** Users' stated reasons approximate their actual reasons well enough for prioritisation. (People rationalise. Interviews partially correct for this; nothing fully does.)
- **A-4** Wishlist behaviour discussed generically about "online fashion shopping" transfers to Myntra specifically — flagged where a claim rests on non-Myntra sources.
- **A-5** The four-stage decomposition (A/B/C/D) is a valid and complete-enough carve of the funnel. FR-2.4 exists to catch it if it is not.
- **A-6** The §5 codebook is *near-exhaustive* — it enumerates the plausible causes of wishlist non-purchase well enough that residual unclassifiable feedback stays under 15%. The blueprint states the honest limit plainly: hypothesis generation cannot guarantee completeness, so the core problem could still sit outside the list. `Z-99` + FR-5.4 is the mechanism that would expose that, and it is the only one available.
- **A-7** Segment is inferrable from public text often enough to make segment-conditional analysis meaningful. If labelled coverage comes back very low, segment findings degrade to directional and must be reported that way.

---

## 11. Key risks to the engine itself

| # | Risk | Consequence | Mitigation |
|---|---|---|---|
| R-1 | Confirmation bias — engine built to validate the pre-registered "Stage C wins" | The discovery is theatre | FR-3.5; pre-register the framework before analysis; report Stage A/B/D counts with equal prominence |
| R-2 | Relevance filter too permissive | Every downstream number is inflated by irrelevant complaints | FR-2.1 + hand-labelled validation (AC-9) |
| R-3 | LLM confabulation in Q&A | Confident invented answers destroy credibility live, in front of evaluators | Retrieval-grounded answers only; mandatory citations; refuse-by-default (FR-4.2/4.3) |
| R-4 | Thin corpus for a specific sub-theme | Over-reading 8 comments as a trend | Minimum-n thresholds before a theme is ranked; show n everywhere |
| R-5 | Source-mix bias | Ranking reflects Reddit's demographics, not Myntra's | §8 weighting + triangulation + explicit blind-spot reporting |
| R-6 | Quantification illusion | Precise-looking percentages read as funnel truth | §8 labelling discipline enforced in the UI copy, not just the docs |
| R-7 | Collection blocked (rate limits, ToS, API changes) | Timeline risk | Multiple source paths; snapshot the corpus early; degrade to smaller-but-cited over larger-but-fragile |
| R-8 | Scope creep into the MVP | Engine ships half-built because effort went to the product | NG-4; the engine is a Part 1 deliverable with its own definition of done |
| R-9 | **Codebook blindness** — a closed set cannot find what it does not list | The true root cause is invisible no matter how much corpus is processed | `Z-99` residual bucket with a hard 15% revision trigger (FR-5.4); A-6 states the limit openly; interviews (Part 3) are the real backstop |
| R-10 | Forced segment labels on text that doesn't support them | Segmentation is fabricated, and the target-segment choice rests on nothing | `unknown` is a first-class label; segment-conditional results computed only on the labelled subset, with coverage shown (§5.8) |
| R-11 | Counting C9 / S3 inside the opportunity | Addressable opportunity is inflated — a wrong answer that survives casual review | Size them explicitly, then exclude (AC-12) |

---

## 12. Open questions — resolved

All ten are answered in `architecture.md`. Recorded here with their resolutions so this document stays self-contained.

| # | Question | Resolution | Where |
|---|---|---|---|
| 1 | Corpus size target | **2,000 relevant records**; per-source yield measured on a pilot first | arch §5.2, §9.3 |
| 2 | Collection mechanism | Four collectors — Play Store, App Store, Reddit (PRAW), YouTube Data API — plus agent-sourced curated research | arch §5.1 |
| 3 | Classification approach | Two-pass hierarchical classification on a frontier model, **plus** independent inductive clustering, **plus** reconciliation of the two | arch §6.2, §6.4, §6.5 |
| 4 | Retrieval design for Q&A | Plan → five parallel retrieval channels → deterministic gate → contracted synthesis → code-level verification. No runtime vectors | arch §8 |
| 5 | Stack | Offline Python pipeline writing frozen artifacts; read-only Streamlit app; OpenAI models; SQLite + Parquet | arch §2, §3 |
| 6 | Weighting scheme | Evidence-strength composite (prevalence, source diversity, counterfactual rate, workaround rate, confidence, recency) with user-adjustable weights and live sensitivity analysis | arch §6.5, §7.2 |
| 7 | Ground-truth set | 150–200 stratified records, labelled in-app on **pilot** output before the full run — a debugging tool, not a report card | arch §6.6 |
| 8 | Codebook prompt strategy | Stage first, then codes within that stage only (≤14, not 33), with full boundary notes | arch §6.2 |
| 9 | Blocking-code determination | Minimum `journey_rank` among assigned codes above a confidence floor | arch §6.5 |
| 10 | Segment inference confidence | Threshold 0.6; below it `unknown`, and `unknown` is reported with coverage rather than hidden | arch §6.3 |

**Open questions now sit in `edgecase.md`** — the failure modes each of these resolutions creates.

---

## 13. Glossary

| Term | Meaning here |
|---|---|
| **Business metric** | % of users purchasing ≥1 wishlisted item within 30 days of adding it |
| **Product outcome** | A user behaviour that, if it changes, moves the business metric (wishlist opens, item clicks, add-to-bag) |
| **Opportunity** | A user problem, viewed from the business side |
| **Hypothesis** | An unvalidated opportunity/user problem |
| **Data Bank** | The provenance-preserving store of collected raw feedback, browsable in-app |
| **Stage A/B/C/D** | Recall/discovery · wishlist-level retrieval · item-level decision · cart-level, per the KPI-tree decomposition |
| **Segment** | S1 buying-soon · S2 future-event/conditional · S3 bookmarker — derived from *why* the user saved (§5.8) |
| **Codebook** | The pre-registered closed set of 33 canonical hypothesis codes (§5) every relevant record is scored against |
| **Canonical code** | A stage-prefixed hypothesis ID (A1.1, C14, D2…) replacing the blueprint's three colliding namespaces |
| **Phase** | Eliminator (hard gate → exit) · Confidence (doubt → defer) · Trigger (no reason to act now) |
| **Outcome** | Exit (intent destroyed) vs Defer (intent intact, postponed). Defer is the winnable population |
| **Z-99** | Residual bucket — relevant to the save→purchase decision but fitting no code; >15% forces codebook revision |
