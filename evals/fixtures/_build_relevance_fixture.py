"""Emit relevance_boundary.jsonl for S2-MET-8 (threshold >=75%).

The relevance filter is the single highest-leverage component in the system:
a permissive filter destroys every number downstream (FR-2.1, R-2).

The hardest boundary, and the one this fixture exists for (EC-REL-1):
  RELEVANT   -- a past bad experience cited as a reason for PRESENT hesitation
  IRRELEVANT -- a complaint about a past order with no bearing on a decision

"My last order came in the wrong size and I'm wary now"  -> IN  (C7)
"My order was late"                                      -> OUT

Each row carries the label, the reason, and where applicable the flags the
relevance pass must also set (secondhand, myntra_specific).
"""
import json
from pathlib import Path

OUT = Path(__file__).parent / "relevance_boundary.jsonl"
R = []


def add(cat, text, relevant, why, **flags):
    R.append({"category": cat, "text_raw": text, "is_relevant": relevant,
              "why": why, **flags})


# --- EC-REL-1: past experience AS PRESENT HESITATION -> RELEVANT (12) ---
P = "past_experience_relevant"
add(P, "Last kurta I ordered from here came two sizes off. Now there's a dress in my wishlist I keep not buying because of that.", 1, "past failure explicitly blocking a current saved-item decision -> C7/C1")
add(P, "Returned three things last year and the pickup was a nightmare. So anything sitting in my saved list just stays there now.", 1, "return effort cited as the reason saved items stay unbought -> C7")
add(P, "Pichli baar fabric bilkul different tha photo se. Ab wishlist mein 15 cheezein padi hain, order karne ki himmat nahi hoti.", 1, "Hinglish: past photo-vs-reality gap now blocking saved items -> C2/C7")
add(P, "I got burned once by a brand whose sizing was random. Now I check every size chart twice and usually just close the app.", 1, "past experience producing present decision paralysis -> C1")
add(P, "After that one exchange that took 20 days I stopped buying anything I'm not 100% sure about. Half my wishlist is exactly that.", 1, "return friction as a present risk floor -> C7")
add(P, "The colour was completely off last time. So now if something's in my saved list I go look for real buyer photos first and mostly give up.", 1, "past miss driving an off-platform verification workaround -> C2/C14")
add(P, "Once bitten. That jacket I saved has been there four months because I don't trust the fit description anymore.", 1, "explicit present non-purchase attributed to past fit failure -> C1")
add(P, "My sister's order came damaged and honestly it made me nervous about the two dresses I've had saved since Diwali.", 1, "second-hand past experience, but the hesitation is the author's own -> C7", secondhand=0)
add(P, "Had a bad experience with a non-returnable item. Now I check returnability before even adding to bag, and often I just don't.", 1, "past experience changed present pre-purchase behaviour -> C7/D3")
add(P, "Ordered two sizes last time to be safe and returning one was such a pain. That's why the stuff in my list stays there.", 1, "workaround with effort, cited as present blocker -> C1 + workaround")
add(P, "The quality was nothing like the pictures. I still browse and save things but I never actually order now.", 1, "past quality miss producing save-without-buy behaviour -> C2")
add(P, "Been wary since a wrong-size delivery. There's a blazer I've wanted for weeks and I still haven't pulled the trigger.", 1, "textbook EC-REL-1 case -> C1/C7")

# --- Past experience WITHOUT present hesitation -> IRRELEVANT (12) ---
N = "past_experience_irrelevant"
add(N, "My order was late by four days. Very disappointing service.", 0, "delivery complaint, no bearing on a save-to-purchase decision")
add(N, "Refund still not credited after 15 days. Worst experience.", 0, "post-purchase refund processing -- out of scope")
add(N, "The delivery guy was rude and left the package with a neighbour.", 0, "fulfilment service complaint")
add(N, "App keeps crashing when I open it. Fix your app.", 0, "app performance -- EC-COL-13, large share of app-store volume")
add(N, "Customer care put me on hold for 40 minutes and then disconnected.", 0, "customer service complaint")
add(N, "Received a damaged product. Raised a return, waiting.", 0, "post-purchase quality complaint, no present decision")
add(N, "Order dispatched but tracking hasn't updated in three days.", 0, "logistics status")
add(N, "Paisa cut gaya but order place nahi hua. Please refund.", 0, "Hinglish: payment/refund incident, not a wishlist decision")
add(N, "Why is there no COD option in my area? Fix this.", 0, "payment method availability as a general complaint, no saved-item decision")
add(N, "The kurta I received was lovely, exactly as shown. Five stars.", 0, "positive post-purchase review -- no barrier, no decision")
add(N, "Login OTP never arrives. Been trying for two days.", 0, "authentication failure -- app problem")
add(N, "They cancelled my order without telling me. Unacceptable.", 0, "order management complaint")

# --- Clearly relevant: the save-to-purchase decision itself (12) ---
C = "clearly_relevant"
add(C, "I have 60 things in my wishlist and I never buy any of them because I can never decide which one.", 1, "comparison paralysis -> C5")
add(C, "Every time I open my saved list half the stuff is sold out in my size.", 1, "dead inventory in the list -> B2.1")
add(C, "I keep the dress saved and check every week to see if the price drops before EOSS.", 1, "conditional waiting -> C6, segment S2")
add(C, "I saved it but I have no idea if the fabric is decent. Wish there were more real photos in the reviews.", 1, "material doubt + thin buyer evidence -> C2/C4")
add(C, "Before buying anything from my list I go watch a YouTube haul of that brand first. Usually I forget to come back.", 1, "off-platform verification exit -> C14, high-value workaround")
add(C, "Saved a lehenga for my cousin's wedding in November. Waiting to see if a better one shows up.", 1, "future-event conditional -> C13/C5, segment S2")
add(C, "I can't find the top I saved last month, the list is just an endless scroll.", 1, "retrieval failure -> B1.1/B1.2")
add(C, "Honestly I need my husband to okay it before I spend that much, so it just sits in the wishlist.", 1, "approval dependency -> C10")
add(C, "Added to bag and then saw the shipping and convenience fee and closed the app.", 1, "cost surprise at cart -> D1")
add(C, "Wishlist mein 200 items hain, kabhi kabhi dekhti hoon bas. Buying ka plan nahi hai.", 1, "Hinglish: relevant to the save-to-purchase question -- and codes to C9/S3")
add(C, "I screenshot things from my wishlist and compare them against what's already in my wardrobe before deciding.", 1, "styling/wardrobe integration workaround -> C3")
add(C, "I forgot the wishlist even existed until you asked. I just search for stuff again when I want it.", 1, "recall failure + re-entry workaround -> A1.1/A3.2")
add(C, "Size ka confusion hamesha rehta hai, isliye saved items order hi nahi karti. Har brand ka size alag hai.", 1, "Hinglish: fit uncertainty blocking saved-item purchase -> C1")

# --- Clearly irrelevant (8) ---
I = "clearly_irrelevant"
add(I, "What are the office timings for the Bangalore warehouse?", 0, "not user feedback at all")
add(I, "Myntra's revenue grew 20% last quarter according to the filing.", 0, "corporate/financial -- out of scope")
add(I, "Anyone know a good tailor in Andheri?", 0, "off-topic community chatter")
add(I, "Buy followers cheap DM me now link in bio", 0, "promotional spam -> exclusions/spam, EC-COL-7")
add(I, "The Insider points expired without any warning.", 0, "loyalty programme complaint, no save-to-purchase decision")
add(I, "Great sale this weekend, 70% off everything!", 0, "promotional content, not user experience")
add(I, "How do I change my registered mobile number?", 0, "account support question")
add(I, "😍😍😍", 0, "no signal -- also caught by the length floor, EC-COL-6")

# --- EC-REL-2: ambiguous intent -> RELEVANT, segment resolves to unknown (5) ---
A = "ambiguous_intent"
add(A, "I keep looking at this dress.", 1, "EC-REL-2: ambiguity resolves at SEGMENT, not at relevance", expect_segment="unknown")
add(A, "This has been in my list forever.", 1, "relevant; no signal for why it was saved", expect_segment="unknown")
add(A, "Still thinking about it.", 1, "live deliberation, segment not inferable", expect_segment="unknown")
add(A, "Maybe later.", 1, "deferral with no stated condition -- NOT S2 (no named trigger)", expect_segment="unknown")
add(A, "It's nice but I don't know.", 1, "unresolved doubt, code unclear -- a likely Z-99 candidate", expect_segment="unknown")

# --- EC-REL-4/5: second-hand reports -> RELEVANT but flagged (4) ---
S = "secondhand"
add(S, "Most people don't buy from their wishlist because they're just window shopping.", 1, "opinion about others -> excluded from counterfactual/workaround analysis", secondhand=1)
add(S, "My sister never buys anything from her saved list, she just collects.", 1, "second-hand report of another person's behaviour", secondhand=1)
add(S, "Girls in my hostel all say the sizing is unpredictable so nobody orders directly.", 1, "generalisation about a group", secondhand=1)
add(S, "I think Indian shoppers wait for sales before buying saved items.", 1, "opinion, not lived behaviour", secondhand=1)

# --- EC-REL-6: competitor / generic online fashion -> RELEVANT, flagged (4) ---
M = "not_myntra_specific"
add(M, "On Ajio I save things and never buy them either, the sizing is just as unreliable.", 1, "competitor but same behaviour -- blueprint scope is online fashion", myntra_specific=0)
add(M, "Online fashion shopping in general: I save 50 things and buy two.", 1, "generic online fashion behaviour -- assumption A-4 flag", myntra_specific=0)
add(M, "Nykaa Fashion has the same problem, my saved list is a graveyard.", 1, "competitor evidence, retained and flagged", myntra_specific=0)
add(M, "Bought it off Instagram instead after seeing it on a reel.", 1, "need extinguished elsewhere -> C11", myntra_specific=0)

# --- EC-REL-7: wrong category -> IRRELEVANT (3) ---
W = "wrong_category"
add(W, "My Flipkart wishlist is full of headphones I never buy.", 0, "structurally similar, behaviourally different -- fashion-specific uncertainty is the domain")
add(W, "I save laptops on Amazon and wait for sales.", 0, "electronics -- no fit/fabric/styling uncertainty")
add(W, "Saved a fridge for six months before buying.", 0, "large-appliance consideration cycle, out of domain")

for i, r in enumerate(R, start=1):
    r["record_id"] = f"fx-rel-{i:03d}"
    r.setdefault("secondhand", 0)
    r.setdefault("myntra_specific", 1)

OUT.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in R) + "\n")

from collections import Counter
print(f"{OUT.name}: {len(R)} cases | relevant={sum(r['is_relevant'] for r in R)} "
      f"irrelevant={sum(1 - r['is_relevant'] for r in R)}")
for k, v in Counter(r["category"] for r in R).items():
    print(f"   {k:<28} {v}")
