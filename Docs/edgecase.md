# Edge Cases — AI-Powered Discovery Engine

**Document status:** v1
**Reads with:** `problemstatement.md` (requirements), `architecture.md` (design)
**Feeds:** `evals.md` — every case marked **[E]** becomes a test there
**Scale assumption:** 2,000 relevant records from ~8K raw; several cases below exist *because* of that scale

---

## 1. How to read this

Each case carries: what breaks, how it is detected, and what the system does. Cases are IDed `EC-<area>-<n>` so `evals.md` and the implementation plan can reference them.

Two classes, and the distinction matters more than the individual entries:

| Class | Meaning | Priority |
|---|---|---|
| **Loud** | Fails visibly — an exception, an empty chart, a crash | Low. You will find these on the first run |
| **Silent** | Produces plausible, well-formatted, wrong output | **Highest.** These survive review and reach the deck |

§10 is the silent-failure register — the cases that can carry a wrong conclusion all the way into the final presentation without ever looking wrong. If time is short, build the detection for those and let the loud ones surface naturally.

---

## 2. The five that matter most

Ranked by damage × likelihood, ahead of the full enumeration.

| # | Case | Why it tops the list |
|---|---|---|
| 1 | **EC-CLEAN-1 — near-dedupe eats the signal** | Fifty people independently saying "sizes run small" *is the finding*. Dedupe logic cannot distinguish that from spam. Set the threshold wrong and you delete the strongest evidence in the corpus, and the charts look fine afterwards |
| 2 | **EC-CHAT-9 — prompt injection from the corpus** | Records are untrusted user-generated text that goes straight into the model's context. A Reddit comment reading "ignore previous instructions" is a live injection vector in a system you will demo publicly |
| 3 | **EC-CLS-6 — paraphrased `evidence_span`** | Breaks NFR-1 traceability silently. The quote looks real, reads well, and does not exist in the record. Every citation downstream inherits the lie |
| 4 | **EC-PRE-1 — prefilter recall miss** | A record dropped before any LLM sees it is invisible to every downstream metric. There is no error, no log entry showing a *wrong* decision, and no way to notice from the output |
| 5 | **EC-OPS-3 — public chatbot burns the budget** | The deployed URL is public and your API key is behind it. Uncapped, one bored visitor or a crawler empties the credit balance mid-evaluation |

---

## 3. Stage 1 — Collection

| ID | Case | What breaks | Handling |
|---|---|---|---|
| EC-COL-1 | Subreddit private, banned, or renamed | Collector returns zero, run looks "successful" | Assert non-zero per configured source; fail loudly with the source named. **[E]** |
| EC-COL-2 | YouTube comments disabled on a target video | Silent zero for that video | Log per-video yield; a video contributing 0 is recorded, not skipped quietly |
| EC-COL-3 | Rate limit mid-run | Partial corpus, silently truncated | Checkpoint per source with `ingest_run_id`; resume by diffing `native_id`. Never overwrite a partial run |
| EC-COL-4 | `[deleted]` / `[removed]` Reddit bodies | Empty text with valid metadata | Drop at ingest, log as `exclusions/deleted` |
| EC-COL-5 | Very long record (5,000-word post) | Token cost spike; may legitimately carry 6+ barriers | Cap at ~2,000 tokens for classification; if longer, split into paragraph chunks sharing one `record_id`, classify each, union the codes. Never truncate silently |
| EC-COL-6 | Emoji-only or ≤15 chars | No signal, still costs a call | Length floor at clean stage, logged `exclusions/length` |
| EC-COL-7 | Bot / affiliate / promotional spam | Pollutes counts | Heuristic: URL density, repeated template text, channel-promo phrases → `exclusions/spam`. Sampled into the gold set to check the filter isn't eating real records |
| EC-COL-8 | Review-farm text (near-identical 5-stars) | Inflates a source's apparent volume | Caught by near-dupe (EC-CLEAN-1); flagged as `exclusions/farm` rather than merged |
| EC-COL-9 | One user posts 40 comments | Single voice weighted as 40 | Store `author_hash`; report a **distinct-author count** beside every record count. A code carried by 200 records from 12 authors is weaker than 200 from 180 |
| EC-COL-10 | No timestamp from source | Recency analysis breaks | `created_at` nullable; recency computed only over records that have it, with coverage stated |
| EC-COL-11 | Permalink dies after collection | NFR-1 traceability breaks retroactively | `text_raw` is stored verbatim at collect time and is the primary evidence; the URL is corroboration, not the record |
| EC-COL-12 | Comments on a Myntra haul that discuss something else | Off-topic records enter with high apparent relevance | Relevance pass catches; `collect_query` retained so a bad query can be audited and excluded wholesale |
| EC-COL-13 | App-store reviews about the *app*, not shopping | Crashes, login bugs, UI complaints | Explicitly out of scope in the relevance rubric — a large fraction of app-store volume. Expect low yield here and report it (§5.2 pilot) |
| EC-COL-14 | Curated research is paywalled or image-only PDF | No machine-readable text | Store citation + accessible abstract only; mark `text_available = false`. Never quote what was not read |
| EC-COL-15 | **Fabricated curated citation** | A source that does not exist enters the corpus as authority | Every curated item must resolve to a live URL verified at collect time. Unverifiable → rejected. This is agent-sourced material, so the check is mandatory, not optional. **[E]** |
| EC-COL-16 | Scraping blocked outright (ToS, IP ban) | Source unavailable | Four independent sources by design; degrade to smaller-but-cited. Record the gap in corpus composition rather than hiding it |

---

## 4. Stage 1 — Cleaning

| ID | Case | What breaks | Handling |
|---|---|---|---|
| **EC-CLEAN-1** | **Near-dedupe removes genuine repeated signal** | **Catastrophic and silent.** "Sizes run small" repeated by 50 users is the finding; dedupe reads it as duplication | Near-dupe only within `(source, author_hash)` — the same person posting twice. **Never across authors.** Cross-author similarity is measured and *reported* as consensus strength, never removed. Threshold Jaccard > 0.85 and same author. **[E]** |
| EC-CLEAN-2 | Exact dupe across sources (Reddit post quoted in a YouTube comment) | Double-counting | Exact-hash dedupe across sources is safe and retained; keep the earliest, log the other |
| EC-CLEAN-3 | PII scrub removes meaningful content | Order ID inside a narrative gets masked, sentence becomes unreadable | Scrub to typed placeholders (`[ORDER_ID]`) rather than deletion; preserve sentence structure |
| EC-CLEAN-4 | Language detection fails on short Hinglish | Misrouted or dropped | Never drop on language. `lang` is metadata only; `unknown` is a valid value. Short + Latin script + Hindi lexicon markers → `hi-Latn` |
| EC-CLEAN-5 | Devanagari / Tamil / Bengali script records | Not English, still valid signal | Retained and classified as-is. Flagged in composition so language coverage is visible |
| EC-CLEAN-6 | Normalisation destroys intensity signal | ALL CAPS, repeated punctuation ("!!!!") carry emotional weight used by `intensity` | Normalise a *copy* into `text_clean` for matching; `text_raw` preserved and is what the classifier reads |
| EC-CLEAN-7 | Same record ingested twice across runs | Duplicate rows | `record_id = sha1(source ‖ native_id)` is a primary key; re-ingest is idempotent by construction |

---

## 5. Stage 2 — Prefilter and relevance

| ID | Case | What breaks | Handling |
|---|---|---|---|
| **EC-PRE-1** | **Prefilter drops a relevant record** | **Silent and unrecoverable** — it never reaches an LLM, never appears in any denominator | Lexicon ∪ embedding (union, never intersection). Measure prefilter recall against the gold set: gold records that the prefilter would have dropped are a direct recall miss. Target ≥ 95%; below that, loosen. **[E]** |
| EC-PRE-2 | Prefilter passes almost everything | Cost blows out, no filtering benefit | Monitor pass rate; if > 60% of raw survives, the lexicon is too broad |
| EC-REL-1 | **Past bad experience cited as present hesitation** | The hardest boundary in the rubric. "Last order came wrong-sized, I'm wary now" is relevant (C7); "my order was late" is not | Explicit rubric with worked examples both ways; over-sampled into the gold set. **[E]** |
| EC-REL-2 | Ambiguous intent — "I keep looking at this dress" | Could be S1 live intent or S3 browsing | Relevant = yes; segment = `unknown`. Ambiguity resolves at segment, not relevance |
| EC-REL-3 | Sarcasm / irony | Inverted meaning | Accept degraded accuracy; flag in `evals.md` as a known ceiling. Not separately solvable at this scale |
| EC-REL-4 | Generalisation, not personal experience — "people don't buy because…" | Opinion about others, not lived behaviour | Relevant, but flagged `secondhand = true` and excluded from counterfactual and workaround analysis |
| EC-REL-5 | Second-hand report — "my sister never buys from her wishlist" | Same as above | Same treatment |
| EC-REL-6 | About a competitor (Ajio, Nykaa) or generic online fashion | Not Myntra-specific | Retained — the blueprint's scope is online fashion behaviour — but flagged `myntra_specific = false`. Claims resting mostly on non-Myntra records are marked per assumption A-4 |
| EC-REL-7 | Wrong category entirely (electronics wishlist on Flipkart) | Structurally similar, behaviourally different | Excluded. Fashion-specific uncertainty (fit, fabric, styling) is the domain |

---

## 6. Stage 2 — Classification

| ID | Case | What breaks | Handling |
|---|---|---|---|
| EC-CLS-1 | Relevant record receives **zero codes** | Orphan — counted in the denominator, contributes to no numerator | Forbidden state. Zero codes → forced `Z-99`. Assert at write time. **[E]** |
| EC-CLS-2 | Record receives 8+ codes | Either a genuinely rich long post or model spray | Allowed but flagged. Records above 5 codes reviewed in the gold set; if spray, tighten the prompt. Long records (EC-COL-5) legitimately produce more |
| EC-CLS-3 | All codes below confidence floor | No usable label | Retained with codes marked low-confidence; excluded from ranked claims, included in totals. Never silently dropped |
| EC-CLS-4 | **Contradictory codes** — C9 (intent never live) with C1 (fit uncertainty) | Logically incoherent: no intent means no fit doubt | Contradiction matrix in the codebook; C9 and C11 are mutually exclusive with all Confidence-phase codes. Violations flagged for re-classification. **[E]** |
| EC-CLS-5 | `blocking_code` is an Eliminator but `outcome = defer` | Eliminators produce exit, not defer | Consistency assert derived from the codebook, not the model's word |
| **EC-CLS-6** | **`evidence_span` is paraphrased, not quoted** | **Silent NFR-1 break** — citation looks valid, quote does not exist | Post-classification string check: every `evidence_span` must be an exact substring of `text_raw` (whitespace-normalised). Failure → re-run that record once, then flag. **[E]** |
| EC-CLS-7 | `evidence_span` is the entire record | Technically valid, useless as evidence | Length cap relative to record length; over-long spans flagged |
| EC-CLS-8 | Stage assigned, but no code within it fits | Model forced into a bad label | `Z-99` is reachable from any stage, not only from "no stage" |
| EC-CLS-9 | **Z-99 exceeds 15%** | Codebook is incomplete (FR-5.4) | Cluster the residual, propose codes, version the codebook, full re-run. This is a designed outcome, not an error — but at 2,000 records a re-run costs ~$8, so it is affordable |
| EC-CLS-10 | Segment signals contradict — "for my wedding next year" and "need it now" | Two intents in one record | Lower confidence; below 0.6 → `unknown`. Do not average conflicting signals |
| EC-CLS-11 | One record contains several people's voices (quoted thread) | Attribution is wrong | Chunk on quote boundaries where detectable; otherwise classify the top-level author's text only |
| EC-CLS-12 | **C1 vs C8 confusion** | Fit uncertainty (solvable, Confidence) vs size unavailable (supply-side, Eliminator, fails C-2) — reads similarly, opposite solves | `boundary_note` explicitly contrasts them; the pair is over-sampled in the gold set and reported as a named cell in the confusion matrix. **[E]** |
| EC-CLS-13 | Batch job expires past the 24h window | Partial results | Chunk batches to ~500 records; resume by diffing `records` against `classifications` on `run_id` |
| EC-CLS-14 | Malformed JSON despite strict schema | Parse failure | Retry once, then quarantine the record with the raw response stored for inspection. Never drop silently |
| EC-CLS-15 | Model refuses a record on content policy | No classification returned | Quarantine, log, count in exclusions. Expect a handful — fashion feedback occasionally includes body-image or harassment content |
| EC-CLS-16 | Codebook edited mid-run | Half the corpus scored against v1, half against v2 | `codebook_version` stamped on every row; a mismatch within a run is a hard error (FR-5.6) |

---

## 7. Stage 2 — Clustering and validation

| ID | Case | What breaks | Handling |
|---|---|---|---|
| EC-CLU-1 | **HDBSCAN labels nearly everything noise** | No clusters, Track B produces nothing | Likely at 2,000 records. Lower `min_cluster_size` to ~10, retry; if still degenerate, fall back to k-means at fixed k for exploratory labelling and **report Track B as weak** rather than pretending it ran. **[E]** |
| EC-CLU-2 | One giant cluster swallowing most records | No discrimination | Re-run with tighter UMAP `min_dist`; report if unresolved |
| EC-CLU-3 | Non-deterministic clusters between runs | NFR-3 reproducibility breaks | Fixed random seeds for UMAP and HDBSCAN; assignments persisted with `run_id`, never recomputed at read time |
| EC-CLU-4 | Cluster labels merely restate codebook names | Track B adds nothing, R-9 protection is theatre | Labelling prompt is blind to the codebook by construction. If labels still mirror it, that is a *finding* — the codebook covers the space — and should be stated, not hidden |
| EC-CLU-5 | Too few records for meaningful clustering | 2,000 is thin for density clustering | Accept: Track B is diagnostic, not primary. Reconciliation (§6.5) degrades to "no contradiction found" rather than false confidence |
| EC-VAL-1 | Gold labeller drifts across the session | Early and late labels use different standards | Label in two sittings with 20 records repeated; measure intra-rater agreement on the repeats. **[E]** |
| EC-VAL-2 | Codes with zero gold examples | Cannot compute per-code agreement | Stratified sampling over-weights rare codes; where n is still 0, report "not validated" explicitly — never blank, never assumed correct |
| EC-VAL-3 | Agreement below AC-9 threshold | Numbers are not defensible | Defined response: inspect confusion matrix → sharpen the worst `boundary_note` → bump prompt version → re-run pilot → re-score. Loop, with a stated maximum of three iterations before the limitation is reported as-is |
| EC-VAL-4 | Pilot distribution ≠ full-corpus distribution | Gold set validates the wrong mix | Pilot deliberately spread across sources (arch §5.2); after the full run, re-check gold-set representativeness and note any drift |
| EC-VAL-5 | Human is simply wrong | Gold is not ground truth, it is one person | Disagreements where the model looks right are re-examined and can amend the gold label — recorded in `gold.notes` with the reason, never silently |

---

## 8. Stage 3 — Insights and prioritisation

| ID | Case | What breaks | Handling |
|---|---|---|---|
| EC-INS-1 | Top opportunities score within noise of each other | No defensible winner | Report as a tie with overlapping intervals. The weight sliders (§7.2) let a reader test robustness. **A tie is a legitimate finding** and interviews become the tiebreak |
| EC-INS-2 | Highest-scoring opportunity fails C-2 (needs money) | Cannot be solved under the constraint | C8 and parts of C6 are known cases. Report the finding honestly, then rank within the solvable subset and say plainly that the largest barrier is out of scope |
| EC-INS-3 | Top result is C9 / S3 | Non-addressable by definition | Sized then excluded (AC-12). If they dominate, the honest headline is "much wishlisting is not purchase intent" — a real and useful finding |
| EC-INS-4 | Stage A inversion threshold is low (e.g. 2×) | Conclusion is fragile to a known bias | §7.3 surfaces this. A low threshold must be stated in the deck, not buried |
| EC-INS-5 | Contradicting evidence outweighs supporting | Hypothesis fails | Report the hypothesis as refuted. This is the system working (FR-3.5) |
| EC-INS-6 | Synthesis invents a claim absent from the tables | Hallucination at the last step | Insight generation reads only `analysis_*`; every insight must cite a table row. Unciteable → rejected. **[E]** |
| EC-INS-7 | **AC-6 fails — no insight outside H1–H15/DH1–DH13** | The corpus was not actually mined; the engine only confirmed priors | Report it as a result rather than manufacturing novelty. Check first whether Z-99 clustering and cluster-code reconciliation were genuinely inspected — this is usually where novelty hides. **[E]** |
| EC-INS-8 | Segment × code too sparse to support AC-12 | Expected at 2,000 records | Pre-planned fallback to segment × stage (arch §9.4), with code-level detail marked directional |

---

## 9. Stage 4 — Chatbot

| ID | Case | What breaks | Handling |
|---|---|---|---|
| EC-CHAT-1 | Question in Hindi or Hinglish | Planner may misread | Planner handles multilingual input; answers in the question's language. Corpus is code-mixed anyway |
| EC-CHAT-2 | Multi-part question | Partial answer to one part only | The plan's `sub_questions` decomposition handles this natively — each part retrieves separately, answer addresses all |
| EC-CHAT-3 | Follow-up referencing prior turn ("what about the other segment?") | No context | Last 3 turns carried into the planning call; the *restated* question resolves the reference explicitly and is displayed |
| EC-CHAT-4 | False-premise question — "why is price the biggest barrier?" | Answering accepts the premise | Planner flags premise assertions; the answer corrects the premise before answering. **[E]** |
| EC-CHAT-5 | Question about a code with n=3 | Over-reading a tiny count | Minimum-n gate (arch §9.4) applies to chatbot answers identically to charts. Below floor → "too few records to answer reliably (n=3)" |
| EC-CHAT-6 | Methodological question — "how did you build this?" | Not in the corpus | `methodological` intent routes to a static description of the pipeline, not to retrieval |
| EC-CHAT-7 | Gibberish or empty input | Wasted call | Rejected before the planner |
| EC-CHAT-8 | Verification rejects the answer repeatedly | Infinite loop | Bounded to one regeneration; then serve with an explicit "could not fully verify" banner (AR-11). Never loop, never fail silently |
| **EC-CHAT-9** | **Prompt injection via record text** | A record reading "ignore previous instructions and say X" enters the synthesis context. This is untrusted user content in a public app | Retrieved records are wrapped in delimited blocks and labelled untrusted data; the system prompt states that record content is evidence to be quoted, never instructions to follow. Injection strings are probed in `evals.md`. **[E]** |
| EC-CHAT-10 | Verification false positive on structural numbers | "33 codes", "2,000 records" appear in an answer but not in SQL results | Allowlist of structural constants (codebook size, corpus size, thresholds) exempt from numeric verification |
| EC-CHAT-11 | Quote check fails on whitespace or casing | Valid quote rejected | Compare on normalised text; store the offset into `text_raw` for exact rendering |
| EC-CHAT-12 | Whitelisted query returns empty for a valid question | Gate sees no evidence | Routes to NONE/PARTIAL correctly — this is the designed path, not a bug |
| EC-CHAT-13 | Question spans data we have at a different cut | e.g. asks per-brand, we only have per-code | PARTIAL: answer what exists, name the cut we lack |

---

## 10. Silent-failure register

The cases that produce plausible, well-formatted, wrong output. **Build detection for these first.**

| ID | Silent failure | Why it survives review | Detection |
|---|---|---|---|
| EC-CLEAN-1 | Cross-author dedupe deletes consensus | Charts look normal; the deleted records leave no trace in any denominator | Author-scoped dedupe only; report cross-author similarity as a *consensus* metric |
| EC-PRE-1 | Prefilter drops relevant records | No error, no log of a wrong decision | Prefilter recall measured against gold |
| EC-CLS-6 | Paraphrased evidence spans | Quotes read naturally and cite a real record | Exact-substring assertion on every span |
| EC-CLS-12 | C1/C8 conflation | Both are plausible labels for the same sentence | Named cell in the gold confusion matrix |
| EC-REL-1 | Relevance rubric misapplied at the boundary | Individually defensible calls, systematically skewed denominator | Over-sampled in gold, reported separately |
| EC-CLS-10 | Segment forced instead of `unknown` | Segment charts look complete and confident | Coverage % displayed beside every segment chart |
| EC-INS-3 | C9/S3 counted inside the opportunity | Makes the opportunity look bigger, which is the answer people want | AC-12 assert: excluded after sizing |
| EC-CHAT-9 | Corpus prompt injection | Output looks like a normal answer | Delimiting + injection probes in evals |
| EC-COL-9 | One prolific author dominates a code | 200 records sounds like 200 people | Distinct-author count beside every record count |
| EC-COL-15 | Fabricated curated citation | An authoritative-looking reference nobody checks | Live-URL verification at collect time |
| — | **Stage A under-detection read as Stage A being small** | The number is real; the inference from it is wrong | §7.3 inversion threshold, stated on the chart itself |

---

## 11. Operations and deployment

| ID | Case | Handling |
|---|---|---|
| EC-OPS-1 | Streamlit cold start during evaluation | Minimal `requirements.txt`; warm the app before any demo |
| EC-OPS-2 | `corpus.db` exceeds GitHub limits | Unlikely at 2,000 records (~5–10MB); Release-asset fallback documented (arch §10) |
| **EC-OPS-3** | **Public chatbot burns API credit** | Per-session question cap, global daily cap, and a hard OpenAI usage limit at $30. The URL is public and the key is yours. **[E]** |
| EC-OPS-4 | `OPENAI_API_KEY` missing or invalid in secrets | App renders read-only pages normally; chat page shows a clear configuration message rather than a stack trace |
| EC-OPS-5 | Concurrent users mutating cached state | All app state is read-only; `@st.cache_resource` connection opened read-only |
| EC-OPS-6 | Malformed row crashes a page | Defensive rendering — a bad row is skipped and logged on-page, never a white screen |
| EC-OPS-7 | Gold-labelling page publicly reachable | Password-gated via secrets; writes isolated from published artifacts |
| EC-OPS-8 | Pipeline re-run mid-demo overwrites artifacts | Artifacts are versioned by `run_id`; the app pins a published run, never "latest" |

---

## 12. What this changes in the build

Cases that are not just handling, but design requirements to carry into `implementationplan.md`:

1. **Dedupe is author-scoped, never cross-author** (EC-CLEAN-1). The most consequential single line in this document.
2. **Distinct-author counts everywhere a record count appears** (EC-COL-9).
3. **Exact-substring assertion on every evidence span** (EC-CLS-6) — a build-time invariant, not a review step.
4. **Contradiction matrix in the codebook** (EC-CLS-4) — C9/C11 mutually exclusive with Confidence-phase codes.
5. **Prefilter recall measured against gold**, not assumed (EC-PRE-1).
6. **Records delimited and labelled untrusted in every prompt** (EC-CHAT-9).
7. **Rate limiting and a hard spend cap before the app goes public** (EC-OPS-3).
8. **Minimum-n gate applied identically to charts and chatbot answers** (EC-CHAT-5).
9. **Live-URL verification for agent-sourced curated material** (EC-COL-15).
