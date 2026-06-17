# Project Specification — Natural Language Analytics Dashboard

| Field | Value |
|---|---|
| **Project** | Natural Language Analytics Dashboard |
| **UI Framework** | Streamlit |
| **Data Backend** | Existing SQL database (SQLite / PostgreSQL / MySQL) |
| **Core Capability** | Plain-English question → SQL → data → chart or written answer + insights + suggested follow-ups |
| **Document Purpose** | Project source-of-truth for downstream Spec-Driven Development |

---

## 1. Overview

Build an analytics application that lets users query structured business data in a SQL database using natural language. The app translates a user's question into a database query, retrieves the data, and presents the result in the clearest form — an appropriate chart for multi-row datasets, or a written sentence for single-value answers — inside a Streamlit interface.

Beyond presenting the data, the app also **explains what the result means in plain language, surfaces actionable insights grounded in the returned data, and suggests relevant follow-up questions** the user can run next. Accurate query generation and faithful visualization remain the foundation; insights are layered on top of correctly retrieved data, never invented in place of it.

---

## 2. Business Problem

Business users often need answers from structured data but don't know SQL. The system lets them ask questions in plain English and receive visual representations of the data without writing queries manually.

Representative questions:

- Show monthly revenue trend for 2025
- Top 10 products by revenue
- Revenue by region
- Customer distribution by segment
- Profit trend over the last 12 months
- Sales by category
- Revenue vs profit by product

---

## 3. Objectives

**The application should:**

- Accept natural-language questions
- Retrieve data from an existing SQL database
- Generate and execute valid SQL queries
- Present multi-row results visually as charts
- Present single-value results as a plain-language sentence (e.g. "Total revenue for this quarter is 200K USD")
- Support multiple chart types
- Generate actionable insights derived from the returned data
- Suggest relevant follow-up questions the user can run next
- Let users explore business data without SQL knowledge

**The application should not:**

- Invent insights or figures not supported by the returned data
- Take actions or make decisions on the user's behalf (it informs and recommends; the user decides and acts)
- Perform statistical forecasting or predictive modeling (see Out of Scope)

---

## 4. User Personas

| Persona | Need | Example Questions |
|---|---|---|
| **Business Analyst** | Quick metrics & trends without SQL | Monthly revenue this year; which products generated the most revenue; compare revenue across regions |
| **Operations Manager** | Operational visibility | Orders by month; product performance by category; revenue distribution by region |
| **Product Manager** | Product-level reporting | Top performing products; product revenue trends; category-wise sales breakdown |

---

## 5. Data Source

The system uses an **existing** SQL database. The schema will be provided before implementation.

- **Supported DB types:** SQLite, PostgreSQL, MySQL
- **Example business entities:** Orders, Products, Customers, Categories, Regions

---

## 6. Core Features

### 6.1 Natural Language Querying
Users ask questions in plain English; the system converts them into valid database queries.
Examples: *Show monthly sales* · *Revenue by category* · *Top 5 products by revenue* · *Orders by region*

### 6.2 Query Execution
- Only **read** operations are permitted
- Results must be displayed to users
- Invalid queries handled gracefully

### 6.3 Result Presentation
The system chooses the clearest presentation for the returned dataset based on its shape:

| Result Shape | Presentation |
|---|---|
| Single value (1 row × 1 column) | Plain-language sentence / metric — e.g. "Total revenue for this quarter is 200K USD" |
| Category + measure | **Bar** chart — revenue by category/region; top products |
| Time series | **Line** chart — monthly revenue trend; daily order volume; quarterly profit |
| Parts of a whole | **Pie** chart — revenue share by category; segment distribution |
| Two numeric measures | **Scatter** plot — revenue vs profit; quantity vs revenue |
| Other / ambiguous | Table only |

### 6.4 Insights
Alongside the chart or written answer, the system generates a short set of **actionable insights** derived from the returned data — e.g. notable peaks, leaders/laggards, concentration, or quarter-over-quarter change. Insights must be grounded in the actual values returned by the query; the system does not introduce numbers or claims the data doesn't support.

### 6.5 Suggested Next Questions
The system proposes a few relevant **follow-up questions** based on the current result (e.g. after "revenue by region," suggest "show the monthly trend for the top region"). Suggestions are presented as one-click prompts that re-run as new queries.

### 6.6 Tabular View
Raw query results in table format, with **pagination**, **sorting**, and **download**.

### 6.7 Query History
Session-level history of user questions: view previously executed questions and re-run them.

---

## 7. User Interface — Main Dashboard

| Component | Description |
|---|---|
| **Question Input** | Enter natural-language requests (e.g. "Show monthly revenue trend for 2025") |
| **Execute Button** | Triggers processing |
| **SQL Display** | Shows generated SQL — for transparency, debugging, validation |
| **Results Table** | Displays returned records |
| **Visualization Area** | Displays a chart, or a written-answer panel when the result is a single value |
| **Insights Panel** | Displays plain-language insights derived from the returned data |
| **Suggested Questions** | Displays clickable follow-up questions that re-run as new queries |
| **Query History Panel** | Displays previously executed requests |

---

## 8. Functional Requirements

| ID | Requirement |
|---|---|
| FR-1 | Users shall submit natural-language questions |
| FR-2 | System shall generate SQL corresponding to the request |
| FR-3 | System shall validate generated SQL before execution |
| FR-4 | System shall execute valid SQL queries |
| FR-5 | System shall display returned data in tabular format |
| FR-6 | System shall select the appropriate presentation (chart type, or written answer for single-value results) based on result shape |
| FR-7 | System shall render charts from returned data |
| FR-8 | System shall present single-value results as a plain-language sentence |
| FR-9 | System shall generate actionable insights grounded in the returned data |
| FR-10 | System shall suggest relevant follow-up questions that can be run with one click |
| FR-11 | System shall maintain query history during the active session |
| FR-12 | Users shall be able to export query results as CSV |

---

## 9. Validation Requirements

Only read-only operations are permitted. The system **must reject**:

`INSERT` · `UPDATE` · `DELETE` · `DROP` · `ALTER` · `TRUNCATE`

---

## 10. Error Handling Requirements

| Scenario | Example | Response |
|---|---|---|
| Invalid question | "Show dragon sales by galaxy" | `Unable to identify requested entities.` |
| Invalid SQL | — | `Generated query could not be validated.` |
| Empty results | — | `No data found for the requested query.` |
| Database error | — | `Unable to retrieve data at this time.` |

---

## 11. Reporting Requirements

| Output | Format |
|---|---|
| Query results | CSV |
| Visualizations | PNG |

---

## 12. Non-Functional Requirements

| Attribute | Requirement |
|---|---|
| **Performance** | Typical query response under 10 seconds; target dataset up to 1 million records |
| **Reliability** | Recovers gracefully from query failures |
| **Insight accuracy** | Insights and written answers must reflect the actual returned data; no fabricated figures or unsupported claims |
| **Usability** | No SQL knowledge required |
| **Maintainability** | All major functionality documented before implementation |

---

## 13. Assumptions

- Database schema is known beforehand
- Users have read-only access to data
- Data quality is outside scope
- Authentication and authorization are outside scope

---

## 14. Out of Scope

Forecasting · Predictive / statistical modeling · ML-based recommendation engines · Autonomous actions or decisions on the user's behalf · Multi-database federation · User management · Role-based access control · Dashboard sharing

> Note: Qualitative insights and suggested follow-up questions are **in scope** (§6.4–6.5). What remains out of scope is *predictive* analytics and *automated action* — the system explains and recommends, but does not forecast or act.

---

## 15. Acceptance Criteria

The project is complete when:

**Querying** — NL questions can be submitted; SQL is generated successfully; SQL executes successfully.
**Visualization** — Bar, line, pie, and scatter charts are supported.
**Results presentation** — Single-value results are explained in plain language; multi-row results are charted.
**Insights** — Actionable insights are generated and grounded in the returned data.
**Next questions** — Relevant follow-up questions are suggested and runnable with one click.
**Results** — Data table is displayed; CSV export works.
**User Experience** — Query history is available; errors are displayed clearly.
**Security** — Non-read-only SQL statements are blocked.
**Documentation** — Requirements, data contracts, workflow, validation rules, and acceptance criteria are documented.
