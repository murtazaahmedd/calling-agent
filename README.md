# Voice AI Patient Registration System

A voice agent that answers a real phone number, conversationally registers a new patient
(or recognizes a returning caller and offers to update their record), and persists the data
through a REST API backed by SQLite.

## Live Demo

- **Phone number:** _fill in after Vapi provisioning — see Setup Part 2_
- **API base URL:** `https://<your-ngrok-subdomain>.ngrok-free.dev` (or your deployed host)
- **API docs (Swagger):** `<API base URL>/docs`

## Architecture

```
Phone Call (Caller)
      |
      v
Vapi (Telephony + STT + TTS + LLM orchestration)
      |  tool calls (function calling) over HTTPS webhook
      v
FastAPI backend  --------------------  SQLite (patients.db)
      |
      v
REST API (/patients, /patients/:id)  <-- used by both Vapi tools and external clients
```

- **Telephony + Voice + LLM orchestration: Vapi.** Vapi owns the phone number, speech-to-text,
  text-to-speech, turn-taking/interruption handling, and calls an LLM (GPT-4o) with a system
  prompt and a set of custom "tools" (functions). This gets a natural, low-latency conversational
  agent without hand-building a media-streaming/STT/TTS pipeline — the highest-leverage shortcut
  given the 3-hour budget, exactly as suggested in the assessment.
- **Backend: FastAPI (Python).** Owns all business logic and validation. Two responsibilities:
  1. A standard REST API (`app/routers/patients.py`) for CRUD on patient records.
  2. A webhook endpoint (`app/routers/vapi_tools.py`) that Vapi calls mid-conversation to look up,
     create, or update a patient. This endpoint reuses the exact same service/validation layer
     (`app/crud.py`, `app/schemas.py`) as the REST API — the voice agent and any other API client
     go through identical server-side validation, so the agent can never bypass a rule.
- **Database: SQLite.** File-based, zero setup, and fully sufficient for this data model and load.
  Chosen over Postgres purely for setup speed within the time box (explicitly sanctioned by the
  assessment as an acceptable trade-off). Swapping to Postgres later is a one-line `DATABASE_URL`
  change since access goes entirely through SQLAlchemy.
- **Hosting: local + ngrok.** Fastest path to a publicly reachable HTTPS webhook for Vapi to call
  during the review window. See "Known Limitations" for the trade-off this implies.

### Why a shared service layer instead of the voice agent calling itself over HTTP twice

The Vapi tool webhook (`/vapi/tools`) and the public REST API (`/patients`) both call into
`app/crud.py` directly against the same DB session — the tool handler doesn't loop back through
`/patients` over HTTP. This keeps one source of truth for validation and business rules while
avoiding pointless self-referential network calls in the same process.

## Data Model

See `app/models.py` (SQLAlchemy) and `app/schemas.py` (Pydantic validation). Implements every
field from the spec: required fields (`first_name`, `last_name`, `date_of_birth`, `sex`,
`phone_number`, `address_line_1`, `city`, `state`, `zip_code`), optional fields (`email`,
`address_line_2`, `insurance_provider`, `insurance_member_id`, `preferred_language`,
`emergency_contact_name`, `emergency_contact_phone`), and auto-generated fields (`patient_id` UUID,
`created_at`/`updated_at` UTC timestamps, `deleted_at` for soft delete).

Validation enforced **server-side** in `app/schemas.py` (not just trusted from the voice agent):
- Names: 1–50 chars, letters/hyphens/apostrophes only.
- Date of birth: valid calendar date, not in the future.
- Phone numbers: normalized to 10 digits (strips formatting, drops a leading US country code `1`).
- State: must be a real 2-letter US state abbreviation (full lookup table).
- Zip: 5-digit or ZIP+4.
- Sex: enum of the four spec values.

## REST API

All responses use the envelope `{ "data": ..., "error": ... }`.

| Method | Endpoint | Description |
|---|---|---|
| GET | `/patients` | List patients. Optional query params: `last_name`, `date_of_birth`, `phone_number`. Excludes soft-deleted records. |
| GET | `/patients/:id` | Get one patient by `patient_id`. 404 if missing/deleted. |
| POST | `/patients` | Create a patient. 201 + record on success, 422 on validation error. |
| PUT | `/patients/:id` | Partial update (only fields provided are changed). |
| DELETE | `/patients/:id` | Soft delete (`deleted_at` set; row stays in the DB). |

Plus `GET /health` and `POST /vapi/tools` (the Vapi tool-call webhook, secured by a shared
secret header `x-vapi-secret`).

## Voice Agent Design

The full system prompt and tool/function schemas live in [`vapi/assistant.json`](vapi/assistant.json)
(importable into the Vapi dashboard) — comments on *why* each instruction exists are inline in the
prompt itself. Key design choices:

- **Ask 1–2 fields at a time**, never read the field list as a form — this was the single biggest
  lever for making the call feel human rather than like an IVR.
- **Duplicate detection**: as soon as a phone number is captured, the agent silently calls
  `lookup_patient_by_phone`. If found, it offers to update instead of create (bonus requirement).
- **Confirmation gate**: the agent must read back the full collected record and get explicit
  confirmation before any `create_patient`/`update_patient` tool call fires — no silent saves.
- **Field-specific re-prompting**: invalid data returns `{"success": false, "error": "..."}` from
  the tool, and the prompt instructs the model to translate that into a natural re-ask of only the
  broken field, not a restart.
- **Corrections & restarts**: explicit prompt instructions for both "actually, it's spelled X"
  mid-collection corrections and a full "start over" request.
- Optional fields (insurance, emergency contact, preferred language) are offered once, as a single
  opt-in question, per the assessment's conversational note — never interrogated one by one.

## Setup

### Part 1 — Backend (works standalone, no Vapi account needed)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # edit VAPI_WEBHOOK_SECRET once you have a Vapi account

uvicorn app.main:app --host 0.0.0.0 --port 8000
```

- Two seed patients (Jane Doe, Carlos Martinez) are inserted automatically on first boot if the
  table is empty (`app/seed.py`).
- Swagger UI at `http://localhost:8000/docs`.
- Run tests: `pytest app/tests -v` (11 tests covering CRUD, validation errors, soft delete,
  persistence, and the Vapi duplicate-lookup tool).

### Part 2 — Expose it publicly and wire up Vapi

1. `ngrok http 8000` → copy the `https://...ngrok-free.dev` URL it prints.
2. Create a free account at [vapi.ai](https://vapi.ai), grab an API key, and add an LLM provider
   key (e.g. OpenAI) in Vapi's dashboard under Provider Keys.
3. Create a new Assistant and import [`vapi/assistant.json`](vapi/assistant.json) (or paste its
   `messages[0].content` as the system prompt and recreate the 3 tools manually). Replace every
   `REPLACE_WITH_NGROK_URL` with your ngrok URL and `REPLACE_WITH_VAPI_WEBHOOK_SECRET` with the
   same value you put in `.env` as `VAPI_WEBHOOK_SECRET`.
4. Buy/assign a free Vapi phone number to the assistant (Phone Numbers tab).
5. Call the number. Watch `uvicorn` stdout — every tool call and every saved patient payload is
   logged there (Observability requirement).

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `PORT` | No | Port for uvicorn (default 8000). |
| `DATABASE_URL` | No | SQLAlchemy URL, defaults to local SQLite file `patients.db`. |
| `VAPI_WEBHOOK_SECRET` | Recommended | Shared secret checked against the `x-vapi-secret` header on `/vapi/tools`, so only Vapi (or whoever holds the secret) can trigger writes. |

Vapi itself holds its own keys (Vapi API key, OpenAI key) inside the Vapi dashboard — they never
touch this codebase, so there's nothing telephony-related to leak from here.

## Observability

Every tool call and every successful create/update logs a structured line to stdout via Python's
`logging` module, including the full collected patient payload (`app/routers/vapi_tools.py`,
`app/routers/patients.py`). In production this would ship to a log aggregator; for this exercise,
stdout satisfies the requirement and is trivially visible during a live review call.

## Edge Cases & Resilience

- **Invalid date of birth / phone / state / zip**: rejected by Pydantic validators server-side
  (422), independent of whatever the voice agent itself already tried to catch. The tool webhook
  converts these into a `{"success": false, "error": "..."}` payload the LLM is instructed to turn
  into a natural, field-specific re-prompt.
- **DB write failure**: `create_patient`/`update_patient` wrap the DB call in try/except and return
  `success: false` with a message rather than letting an exception propagate to dead air — the
  prompt explicitly instructs the agent to apologize and explain rather than go silent.
- **Caller wants to start over**: handled at the prompt level (discard in-progress slot-filling,
  restart collection) rather than requiring a DB transaction, since nothing is persisted until the
  final confirmed save.
- **Telephony connection drops mid-call**: nothing is written to the database until the final
  confirmed `create_patient`/`update_patient` call, so a dropped call simply results in no partial
  record — never a half-written patient.
- **Returning caller**: `lookup_patient_by_phone` runs automatically once a phone number is known,
  before any other field is collected, so duplicates are caught early rather than after a full
  intake.

## Known Limitations & Trade-offs

- **Local + ngrok hosting**: fast to stand up, but the ngrok URL and the backend process only stay
  alive as long as this machine keeps them running; a real deployment (Railway/Render/Fly) would be
  needed for a durable, always-on demo. This was a deliberate speed trade-off for the time box.
- **SQLite**: fine for this dataset/load; would move to Postgres for concurrent writers or multi-instance deployment.
- **No auth on the REST API itself** beyond the Vapi webhook secret — acceptable per the assessment
  ("do not store real patient data," no HIPAA requirement), but a real system would need API auth
  (API keys/OAuth) in front of `/patients`.
- **Voice/LLM behavior depends on Vapi + GPT-4o's live behavior** at call time, not something unit
  tests can fully pin down — the prompt was designed and iterated by reasoning about the transcript
  it should produce; a full evaluation harness (recorded call transcripts scored automatically)
  would be the next investment.
- **Bonus items not implemented**: multi-language switching, appointment scheduling, call
  transcript storage, and a dashboard UI were left out to keep the core five requirement areas
  solid within the time budget.

## Next Steps (if continuing past the time box)

1. Deploy the backend to Railway/Render for a durable public URL instead of ngrok.
2. Add a small dashboard (server-rendered or a single React page) hitting `GET /patients`.
3. Store a call transcript/summary per patient (Vapi provides post-call transcripts via webhook —
   add an `end-of-call-report` webhook handler and a `call_transcripts` table).
4. Add API-level auth (API key header) in front of `/patients` for anything beyond local demo use.
5. Multi-language: Vapi supports dynamic language switching on the transcriber/voice; wire a
   "Hablo español" branch in the prompt plus a Spanish-capable voice/transcriber config.
