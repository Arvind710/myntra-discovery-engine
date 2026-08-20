# Problem-framing canvas
_Generated 2026-08-20 from the analysis tables. Every figure is a share of DISCUSSION, never a drop-off or conversion rate._

## 1 · Who

**(4) Stuck Deciders** — 392 records, 43.9% of the addressable population.

> 392 records (43.9% of the addressable population); 100% of its coded barriers are solvable without a monetary incentive; most distinctive barrier C10 at 2.18x the corpus rate. Basis: segment x code

**Explicitly not this problem:**

- 126 records (12.4%) are people saving as a taste archive. Converting them is not a goal; it would be optimising against the user.
- 21 records (2.1%) show no live purchase intent at any point.

Both were counted before being removed, which is why the addressable population is 892 and not 1018.

## 2 · What is in the way

**1. C2 — Physical-vs-digital gap (material & quality)** · n=241 · score 0.82 · solvable without money: yes
   Will the fabric, colour and quality match the photos?
**2. C1 — Fit & size uncertainty** · n=189 · score 0.80 · solvable without money: yes
   Which size, when every brand runs different?
**3. C3 — Styling & self-image / wardrobe integration** · n=154 · score 0.72 · solvable without money: yes
   Will it look good on *me*, with what I own?
**4. C4 — Real-buyer evidence insufficient** · n=82 · score 0.72 · solvable without money: yes
   What did people who actually received it say?
**5. C4.5 — Approval & permission** · n=68 · score 0.69 · solvable without money: yes
   I need to check with my partner/parent

## 3 · How confident, and how would we know we are wrong

- The top-ranked opportunity holds first place in **99.6%** of 1,000 weightings perturbed ±30%. The ranking is robust to reasonable disagreement about the weights.
- Stage A would have to be under-reported by **6.6×** to overtake stage C.
- Stage D would have to be under-reported by **14.5×** to overtake stage C.
- Stage B would have to be under-reported by **25.0×** to overtake stage C.
- Known measurement failures, carried forward rather than restated as passing: per-code agreement with a human coder clears its threshold for only 2 of 5 measurable codes; relevance recall is an estimate of ~79% against an 85% threshold; C10 is unreliable at κ 0.10.

## 4 · What we would learn that we do not know

- **HYP-02** (high confidence): In 6 interviews with people who saved clothing but did not buy, if fewer than 2 can name a specific size/fit uncertainty they could not resolve (e.g., exact waist/hip fit, stretch, length on their height), the mechanism is wrong—the hesitation was not caused by size mapping.
- **HYP-01** (medium confidence): In interviews with 6 recent wishlist non‑buyers who mention quality/material doubt, if 4 or more report they did not seek any off‑platform validation before deciding not to buy (and still abandoned), the mechanism is wrong: the quality gap is not what drives the loss after saving.
- **HYP-07** (medium confidence): In 6 interviews with shoppers who report leaving the app to check YouTube/Reddit before buying, if 5 or more say they usually come back and purchase the same saved item afterward, the mechanism is likely wrong—the off‑platform step is not causing the loss.
- **HYP-03** (medium confidence): In a short survey of 30 wishlist non‑buyers, if fewer than 10 select any reason indicating they were waiting for price clarity, a known sale/window, or fee transparency before deciding, this hypothesis fails—the delay is not driven by value/timing opacity.

## 5 · Constraints that shape any answer

- **No monetary incentives.** Discounts, coupons and cashback are out of scope, which matters most for the price/value barrier: it must resolve into transparency, anchoring or timing or not at all.
- **No internal analytics.** Public feedback is a proxy for the funnel and never a substitute. Nothing here is a drop-off rate.
- **Only ~36% of the corpus is Myntra-specific**, so platform-mechanical claims are ranked on their Myntra-specific counts.

## 6 · What the corpus said that the framework did not predict

- Value/quality doubt and real‑buyer evidence travel together: C2 and C4 co‑occur at lift 2.730 (n_joint 53), and within C2 the dominant sub‑code is C2.4 at 0.606 share.
  _These two codes behave as one compound hesitation rather than separate issues, implying that closing the physical–digital gap often depends on credible buyer evidence._
- Fit uncertainty often sits alongside needing permission: C1 and C10 co‑occur at lift 2.931 (n_joint 37), though C10’s mean_confidence is only 0.503 versus C1’s 0.816, so this pairing is less certain on the C10 side.
  _Fit doubts can trigger approval/permission checks in the same moment, but any investment here should factor the lower coding confidence on C10._
- BLIND Track B shows sizing is a multi‑code situation: the ‘Sizing and measurements questions’ cluster (size 157) maps to 113 C1 records, 37 C10, 17 C3, and 10 C2.
  _Sizing questions spill into permission, styling, and material doubts, indicating one shopper moment that the codebook slices into several codes._
- Some hypothesised wishlist mechanics are absent here: B1.2 ‘Reverse‑chronological only’ and A1.2 ‘No change signal’ both have n=0 across a 1,018‑record corpus.
  _The corpus cannot demonstrate problems that do not appear in discussion; these two specific mechanics are not evidenced in this dataset._
- Two kinds of hesitation separate: fulfilment‑risk rarely co‑occurs with price/value doubt (C6|C7 lift 0.738; n_joint 21) but often pairs with material/quality doubt (C2|C7 lift 1.961; n_joint 65).
  _Trust complaints align with quality concerns more than with price, pointing to distinct clusters of worry._
