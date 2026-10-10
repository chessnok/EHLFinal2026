"""How the buyer behaves: the conduct every strategy keeps, and where code holds it to that.

The arena's suppliers react like people to tone, trust and track record, and they check every data ID we
cite - a fact that turns out wrong costs trust at once. So honesty is not a cost here, it is a lever.

 1. Honest before friendly. A reputation for honesty makes the other side trust and deceive less; one
    proven lie turns it around.                        -> no sentence states what the data does not show
 2. Never lie, but do not tell everything. Budget, urgency, a missing alternative, our target and upper
    bound stay with us; nothing is invented.           -> no strategy writes them (upper_c is "never said")
 3. Only facts with a source. Every figure carries its data ID; a sentence whose IDs are all unknown is
    dropped, not sent without its source.               -> guards.clean_message (unsupported_sentences)
 4. Build trust first. Thank, answer what the supplier asked for, name the request an option meets.
                                                        -> the first lines of each e-mail, `_answered`
 5. Fair and reciprocal. Our step answers its step (reciprocity in C); its concessions are acknowledged
    only when it really moved (a drop of C, not just of the price). A small step without one of its own
    stays: these bots punish a repeated offer.         -> Policy.reciprocity, MIN_STEP, plan.stalls
 6. Respect, no empty threats. No walk-away threat, no "other offers" we cannot show.
                                                        -> guards.clean_message (BLUFF)
 7. Take the supplier's situation seriously: its cost drivers, cash, capacity; offer options that help
    it at no cost to us.                                -> profile traits, equal-C menus, trade_note
 8. Do not ruin it. A strategic supplier is never asked below its sustainable margin - in stabilise and
    secure_supply that would cost us C as well.        -> RELATIONSHIP_COST_FLOOR, ANCHOR_RELATIONSHIP
    (In leverage cases we may ask a little under its estimated full cost; the supplier decides, its own
    floor protects it, and a shallower ask there costs score.)
 9. Keep our word. Every option we send is one we accept if it is agreed; "one last step and we can
    sign" is followed by signing; a volume we "commit to" is on every option.
                                                        -> guards (send/accept), probe -> take, _volume_proof
10. Clear and short. No padding: it buys no price.     -> template e-mails, ~90 words
"""

import re
from collections.abc import Callable

# claims of other offers or a walk-away: only with a rival's offer or quote cited in the same message
BLUFF = re.compile(
    r"walk away|end (?:the|our|these) (?:negotiation|talks)|look elsewhere"
    r"|(?:switch|move) to (?:another|other) supplier"
    r"|(?:other|another) (?:suppliers?|bidders?) (?:offers?|quotes?|bids?)|competitors?\b"
    r"|competing (?:offer|bid|quote)|better offers? (?:from|elsewhere)"
    r"|last chance|take it or leave it",
    re.I,
)
SENTENCE = re.compile(r"(?<=[.!?])\s+")


def unsupported_sentences(
    body: str, id_re: re.Pattern, known: Callable[[str], bool], rival_cited: bool
) -> tuple[str, list[str]]:
    """The body without sentences that would state something we cannot back, and those sentences.

    Dropped: a sentence whose data IDs are all unknown (its source is gone, the claim is not), and a
    threat or an "other offer" without a rival's offer or quote cited in the same message."""
    kept, dropped = [], []
    for para in body.split("\n"):
        out = []
        for sent in SENTENCE.split(para):
            ids = id_re.findall(sent)
            if (ids and not any(known(i) for i in ids)) or (BLUFF.search(sent) and not rival_cited):
                dropped.append(sent)
            else:
                out.append(sent)
        kept.append(" ".join(out))
    return ("\n".join(kept), dropped) if dropped else (body, [])
