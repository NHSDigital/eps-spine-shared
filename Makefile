SHELL:=/usr/bin/env bash -O globstar
.SHELLFLAGS = -ec

.PHONY: install lint format test

install:
	asdf install && \
	poetry install && \
	poetry run pre-commit install

lint:
	poetry run flake8 src tests
	poetry run black --check src tests
	poetry run isort --check-only src tests

format:
	poetry run black src tests
	poetry run isort src tests

test:
	poetry run pytest tests
