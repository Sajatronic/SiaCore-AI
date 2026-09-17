# SiaCore News Intelligence Pipeline

> An AI-powered news intelligence service for detecting, enriching, and assessing supply-chain risks from unstructured external signals.

This repository contains the **News Intelligence pipeline** developed as part of **SiaCore**, an end-to-end supply-chain risk intelligence platform. The system collects articles and risk signals from multiple providers, filters irrelevant content, converts relevant articles into structured `RiskEvent` records, links events to canonical supply-chain entities, estimates severity, predicts potential operational impact, and exposes the results through the SiaEye dashboard API.

The implementation is designed to transform noisy news data into explainable, entity-specific intelligence for manufacturers, distributors, components, locations, and market-supply decisions.

## Project Context

SiaCore combines internal supply-chain data, such as inventory and distributor information, with external risk signals, including news, natural disasters, market events, compliance events, and product-change notices. This repository focuses on the **news and external-signal processing layer**.

The project was developed as a team-based graduation project. My contribution focused on the news-processing workflow and its supporting intelligence services, including relevance filtering, named entity recognition and entity linking, event classification, severity estimation, deduplication, clustering, provenance tracking, risk analysis, and impact prediction.

## What the System Does

The pipeline performs the following stages:

1. **Ingestion** – Fetches articles and external signals through registered providers.
2. **Relevance filtering** – Scores articles using configurable supply-chain topics, canonical entities, manufacturers, categories, and provider metadata.
3. **Normalization** – Converts provider-specific records into a common article model.
4. **Entity extraction and linking** – Detects manufacturers, suppliers, locations, components, and related supply-chain entities, then links them to the canonical entity registry.
5. **Event classification** – Maps articles to the configured event taxonomy.
6. **Severity estimation** – Produces a severity score and supporting signal information.
7. **Deduplication and clustering** – Detects repeated coverage of the same event using fingerprints and fuzzy title matching.
8. **Risk analysis** – Generates structured, explainable business and supply-chain impact analysis for qualifying events.
9. **Impact prediction** – Estimates dimensions such as supply delay, manufacturing disruption, logistics disruption, inventory shortage, and price increase.
10. **Persistence and serving** – Stores results when configured and exposes them through the SiaEye read API and dashboard.

Every event retains source URLs, processing-stage audit information, confidence values, and provenance metadata. This supports traceability and helps identify records that require human review.

## Architecture

```text
News and external-signal providers
                |
                v
        Provider registry
                |
                v
       Relevance pre-filter
                |
                v
      LangGraph pipeline graph
                |
      +---------+----------+----------------+
      |                    |                |
      v                    v                v
 Entity extraction   Classification   Severity scoring
      |                    |                |
      +---------+----------+----------------+
                |
                v
       Entity linking and enrichment
                |
      +---------+----------+----------------+
      |                    |                |
      v                    v                v
 Deduplication       Risk analysis    Impact prediction
                |
                v
        Persistence and JSON output
                |
                v
       FastAPI SiaEye API
                |
                v
       React/Vite dashboard
```

The backend is organized around a stateful pipeline graph. Pydantic models define the structured state and output contracts, while YAML configuration files control taxonomies, relevance rules, alert rules, source reliability, and impact baselines.

## Supported Providers

The provider registry currently includes adapters for:

- **GDELT**
- **GDACS**
- **Marketaux**
- **GNews**
- **NewsData.io**

Providers can be enabled or disabled through configuration. The default search query targets semiconductor and supply-chain disruption signals, including factory shutdowns, sanctions, port closures, and strikes.

## Repository Structure

```text
.
├── api/                  FastAPI application and SiaEye API routes
├── canonical/            Canonical entity registry and matching logic
├── config/               Settings, taxonomies, thresholds, and YAML rules
├── data/                 Canonical entities and pipeline audit snapshots
├── db/                   PostgreSQL and Supabase persistence adapters
├── frontend/             React/Vite SiaEye dashboard
├── graph/                LangGraph pipeline construction and state setup
├── migrations/           SQL schema migrations
├── models/               Pydantic pipeline and domain schemas
├── nodes/                Pipeline nodes, processing, and pre-filtering
├── providers/            External news and risk-signal providers
├── scripts/              Utility and provider test scripts
├── services/             Analysis, deduplication, storage, alerts, and prediction
├── tests/                Unit and pipeline integration tests
├── main.py               Command-line pipeline entry point
├── requirements.txt      Python dependencies
└── .env.example          Environment variable template
```

## Requirements

- Python **3.10+**
- Node.js **18+** and npm for the dashboard
- PostgreSQL or Supabase if persistent database storage is required
- API credentials for the selected news providers and language model provider when running live ingestion or LLM-assisted stages

## Backend Setup

Clone the repository and create a virtual environment:

```bash
git clone https://github.com/nourhan03/news-agent.git
cd news-agent

python -m venv .venv
source .venv/bin/activate       # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
```

Create a local environment file:

```bash
cp .env.example .env
```

Then configure only the providers, model credentials, and database settings required for your run. Do not commit `.env` or server-side database credentials.

The project supports OpenRouter-compatible LLM endpoints and Cerebras configuration. Database persistence can use either a PostgreSQL connection string or Supabase REST credentials, depending on the deployment environment.

## Running the Pipeline

### Dry run without external API calls

The dry run uses sample articles and is the quickest way to verify the pipeline locally:

```bash
python main.py --dry-run
```

Write the machine-readable result to a file:

```bash
python main.py --dry-run --output result.json
```

### Live ingestion

After configuring provider and model credentials, fetch live articles and process them:

```bash
python main.py --ingest --output result.json
```

### Build the canonical entity registry

If the supply-chain database is available, generate the canonical entity snapshot with:

```bash
python main.py --build-entities
```

### Apply database migrations

For a configured PostgreSQL database:

```bash
python main.py --migrate
```

### Backfill supply-chain links

Recompute links for persisted Supabase events without writing changes first:

```bash
python main.py --backfill-supabase --backfill-dry-run
```

Run the actual backfill only after reviewing the dry-run summary:

```bash
python main.py --backfill-supabase
```

## Running the SiaEye API

Start the FastAPI service with Uvicorn:

```bash
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

The interactive API documentation is available at:

```text
http://localhost:8000/docs
```

The API can serve the built React dashboard when `frontend/dist` exists. It also includes a fallback static interface under `api/static`.

### Main endpoints

| Endpoint | Description |
| --- | --- |
| `GET /health` | Lightweight health check |
| `GET /api/health` | SiaEye API health and platform metadata |
| `GET /api/meta` | Product and pipeline metadata |
| `GET /api/events` | List risk events with filtering options |
| `GET /api/events/{event_id}` | Retrieve one event in detail |
| `GET /api/stats/summary` | Summary statistics for processed events |
| `GET /api/stats/geo` | Geographic event statistics, with optional severity filtering |
| `GET /api/alerts` | List configured or matched alerts |
| `GET /api/runs` | List pipeline runs |

Example health request:

```bash
curl http://localhost:8000/api/health
```

Example event request:

```bash
curl "http://localhost:8000/api/events?min_severity=50"
```

## Running the Frontend

The SiaEye dashboard is a React application built with Vite and Leaflet:

```bash
cd frontend
npm install
npm run dev
```

For a production build:

```bash
npm run build
npm run preview
```

The frontend reads data from the SiaEye API. Ensure the API is running and that the configured CORS origins include the dashboard URL.

## Configuration

The main configuration files are:

- `config/event_taxonomy.yaml` – Event categories and classification rules.
- `config/relevance_keywords.yaml` – Topic and keyword scoring rules.
- `config/source_reliability.yaml` – Provider reliability settings.
- `config/alert_rules.yaml` – Alert matching rules.
- `config/impact_baselines.yaml` – Baseline factors used in impact prediction.
- `config/strategic_locations.py` – Strategic geographic locations.
- `data/canonical_entities.json` – Canonical manufacturers, suppliers, distributors, locations, and components.

Important environment variables include `SUPPLY_CHAIN_SEARCH_QUERY`, `PROVIDER_FETCH_LIMIT`, `RELEVANCE_MIN_SCORE`, `PERSIST_EVENTS`, `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_KEY`, `RISK_ANALYSIS_ENABLED`, and `IMPACT_PREDICTION_ENABLED`. The complete template is available in `.env.example`.

## Testing

Install the development dependencies from `requirements.txt`, then run:

```bash
pytest -q
```

The test suite covers provider adapters, relevance filtering, entity linking, event classification, severity and confidence engines, deduplication, storage, impact prediction, risk analysis, API routes, and pipeline integration.

The integration smoke test can also be run directly:

```bash
pytest -q tests/test_pipeline_integration.py
```

## Output Model

The central output type is `RiskEvent`. Each event can include:

- Event title, summary, type, category, and lifecycle status.
- Severity score and classification confidence.
- Extracted and linked manufacturers, suppliers, locations, and components.
- Source URLs, article identifiers, and verification score.
- Geographic information when available.
- Structured risk analysis and impact prediction.
- Explainability fields and processing provenance.
- Audit stages and human-review indicators.

The default command-line output is JSON, which allows downstream services to consume pipeline results without depending on the internal Python implementation.

## Design Principles

**Explainability over opaque scoring.** The system preserves evidence, confidence, matched terms, source information, and processing stages alongside the result.

**Provider isolation.** Each external source is implemented behind a provider interface so that ingestion logic remains independent of provider-specific response formats.

**Configurable intelligence.** Taxonomies, thresholds, reliability rules, alert rules, and impact baselines are stored outside the core pipeline code where possible.

**Safe persistence.** Event identity is stabilized through fingerprints and fuzzy matching to reduce duplicate records while retaining update behavior for recurring coverage.

**Human review support.** Low-confidence or ambiguous events can be routed to a review queue instead of being treated as equally reliable automated decisions.

## Current Scope and Limitations

This repository is primarily a news-intelligence and read-API service. Alert rules are represented and evaluated, but alert delivery is not the focus of the current phase. Live ingestion also depends on the availability and rate limits of external providers and configured model endpoints. Database-backed operation requires valid PostgreSQL or Supabase credentials and applied migrations.

## License

No license file is currently included in the repository. Add a license before distributing or reusing the project outside its current project context.

## References

[1]: https://github.com/nourhan03/news-agent "SiaCore News Intelligence Pipeline repository"

[2]: https://langchain-ai.github.io/langgraph/ "LangGraph documentation"

[3]: https://fastapi.tiangolo.com/ "FastAPI documentation"

[4]: https://vite.dev/guide/ "Vite documentation"
