# Submission & Approval Workflow — Backend

FastAPI + MongoDB backend for the generic request submission and approval process
(Assignment B — Full-Stack Developer Technical Assessment).

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Python 3.11+ (for local dev without Docker)

### Option 1: Docker (recommended)

```bash
docker-compose up --build
```

This starts:
- MongoDB 7.0 on port 27017
- FastAPI backend on port 8000
- Automatically seeds demo users on first start

### Option 2: Local development

```bash
# Start MongoDB (or use an existing instance)
docker run -d -p 27017:27017 -e MONGO_INITDB_ROOT_USERNAME=root -e MONGO_INITDB_ROOT_PASSWORD=example mongo:7.0

# Copy .env and configure
cp .env.example .env   # (already provided)

# Install dependencies
pip install -r requirements.txt

# Seed demo users
python seed.py

# Run server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## API Endpoints

### Auth
| Method | Endpoint      | Description              |
|--------|---------------|--------------------------|
| POST   | `/auth/login` | Login, returns JWT       |
| GET    | `/auth/me`    | Current user profile     |

### Applications (Applicant)
| Method | Endpoint                            | Description                    |
|--------|-------------------------------------|--------------------------------|
| POST   | `/applications/`                    | Create a new DRAFT application |
| PUT    | `/applications/{id}`                | Edit a DRAFT (owner only)      |
| GET    | `/applications/mine`                | List my applications           |
| POST   | `/applications/{id}/transition`     | Submit (action: "submit")      |

### Applications (Reviewer)
| Method | Endpoint                            | Description                         |
|--------|-------------------------------------|-------------------------------------|
| GET    | `/applications/queue`               | Review queue (filterable, searchable)|
| POST   | `/applications/{id}/transition`     | review / approve / reject / return  |

### Shared
| Method | Endpoint                        | Description                        |
|--------|---------------------------------|------------------------------------|
| GET    | `/applications/{id}`            | Detail with full audit trail       |

## Data Model

### Users (`users` collection)
```
{
  _id: ObjectId,
  email: string (unique),
  password_hash: string (bcrypt),
  role: "applicant" | "reviewer",
  name: string,
  created_at: datetime
}
```

### Applications (`applications` collection)
```
{
  _id: ObjectId,
  title: string (required),
  category: string (required),
  description: string,
  amount: float,
  applicant_id: string (email of owner),
  status: "DRAFT" | "SUBMITTED" | "UNDER_REVIEW" | "APPROVED" | "REJECTED" | "RETURNED_FOR_CHANGES",
  reviewer_comment: string,
  created_at: datetime,
  updated_at: datetime,
  attachment_url: string? (optional)
}
```

### Audit Logs (`audit_logs` collection)
```
{
  _id: ObjectId,
  application_id: string (ref),
  performed_by: string (email),
  performer_role: "applicant" | "reviewer",
  old_status: string,
  new_status: string,
  comment: string,
  timestamp: datetime
}
```

### Indexes
- `users.email` — unique
- `applications.applicant_id`
- `applications.status`
- `audit_logs.application_id`

## State Machine

```
DRAFT --submit--> SUBMITTED --review--> UNDER_REVIEW --approve--> APPROVED
                     |        |                              --reject--> REJECTED
                     |        +--return--> RETURNED_FOR_CHANGES --edit--> DRAFT
                     |
                     (no direct path to APPROVED/REJECTED from SUBMITTED)
```

### Transition Rules
- **DRAFT -> SUBMITTED**: Applicant only, own application
- **SUBMITTED -> UNDER_REVIEW**: Reviewer only
- **SUBMITTED -> RETURNED_FOR_CHANGES**: Reviewer only, **comment required**
- **UNDER_REVIEW -> APPROVED**: Reviewer only
- **UNDER_REVIEW -> REJECTED**: Reviewer only, **comment required**
- **RETURNED_FOR_CHANGES -> DRAFT**: Applicant edits and may resubmit

### Authorization Enforced
- Applicant cannot approve/review their own application -> **403**
- Reviewer cannot submit an application -> **403**
- Applicant cannot edit after submission -> **403**
- Applicant cannot view another applicant's application -> **403**
- Reject/return without comment -> **400**
- Illegal state transition -> **409**

## Testing

```bash
# Unit tests (state machine — no DB needed)
pytest tests/test_state_machine.py -v

# API integration tests (requires running MongoDB)
pytest tests/test_api.py -v

# All tests
pytest -v
```

### Test Coverage
- **State machine unit tests** (34 tests): Every legal and illegal transition, comment requirements, full workflow sequences (happy path, return round-trip, rejection path), exhaustive LEGAL_TRANSITIONS validation.
- **API integration tests** (20+ tests): Auth (login, bad password, unauthenticated), CRUD (create, update, list, cannot edit after submit), transitions (full happy path, reject with/without comment), authorization (applicant cannot approve, reviewer cannot submit, reviewer cannot edit applicant draft, applicant cannot view others), reviewer queue (filters, search).

## Trade-offs & Known Limitations

### What I'd add with more time
1. **Refresh tokens** — currently only access tokens with 8h expiry.
2. **File attachments** — the model supports `attachment_url` but the upload endpoint is not implemented (stretch goal).
3. **Email notifications** — on status change, this was a listed stretch goal.
4. **Rate limiting** — no protection against brute-force login.
5. **Pagination on list endpoints** — offset/limit supported but cursor-based would scale better.
6. **Proper .env.example** — the .env is committed with dev defaults for convenience.

### Architectural decisions
- **Motor (async MongoDB)** — chosen over SQLAlchemy/Postgres because the existing codebase uses MongoDB and Motor provides native async support for FastAPI. The state machine logic is DB-agnostic.
- **JWT with HS256** — simple shared-secret JWT; in production, use RS256 with rotating keys.
- **Single-database (multi-collection)** — all data in one DB rather than multi-tenant pattern, since this is a single-purpose workflow app.
- **Centralised state machine** — all transition logic lives in `services/state_machine.py`, which is the single source of truth for both the API and tests.

## AI Usage
- All code was generated with GitHub Copilot assistance.
- The state machine design, authorization rules, and test cases were reviewed and refined by the author.
- Every line can be explained and justified.

## Demo Users

| Email                | Password      | Role      |
|----------------------|---------------|-----------|
| demo@applicant.com   | password123   | Applicant |
| demo@reviewer.com    | password123   | Reviewer  |

Created automatically by `seed.py` on startup.