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

Edit `.env` and set your Postgres URL:

```
DATABASE_URL=postgresql://USER:PASSWORD@localhost:5432/freelancehub
SECRET_KEY=your-long-random-secret
```

### 3. Install dependencies

```bash
cd backend
.\.venv\Scripts\activate
pip install -r requirements.txt
```

### 4. Run the API

```bash
uvicorn app.main:app --reload --port 8000
```

Tables are created automatically on startup.

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
