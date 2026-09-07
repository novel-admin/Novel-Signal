# Supabase-only authentication for Novel Signal

Supabase Auth is the only identity provider. There is no public signup, no
signup page/API, no provisioning API, no invitations inside Novel Signal, no
self-service workspace creation, no Admin API usage, and no service-role key
in the application.

## Account creation policy (private deployment)

1. Platform owner creates the user manually in Supabase Dashboard
   (Authentication → Users → Invite/Create).
2. Owner separately assigns application workspace membership and role using
   the approved owner/admin flow:
   - `PUT /api/v1/auth/members/{user_id}` with `{"role": "owner|admin|analyst|viewer"}`
   - or the existing CLI/DB process.
3. User receives the Supabase invite/reset email, sets a password through the
   secure Supabase link (`/first-login` explains this), verifies email,
   enrolls TOTP, verifies TOTP, reaches AAL2, then logs in.

If a user does not exist in Supabase Auth, login fails with generic
"Invalid email or password." The app never reveals whether an email exists.

## Identity mapping (supabase_user_id only)

The production request path maps identity by exactly one key:

```text
Supabase auth.users.id (JWT sub) → application users.supabase_user_id
```

Email is a display/contact field, never an identity key. A request whose
`sub` has no linked application profile gets 403, even if the email matches
an existing profile. This stays correct across email changes, re-created
Supabase users, and data migrations.

One-time linking of pre-existing development profiles is explicit only:

- `python -m novel_signal.cli link-supabase-user --email <app-email> --supabase-id <auth.users.id>`
  (refuses unknown emails and already-linked-elsewhere profiles), or
- `AUTH_ALLOW_EMAIL_FALLBACK_LINKING=true` for a bounded development
  migration window: the first verified request links an unlinked profile with
  the same email, once, and never steals an existing link.

`AUTH_ALLOW_EMAIL_FALLBACK_LINKING` defaults to `false` and MUST remain
`false` in production (`render.yaml` pins it explicitly).

## Required flows (all via Supabase)

- Login: `/login` → `signInWithPassword` (PKCE, cookie SSR).
- Email verification: `/verify-email` + `/auth/callback` code exchange.
- First-login password setup: `/first-login` → `updateUser({password})` from the invite link.
- Forgot/reset: `/forgot-password` → `resetPasswordForEmail` → `/reset-password` → `updateUser`.
- Password change: `/settings/security` → `updateUser({password})` (authenticated).
- Logout: Supabase `signOut` + backend `/auth/logout` audit.
- Session restore/refresh/expiry: `@supabase/ssr` middleware (`updateSession`)
  refreshes cookies per request; expired sessions redirect to `/login`.
- Mandatory TOTP: `/mfa/setup` enroll → QR → challenge → verify → AAL2.
- Challenge: `/mfa/challenge` on future logins until AAL2.
- Security settings: `/settings/security` (factors, unenroll, password, recovery info).
- Lost authenticator: owner-controlled recovery. User contacts the owner, owner
  verifies identity out-of-band, removes the old factor (owner/admin), user
  re-enrolls at `/mfa/setup`. No self-service bypass exists.

Backend enforcement order per protected request:

```text
Supabase JWT → identity → email verification → AAL2 → active membership → role → resource ownership
```

- Missing/expired/malformed/wrong-project tokens → 401 (generic).
- Unverified email → 403 `EMAIL_UNVERIFIED`.
- AAL1 on protected data → 403 `MFA_REQUIRED`. AAL2 is never downgraded.
- No membership → 403. Wrong workspace ID → 403/404 without existence leak.
- Viewer: read-only. Analyst+: writes. Admin: workspace data/jobs/connections.
  Owner: membership/role admin. Users cannot change their own role.

## Configuration

### Supabase project

- `SUPABASE_URL` (backend) / `NEXT_PUBLIC_SUPABASE_URL` (frontend):
  e.g. `https://xyzcompany.supabase.co`.
- `SUPABASE_ANON_KEY` / `NEXT_PUBLIC_SUPABASE_ANON_KEY`: publishable key only.
  Never put a service-role key in frontend or backend env.
- `SUPABASE_JWT_SECRET`: legacy HS256 secret for JWT verification fallback.
- `SUPABASE_JWKS_URL`: defaults to `{SUPABASE_URL}/auth/v1/.well-known/jwks.json`.
- `SUPABASE_ISSUER`: defaults to `{SUPABASE_URL}/auth/v1`. Tokens with another
  `iss` are rejected (`AUTH_WRONG_PROJECT`).
- `SUPABASE_AUDIENCE`: `authenticated`.
- `FRONTEND_URL` / `CORS_ORIGINS`: e.g. `https://novel-signal-web.onrender.com`.

Backend verifies JWTs with JWKS (RS256/ES256) first, HS256 secret second.
No network calls are made in normal CI (HS256 test secret); JWKS is cached
(`SUPABASE_JWKS_CACHE_TTL_SECONDS`).

### Redirect URLs (Supabase Dashboard → Authentication → URL Configuration)

- `https://<web>/auth/callback`
- `http://localhost:3000/auth/callback` (local)
- Site URL: `https://<web>` (prod) / `http://localhost:3000` (local)

### Email verification / password reset / SMTP

- Auth → Email: enable "Confirm email", set secure redirect to `/auth/callback`.
- Password reset redirect to `/auth/callback` (then `/reset-password`).
- Production must use custom SMTP (Auth → SMTP Settings) so invite,
  verification, and reset emails deliver reliably. Dev may use Supabase default
  with rate limits.

### MFA settings (Supabase Dashboard → Authentication → MFA)

- Enable TOTP. Require MFA for this project (app additionally enforces AAL2).
- The app treats `aal` claim or `amr` containing `totp`/`otp` as AAL2.

### JWT verification settings

- `iss` must equal `SUPABASE_ISSUER`.
- `aud` must be `authenticated` (or configured audience).
- `exp` enforced; expired → 401 `SESSION_EXPIRED`.
- `sub` (auth.users.id) maps to `users.supabase_user_id`.

### Render environment variables

Backend (`novel-signal-api`):

- `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_JWT_SECRET`,
  `SUPABASE_JWKS_URL` (optional), `SUPABASE_ISSUER` (optional),
  `SUPABASE_AUDIENCE=authenticated`, `FRONTEND_URL`, `CORS_ORIGINS`.

Frontend (`novel-signal-web`):

- `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`,
  `NEXT_PUBLIC_API_URL=https://novel-signal-api.onrender.com/api/v1`.

No `SUPABASE_SERVICE_ROLE_KEY` anywhere. No `DASHBOARD_ACCESS_CODE` in prod.

### Local development

```powershell
# Backend
$env:SUPABASE_URL="https://xyzcompany.supabase.co"
$env:SUPABASE_ANON_KEY="<anon>"
$env:SUPABASE_JWT_SECRET="<jwt-secret>"
.\.venv\Scripts\python.exe -m alembic -c apps/backend/alembic.ini upgrade head

# Frontend
$env:NEXT_PUBLIC_SUPABASE_URL="https://xyzcompany.supabase.co"
$env:NEXT_PUBLIC_SUPABASE_ANON_KEY="<anon>"
corepack pnpm dev:web
```

Without Supabase env, backend middleware allows domain tests through (legacy
fixtures) and fails closed in production (503). Frontend throws a clear
"Supabase is not configured" error on auth pages.

## Tenant isolation (two layers, every table)

Every tenant-owned row carries a denormalized `workspace_id`
(`WorkspaceOwnedMixin`, 51 tables: universe, keywords, rank/visibility,
ads, listings, price, reviews, market share, scorecards, actions/gaps,
alerts, collection). Isolation has two independent layers:

1. Application/ORM layer (`apps/backend/src/novel_signal/tenant.py`): the
   middleware resolves the request workspace from verified membership and
   sets a request scope. SQLAlchemy events then automatically stamp
   `workspace_id` on inserts (`before_flush`) and filter every ORM
   SELECT/UPDATE/DELETE (`with_loader_criteria`), so even a future query
   that forgets an explicit workspace filter cannot leak rows. The scope
   also covers `session.get()` by primary key. Background collection work
   runs under the job's workspace scope (`run_collection_job`); planning
   derives each job's workspace from its subject (keyword/product); raw
   evidence derives it from its job; lifecycle children derive it from
   their job; `seed-demo` stamps the demo workspace.
2. Database layer (PostgreSQL RLS): migration `20260830_01` (on top of
   `20260829_01`) adds `workspace_id` + per-table index to all 51 tables,
   backfills existing rows to the earliest workspace (rows stay invisible
   until owned — fail closed), and enforces a strict
   `workspace_id = app.current_workspace_id()` policy (no NULL bypass) on
   every one of them. `after_begin` issues `SET LOCAL` per transaction.

Deliberately excluded, with reasons:

- `users`: identity keyed by `supabase_user_id`, reachable only through
  membership-checked endpoints; RLS on it would break owner/admin member
  listing.
- `workspaces` / `workspace_members`: already RLS-protected (member read,
  workspace isolation).
- `source_credentials`: child isolated through its parent connection's
  policy.
- `parser_versions`: global code metadata, identical for every tenant.
- `auth_audit_events`: append-only audit that must never block; keeps its
  NULL-allowing policy and never stores secrets.

Known follow-up (not isolation): unique constraints (competitor names,
fingerprints, idempotency keys) are still global. Per-workspace uniqueness
would matter only if the deployment ever hosts mutually untrusted tenants.

Verify:

```powershell
.\.venv\Scripts\python.exe -m pytest apps/backend/tests/test_tenant_isolation.py -q
.\.venv\Scripts\python.exe -m pytest apps/backend/tests/test_supabase_rls_pg.py -q
.\.venv\Scripts\python.exe -m alembic -c apps/backend/alembic.ini heads
```

## Security notes

- HTTPS-only in production (Render TLS). Cookies: `HttpOnly`, `Secure` in
  prod, `SameSite=Lax` (Supabase SSR defaults; `None` only where cross-site
  requires Secure).
- CORS restricted to `CORS_ORIGINS` (prod: web origin only), credentials on,
  methods limited, `Authorization` + `X-Workspace-Id` headers.
- Login rate limiting: Supabase built-in (auth rate limits, MFA attempt
  limits). Backend adds generic errors to avoid oracles.
- Audit events (no secrets): login, logout, password changes/resets, MFA
  enrollment/verification/removal, auth failures, authorization failures,
  membership/role changes. Secrets redacted (`[redacted]`) in logs.
- No passwords or TOTP secrets in application tables. No tokens in responses.
- Authenticated responses send `Cache-Control: no-store`.

## Manual verification (before real client data)

1. Create user in Supabase Dashboard → user gets invite/reset email.
2. User sets password (`/first-login`), verifies email (`/verify-email`).
3. User enrolls TOTP (`/mfa/setup`), verifies code, reaches AAL2.
4. User logs in (`/login`), completes MFA challenge (`/mfa/challenge`), opens workspace.
5. Password reset: `/forgot-password` → email link → `/reset-password` → login again + MFA.
6. Check role permissions (viewer read-only, analyst writes, admin manages, owner administers).
7. Deactivate the user / remove membership → verify 403 on next request.
8. Cross-workspace: two real users in two workspaces; verify neither can
   list, read, or write the other's competitors, products, keywords, jobs,
   evidence, scorecards, gaps, actions, or alerts (expect 403/404, no
   existence leaks either way).
9. Confirm `AUTH_ALLOW_EMAIL_FALLBACK_LINKING` is `false`/unset in Render.
10. Confirm Render env vars (`SUPABASE_URL`, anon key, JWT secret/JWKS,
    issuer, audience, `FRONTEND_URL`, `CORS_ORIGINS`); no service-role key.
11. Install Chromium and rerun the remaining browser test.
12. Confirm the auth audit log never stores tokens or secrets
    (`auth_audit_events` rows + log output contain only `[redacted]`).
13. Check `/api/v1/auth/me` returns workspaces/roles, no secrets.

## Remaining limitations (plain)

- Unique constraints (competitor names, fingerprints, idempotency keys) are
  global, not per-workspace. Fine for this private single-tenant deployment;
  revisit only for mutually untrusted tenants.
- Legacy `users.password_hash` column retained nullable for fixtures; no new
  passwords are created and it is not used in production auth.
- `INTERNAL_AUTH_SECRET`/`DASHBOARD_*` settings retained deprecated; production
  middleware ignores them.
- Live Supabase integration test is opt-in (needs real credentials).
- Playwright browser test needs real Chromium; excluded from CI here.
