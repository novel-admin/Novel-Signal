# Merge-request comments

## MR 1: CORS and demo authentication

**Request:** Merge the deployment foundation after confirming that `CORS_ORIGINS` accepts the Vercel URL, the backend API uses `/api/v1`, and the access-code cookie blocks unauthenticated requests.

**Reviewer checks:**

- No credentials are present in `.env.example`.
- `DASHBOARD_ACCESS_CODE` is set only in the cloud environment.
- `INTERNAL_AUTH_SECRET` is long and random.
- Login, session, logout, CORS, and protected-route tests pass.

## MR 2: Amazon public collection

**Request:** Merge the Amazon.in collector and raw evidence path after a real logged-out capture succeeds for one Novel ASIN and one seed keyword.

**Reviewer checks:**

- Raw evidence is stored before parsing.
- The request is allowlisted and rate-limited.
- A challenge stops the attempt and is visible as a failure.
- Parser output has source, timestamps, parser version, confidence, and evidence references.

## MR 3: Competitor discovery

**Request:** Merge candidate discovery after repeated ASIN appearances create an evidence-backed candidate without automatically activating an uncertain match.

**Reviewer checks:**

- ASIN deduplication is idempotent.
- Candidate confidence and source captures are visible.
- Approve/reject actions are auditable.
- Approved candidates create battle-card records correctly.

## MR 4: Amazon intelligence dashboard

**Request:** Merge the dashboard after one configured Novel SKU can be compared with one approved competitor using real captures.

**Reviewer checks:**

- Rank, price, listing, review, availability, and sponsored values show evidence and freshness.
- Missing data is unknown, not zero.
- Listing and price changes are visible.
- Credential-dependent own-performance fields remain clearly unavailable until credentials are configured.
