# S7 Reviews and Voice of Customer

The S7 API accepts approved review observations and stores only privacy-safe
review text. Source identity and a caller-provided fingerprint make retries
idempotent. Topic extraction is deterministic (`rules-v1`) and exposes sample
size and confidence so small samples are not presented as reliable findings.

Endpoints:

- `POST /reviews` ingests one review.
- `GET /reviews` lists observations with cursor pagination.
- `GET /reviews/topics` returns complaint/praise topic summaries.
- `GET /reviews/trends` materializes weekly topic trends.

Reviewer names, profile URLs, contact details, and order identifiers are not
accepted as fields. Email addresses and phone-like strings in text are masked
before persistence.
