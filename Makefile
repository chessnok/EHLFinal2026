# The negotiation arena agent (agent/). The key: ARENA_API_KEY in the root .env.
#   make me | sandbox | stats | final | test | lint

NEGOTIATOR = cd agent && uv run negotiator

.PHONY: install me sandbox stats report final test lint

install:
	git submodule update --init
	cd agent && uv sync

me:
	$(NEGOTIATOR) me

sandbox:
	$(NEGOTIATOR) run --set sandbox

stats:
	$(NEGOTIATOR) stats

report:
	$(NEGOTIATOR) report latest

final:
	$(NEGOTIATOR) final --parallel 10

test:
	cd agent && uv run pytest

lint:
	cd agent && uv run ruff check . && uv run ruff format --check .
