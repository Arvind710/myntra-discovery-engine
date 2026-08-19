"""Emit code_boundary.jsonl — hand-labelled cases for the codebook's
adjacent-code pairs (S2-MET-7 / EC-CLS-12).

C1 vs C8 is the headline pair: fit uncertainty (Confidence, solvable
without money) versus size unavailable (Eliminator, supply-side, fails the
C-2 constraint). They read almost identically and have OPPOSITE solves, so
confusing them means building the wrong thing while the data appears to
agree.

The discriminating test, stated in the C8 boundary note: could the user
have completed the purchase if they had been certain? YES -> C1. NO, the
option did not exist -> C8.
"""
import json
from pathlib import Path

OUT = Path(__file__).parent / "code_boundary.jsonl"
R = []


def add(pair, text, expect, why):
    R.append({"pair": pair, "text_raw": text, "expect_code": expect, "why": why})


# ---- C1 vs C8 : the danger pair (16) ----
P = "C1_vs_C8"
add(P, "Every brand here has different sizing. I wear M in one and L in another, so I never know what to order and usually just don't.", "C1", "doubt about WHICH size; item purchasable")
add(P, "The size chart says 38 but reviews say it runs small. I've had it saved for weeks because I can't decide.", "C1", "conflicting size information, not availability")
add(P, "I want it badly but it's been out of stock in my size for two months.", "C8", "size not purchasable")
add(P, "My size is never available. Everything is S and XXL by the time I look.", "C8", "supply-side, not a decision doubt")
add(P, "Not sure whether to size up for an oversized fit or stick to my usual. Still haven't ordered.", "C1", "styling-of-fit doubt, item available")
add(P, "Added to bag, went back next day and my size was gone.", "C8", "availability at decision time")
add(P, "I ordered two sizes because I couldn't tell which would fit, returned one.", "C1", "classic C1 workaround")
add(P, "They only stock up to L. I'm an XXL so it's not even an option for me.", "C8", "size not carried at all")
add(P, "Their size guide is useless. Measurements don't match what arrives, so I hesitate every time.", "C1", "size information unreliable")
add(P, "Sold out in 32 waist. Been waiting for a restock since Diwali.", "C8", "waiting for restock")
add(P, "I'm between sizes and the brand doesn't do half sizes, so I keep putting off the decision.", "C1", "user cannot resolve which size")
add(P, "Everything I like is available only in sizes nobody wears.", "C8", "supply-side availability")
add(P, "Is this true to size? Nobody in the reviews mentions it and I don't want to guess.", "C1", "unresolved size question")
add(P, "It came back in stock but by then I'd lost interest.", "C12", "availability resolved; desire decayed - neither C1 nor C8")
add(P, "I know my size in this brand, I just think 2000 is too much for a plain top.", "C6", "no size doubt at all; value doubt")
add(P, "Size ka confusion rehta hai har brand mein, isliye order karne se pehle 10 baar sochti hoon.", "C1", "Hinglish: which-size doubt")

# ---- C4 vs C14 : content problem vs retention problem (8) ----
P = "C4_vs_C14"
add(P, "The reviews here have almost no photos, so I can't tell what it actually looks like on a real person.", "C4", "on-platform evidence thin - a CONTENT problem")
add(P, "I always go watch a YouTube haul of the brand before ordering. Usually I forget to come back.", "C14", "leaves platform, session dies")
add(P, "Only three reviews and all of them say nice product. That tells me nothing.", "C4", "review quality insufficient")
add(P, "Ended up searching the product on Reddit to see if anyone had actually bought it.", "C14", "off-platform verification")
add(P, "Wish there were more customer photos instead of just model shots.", "C4", "wants better on-platform evidence")
add(P, "I check the brand on Instagram first to see real people wearing it.", "C14", "external verification behaviour")
add(P, "Reviews are all from 2022, no idea if the quality is still the same.", "C4", "stale on-platform evidence")
add(P, "Compared the price on Ajio and Amazon before deciding, then bought there.", "C11", "left AND completed elsewhere - need extinguished")

# ---- C6 vs D1 : item price doubt vs cost revealed late (6) ----
P = "C6_vs_D1"
add(P, "2400 for a cotton kurta feels steep. I keep waiting for it to drop.", "C6", "doubt about the ITEM's price")
add(P, "Got to checkout and there was a shipping charge and a convenience fee. Closed the app.", "D1", "cost revealed LATE - a disclosure problem")
add(P, "Is it worth this much? I can't tell if the quality justifies it.", "C6", "value uncertainty")
add(P, "Cart said 1299, final page said 1450 with fees. Felt cheated.", "D1", "late cost surprise")
add(P, "Waiting for EOSS before I buy anything from my saved list.", "C6", "timing/sale waiting")
add(P, "COD charge of 50 rupees appeared only at the last step.", "D1", "late fee disclosure")

# ---- C9 vs C12 : never intent vs decayed intent (5) ----
P = "C9_vs_C12"
add(P, "My wishlist is basically a mood board. I never intended to buy any of it.", "C9", "intent NEVER existed - denominator control")
add(P, "I really wanted that jacket in November. Looked at it last week and felt nothing.", "C12", "intent existed and faded")
add(P, "I save things I could never afford, just to look at them.", "C9", "aspirational collecting")
add(P, "By the time I'd decided, I didn't want it anymore.", "C12", "desire decay")
add(P, "Just window shopping honestly, my saved list has 300 things.", "C9", "bookmarker behaviour")

# ---- B2.1 vs C8 : list clutter vs specific-item unavailability (4) ----
P = "B2.1_vs_C8"
add(P, "Half my wishlist is sold out. Scrolling past dead items every time is exhausting.", "B2.1", "OOS items degrading the LIST as a surface")
add(P, "The one dress I actually wanted is out of stock in my size.", "C8", "specific item, decision blocked")
add(P, "My saved list is a graveyard, most of it isn't buyable anymore.", "B2.1", "list hygiene problem")
add(P, "Went to buy the shoes I saved and they'd been delisted entirely.", "B2.2", "product removed, not merely OOS")

# ---- C3 vs C10 : own doubt vs needing someone else (4) ----
P = "C3_vs_C10"
add(P, "Not sure it suits my body type. I look at the model and can't picture myself.", "C3", "self-image / fit-to-person")
add(P, "Sent the link to my husband, waiting to hear what he thinks before ordering.", "C10", "external approval dependency")
add(P, "If I cannot make four outfits with things I already own, it's not worth buying.", "C3", "stated wardrobe DECISION RULE - v1.2 boundary")
add(P, "Put it in a group chat poll before deciding.", "C10", "social validation required")

# ---- A1.1 vs C13 : forgot the list vs no reason to act today (4) ----
P = "A1.1_vs_C13"
add(P, "Honestly I forgot the wishlist feature even existed until this thread.", "A1.1", "never returned to the list at all")
add(P, "I know exactly what I want and it's sitting there. Just never feels like the day to buy it.", "C13", "resolved intent, no trigger")
add(P, "Nothing ever reminds me that I saved anything.", "A1.1", "no outbound trigger to return")
add(P, "No doubts left, I just haven't got round to pressing order.", "C13", "no reason to act now")

for i, r in enumerate(R, 1):
    r["record_id"] = f"fx-code-{i:03d}"

OUT.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in R) + "\n")
from collections import Counter
print(f"{OUT.name}: {len(R)} cases")
for k, v in Counter(r["pair"] for r in R).items():
    print(f"   {k:<14} {v}")
