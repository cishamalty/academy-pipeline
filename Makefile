# academy-pipeline Makefile
# Usage:
#   make test                        run all tests
#   make run                         run full pipeline (all 6 courses)
#   make run-course c=compliance     run one course only
#   make lint                        check code style
#   make clean                       remove generated files

.PHONY: test run run-course lint clean

test:
	python -m pytest tests/ -v

run:
	python run.py

run-course:
	python run.py $(c)

lint:
	ruff check src/ flows/ tests/

clean:
	rm -rf data/processed/*
	rm -rf reports/*
	rm -rf logs/*
	rm -f data/academy.duckdb
