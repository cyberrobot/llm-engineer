# AI Discovery Assistant

An AI discovery assistant monorepo containing a Retrieval-Augmented Generation (RAG) backend and its React web application.

## Applications

| Application | Path | Stack |
| --- | --- | --- |
| API | `apps/api` | FastAPI, PostgreSQL + pgvector, Redis, OpenAI |
| RAG UI | `apps/rag-ui` | React, TypeScript, Tailwind CSS, Vite |

## Prerequisites

- Python 3.12
- Node.js 24 and npm
- Docker with Docker Compose

## Install

Install the monorepo workspaces from the repository root:

```sh
npm ci
```

Install the backend:

```sh
cd apps/api
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Create `apps/api/.env`:

```dotenv
OPENAI_API_KEY=your_openai_key
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/llm_engineer
REDIS_URL=redis://localhost:6379/0
DISABLE_CACHE=false
DEBUG_DELAY=false
DISABLE_INGEST=false
```

Create `apps/rag-ui/.env`:

```dotenv
VITE_API_URL=http://localhost:8000
```

## Run locally

Start PostgreSQL and Redis from the repository root:

```sh
docker compose up -d
```

Run the backend:

```sh
source apps/api/venv/bin/activate
npm run dev:api
```

Run the web app in another terminal:

```sh
npm run dev:web
```

The API is available at `http://localhost:8000` and the Vite development server at `http://localhost:5173`.

## Common commands

```sh
npm run build
npm run lint
npm run test:api
npm run test:storybook
```

## Docker

Build the backend image with the backend directory as its context:

```sh
docker build -t ai-discovery-assistant-api apps/api
```

## API endpoints

- `POST /rag-chat`
- `POST /ingest`
- `GET /audit-logs`

In production, consider setting `DISABLE_INGEST=true`, `DISABLE_CACHE=false`, and `DEBUG_DELAY=false`.
