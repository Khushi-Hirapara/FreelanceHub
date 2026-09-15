# FreelanceHub Backend

FastAPI + PostgreSQL API for the FreelanceHub marketplace.

## Endpoints (prefix `/api`)

| Domain | Methods |
|--------|---------|
| **Auth** | `POST /auth/register`, `POST /auth/login`, `GET /auth/me` |
| **Users** | `GET/PUT /users/me`, `PUT /users/me/password`, `GET /users/{id}` |
| **Projects** | `GET/POST /projects`, `GET /projects/mine`, `GET/PUT/DELETE /projects/{id}` |
| **Proposals** | `POST /proposals`, `GET /proposals/mine`, `GET /projects/{id}/proposals`, `GET/PATCH /proposals/{id}` |
| **Messages** | `GET /conversations`, `GET /conversations/{id}/messages`, `GET /messages?conversation_id=`, `POST /messages` |

Interactive docs: http://localhost:8000/docs

## Setup

> **Important:** Do **not** use Python 3.14. Packages like `psycopg2-binary` and `pydantic` do not have Windows wheels for 3.14 yet, so `pip install` will fail. Use **Python 3.11**.

Create / activate the venv with:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 1. Create PostgreSQL database

```sql
CREATE DATABASE freelancehub;
```

### 2. Configure environment

```bash
cd backend
copy .env.example .env
```

Edit `.env` and set:

```
DATABASE_URL=postgresql://USER:PASSWORD@localhost:5432/freelancehub
SECRET_KEY=<random string of at least 32 characters>
APP_ENV=development
CORS_ORIGINS=http://localhost:5500,http://127.0.0.1:5500
PAYMENTS_MODE=mock
```

**Production checklist**

- Set `APP_ENV=production` (disables OpenAPI docs, rejects weak `SECRET_KEY`).
- Generate a unique `SECRET_KEY` (≥32 chars). Never reuse example placeholders.
- Set `CORS_ORIGINS` to your real frontend origins only (no `*`, no `null`).
- Set `PAYMENTS_MODE=disabled` until a real PSP + signed webhooks exist. Stripe was removed; mock confirm endpoints are demo-only.
- Apply schema with Alembic only: `alembic upgrade head` (startup no longer runs `create_all`).
- Put rate limiting at the reverse proxy/CDN for multi-instance deploys. The API also applies in-process limits on `/auth/*`, `/ai/*`, and uploads.

### 3. Install dependencies

```bash
cd backend
.\.venv\Scripts\activate
pip install -r requirements.txt
```

### 4. Migrate and run the API

```bash
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

Do **not** rely on automatic table creation at startup.

## Auth usage

1. Register or login → receive `access_token`
2. Send header: `Authorization: Bearer <access_token>`
3. Frontend stores token in `localStorage` as `token`

## Example

```bash
# Register
curl -X POST http://localhost:8000/api/auth/register ^
  -H "Content-Type: application/json" ^
  -d "{\"name\":\"Priya Nair\",\"email\":\"priya@example.com\",\"password\":\"password123\",\"role\":\"freelancer\"}"

# Login
curl -X POST http://localhost:8000/api/auth/login ^
  -H "Content-Type: application/json" ^
  -d "{\"email\":\"priya@example.com\",\"password\":\"password123\",\"role\":\"freelancer\"}"
```
