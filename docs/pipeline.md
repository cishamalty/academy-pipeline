# Pipeline Guide — NSSF Hi-Innovator Academy Pipeline

> Last updated: April 2026
> Maintainer: Mugume Martin, Data Analyst — Outbox Uganda

---

## Overview

This pipeline replaces 6 manual Jupyter notebooks that previously cleaned
Thinkific LMS exports for the NSSF Hi-Innovator programme. It runs all
6 courses through a single parametrized pipeline, writes cleaned data to
DuckDB, and exports dated Excel/CSV files for stakeholders.

**Courses processed:**

| Course | Key | Output table |
|---|---|---|
| Business Foundation (Academy) | `academy` | `master_participants` |
| Business Compliance | `compliance` | `course_compliance` |
| Career Planning | `career_planning` | `course_career_planning` |
| E-Business Essentials | `e_biz` | `course_e_biz` |
| Financial Literacy 4 Artisans | `fl4_artisans` | `course_fl4_artisans` |
| Omusomo Gwa NSSF | `omusomo` | `course_omusomo` |

---

## Architecture

```
data/raw/{course}/          ← drop Thinkific export files here
        ↓
  src/ingest.py             ← discovers latest files, loads into DataFrames
        ↓
  src/validate.py           ← schema checks before cleaning (hard stop on failure)
        ↓
  flows/course_flow.py      ← merges all sources on email
        ↓
  src/clean.py              ← applies all cleaning functions
        ↓
  src/quality.py            ← quality assertions + writes report to reports/
        ↓
  src/export.py             ← writes to DuckDB + dated Excel/CSV file
        ↓
  data/academy.duckdb       ← Power BI connects here
  data/processed/YYYY-MM-DD/  ← stakeholder files
  reports/                  ← quality report per run
  logs/                     ← pipeline log per day
```

**Academy runs first.** It produces `data/processed/final_cleaned_bfc.xlsx`
which the other 5 courses merge against. If Academy fails, the full pipeline stops.

---

## Setup (first time)

**1. Clone the repository**
```bash
git clone https://github.com/cishamalty/academy-pipeline.git
cd academy-pipeline
```

**2. Create virtual environment and install dependencies**
```bash
python -m venv .venv
source .venv/Scripts/activate     # Windows
pip install -r requirements.txt
```

**3. Create your `.env` file**
```bash
cp .env.example .env
```
Edit `.env` if your paths differ from the defaults.

---

## Weekly run (every Monday)

**Step 1 — Download files from Thinkific**

For each course, log in to Thinkific and download:
- Post-course assessment results (CSV)
- Pre-course assessment results (CSV) — not needed for FL 4 Artisans
- Progress tracking (CSV)
- User export (CSV)

**Step 2 — Drop files into the correct folder**

```
data/raw/academy/          ← Academy files
data/raw/compliance/       ← Business Compliance files
data/raw/career_planning/  ← Career Planning files
data/raw/e_biz/            ← E-Business Essentials files
data/raw/fl4_artisans/     ← FL 4 Artisans files
data/raw/omusomo/          ← Omusomo files
```

No renaming needed. The pipeline picks up the most recently modified
file matching each pattern automatically.

**Step 3 — Run the pipeline**

```bash
# Activate environment
source .venv/Scripts/activate

# Run all 6 courses
make run

# Or run a single course
make run-course c=compliance
```

**Step 4 — Check the quality report**

After each run, open the latest `.txt` file in `reports/`:
```
reports/business_compliance_20260410_143022.txt
```

Review any FAIL or WARNING lines before sharing outputs with stakeholders.

**Step 5 — Share outputs**

Cleaned files are in:
```
data/processed/2026-04-10/
  Business Compliance_2026-04-10.csv
  Career Planning_2026-04-10.csv
  E Business_2026-04-10.csv
  FL A Artisans_2026-04-10.xlsx
  Omusomo_2026-04-10.csv
```

Power BI connects directly to `data/academy.duckdb` — no manual refresh needed.

---

## Running individual courses

```bash
# From terminal
python -m flows.pipeline compliance
python -m flows.pipeline career_planning
python -m flows.pipeline e_biz
python -m flows.pipeline fl4_artisans
python -m flows.pipeline omusomo
python -m flows.pipeline academy

# From Python
from flows.course_flow import run_course_flow
run_course_flow(course_key="compliance")
```

---

## Running tests

```bash
make test
# or
python -m pytest tests/ -v
```

All 102 tests should pass before any pipeline run in a new environment.

---

## Linting

```bash
make lint
# or
ruff check src/ flows/ tests/
```

CI runs this automatically on every push to GitHub.

---

## Adding a new course

1. **Add course config** — create `config/{course_key}.yaml` following the
   pattern of an existing course (e.g. `config/compliance.yaml`).
   Set: `course_name`, `course_key`, `raw_data_folder`, `source_files`,
   `survey_response_mapping`, `output`, feature flags.

2. **Add raw data folder** — create `data/raw/{course_key}/`.

3. **Add to pipeline** — add the course key to `COURSE_KEYS` list in
   `flows/pipeline.py`.

4. **Add tests** — add course-specific test cases to `tests/test_clean.py`
   if the course has unique mappings (e.g. extra hub names, language variants).

5. **Run and verify** — `make run-course c={course_key}`, check quality report.

---

## Adding a new hub

Open `config/base.yaml`, find the `hubs:` section.

Add to `hubs.valid`:
```yaml
- New Hub Name
```

Add to `hubs.mappings` for every raw variant you expect:
```yaml
new hub name: New Hub Name
new hub: New Hub Name
nhn: New Hub Name
```

No code changes needed. Tests will catch any issues on next `make test`.

---

## When Thinkific API access is granted

1. Open `config/base.yaml`
2. Change:
   ```yaml
   ingestion:
     mode: file
   ```
   to:
   ```yaml
   ingestion:
     mode: api
     api_key: "your-api-key-here"
     api_base_url: "https://api.thinkific.com/api/v2"
   ```
3. Implement `ThinkificIngester.load()` in `src/ingest.py`
4. Nothing else changes — all downstream modules are unaffected

---

## Rollback procedure

Each run writes to a dated folder. To roll back to a previous run:

1. Find the previous dated folder: `data/processed/2026-04-03/`
2. Share those files with stakeholders instead
3. To restore DuckDB to a previous state, re-run the pipeline
   pointing at the previous raw files

For DuckDB specifically — each run replaces the table entirely.
If you need to preserve a snapshot, copy `data/academy.duckdb` to
`data/academy_2026-04-03.duckdb` before running.

---

## Troubleshooting

**Pipeline fails with "Validation failed"**
A source file is missing a required column or the email column was not found.
Check the raw file — Thinkific may have changed its export format.
Update `config/base.yaml` → `email_columns` if the column name changed.

**Pipeline fails with "No file found for..."**
The file pattern in the course config doesn't match the downloaded filename.
Check `config/{course_key}.yaml` → `source_files` and update the glob pattern.

**Quality report shows high null rate on ESO Hub**
A new hub name variant appeared in the survey that isn't in the mappings.
Add it to `config/base.yaml` → `hubs.mappings` (or course config if course-specific).

**Power BI not refreshing**
Confirm Power BI is connected to `data/academy.duckdb` not a CSV file.
After a pipeline run the DuckDB tables are replaced — Power BI should
pick up the new data on next refresh.

**CI failing on GitHub**
Check the Actions tab on GitHub. Most common causes:
- A new import was added but not added to `requirements.txt` → `pip freeze > requirements.txt`
- Lint failure → run `ruff check src/ flows/ tests/ --fix` locally then push

---

## Project structure

```
academy-pipeline/
├── config/
│   ├── base.yaml              ← shared config (hubs, regions, gender, etc.)
│   ├── academy.yaml           ← Academy course config
│   ├── compliance.yaml
│   ├── career_planning.yaml
│   ├── e_biz.yaml
│   ├── fl4_artisans.yaml
│   └── omusomo.yaml
├── src/
│   ├── ingest.py              ← file discovery + loading
│   ├── validate.py            ← schema validation
│   ├── clean.py               ← all cleaning functions
│   ├── quality.py             ← quality checks + report writer
│   ├── export.py              ← DuckDB + file export
│   └── logger.py              ← logging setup
├── flows/
│   ├── course_flow.py         ← parametrized single-course Prefect flow
│   └── pipeline.py            ← master flow (all 6 courses)
├── tests/
│   ├── test_clean.py          ← 80 tests for clean.py
│   └── test_validate.py       ← 22 tests for validate.py
├── data/
│   ├── raw/{course}/          ← drop Thinkific files here
│   ├── processed/YYYY-MM-DD/  ← cleaned outputs (gitignored)
│   └── academy.duckdb         ← DuckDB database (gitignored)
├── docs/
│   ├── data_dictionary.md     ← column definitions
│   └── pipeline.md            ← this file
├── reports/                   ← quality reports per run (gitignored)
├── logs/                      ← pipeline logs per day (gitignored)
├── .github/workflows/ci.yml   ← GitHub Actions CI
├── .env                       ← local config (gitignored)
├── .env.example               ← config template
├── pyproject.toml             ← ruff + pytest config
├── Makefile                   ← make test / run / lint / clean
└── requirements.txt           ← pinned dependencies
```
