PYTHON ?= python3
WEB_DIR := apps/web
PYTHON_SERVICES := services/api-gateway services/agent services/retrieval services/inference

.PHONY: help install install-python install-web test test-python test-web lint lint-python lint-web run-web eval-quality eval-quality-check clean

help:
	@echo "Targets:"
	@echo "  install       Install Python and web development dependencies"
	@echo "  test          Run all unit tests"
	@echo "  lint          Run Python and TypeScript static checks"
	@echo "  run-web       Start the web development server"
	@echo "  eval-quality  Run the offline quality evaluation and write its reports"
	@echo "  eval-quality-check  Run the quality evaluation and fail on a threshold regression"
	@echo "  clean         Remove local build and test artifacts"

install: install-python install-web

install-python:
	$(PYTHON) -m pip install -e "libs/observability[dev]" -e "services/api-gateway[dev]" -e "services/agent[dev]" -e "services/retrieval[dev]" -e "services/inference[dev]"

install-web:
	npm --prefix $(WEB_DIR) install

test: test-python test-web

test-python:
	$(PYTHON) -m pytest

test-web:
	npm --prefix $(WEB_DIR) test -- --run

lint: lint-python lint-web

lint-python:
	$(PYTHON) -m ruff check libs services tests scripts evaluation load-tests

lint-web:
	npm --prefix $(WEB_DIR) run lint

run-web:
	npm --prefix $(WEB_DIR) run dev

eval-quality:
	$(PYTHON) -m evaluation.quality.run

eval-quality-check:
	$(PYTHON) -m evaluation.quality.run --check-thresholds

clean:
	find . -type d \( -name __pycache__ -o -name .pytest_cache -o -name .ruff_cache -o -name dist \) -prune -exec rm -rf {} +
