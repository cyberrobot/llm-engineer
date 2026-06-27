# Enterprise RAG Demo

A Retrieval-Augmented Generation (RAG) system demonstrating grounded AI responses, hybrid retrieval, audit logging, caching, and observability tooling.

Built with FastAPI, React, PostgreSQL + pgvector, Redis, and OpenAI APIs.

⸻

### Features

- Semantic vector retrieval
- Hybrid vector + keyword search
- Source-grounded AI responses
- Retrieval reranking
- Role-based access control
- Redis caching
- Audit log history
- Retrieval & generation debug panel
- Redis-backed API rate limiting
- Railway deployment support

⸻

### Tech Stack

**Frontend**

- React
- TypeScript
- Tailwind CSS
- Vite

**Backend**

- FastAPI
- PostgreSQL
- pgvector
- Redis
- SlowAPI
- OpenAI API

⸻

### Architecture

React UI →
FastAPI API →
Retrieval Pipeline →
PostgreSQL + pgvector →
OpenAI APIs →
Redis Cache

⸻

### Running Locally

**Backend**

```
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Create .env:

```
OPENAI_API_KEY=your_openai_key
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/llm_engineer
REDIS_URL=redis://localhost:6379/0
DISABLE_CACHE=false
DEBUG_DELAY=false
DISABLE_INGEST=false
```

Start services:

```
docker compose up -d
uvicorn api.main:app --reload
```

⸻

**Frontend**

```
npm install
npm run dev
```

Create .env:

```
VITE_API_URL=http://localhost:8000
```

Production builds use:

```
VITE_API_URL=https://api.redmoorconsulting.co.uk
```

⸻

### API Endpoints

**Chat**

```
POST /rag-chat
```

**Ingest**

```
POST /ingest
```

Protected using:

DISABLE_INGEST

**Audit Logs**

```
GET /audit-logs
```

⸻

### Observability

The debug interface exposes:

- Retrieval rank
- Hybrid scores
- Vector distance
- Source citations
- Execution timings
- Cache hit/miss status
- Audit history

⸻

### Production Recommendations

```
DISABLE_INGEST=true
DISABLE_CACHE=false
DEBUG_DELAY=false
```

**Endpoint Limit**

```
/rag-chat	20/minute
/ingest	5/minute
/audit-logs	60/minute
```

⸻

### Future Improvements

- Streaming responses
- Automated evaluation
- Authentication
- Admin dashboard
- Advanced reranking
- Multi-tenant support

⸻

### License

MIT
