# City Care Clinic Front Desk Bot

Pipecat Flows text chatbot for a Bangalore clinic: verify or register patient, short pre-talk, suggest doctor, book slot, clinic FAQs, cancel. English replies only in v1. Patients can speak a message (mic, Pipecat STT on `/stt`; the text fills the box and is sent only on Enter) and hear replies read aloud by the browser (SPEC §10.1). A separate staff portal (`admin/`, SPEC §17) for doctors and the clinic admin uses the same backend under `/staff`. 24-hour build; hosted demo (React widget and staff portal on Vercel, FastAPI backend and PostgreSQL on Render), README, red-flag eval.

The full design is in `SPEC.md`. It is the single source of truth. Do not change a locked decision (SPEC §1) without asking the owner first. If code and SPEC disagree, ask.

## Read before you work on

| Area | SPEC section |
|---|---|
| Any decision or tradeoff | §1 |
| Nodes, flow state, prompts, pre-talk, specialty mapping, follow-up | §4 |
| LLM-facing tools, date resolution | §5 |
| Guardrails, emergency, self-harm, medication, off-topic | §6, §16.5 |
| RAG, MedlinePlus, `answer_faq` routing | §7 |
| Verification and lockout | §8 |
| Schema and seed data | §9 |
| Widget, voice input and read-aloud | §10, §10.1, §16.11 |
| Env vars and LLM providers | §3 |
| Deploy | §11 |
| Tests and eval | §12, §16.10 |
| Domain, ports, UoW, registry, nodes (code shape) | §16.2 to §16.6 |
| Build order and cut line | §13 |
| Staff portal (admin and doctor), `/staff` API, `admin/` app | §17 |

Read only the sections the task touches.

## Commands

- Install: `cd server && uv sync`
- Run backend: `uv run uvicorn clinic_bot.api.app:app --reload`
- Run widget: `cd web && npm run dev`
- Run staff portal: `cd admin && npm run dev` (port 5174)
- Create or reset a staff admin: `uv run clinic-create-admin --email you@example.com` (prompts for the password). `ADMIN_EMAIL` / `ADMIN_PASSWORD` only create the first admin at startup if none exists
- Database: `make db` (PostgreSQL 18 + pgvector in Docker: `clinic`, plus `clinic_test` for tests; the RAG index lives in it)
- Everything (db, backend, widget, staff portal): `docker compose up` (needs `server/.env`)
- Tests: `uv run pytest` (frozen clock via `CLINIC_NOW`; needs `make db`; `TEST_DATABASE_URL` overrides the `clinic_test` database)
- Lint and types: `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run lint-imports`
- Red-flag eval: `uv run python eval/run_red_flag_eval.py` (`--layer1-only` runs without an API key)
- Latency budgets: `uv run python eval/measure_latency.py`
- RAG cut-offs for an embedding model: `uv run python eval/tune_rag_threshold.py` (defaults live in `config.py`)
- Reseed DB (wipes all data): `make reseed`
- Regenerate widget UI types: `make types`

Update this list if a command changes.

## Layers

`api → pipeline → conversation → services → ports → domain`. Adapters implement ports. Only `container.py` imports adapters. `domain`, `ports` and `services` never import pipecat, sqlalchemy, fastapi, pgvector, fastembed, litellm or httpx. import-linter enforces this.

## Invariants (never break)

- LLM-facing function schemas never take `patient_id`, fee or visit type. Handlers read them from `FlowState`.
- The LLM can only pass ids that were offered in this session (`listed_doctor_ids`, `offered_slot_ids`).
- `confirm_booking()` takes no arguments; it reads everything from state.
- No patient data read or written before `verify_patient` or `register_patient` succeeds.
- In the chatbot, `confirm_booking` and `cancel_appointment` are the only writes to `appointments`. The staff portal changes only an appointment's status (booked, completed, no-show; never cancelled) and its intake details (SPEC §17.2).
- The chatbot never reads `consultations` (doctor-written medication must never reach a patient through the bot).
- Staff passwords are stored only as scrypt hashes and session tokens only as SHA-256 digests. The admin table browser never shows `password_hash` or `staff_sessions`.
- Fees come only from the `doctors` table. Follow-up fee only with an active grant and `same_issue=true`.
- The LLM passes day tokens (`tomorrow`, `saturday`); the server resolves dates in Asia/Kolkata.
- All time comes from the `Clock` port. No `datetime.now()` anywhere else.
- Function handlers `await state.verdict` before any side effect. OutputGate holds bot text until the guardrail verdict.
- Every medication question is refused with the fixed message. No drug info, no exceptions.
- On an emergency or self-harm red flag, the soft note with 108/112 (or Tele-MANAS 14416) always shows, and the chat carries on (SPEC §6.3, §6.4).
- Patient-facing fixed text lives in `data/messages.en.json`. No literal patient strings in Python.
- Provider names and model ids only in `config.py`, `adapters/llm/` and `adapters/embeddings/`.
- Replies: English, 2 to 3 short sentences, no markdown, never mention ids, function names or error codes.
- The bot never claims to send an SMS or WhatsApp message.
- Spoken input is never sent automatically: `/stt` only returns a transcript to the message box, and the patient sends it like typed text. `/stt` never reaches the LLM or the database, and transcripts are never logged.

## Code rules

- Python 3.12, `uv`, pinned versions. `mypy --strict` on domain, ports, services, conversation. No `Any` in public signatures.
- Domain types: frozen slotted dataclasses. Pydantic only at boundaries (settings, LLM args, UI payloads, API). Money is integer paise.
- Business rules live in `domain/policies.py` and services. Function handlers stay under ~15 lines.
- Functions ≤ 40 lines, classes ≤ 200, modules ≤ 300. Inheritance depth ≤ 1. Prefer composition.
- Only the patterns listed in SPEC §16.12. Don't add one unless something actually varies.
- Adapters translate infrastructure errors into `DomainError`. Broad `except` only in the registry wrapper and the session boundary.
- Logs: structlog JSON. Phone masked, DOB never, message text only as a hash.
- Tests use in-memory fakes and `FrozenClock`. Repo contract tests run against both fakes and SQL.
- Web: TypeScript strict, function components. Only modules in `transport/` import the Pipecat SDK. In `admin/`, only `src/api/client.ts` calls `fetch`.

## Pipecat

Pipecat and Pipecat Flows APIs change between releases. Flows is imported from `pipecat.flows` (bundled in `pipecat-ai`); the standalone `pipecat-ai-flows` package is frozen and not used. Check the pinned version in `pyproject.toml` before using global functions, context strategies, handler signatures or RTVI send-text. Don't rely on memory for these.

## Scope

Never cut: booking path, Layer 1 + Layer 2 + OutputGate, emergency check, medication refusal, FAQ detour, red-flag eval with holdout, deployment, README. Cut order if behind is in SPEC §13. Items in SPEC §14 are not built in v1.

The red-flag dev set (`eval/red_flags.dev.jsonl`) is committed before `patterns.py` exists. Never tune patterns on the holdout set.
