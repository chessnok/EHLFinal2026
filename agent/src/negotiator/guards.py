"""Hard rules that keep a case from scoring 0 by mistake. Code, not judgement; checked before every
send and every accept, whatever the strategy decided.

Accept:  the sheet is the supplier's current standing offer; it keeps every must-have on the terms
         it would really close on (sheet, then the supplier's standard terms from its quote PDF) -
         and a must-have field we cannot read from either counts as broken; C is finite and beats
         the alternative - and, when there is one, the cheapest opening too (else the alternative
         scores at least as much).
Send:    every term sheet carries exactly the negotiable fields with allowed values and keeps the
         must-haves (a supplier may agree to any sheet we send, and we must be able to accept it);
         every cited ID exists in the data, the case's facts or this session's offers - a sentence
         whose IDs are all unknown goes, and so does a threat or an "other offer" without a rival's
         offer cited (conduct.py); at most 3 sheets and 20 refs.
"""

import math
import re

from arena_kit.cost import must_haves_ok

from negotiator.conduct import unsupported_sentences

ID_RE = re.compile(r"\b(?:idx|quote|offer|sc|qn|po|cost|fc|news|doc|ctr):[\w.:@#/-]*\w")
MAX_SHEETS = 3
MAX_REFS = 20


def unreadable_must_have_fields(case: dict, terms: dict, standard: dict | None) -> list[str]:
    """Must-have fields neither the sheet, the supplier's standard terms nor the case fixes.

    `closing_terms` fills such gaps from the buyer's plan (e.g. lead time = what we need), which
    would let a sheet pass that the arena closes on the supplier's real standard - unknown to us."""
    known = {**(standard or {}), **case.get("fixed_terms", {}), **{k: v for k, v in terms.items() if v is not None}}
    return [m["field"] for m in case["buyer"].get("must_haves", []) if m["field"] not in known]


def accept_problems(neg, supplier_id: str, term_sheet_id: str | None) -> list[str]:
    """Why accepting this sheet would be a mistake (empty: safe)."""
    t = neg.threads.get(supplier_id)
    if t is None:
        return ["unknown supplier"]
    standing_id, terms = t.standing
    problems = []
    if not term_sheet_id or term_sheet_id != standing_id:
        # the arena closes on the primary sheet whatever id we send (P10): only that one can be accepted
        problems.append(f"{term_sheet_id} is not the standing offer {standing_id}")
    if not terms or terms.get("unit_price") is None:
        problems.append("the standing offer has no price")
        return problems
    std = t.standard_terms
    if missing := unreadable_must_have_fields(neg.case, terms, std):
        problems.append(f"must-have field(s) {missing} unknown: no quote PDF standard terms")
    if not must_haves_ok(neg.case, terms, std):
        problems.append("breaks a must-have")
    c = neg.cost(supplier_id, terms)
    if not math.isfinite(c):
        problems.append("C is not finite")
    elif c >= neg.c_alt:
        problems.append(f"C {c:,.0f} does not beat the alternative {neg.c_alt:,.0f}")
    elif math.isfinite(neg.c_alt) and c >= neg.c_open:
        # a deal no better than the cheapest opening scores 0; the alternative scores at least that
        problems.append(f"C {c:,.0f} is not better than the opening {neg.c_open:,.0f}")
    return problems


def sheet_problems(case: dict, terms: dict, standard: dict | None = None) -> list[str]:
    problems = []
    negotiable = case["negotiable"]
    if set(terms) != set(negotiable):
        problems.append(f"fields {sorted(terms)} != negotiable {sorted(negotiable)}")
    options = case.get("term_options", {})
    for f, v in terms.items():
        if f == "unit_price":
            if not isinstance(v, int | float) or v <= 0:
                problems.append(f"unit_price {v!r}")
        elif options.get(f) and v not in options[f]:
            problems.append(f"{f}={v!r} not in options")
    # on the terms it would close on: a must-have on a field that is neither negotiable nor fixed is kept
    # (or broken) by the supplier's standard terms, not by our sheet
    if not must_haves_ok(case, terms, standard):
        problems.append("breaks a must-have")
    return problems


def known_id(neg, ref: str) -> bool:
    if neg.data and neg.data.fact(ref):
        return True
    if ref in (neg.case.get("facts") or {}):
        return True
    return any(
        s.get("term_sheet_id") == ref
        for t in neg.threads.values()
        for m in t.supplier_messages
        for s in m.get("term_sheets") or []
    )


def clean_message(neg, supplier_id: str, message: dict) -> tuple[dict, list[str]]:
    """The message with invalid sheets and unknown IDs removed, and what was removed."""
    removed: list[str] = []
    sheets = []
    for sheet in (message.get("term_sheets") or [])[:MAX_SHEETS]:
        thread = neg.threads.get(supplier_id)
        problems = sheet_problems(neg.case, sheet.get("terms", {}), thread.standard_terms if thread else None)
        if problems:
            removed.append(f"sheet {sheet.get('terms')}: {'; '.join(problems)}")
        elif sheet not in sheets:
            sheets.append(sheet)
    refs = []
    for ref in message.get("refs") or []:
        if known_id(neg, ref):
            if ref not in refs:
                refs.append(ref)
        else:
            removed.append(f"ref {ref}")

    def keep(m: re.Match) -> str:
        if known_id(neg, m.group(0)):
            return m.group(0)
        removed.append(f"body id {m.group(0)}")
        return ""

    # conduct.py: no claim without its source, no threat or "other offer" we cannot show
    rival_ids = {
        s.get("term_sheet_id")
        for other, t in neg.threads.items()
        if other != supplier_id
        for m in t.supplier_messages
        for s in m.get("term_sheets") or []
    }
    rival_cited = any(r in rival_ids or r.startswith("quote:") for r in refs)
    body, unsupported = unsupported_sentences(message.get("body") or "", ID_RE, lambda i: known_id(neg, i), rival_cited)
    removed += [f"unsupported sentence: {s}" for s in unsupported]
    body = ID_RE.sub(keep, body)
    body = re.sub(r"\s*\(\s*[,;\s]*\)", "", body)
    out = {**message, "body": body[:8000], "subject": (message.get("subject") or "")[:300], "refs": refs[:MAX_REFS]}
    if "term_sheets" in message:
        out["term_sheets"] = sheets
    return out, removed
