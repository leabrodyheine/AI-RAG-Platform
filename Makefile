PYTHON ?= python3
WEB_DIR := apps/web
PYTHON_SERVICES := services/api-gateway services/agent services/retrieval services/inference

.PHONY: help install install-python install-web test test-python test-web lint lint-python lint-web run-web clean

help:
	@echo "Targets:"
	@echo "  install      Install Python and web development dependencies"
	@echo "  test         Run all unit tests"
	@echo "  lint         Run Python and TypeScript static checks"
	@echo "  run-web      Start the web development server"
	@echo "  clean        Remove local build and test artifacts"

install: install-python install-web

install-python:
	$(PYTHON) -m pip install -e "services/api-gateway[dev]" -e "services/agent[dev]" -e "services/retrieval[dev]" -e "services/inference[dev]"

install-web:
	npm --prefix $(WEB_DIR) install

test: test-python test-web

test-python:
	$(PYTHON) -m pytest

test-web:
	npm --prefix $(WEB_DIR) test -- --run

lint: lint-python lint-web

lint-python:
	$(PYTHON) -m ruff check services tests scripts

lint-web:
	npm --prefix $(WEB_DIR) run lint

run-web:
	npm --prefix $(WEB_DIR) run dev

clean:
	find . -type d \( -name __pycache__ -o -name .pytest_cache -o -name .ruff_cache -o -name dist \) -prune -exec rm -rf {} +
