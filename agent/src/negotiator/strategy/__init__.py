"""Strategies by name. Add yours here: any class with prepare/decide/conclude/keepalive (see base.py),
constructed as Strategy(data, llm)."""

from collections.abc import Callable
from functools import partial

from negotiator.strategy.base import Decision, Strategy
from negotiator.strategy.baseline import BaselineStrategy
from negotiator.strategy.decided import DecidedStrategy
from negotiator.strategy.experiments import TACTICS, ExperimentStrategy
from negotiator.strategy.llm_strategy import LLMStrategy
from negotiator.strategy.patient import SCALES, PatientStrategy
from negotiator.strategy.playbook import VARIANTS, PlaybookStrategy
from negotiator.strategy.tactical import FLAGS as TACTICAL_FLAGS
from negotiator.strategy.tactical import TacticalStrategy
from negotiator.strategy.written import WrittenStrategy

STRATEGIES: dict[str, Callable[..., Strategy]] = {
    "tactical": TacticalStrategy,
    "baseline": BaselineStrategy,
    "llm": LLMStrategy,
    **{name: partial(ExperimentStrategy, tactic) for name, tactic in TACTICS.items()},
    **{name: partial(PlaybookStrategy, playbook) for name, playbook in VARIANTS.items()},
    **{name: partial(PatientStrategy, scale, name) for name, scale in SCALES.items()},
    "decided": DecidedStrategy,
    # tactical with one candidate change switched on, to measure it on its own (see FLAGS in tactical.py)
    **{f"tactical+{flag}": partial(TacticalStrategy, **{flag: True}) for flag in TACTICAL_FLAGS},
    # David's winner strategy: a fixed frame, the head computes and the mouth argues with it, patience (default),
    # yes only to conditions that cost us little and never to the price
    "tactical+winner": partial(TacticalStrategy, clause_rel_only=True, justified_arg=True, cheap_yes=True),
    # the final model before the winner defaults (tag final-candidate-2026-10-11c), for comparison
    "tactical-11c": partial(TacticalStrategy, clause_rel_only=False, justified_arg=False, cheap_yes=False),
    # the default without justified_arg (alone it lost P01 and P08, P-47)
    "tactical-nojust": partial(TacticalStrategy, justified_arg=False),
    # tactical's numbers, a model for the words (and, with +reader, for the levers the regular expressions miss)
    "tactical-llm": WrittenStrategy,
    "tactical-llm+reader": partial(WrittenStrategy, reader=True),
    # the evening's package: say yes to its structure and conditions, answer everything, negotiate longer and steadier
    "tactical+intense": partial(TacticalStrategy, alt_structure=True, answers=True, persistent=True),
    "tactical+yes": partial(TacticalStrategy, alt_structure=True, answers=True),
}
NEEDS_LLM = {"llm", "tactical-llm", "tactical-llm+reader"}
NEEDS_DECISIONS = {"decided"}  # constructed as Strategy(data, DecisionsClient)

__all__ = [
    "NEEDS_DECISIONS",
    "NEEDS_LLM",
    "DecidedStrategy",
    "STRATEGIES",
    "BaselineStrategy",
    "Decision",
    "LLMStrategy",
    "Strategy",
    "TacticalStrategy",
    "WrittenStrategy",
]
