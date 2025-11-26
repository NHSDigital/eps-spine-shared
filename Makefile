SHELL:=/usr/bin/env bash -O globstar
.SHELLFLAGS = -ec

.PHONY: build check-licenses format install lint test

build:
	poetry build

check-licenses:
	scripts/check_python_licenses.sh

format:
	poetry run black src tests
	poetry run isort src tests

install:
	asdf install && \
	poetry install && \
	poetry run pre-commit install

lint:
	poetry run flake8 src tests
	poetry run black --check src tests
	poetry run isort --check-only src tests

test:
	poetry run pytest tests
