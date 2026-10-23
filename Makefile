.PHONY: setup seed test chat target graph dataset review smoke eval calibrate

AGENT ?= triage
TENANT ?= T-003
NOW ?= 2026-01-14T19:30:00
IDS ?= D02 D24 D32
SPLIT ?= dev
REPS ?= 3
PREFIX ?= baseline
LIMIT ?=
JUDGE ?= 1
EXPERIMENT ?=

setup:
	uv sync

seed:
	uv run python -m app.seed

test:
	uv run pytest -q

chat:
	uv run python -m app.cli --agent $(AGENT) --tenant $(TENANT) --now $(NOW)

target:
	uv run python -m app.eval_target

graph:
	uv run python -m app.agent

dataset:
	uv run python -m evals.push_dataset

review:
	uv run python -m evals.review

smoke:
	uv run python -m evals.smoke --agent $(AGENT) $(IDS)

eval:
	uv run python -m evals.run_eval --agent $(AGENT) --split $(SPLIT) --reps $(REPS) --prefix $(PREFIX) $(if $(LIMIT),--limit $(LIMIT)) $(if $(filter 0,$(JUDGE)),--no-judge)

calibrate:
	uv run python -m evals.calibrate $(if $(EXPERIMENT),--experiment $(EXPERIMENT))
