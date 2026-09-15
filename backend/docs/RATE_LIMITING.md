# Rate limiting strategy

FreelanceHub applies **in-process** rate limits (per client IP) on:

| Route group | Default | Setting |
|-------------|---------|---------|
| `/api/auth/login`, `/api/auth/register` | 20/min | `RATE_LIMIT_AUTH_PER_MINUTE` |
| `/api/ai/project-brief` | 10/min | `RATE_LIMIT_AI_PER_MINUTE` |
| `/api/attachments` uploads | 30/min | `RATE_LIMIT_UPLOAD_PER_MINUTE` |

Disable with `RATE_LIMIT_ENABLED=false` only for local debugging.

## Production recommendation

In-process counters **do not coordinate across multiple Uvicorn workers or hosts**.

For production:

1. Enforce limits at the **edge** (Cloudflare, nginx `limit_req`, API gateway).
2. Or use a **Redis-backed** limiter shared by all workers.
3. Keep application limits as a defense-in-depth layer.

Suggested edge baselines:

- Auth: 5–20 requests / minute / IP
- AI brief: 5–10 / minute / user (after auth)
- Uploads: 20–60 / minute / user
- Global API: soft ceiling to blunt scraping
