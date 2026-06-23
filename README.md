# Submission & Approval Workflow — Backend

FastAPI + PostgreSQL backend for the generic request submission and approval process
(Assignment B — Full-Stack Developer Technical Assessment).

**Live API:** `https://open-ownership-backend.vercel.app`  
**API Docs:** `https://open-ownership-backend.vercel.app/docs`

## Quick Start

### Prerequisites
- Python 3.11+
- PostgreSQL 16 (local or [Neon](https://neon.tech) serverless)

### Option 1: Docker (recommended)

```bash
docker-compose up --build
```

This starts:
- PostgreSQL 16 on port 5432
- FastAPI backend on port 8000
- Automatically creates tables and seeds demo users on first start

### Option 2: Local development

```bash
# Install dependencies
pip install -r requirements.txt

# Configure .env (update DATABASE_URL if not using local PostgreSQL)
# DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/open_ownership

# Seed demo users + create tables
python seed.py

# Run server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Option 3: Neon Serverless (used in production)

```bash
# Set your Neon connection string in .env:
# DATABASE_URL=postgresql+asyncpg://user:pass@ep-xxx.us-east-1.aws.neon.tech/neondb?ssl=require

pip install -r requirements.txt
python seed.py
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## API Endpoints

### Auth
| Method | Endpoint               | Description              |
|--------|------------------------|--------------------------|
| POST   | `/auth/login`          | Login, returns JWT       |
| POST   | `/auth/register`       | Register new user        |
| GET    | `/auth/me`             | Current user profile     |

### Applications
| Method | Endpoint                            | Description                              |
|--------|-------------------------------------|------------------------------------------|
| POST   | `/applications/`                    | Create a new DRAFT application           |
| PUT    | `/applications/{id}`                | Edit a DRAFT (owner only)                |
| DELETE | `/applications/{id}`                | Delete (applicant: DRAFT only)           |
| GET    | `/applications/mine`                | List my applications (applicant)         |
| GET    | `/applications/queue`               | Review queue with search/filter/pagination |
| GET    | `/applications/{id}`                | Detail with full audit trail             |
| POST   | `/applications/{id}/transition`     | submit / review / approve / reject / return |

### Notifications
| Method | Endpoint                | Description                              |
|--------|-------------------------|------------------------------------------|
| GET    | `/notifications/`       | Recent activity (supports `?since=` )    |
| PUT    | `/notifications/read`   | Mark all as read (stores timestamp in DB)|

## Data Model

### Users (`users` table)
| Column           | Type           | Notes                        |
|------------------|----------------|------------------------------|
| id               | SERIAL PK      | Auto-increment               |
| email            | VARCHAR(255)   | UNIQUE, NOT NULL             |
| password_hash    | VARCHAR(255)   | bcrypt hashed                |
| role             | VARCHAR(50)    | 'applicant' or 'reviewer'    |
| name             | VARCHAR(255)   | Display name                 |
| created_at       | TIMESTAMPTZ    | DEFAULT NOW()                |
| last_notif_read  | TIMESTAMPTZ    | NULLABLE — notification state|

### Applications (`applications` table)
| Column           | Type           | Notes                                    |
|------------------|----------------|------------------------------------------|
| id               | SERIAL PK      | Auto-increment                           |
| title            | VARCHAR(255)   | NOT NULL                                 |
| category         | VARCHAR(255)   | NOT NULL                                 |
| description      | TEXT           | DEFAULT ''                               |
| amount           | FLOAT          | DEFAULT 0.0                              |
| applicant_id     | VARCHAR(255)   | Email of owner                           |
| status           | VARCHAR(50)    | One of 6 workflow states                 |
| reviewer_comment | TEXT           | DEFAULT ''                               |
| created_at       | TIMESTAMPTZ    | DEFAULT NOW()                            |
| updated_at       | TIMESTAMPTZ    | DEFAULT NOW(), ON UPDATE                 |
| attachment_url   | TEXT           | NULLABLE                                 |

### Audit Logs (`audit_logs` table)
| Column           | Type           | Notes                                    |
|------------------|----------------|------------------------------------------|
| id               | SERIAL PK      | Auto-increment                           |
| application_id   | INTEGER FK     | REFERENCES applications(id)              |
| performed_by     | VARCHAR(255)   | Email                                    |
| performer_role   | VARCHAR(50)    | 'applicant' or 'reviewer'                |
| old_status       | VARCHAR(50)    | Previous state                           |
| new_status       | VARCHAR(50)    | New state                                |
| comment          | TEXT           | DEFAULT ''                               |
| timestamp        | TIMESTAMPTZ    | DEFAULT NOW()                            |

### Key Design Decisions
- **PostgreSQL over MongoDB** — chosen mid-project for better relational integrity (foreign keys between audit_logs and applications), ACID transactions, and Neon's serverless scaling. The state machine logic is DB-agnostic.
- **SQLAlchemy async + asyncpg** — native async PostgreSQL driver, avoids ORM overhead for simple queries while keeping model definitions clean.
- **`last_notif_read` on User** — stores notification read state server-side so it persists across devices/sessions, rather than relying on localStorage.
- **Audit log as separate table** — every status transition is an append-only row. Deletes cascade: deleting an application first removes its audit logs.

## State Machine

```
DRAFT --submit--> SUBMITTED --review--> UNDER_REVIEW --approve--> APPROVED
                     |        |                              --reject--> REJECTED
                     |        +--return--> RETURNED_FOR_CHANGES --edit--> DRAFT
```

### Transition Rules
- **DRAFT -> SUBMITTED**: Applicant only, own application
- **SUBMITTED -> UNDER_REVIEW**: Reviewer only
- **SUBMITTED -> RETURNED_FOR_CHANGES**: Reviewer only, **comment required**
- **UNDER_REVIEW -> APPROVED**: Reviewer only
- **UNDER_REVIEW -> REJECTED**: Reviewer only, **comment required**
- **RETURNED_FOR_CHANGES -> DRAFT**: Applicant resubmits after editing

### Authorization Enforced (server-side)
- Applicant cannot approve/review/reject -> **403**
- Reviewer cannot submit -> **403**
- Applicant cannot edit after submission -> **403**
- Applicant cannot view another's application -> **403**
- Applicant can only delete DRAFT applications -> **403**
- Reject/return without comment -> **400**
- Illegal state transition -> **409**

## Testing

```bash
# Unit tests (state machine — no DB needed)
pytest tests/test_state_machine.py -v

# API integration tests (requires running PostgreSQL)
pytest tests/test_api.py -v

# All tests
pytest -v
```

### Test Coverage
- **State machine unit tests** (34 tests): Every legal and illegal transition, comment requirements, full workflow sequences (happy path, return round-trip, rejection path), exhaustive LEGAL_TRANSITIONS validation.
- **API integration tests** (20+ tests): Auth, CRUD, transitions, authorization (403 on forbidden actions), reviewer queue filters/search.

## Trade-offs & Known Limitations

### What I'd add with more time
1. **Refresh tokens** — currently only access tokens with 8h expiry.
2. **File attachments** — the model supports `attachment_url` but no upload endpoint.
3. **Email notifications** — on status change (listed stretch goal).
4. **Rate limiting** — no brute-force protection on login.
5. **Cursor-based pagination** — offset/limit works but doesn't scale as well.
6. **Alembic migrations** — currently uses `ALTER TABLE IF NOT EXISTS` on startup; proper migrations would be safer.

### Architectural Decisions
- **SQLAlchemy async** — native async support for FastAPI without callback overhead.
- **JWT with HS256** — simple shared-secret; production would use RS256 with rotating keys.
- **Single-database** — all data in one PostgreSQL database; sufficient for this workflow scope.
- **Centralised state machine** — `services/state_machine.py` is the single source of truth for transition validation, used by both API and tests.

## Deployment

### Docker

```bash
# Build and run with Docker Compose (PostgreSQL + backend)
docker-compose up --build

# Or build standalone image
docker build -t open-ownership-backend .
docker run -p 8000:8000 \
  -e DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/db \
  -e JWT_SECRET=your-secret \
  open-ownership-backend
```

The Dockerfile:
- Uses `python:3.11-slim`
- Installs system deps, Python packages
- Runs `start.sh` which seeds users then starts uvicorn
- Exposes port 8000

### Vercel + Neon (Production)

Hosted on **Vercel** with Neon PostgreSQL:
- Backend: `https://open-ownership-backend.vercel.app`
- Database: Neon serverless PostgreSQL (connection string in environment variables)
- Auto-deploys on push to `main`

### GitHub Actions CI/CD

On every push/PR to `main`:

| Job       | What it does                                              |
|-----------|-----------------------------------------------------------|
| **test**  | Spins up PostgreSQL 16, runs `pytest` (unit + API tests)  |
| **deploy**| Deploys to Vercel (production, on push to main only)      |

Workflow: `.github/workflows/backend.yml`  
Required secrets: `VERCEL_TOKEN`, `VERCEL_ORG_ID`, `VERCEL_PROJECT_ID`

## AI Usage

This project was built with assistance from multiple AI tools:

| Tool               | Used For                                                    |
|--------------------|-------------------------------------------------------------|
| **GitHub Copilot** | Code generation, autocomplete, refactoring across all files |
| **DeepSeek V4 Pro**| Architecture planning, state machine design, SQL migrations |
| **Claude Opus 4.6**| UI/UX design system, responsive layout, component structure |
| **Gemini Nano**    | Image generation (logo, office hero image)                  |
| **Vercel + Neon**  | DevOps — hosting backend API and PostgreSQL database        |

All AI-generated code was reviewed, tested, and refined. Every line can be explained and justified.

## Demo Users

| Email                | Password      | Role      |
|----------------------|---------------|-----------|
| demo@applicant.com   | password123   | Applicant |
| demo@reviewer.com    | password123   | Reviewer  |

Created automatically by `seed.py` on startup.