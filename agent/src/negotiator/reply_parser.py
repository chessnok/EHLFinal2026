"""Everything a supplier's e-mail says, as data: questions, wishes, conditions, its own figures and its signals.

The arena's suppliers write from ~40 fixed sentences (its standard terms, material share, cost drivers, prices per
lever, claim checks) plus free text around them. Level 1 reads the fixed sentences exactly; level 2 reads the free
text by phrase families (a price for a structure, a limit, "must", a reciprocal step). Whatever informative sentence
neither reads is kept in `unread`, so nothing is silently lost and the patterns can grow.

Reading is all this module does: what the strategy makes of the facts is decided (and measured) there."""

import re
from dataclasses import dataclass, field

NUM = r"(\d[\d,]*(?:\.\d+)?)"
EUR = r"(?:€|EUR)\s?" + NUM
SERIES = r"([A-Z]{2,}[A-Z0-9-]*\d[\w-]*|[A-Z]{2,}-[A-Z0-9-]+)"


def _num(text: str) -> float:
    return float(text.replace(",", ""))


@dataclass
class ReplyFacts:
    questions: set = field(default_factory=set)  # volume, figures, competitor, call
    wishes: dict = field(default_factory=dict)  # lever -> what it wants
    conditions: list = field(default_factory=list)  # (kind, detail): what it says it must have
    standard: dict = field(default_factory=dict)  # its standard terms named in the text
    material_share: float | None = None
    drivers: list = field(default_factory=list)  # the cost drivers it names
    driver_moves: list = field(default_factory=list)  # (series, change %, months, share of its cost %)
    hedged_until: str | None = None
    priced_options: list = field(default_factory=list)  # (price, terms text) it names in words
    claim_reactions: list = field(default_factory=list)  # (data kind, "counted" | "no_change" | "known" | "new")
    signals: set = field(default_factory=set)
    read: list = field(default_factory=list)  # sentences one of the rules read
    unread: list = field(default_factory=list)  # informative sentences no rule read

    def summary(self) -> dict:
        out = {k: v for k, v in self.__dict__.items() if v and k not in ("read", "unread")}
        out["unread"] = len(self.unread)
        return {k: sorted(v) if isinstance(v, set) else v for k, v in out.items()}


SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'(])")
INFORMATIVE = re.compile(
    r"\d|€|%|\?|\b(?:must|cannot|can't|final|limit|approval|index|clause|volume|payment|lead time|"
    r"Lieferzeit|Zahlungsziel|contract|capacity|price|cost|margin|quality|ppm|freight|EXW|DAP|FCA)\b",
    re.I,
)


def _rules(f: ReplyFacts) -> list:
    """(pattern, action): action(match) records what the sentence says."""

    def q(name):
        return lambda m: f.questions.add(name)

    def sig(name):
        return lambda m: f.signals.add(name)

    def wish(lever, what):
        return lambda m: f.wishes.__setitem__(lever, what)

    def cond(kind, group=None):
        return lambda m: f.conditions.append((kind, m.group(group) if group else None))

    def std(lever):
        return lambda m: f.standard.__setitem__(lever, int(_num(m.group(1))))

    def share(m):
        f.material_share = _num(m.group(1))

    def drivers(m):
        f.drivers += [d for d in re.findall(SERIES, m.group(0)) if d not in f.drivers]

    def move(m):
        f.driver_moves.append(
            (
                m.group(1),
                (1 if m.group(2).lower() == "rose" else -1) * _num(m.group(3)),
                12,
                _num(m.group(4)) if m.group(4) else None,
            )
        )

    def hedge(m):
        f.hedged_until = m.group(1)

    def priced(m):
        if all(abs(p - _num(m.group("p"))) > 1e-9 for p, _ in f.priced_options):
            f.priced_options.append((_num(m.group("p")), m.group(0)))

    def reaction(m):
        verdict = {"took": "counted", "does not change": "no_change", "already": "known"}
        v = next((val for key, val in verdict.items() if key in m.group(0)), "counted")
        f.claim_reactions.append((m.group(1), v))

    return [
        # questions
        (r"Which volume can you commit to|what volume can you commit", q("volume")),
        (r"Which figures is that based on|Please (?:send us|provide) the data|data that forms the basis", q("figures")),
        (r"send us the competing offer|which (?:competing )?offer (?:do you|are you)", q("competitor")),
        (r"discuss this in a call|schedule a call|a short call", q("call")),
        # wishes
        (
            r"faster payment|pay(?:ing)? (?:us )?earlier|earlier payment|shorter payment|we need the cash",
            wish("payment_days", "faster"),
        ),
        (
            r"binding (?:higher )?volume|higher volume would help|commit to (?:a )?(?:higher )?volume",
            wish("volume_per_year", "higher"),
        ),
        (r"longer[- ]term|long-term|multi-year|extended contract|longer contract", wish("contract_months", "longer")),
        (
            r"keeping the delivery (EXW|FCA|DAP)|propose (EXW|FCA|DAP)",
            lambda m: f.wishes.__setitem__("incoterm", m.group(1) or m.group(2)),
        ),
        (r"your preference for the (\d+)-day payment", lambda m: f.wishes.__setitem__("payment_days", int(m.group(1)))),
        # conditions
        (
            r"must include an? " + SERIES + r" index clause|requires? an? " + SERIES + r" index clause",
            lambda m: f.conditions.append(("index_clause", m.group(1) or m.group(2))),
        ),
        (r"cannot offer a fixed price", cond("index_clause")),
        (r"(?:calculated|valid) specifically for (?:a |the )?(\d+)[- ]day", cond("payment_days", 1)),
        (r"lead time would (?:strictly )?increase the price|standard lead time of (\d+)", cond("lead_time_days", 1)),
        (r"DAP delivery adds significant freight|would add significant freight", cond("incoterm")),
        # its own figures
        (r"standard Zahlungsziel is (\d+) days", std("payment_days")),
        (r"Our Lieferzeit is (\d+) days", std("lead_time_days")),
        (
            r"With overtime we can deliver in (\d+) days",
            lambda m: f.wishes.__setitem__("lead_time_overtime", int(m.group(1))),
        ),
        (r"Material accounts for about ([\d.,]+)\s?%", share),
        (r"(?:price follows our main cost drivers|Our costs move with)[^.]*", drivers),
        (SERIES + r" (rose|fell) ([\d.,]+) ?% in twelve months(?: and is ([\d.,]+) ?% of our cost)?", move),
        (r"covered (?:at fixed prices )?until ([A-Z][a-z]+ \d{4})", hedge),
        (r"Alternatively, with [^:]+: " + EUR.replace(NUM, r"(?P<p>\d[\d,]*(?:\.\d+)?)"), priced),
        (r"(?:price|it) (?:to|of|at) " + EUR.replace(NUM, r"(?P<p>\d[\d,]*(?:\.\d+)?)") + r"[^.]*", priced),
        (r"We can offer a Preisgleitklausel on " + SERIES, lambda m: f.wishes.__setitem__("index_clause", m.group(1))),
        # how it took our arguments
        (r"We (?:also )?checked the ([a-z ]+?) data you cited; it holds[^.]*", reaction),
        (
            r"We have already taken that ([a-z ]+?) data into account",
            lambda m: f.claim_reactions.append((m.group(1), "known")),
        ),
        (r"We did not know that", lambda m: f.claim_reactions.append(("last", "new"))),
        (r"Your figures confirm our case", sig("figures_confirm_its_case")),
        (r"not our reality", sig("argument_not_its_reality")),
        # signals
        (r"further step needs approval", sig("approval_needed_next")),
        (r"reached the limit", sig("limit_reached")),
        (r"clarify (?:this |it )?internally|come back to you on (?:the )?price", sig("clarifying_internally")),
        (r"clarified this internally and can move", sig("moved_after_approval")),
        (r"final offer|our best possible price|last offer", sig("final")),
        (r"hold our (?:Angebot|offer)|maintain our (?:current )?(?:offer|price)|offer stands", sig("holds")),
        (
            r"Building on your (?:Option )?(\w+)|build on your (\w+) option",
            lambda m: f.signals.add(f"builds_on_option_{(m.group(1) or m.group(2)).lower()}"),
        ),
        (
            r"two cents|more significant step|marginal (?:increase|step)|steps are (?:really )?tiny"
            r"|remains insufficient",
            sig("our_step_too_small"),
        ),
        (r"miles apart|far apart|far below (?:our|what)", sig("far_apart")),
        (r"free capacity", sig("free_capacity")),
        (r"capacity utili[sz]ation|fully booked|order book is full", sig("capacity_tight")),
        (r"cannot give up margin|margin", sig("margin_pressure")),
        (r"another bidder|other bidder|competing", sig("rival_noted")),
        (r"reciprocate|in response to your step|to meet you", sig("reciprocal_step")),
        (r"long-standing (?:relationship|partnership)|family-run|reliable cooperation", sig("relationship_appeal")),
        (
            r"cost breakdown attached|breakdown you requested|do not share a breakdown|calculation (?:stays|is our)",
            sig("breakdown_answer"),
        ),
        (r"accept your (?:request|proposal|proposed)[^.]*", sig("accepts_our_structure")),
        (r"quality|ppm", sig("quality_mentioned")),
        (r"(?:€|EUR)\s?(?P<p>\d[\d,]*(?:\.\d+)?)(?: per unit)? (?:for|based on)[^.]*", priced),
        (
            r"cannot reduce the price further|all possible concessions|can't drop the price any further"
            r"|take it or leave it|last price|one final adjustment",
            sig("final"),
        ),
        (r"withdrawing from this negotiation", sig("walking_away")),
        (r"need the (\d+) days payment", lambda m: f.wishes.__setitem__("payment_days", int(m.group(1)))),
        (r"specify the anticipated volume|requested volume commitment", q("volume")),
        (
            r"provided the " + SERIES + r" index clause is applied",
            lambda m: f.conditions.append(("index_clause", m.group(1))),
        ),
        (r"Main cost drivers:[^.]*", drivers),
        (r"without a change in the underlying terms", sig("terms_room")),
        (
            r"valid for (\d+) days|valid (\d+) days",
            lambda m: f.standard.__setitem__("validity_days", int(m.group(1) or m.group(2))),
        ),
        (r"longer Zahlungsziel costs us interest|payment[^.]*priced in", sig("payment_priced_in")),
        (r"contract term is (?:also )?reflected in the price", sig("contract_priced_in")),
        (r"shorter Lieferzeit means overtime", sig("lead_time_priced_in")),
        (r"standard Lieferzeit is (\d+) days", std("lead_time_days")),
        (r"we would need facts|need facts, not", q("figures")),
        (r"list price stays|frozen (?:all )?price reductions|price freeze", sig("price_frozen")),
        (
            r"on the terms we have room|talk about the terms instead|in direct exchange for (?:such )?improved terms",
            sig("terms_room"),
        ),
        (r"complaints seriously|8D report", sig("quality_response")),
        (
            r"contingent upon the (\d+)-day payment term(?: and (\d+)-month contract)?",
            lambda m: f.conditions.append(("payment_days", m.group(1))),
        ),
        (r"cannot extend our Zahlungsziel", cond("payment_days")),
        (r"Without movement from your side", sig("needs_our_move")),
        (r"(?:Yes, )?we can commit to the (\d+) days lead time", lambda m: f.signals.add("confirms_lead_time")),
        (r"drop the price to (?P<p>\d[\d,]*(?:\.\d+)?) EUR[^.]*", priced),
    ]


def parse_reply(body: str) -> ReplyFacts:
    f = ReplyFacts()
    rules = [(re.compile(p, re.I), act) for p, act in _rules(f)]
    for sent in SENTENCE.split(" ".join((body or "").split())):
        hit = False
        for pat, act in rules:
            for m in pat.finditer(sent):
                act(m)
                hit = True
        if hit:
            f.read.append(sent)
        elif INFORMATIVE.search(sent) and not re.match(r"(?:Dear|Kind regards|Mit freundlichen|Best regards)", sent):
            f.unread.append(sent)
    return f
