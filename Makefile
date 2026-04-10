# academy-pipeline Makefile
# Usage:
#   make test              run all tests
#   make run               run full pipeline (all 6 courses)
#   make run-course c=compliance   run one course only
#   make lint              check code style
#   make clean             remove generated files

.PHONY: test run run-course lint clean

# Run all tests
test:
	python -m pytest tests/ -v

# Run full pipeline — Academy first, then all 5 courses
run:
	python -m flows.pipeline

# Run a single course: make run-course c=compliance
run-course:
	python -m flows.pipeline $(c)

# Lint with ruff
lint:
	ruff check src/ flows/ tests/

# Remove generated outputs (keeps source data)
clean:
	rm -rf data/processed/*
	rm -rf reports/*
	rm -rf logs/*
	rm -f data/academy.duckdb
