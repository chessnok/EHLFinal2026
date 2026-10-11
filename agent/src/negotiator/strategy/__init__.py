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
    # tactical's numbers, a model for the words (and, with +reader, for the levers the regular expressions miss)
    "tactical-llm": WrittenStrategy,
    "tactical-llm+reader": partial(WrittenStrategy, reader=True),
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
