"""Strategies by name. Add yours here: any class with prepare/decide/conclude/keepalive (see base.py),
constructed as Strategy(data, llm)."""

from collections.abc import Callable
from functools import partial

from negotiator.strategy.base import Decision, Strategy
from negotiator.strategy.baseline import BaselineStrategy
from negotiator.strategy.experiments import TACTICS, ExperimentStrategy
from negotiator.strategy.llm_strategy import LLMStrategy
from negotiator.strategy.playbook import VARIANTS, PlaybookStrategy
from negotiator.strategy.tactical import TacticalStrategy

STRATEGIES: dict[str, Callable[..., Strategy]] = {
    "tactical": TacticalStrategy,
    "baseline": BaselineStrategy,
    "llm": LLMStrategy,
    **{name: partial(ExperimentStrategy, tactic) for name, tactic in TACTICS.items()},
    **{name: partial(PlaybookStrategy, playbook) for name, playbook in VARIANTS.items()},
}
NEEDS_LLM = {"llm"}

__all__ = ["NEEDS_LLM", "STRATEGIES", "BaselineStrategy", "Decision", "LLMStrategy", "Strategy", "TacticalStrategy"]
