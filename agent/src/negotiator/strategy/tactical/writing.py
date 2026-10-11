"""The words: which arguments go into a message, and the e-mail around the term sheets."""

from arena_kit.cost import RELATIONSHIP_GOALS

from negotiator.data import Evidence
from negotiator.menu import satisfies
from negotiator.session import Negotiation
from negotiator.strategy.baseline import SIGNATURE, describe
from negotiator.strategy.tactical.plan import Plan

FIELD_WORDS = {
    "payment_days": "payment terms",
    "contract_months": "the contract length",
    "lead_time_days": "the lead time",
    "incoterm": "the delivery terms",
    "volume_per_year": "the volume",
    "index_clause": "an index clause",
    "effective_date": "the start date",
    "ppm_commitment": "the quality commitment",
    "chargeback_eur_per_complaint": "the chargeback",
    "tooling_eur": "tooling",
}


EVIDENCE_FIRST = {  # profile trait / goal -> evidence kinds to put first
    "not_tracking_costs": ["index"],
    "open_book": ["should_cost"],
    "quality_first": ["quality", "scorecard"],
}


class WritingMixin:
    def _choose_claims(self, neg, sid, plan, first: bool) -> list[Evidence]:
        self._drop_hedged_series(neg, plan)
        banned = plan.banned_kinds | self.banned_case_kinds
        if neg.buyer.get("category_goal") != "quality_first":
            banned = banned | {"scorecard"}
        fresh = [e for e in plan.counters if e.kind not in banned and e.sentence not in plan.used_sentences]
        fresh.sort(key=lambda e: -e.strength)
        pool = fresh + [e for e in plan.evidence if e.kind not in banned and e.sentence not in plan.used_sentences]
        rival = self._rival_evidence(neg, sid)
        if rival and "rival_offer" not in banned:
            pool.insert(0, rival)
        prefer: list[str] = []
        for key in [*sorted(plan.profile.traits), neg.buyer.get("category_goal", "")]:
            prefer += EVIDENCE_FIRST.get(key, [])
        pool.sort(key=lambda e: (e not in fresh, e.kind not in prefer, -e.strength))
        limit = plan.policy.claims_first if first else (2 if fresh else 1)
        picked, kinds = [], set()
        for e in pool:
            if len(picked) >= limit:
                break
            if e.kind == "rival_offer":
                if any((sid, r) in self.used_rival_refs for r in e.refs):
                    continue
            elif any(r in self.used_refs for r in e.refs) or (e.kind in kinds and e.kind != "recent_drop"):
                continue
            if first and (e.meta or {}).get("later"):
                continue
            picked.append(e)
            kinds.add(e.kind)
        for e in picked:
            plan.used_sentences.add(e.sentence)
        for e in picked:
            if e.kind == "rival_offer":
                self.used_rival_refs.update((sid, r) for r in e.refs)
            else:
                self.used_refs.update(e.refs)
        return picked

    @staticmethod
    def _drop_hedged_series(neg, plan: Plan) -> None:
        """Its material is bought at fixed prices: a fall of the series its clause would follow is "not our reality"
        (P08, every session) - the slot goes to the next argument (main's P-57: P08 0.626 -> 0.659, the other nine
        identical). One fact is cited once (the counters may hold it)."""
        clauses = neg.case.get("term_options", {}).get("index_clause") or []
        series = {o.get("series") for o in clauses if o}
        if not (plan.profile.has("hedged") and series):
            return
        prefixes = tuple(f"idx:{s}@" for s in series)

        def keep(e: Evidence) -> bool:
            return not any(r.startswith(prefixes) for r in e.refs or []) and not any(
                s in (e.sentence or "") for s in series
            )

        plan.counters = [e for e in plan.counters if keep(e)]
        plan.evidence = [e for e in plan.evidence if keep(e)]
        cited = {r for e in plan.counters for r in e.refs or []}
        plan.evidence = [e for e in plan.evidence if not set(e.refs or []) & cited]

    def _write(self, neg, plan: Plan, sheets: list[dict], claims: list[Evidence], probe: bool) -> dict:
        p, case = plan.profile, neg.case
        first = neg.threads[plan.supplier_id].rounds_used == 0
        lines = [f"Dear {plan.name} team,", ""]
        if first:
            if p.has("relationship") or neg.buyer.get("category_goal") in RELATIONSHIP_GOALS:
                lines.append("thank you for your quote and for the reliable cooperation we value.")
            else:
                lines.append("thank you for your quote. We have reviewed it carefully against our data.")
        elif probe:
            lines.append("thank you - we are close. One last step from your side and we can sign.")
        elif plan.stalls:
            pressure = (
                f"{plan.pressures[-1]} weighs on your costs" if plan.pressures else "your costs are under pressure"
            )
            lines.append(
                f"thank you for your reply. We understand that {pressure}; to meet you, we propose a different "
                "structure."
            )
        else:
            lines.append("thank you for your reply and the step towards us. We move as well.")
        said = [c.sentence for c in claims]
        if plan.yes_line:
            said.append(plan.yes_line)
            plan.yes_line = None
        if first and self.flags["no_q1"]:
            said = [x for x in said if not x.rstrip().endswith("?")]
        lines += said
        if (
            not plan.asked_breakdown
            and p.has("open_book")
            and not plan.breakdown_read
            and not (first and self.flags["no_q1"])  # asked from round 2 on
        ):
            lines.append("Could you send us a cost breakdown for this part?")
            plan.asked_breakdown = True
        if len(sheets) > 1:
            reference = neg.threads[plan.supplier_id].standing[1].get("payment_days") or 0
            if p.has("cash_short") and any((sh["terms"].get("payment_days") or 999) < reference for sh in sheets):
                lines.append("If faster payment helps you, one option below pays early.")
            elif any(
                f in plan.policy.trade_first and f in case["negotiable"] for f in ("contract_months", "volume_per_year")
            ):
                lines.append("We are ready to commit for longer if the price reflects it.")
        theirs = neg.threads[plan.supplier_id].standing[1]
        for i, sheet in enumerate(sheets if plan.requests else []):
            if said := self._answered(neg, plan, sheet["terms"], theirs, f"Option {chr(65 + i)}").strip():
                lines.append(said)
                break
        volume = self._volume_proof(neg, plan, sheets)
        if volume:
            lines.append(volume[0])
        lines += ["", "We can award on any of these options:" if len(sheets) > 1 else "Our proposal:"]
        for i, sheet in enumerate(sheets):
            note = trade_note(case, sheets[0]["terms"], sheet["terms"])
            lines.append(f"Option {chr(65 + i)}: {describe(case, sheet['terms'])}{note}")
        lines += ["", SIGNATURE]
        return {
            "subject": case.get("title", "Your quote"),
            "body": "\n".join(lines),
            "term_sheets": sheets,
            "refs": sorted({r for c in claims for r in c.refs} | ({volume[1]} if volume and volume[1] else set())),
        }

    def _alternative_line(self, neg, sheet: dict, best: dict) -> str:
        return "thank you. We accept your alternative as stated below and are ready to place the order on it."

    def _volume_proof(self, neg, plan: Plan, sheets: list[dict]) -> tuple[str, str] | None:
        """ "Which volume can you commit to?" (the bots' most common question) - answered once, with the
        forecast we share with suppliers, by ID, so it reads as documentation and not as a claim."""
        if "volume_per_year" not in plan.requests or plan.volume_proved or not self.data:
            return None
        if any(r.startswith("fc:") for r in self.used_refs):
            plan.volume_proved = True  # a duplicate earns nothing ("we have already taken that data into account")
            return None
        parts = neg.case.get("parts") or []
        if len(parts) != 1:
            return None
        num = parts[0].split(":", 1)[-1]
        ids = sorted(k for k in self.data.facts if k.startswith(f"fc:{num}@"))
        if not ids:
            return None
        fc = self.data.facts[ids[-1]]
        change, volume = fc.get("change_pct"), fc.get("volume_per_year")
        if change is None or change < 0:
            return None  # a falling forecast is no argument for a better price
        plan.volume_proved = True
        self.used_refs.add(ids[-1])
        # a commitment we state is one every option keeps (conduct.py: keep our word)
        on_every_option = volume and all(sh["terms"].get("volume_per_year") == volume for sh in sheets)
        commit = f" and we commit to {volume:,} units a year" if on_every_option else ""
        return (
            f"Our demand forecast for this part, shared with you, rose {change:+.1f}% ({ids[-1]}){commit}.",
            ids[-1],
        )

    @staticmethod
    def _answered(neg, plan: Plan, terms: dict, theirs: dict, label: str = "Option A") -> str:
        """One sentence on the requests this offer answers - and on a request the case does not let us meet."""
        words = {
            "index_clause": "the index clause you asked for",
            "contract_months": "the longer commitment you asked for",
            "volume_per_year": "a binding volume",
            "payment_days": "the payment term you proposed",
            "ppm_commitment": "the quality commitment you proposed",
            "chargeback_eur_per_complaint": "the chargeback you proposed",
            "lead_time_days": "your lead time",
            "incoterm": "your delivery terms",
            "effective_date": "your start date",
            "tooling_eur": "your tooling terms",
        }
        met = [
            words[r]
            for r in sorted(plan.requests)
            if r in words and satisfies(neg.case, terms, theirs, r, plan.proposed)
        ]
        return f" {label} includes {' and '.join(met)}." if met else ""

    def keepalive(self, neg: Negotiation, supplier_id: str) -> dict | None:
        """A held thread's clock runs while others negotiate: a harmless question keeps it alive."""
        t = neg.threads[supplier_id]
        if (neg.case.get("round_limit") or 10) - t.rounds_used <= 2:
            return None
        plan = self.tplans[supplier_id]
        asks = [
            "could you confirm your delivery capacity for our annual volume?",
            "could you confirm the lead time you can commit to for the first call-off?",
            "could you confirm the validity of your offer?",
        ]
        question = asks[t.rounds_used % len(asks)]
        return {
            "subject": neg.case.get("title", "Your quote"),
            "body": f"Dear {plan.name} team,\n\nthank you. While we complete our evaluation: {question}\n\n{SIGNATURE}",
        }


TRADE_WORDS = {
    "payment_days": lambda v: f"payment at {v} days",
    "contract_months": lambda v: f"a {v}-month commitment",
    "volume_per_year": lambda v: f"{v:,} units a year",
    "lead_time_days": lambda v: f"{v} days lead time",
    "incoterm": lambda v: f"delivery {v}",
    "index_clause": lambda v: "an index clause" if v else "a fixed price",
    "ppm_commitment": lambda v: f"{v} ppm",
    "chargeback_eur_per_complaint": lambda v: f"EUR {v} per complaint",
    "effective_date": lambda v: f"a start on {v}",
}


def trade_note(case: dict, lead: dict, terms: dict) -> str:
    """How an option differs from option A, said as the trade it is: "- if you prefer payment at 14 days"."""
    if terms is lead:
        return ""
    diffs = [TRADE_WORDS[f](terms[f]) for f in case["negotiable"] if f in TRADE_WORDS and terms.get(f) != lead.get(f)]
    return f" - our price for {' and '.join(diffs[:2])}" if diffs else ""
