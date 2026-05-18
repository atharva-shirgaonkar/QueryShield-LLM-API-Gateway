# QueryShield 🛡️

> A smart API gateway that sits between your app and any LLM API.
> Control costs, enforce budgets, cache responses, and protect your
> system — all in one place.

![Python](https://img.shields.io/badge/Python-3.11-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-async-green)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-blue)
![Redis](https://img.shields.io/badge/Redis-7-red)
![Docker](https://img.shields.io/badge/Docker-compose-blue)
![Tests](https://img.shields.io/badge/Tests-44%20passing-brightgreen)

---

## What Problem Does It Solve?

Every app that calls an LLM API faces the same problems:

- **Runaway costs** — users hammer the API and the bill explodes
- **No visibility** — you don't know who's spending what
- **Repeated calls** — the same prompt gets sent 100 times
- **No protection** — if OpenAI goes down, your app crashes

QueryShield fixes all of this by sitting in front of your LLM API
and acting as a smart gatekeeper.

---

## How A Request Flows

```text
Client Request
↓
Auth Check (JWT or API Key)
↓
Tier Limit Check (free / pro token budget)
↓
Cache Check (Redis — return instantly if seen before)
↓
Circuit Breaker (is OpenAI healthy?)
↓
OpenAI API Call
↓
Save to Cache + Track Usage in DB
↓
Return Response
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| API Framework | FastAPI (async) |
| Database | PostgreSQL + SQLAlchemy (async) |
| Migrations | Alembic |
| Cache | Redis |
| Auth | JWT + API Keys |
| LLM | OpenAI (gpt-3.5-turbo) |
| Token Counting | tiktoken |
| Containerisation | Docker + docker-compose |

---

## Features

- **JWT Authentication** — register and login with secure bcrypt passwords
- **API Key System** — generate, list, and revoke `qs_...` prefixed keys
- **Dual Auth** — every endpoint accepts both JWT and API key transparently
- **Token Tracking** — every request logs prompt, completion, and total tokens per user
- **Tier Enforcement** — free and pro users have separate token budgets
- **Redis Caching** — SHA256 prompt hashing with 1 hour TTL
- **Circuit Breaker** — CLOSED / OPEN / HALF_OPEN state machine protects against OpenAI failures
- **44 Tests** — full coverage across auth, query, API key, usage, admin, middleware, and semantic cache flows

---

## Getting Started

### Prerequisites

- Docker Desktop running
- OpenAI API key

### Run Locally

```bash
# Clone the repo
git clone https://github.com/yourusername/queryshield.git
cd queryshield

# Copy environment file
cp .env.example .env
# Add your OpenAI API key and secrets to .env

# Start Postgres and Redis
docker-compose up -d

# Install dependencies
pip install -r requirements.txt

# Run migrations
alembic upgrade head

# Start the server
uvicorn app.main:app --reload
```

### Run Tests

```bash
pytest tests/ -v
```

---

## API Endpoints

### Auth

| Method | Endpoint | Description |
|---|---|---|
| POST | `/auth/register` | Create a new account |
| POST | `/auth/login` | Get a JWT token |
| GET | `/auth/me` | Get current user info |

### Query

| Method | Endpoint | Description |
|---|---|---|
| POST | `/query` | Send a prompt to OpenAI via QueryShield |

### API Keys

| Method | Endpoint | Description |
|---|---|---|
| POST | `/keys` | Generate a new API key |
| GET | `/keys` | List your API keys |
| DELETE | `/keys/{key_id}` | Revoke an API key |

### System

| Method | Endpoint | Description |
|---|---|---|
| GET | `/health` | App status and token limits |

---

## Environment Variables

```env
DATABASE_URL=postgresql+asyncpg://user:password@localhost/queryshield
REDIS_URL=redis://localhost:6379
OPENAI_API_KEY=sk-...
SECRET_KEY=your-secret-key
FREE_TOKEN_LIMIT=10000
PRO_TOKEN_LIMIT=100000
```

---

## Observability

Every request through QueryShield is fully traced:

- Unique `X-Request-ID` header on every response
- Structured JSON logs with timestamp, level, request_id, method, path, status_code, duration_ms
- Cache hit/miss logged on every query
- Token counts logged after every OpenAI call
- Circuit breaker state changes logged automatically
- Startup and shutdown events logged

Example log entry:

```json
{
  "timestamp": "2026-05-15T10:00:00Z",
  "level": "INFO",
  "request_id": "uuid-here",
  "method": "POST",
  "path": "/query",
  "status_code": 200,
  "duration_ms": 143
}
```

---

## Project Structure

```text
queryshield/
├── app/
│   ├── main.py              # FastAPI app entry point
│   ├── dependencies.py      # get_current_user dependency
│   ├── core/
│   │   ├── config.py        # Settings from .env
│   │   ├── database.py      # Async SQLAlchemy setup
│   │   ├── security.py      # JWT + bcrypt + key generation
│   │   ├── token_counter.py # tiktoken wrapper
│   │   ├── usage_service.py # Token usage queries
│   │   ├── cache.py         # Redis cache logic
│   │   ├── redis_client.py  # Async Redis client
│   │   └── circuit_breaker.py # Circuit breaker state machine
│   ├── models/
│   │   ├── user.py          # User table
│   │   ├── usage.py         # Usage tracking table
│   │   └── api_key.py       # API key table
│   ├── schemas/
│   │   ├── auth.py          # Auth request/response models
│   │   ├── query.py         # Query request/response models
│   │   └── api_key.py       # API key schemas
│   └── api/routes/
│       ├── auth.py          # /auth endpoints
│       ├── query.py         # /query endpoint
│       └── keys.py          # /keys endpoints
├── alembic/                 # Database migrations
├── tests/                   # 44 passing tests
├── docker-compose.yml       # Postgres + Redis
├── requirements.txt
└── .env.example
```

---

## Deployment

QueryShield is configured for one-click deployment on Render.

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy)

### Steps

1. Fork this repo
2. Go to render.com and sign up with GitHub
3. Click **New Web Service** and connect your repo
4. Render auto-detects `render.yaml` and configures everything
5. Add your `OPENAI_API_KEY` and `SECRET_KEY` in the Environment tab
6. Click Deploy

> Note: Free tier spins down after 15 minutes of inactivity.
> First request after inactivity takes ~30 seconds to wake up.

---

## Author

**Atharva Shirgaonkar**
Python Developer | Building AI Systems
Pune, Maharashtra

[GitHub](https://github.com/yourusername) ·
[LinkedIn](https://linkedin.com/in/yourusername)
