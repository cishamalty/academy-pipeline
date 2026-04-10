# Data Dictionary — NSSF Hi-Innovator Academy Pipeline

> Last updated: April 2026
> Maintainer: Mugume Martin, Data Analyst — Outbox Uganda

This document defines every column in the cleaned output tables.
All courses share the core columns. Course-specific columns are noted.

---

## Core output columns (all courses)

| Column | Type | Description | Source | Values |
|---|---|---|---|---|
| `email` | string | Participant email address — primary key | Thinkific user export | Cleaned: lowercase, trimmed |
| `Full Name` | string | First name + last name concatenated | Thinkific user export | e.g. "Alice Nakamya" |
| `First Name` | string | Participant first name | Thinkific user export | Free text |
| `Last Name` | string | Participant last name | Thinkific user export | Free text |
| `Gender` | string | Participant gender | Post-course survey (Response.1) | Male · Female · Other · Prefer not to say · Not Specified |
| `Age group` | string | Participant age band | Post-course survey (Response.2) | Below 18 · 18-24 · 25-35 · 36+ · Not Assigned |
| `ESO Hub` | string | Enterprise Support Organisation hub | Post-course survey (Response.5) | Outbox · Mubs-Eiic · Miic · Sbil · Witu · Mkazipreneur · Ucu Mbale · Starthub · Zimba Women · Curad · Inpact · Adc · Shona · Not Assigned |
| `Region` | string | Geographic region derived from district | Derived from District | Central · Eastern · Northern · Western · Unknown |
| `District` | string | District of residence | Post-course survey (Omusomo: Response.3) | 112 districts of Uganda |
| `DISABILITY` | string | Disability status, standardised | Post-course survey | Visual Impairment · Hearing Impairment · Physical Disability · Intellectual Disability · Not Disabled |
| `NATIONALITY` | string | Nationality of participant | User export | National · [country name] — defaults to "National" if blank |
| `% Completed` | float | Course completion percentage | Thinkific progress tracking | 0.0 – 100.0 |
| `% Completed Category` | string | Binned completion category | Derived from % Completed | 0%-25% · 26%-50% · 51%-75% · 76%-100% |
| `Completed At` | datetime | Date and time course was completed | Thinkific progress tracking | ISO datetime, null if not completed |
| `Activated At` | datetime | Date participant first activated their account | Thinkific user export | ISO datetime |
| `Started At` | datetime | Date participant started the course | Thinkific progress tracking | ISO datetime |
| `Last Sign In` | datetime | Date of participant's last login | Thinkific user export | ISO datetime |
| `Quarter` | string | Programme quarter derived from completion date | Derived from Completed At | Y4Q3 · Y4Q4 · Y5Q1 … Y7Q2 |
| `Phone number` | string | Participant phone number | Thinkific user export | Free text, may include country code |
| `_loaded_at` | datetime | Timestamp when this row was loaded into the database | Pipeline metadata | ISO datetime |
| `_course` | string | Course name this row belongs to | Pipeline metadata | e.g. "Business Compliance" |

---

## Email validation columns (Compliance, Career Planning, E-Business only)

| Column | Type | Description | Values |
|---|---|---|---|
| `email_status` | string | Validation result for email address | VALID · NEEDS_REVIEW · SUSPICIOUS · LIKELY_FAKE · INVALID |
| `email_risk_score` | integer | Risk score 0–10 (higher = more suspicious) | 0 = clean, 10 = invalid format |
| `corrected_email` | string | Email with domain typo corrected if detected | e.g. "user@gmail.com" if original was "user@gmial.com" |
| `can_receive_emails` | boolean | Whether this email can receive communications | True · False |
| `likely_authentic` | boolean | Whether this email is likely a real person | True · False |

---

## Course-specific columns

| Column | Course | Description |
|---|---|---|
| `Own a Business` | Career Planning only | Whether participant owns a business at time of enrolment |
| `Business Name` | Academy only | Name of participant's business |
| `Sector` | Academy only | Business sector |
| `Seed Funded` | Academy only | Whether the business received seed funding |
| `NSSF Compliance` | Academy only | Whether the business is NSSF-compliant |

---

## DuckDB tables

| Table | Description | Refreshed |
|---|---|---|
| `master_participants` | Academy BFC master — all 438 SGBs with full profiling data | Every Academy run |
| `course_compliance` | Cleaned Business Compliance course data | Every pipeline run |
| `course_career_planning` | Cleaned Career Planning course data | Every pipeline run |
| `course_e_biz` | Cleaned E-Business Essentials course data | Every pipeline run |
| `course_fl4_artisans` | Cleaned Financial Literacy 4 Artisans data | Every pipeline run |
| `course_omusomo` | Cleaned Omusomo Gwa NSSF data | Every pipeline run |

### Querying DuckDB

```python
from src.export import query_duckdb, list_tables

# See all tables
tables = list_tables("data/academy.duckdb")

# Query a course
df = query_duckdb("SELECT * FROM course_compliance", "data/academy.duckdb")

# Cross-course completion summary
df = query_duckdb("""
    SELECT _course, COUNT(*) AS enrolled,
           SUM(CASE WHEN "% Completed" = 100 THEN 1 ELSE 0 END) AS completed,
           ROUND(AVG("% Completed"), 1) AS avg_completion
    FROM course_compliance
    GROUP BY _course
""", "data/academy.duckdb")
```

---

## Value reference

### ESO Hub codes

| Standard value | Raw variants accepted |
|---|---|
| Outbox | outbox, outbox hub |
| Mubs-Eiic | mubs, mubs-eiic, mubs eiic, makerere university business school |
| Miic | miic, miic hub, metropolitan, makerere innovation and incubation center |
| Sbil | sbil, stanbic, stanbic business incubator, stanbic business incubation |
| Witu | witu, women in tech, women in technology uganda |
| Mkazipreneur | mkazipreneur, mkaziprenuer, mkazi |
| Ucu Mbale | ucu, ucu mbale, ucu innovation hub, uganda christian university |
| Starthub | starthub, start hub |
| Zimba Women | zimba, zimba women |
| Curad | curad |
| Inpact | inpact |
| Adc | adc, agribusiness development centre |
| Shona | shona |
| Not Assigned | (blank), not assigned |

### Quarter labels

| Label | Period |
|---|---|
| Y4Q3 | Jan – Mar 2024 |
| Y4Q4 | Apr – Jun 2024 |
| Y5Q1 | Jul – Sep 2024 |
| Y5Q2 | Oct – Dec 2024 |
| Y5Q3 | Jan – Mar 2025 |
| Y5Q4 | Apr – Jun 2025 |
| Y6Q1 | Jul – Sep 2025 |
| Y6Q2 | Oct – Dec 2025 |
| Y6Q3 | Jan – Mar 2026 |
| Y6Q4 | Apr – Jun 2026 |

### Disability categories

| Standard value | Keywords matched |
|---|---|
| Visual Impairment | blind, visual, sight, low vision |
| Hearing Impairment | deaf, hearing, mute |
| Physical Disability | physical, mobility, wheelchair, amputee, limb |
| Intellectual Disability | intellectual, learning disability, cognitive |
| Not Disabled | none, no, not applicable, n/a, not disabled, (blank) |

---

## Data quality flags

Any row where `email_status` is not VALID should be reviewed before use in communications.
Rows where `ESO Hub = "Not Assigned"` were not matched to any known hub — check the raw source file.
Rows where `Quarter` is null have no completion date recorded.
