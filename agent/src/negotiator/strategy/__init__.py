"""Strategies by name. Add yours here: any class with prepare/decide/conclude/keepalive (see base.py),
constructed as Strategy(data, llm)."""

from collections.abc import Callable

from negotiator.strategy.base import Decision, Strategy
from negotiator.strategy.baseline import BaselineStrategy
from negotiator.strategy.decided import DecidedStrategy
from negotiator.strategy.llm_strategy import LLMStrategy
from negotiator.strategy.tactical import TacticalStrategy

STRATEGIES: dict[str, Callable[..., Strategy]] = {
    "tactical": TacticalStrategy,
    "baseline": BaselineStrategy,
    "llm": LLMStrategy,
    "decided": DecidedStrategy,
}
NEEDS_LLM = {"llm"}
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
]
