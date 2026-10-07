# Healthcare Chatbot (City Care Clinic front desk)

A Pipecat Flows text chatbot for a multi-specialty clinic in Bangalore. It verifies the patient (or registers a new one), takes the complaint in a short pre-talk, suggests a doctor, books a slot, answers clinic FAQs and cancels appointments. Replies are English only in v1. The design is in [SPEC.md](SPEC.md); [CLAUDE.md](CLAUDE.md) is the short index into it.

All patient data is synthetic. The widget says so on screen.

A separate **staff portal** (`admin/`) gives doctors and the clinic admin a login on the same backend. See [Staff portal](#staff-portal).

## Run it locally

Prerequisites: Python 3.12 with [uv](https://docs.astral.sh/uv/), Node 22, Docker (for PostgreSQL with pgvector), and a Google AI Studio API key (Gemini free tier).

```bash
make install                         # uv sync + npm install (web and admin)
cp server/.env.example server/.env   # then set GOOGLE_API_KEY (and model ids if needed)
cp web/.env.example web/.env         # already points at localhost:8000
cp admin/.env.example admin/.env     # staff portal, already points at localhost:8000
make db                              # PostgreSQL on localhost:5432 (Docker)
make run                             # backend on http://localhost:8000
make web                             # widget on http://localhost:5173 (second terminal)
```

Or everything at once (database, backend, widget and staff portal) with `docker compose up` (needs `server/.env`).

The database is PostgreSQL with the pgvector extension (image `pgvector/pgvector:pg18`), which also holds the RAG index. `make db` (`docker compose up -d db`) starts it on `localhost:5432` with user and password `clinic`, the app database `clinic` and the test database `clinic_test`; `make run` expects it to be up. To browse it: `docker compose exec db psql -U clinic -d clinic`, or connect any PostgreSQL client (pgAdmin, DBeaver, the VS Code PostgreSQL extension) to those settings.

On first start the backend seeds the empty database with demo data, enables pgvector and builds the RAG index (`doc_chunks`) from the clinic documents (about 5 seconds; the embedding model downloads once). Later starts reuse the index unless the documents or the embedding model changed. Open the widget, expand "Try it with a test patient" and use one of the three demo patients.

Upgrading a checkout from before the pgvector switch: the compose database now uses the `pgvector/pgvector:pg18` image and a new volume, `pgvector_data`, so `make db` starts an empty database that is seeded with demo data. The old `pgdata` volume (`postgres:18-alpine`) is left alone; to keep its data, `pg_dump` it from the old image and `pg_restore` into the new one. Don't point the new image at the old volume: it was created on Alpine, and its text collation differs from the Debian-based pgvector image.

Model ids are env only. The defaults in `.env.example` (`gemini-3.6-flash` for the main model, `gemini-3.5-flash-lite` for the classifier) were current when this was built; check AI Studio for what your free tier offers and change `MAIN_MODEL` / `CLASSIFIER_MODEL` if needed. Embeddings default to the local fastembed model (free, no API calls); `EMBED_BACKEND=gemini` with `EMBED_MODEL=gemini-embedding-001` uses Gemini instead, with its own cut-offs and a free-tier limit of 100 embedded texts per minute (see "RAG cut-offs" under the decisions below). Switching to OpenAI or Anthropic is `LLM_PROVIDER=openai` (or `anthropic`) plus that provider's model ids and key, or a per-role override such as `CLASSIFIER_PROVIDER=openai`. Voice input always uses Gemini Live, so it still needs `GOOGLE_API_KEY`.

### Commands

| What | Command |
|---|---|
| Backend tests (unit, contract, concurrency, WebSocket integration; need `make db`) | `cd server && uv run pytest` |
| Widget tests | `cd web && npm test` |
| Lint, format, strict types, import contracts | `make lint` |
| Red-flag eval, both layers (needs API key) | `make eval` |
| Red-flag eval, Layer 1 only (free, deterministic) | `make eval-l1` |
| Server latency budgets | `cd server && uv run python eval/measure_latency.py` |
| RAG cut-offs for the configured embedding model | `cd server && uv run python eval/tune_rag_threshold.py` |
| Start PostgreSQL (Docker) | `make db` |
| Wipe the database and reload demo data | `make reseed` |
| Force a RAG index rebuild from the files in `server/data/docs` (normally not needed: the backend builds it on start, and the next start re-applies admin edits to the documents) | `make index` |
| Regenerate widget UI types from the server schema | `make types` |
| Staff portal on http://localhost:5174 | `make admin` |
| Portal tests, lint, types | `cd admin && npm test && npm run lint && npm run typecheck` |
| Create or reset a staff admin (prompts for the password) | `cd server && uv run clinic-create-admin --email you@example.com` (or `make create-admin EMAIL=you@example.com`) |

## Deploy

**Backend on Render.** `render.yaml` is a blueprint for a Docker web service built from the root `Dockerfile`. The image installs dependencies, downloads the embedding model and pre-warms the MedlinePlus cache at build time, and the blueprint also creates a free Render PostgreSQL database and sets `DATABASE_URL` from it; the first start enables pgvector, seeds the data and builds the RAG index, later starts keep both. Render's free database expires after 30 days; for longer, set `DATABASE_URL` to another PostgreSQL that offers pgvector (Neon, Supabase). Set `GOOGLE_API_KEY`, `MAIN_MODEL`, `CLASSIFIER_MODEL` and `ALLOWED_ORIGINS` (your Vercel URL) in the Render dashboard.

**Widget on Vercel.** Import the repo with `web` as the root directory (Vite preset), and set `VITE_WS_URL=wss://<render-host>/ws` and `VITE_API_URL=https://<render-host>`. Voice input connects to `wss://<render-host>/stt`, derived from `VITE_WS_URL` (`VITE_STT_URL` overrides it). The widget pings `/healthz` on load and shows "Waking up the demo server..." while the free Render instance starts.

**Staff portal on Vercel.** Create a second Vercel project from the same repo with `admin` as the root directory (Vite preset) and set `VITE_API_URL=https://<render-host>`. On Render, add the portal's URL to `STAFF_ORIGINS` and set `ADMIN_EMAIL` and `ADMIN_PASSWORD` for the first admin.

## Voice input and read-aloud

SPEC §10.1. The mic button beside Send asks for microphone permission on first use. While it is on, the widget streams 16 kHz audio to the backend's `/stt` WebSocket, where a small Pipecat pipeline (Gemini Live speech-to-text, using `GOOGLE_API_KEY`) sends the words back as they are recognised. They fill the message box and nothing is sent until the patient presses Enter, so spoken messages pass the same guardrails as typed ones. Press the mic again to stop; the box can then be edited.

Replies are read aloud by the browser's built-in speech (no server TTS, no extra key). The speaker button and slider at the top right mute it or set the volume, and the choice is remembered. Browsers allow speech only after the user has interacted with the page, so the greeting itself is not read. The mic works on HTTPS or localhost only.

## Staff portal

`admin/` is its own React + Vite app (SPEC §17), deployed separately from the widget. It calls the backend's `/staff` JSON API with a bearer token.

- **Login.** Email and password. The first admin comes from `ADMIN_EMAIL` / `ADMIN_PASSWORD` in `server/.env` (created on startup if missing) or from `uv run clinic-create-admin`. There is no sign-up: the admin creates each doctor's login and hands over the initial password; doctors can change it under "Change password". Five wrong passwords lock an email for 15 minutes.
- **Doctor.** Today's, upcoming and past appointments. On an appointment: patient details, what the bot collected in the pre-talk, the patient's chat summaries and earlier consultations. The doctor can set the outcome (completed, no-show), correct the visit details, and submit the consultation: notes, diagnosis, medication and a "follow-up required" tick with a window in days. Ticking follow-up creates the follow-up grant, so when the patient books again through the chatbot for the same issue they get the follow-up fee.
- **Admin.** Overview counts, appointments by day, doctor profiles and fees (the chatbot picks up changes at once), doctor logins (create, reset password, deactivate), clinic information (the FAQ documents the chatbot answers from; saving re-indexes them), closure days, and a read-only view of every database table. Password hashes and session tokens are never shown.

Run it locally with the backend on 8000: `cd admin && cp .env.example .env && npm install && npm run dev`, then open http://localhost:5174.

## Architecture

```
React widget (Vercel)  ──WSS, RTVI over protobuf──►  FastAPI /ws  (one pipeline per connection)
                                                     transport.input
                                                     → RTVIProcessor        send-text becomes a user message
                                                     → GuardrailInput       Layer 1 regex (sync); Layer 2 classifier started
                                                     → user aggregator
                                                     → LLM (Gemini) + FlowManager
                                                     → OutputGate           holds bot text until the verdict
                                                     → UIEmitter            tool UI payload → RTVI server message
                                                     → assistant aggregator
                                                     → transport.output
```

The backend is layered ports and adapters, `api → pipeline → conversation → services → ports → domain`, with adapters (SQLAlchemy and the staff table browser, pgvector, fastembed, LiteLLM, Gemini Live STT, MedlinePlus, clock, message catalog) wired only in `container.py`. import-linter enforces the layers in CI; `mypy --strict` covers domain, ports, services and conversation.

- **Domain**: frozen value objects (phone, DOB, money in paise, day tokens), entities that own their invariants, and small policies (booking rules, fees, cancellation cutoff, lockout).
- **Services**: verification, doctor directory and specialty mapping, scheduling, booking, intake checklists, FAQ routing, callbacks, guardrails, transcripts and chat summaries, and the staff services (auth, accounts, records, consultations, clinic documents, closures).
- **Conversation**: Flows nodes (one class per node, built by a template method; the greeting opens with a menu of buttons: book, cancel, FAQ) and thin LLM-facing function handlers registered through one wrapper that validates args, waits for the guardrail verdict, maps domain errors to codes, pushes UI and resolves transitions.
- **Pipeline**: the guardrail input processor, the output gate, the UI emitter, latency metrics, the per-connection chat session, and the speech session behind `/stt`.

### Why tools, not prompts, carry authorisation

The LLM never sees or passes a `patient_id`, fee or visit type. Handlers read the verified patient from flow state, fees come only from the `doctors` table, and the visit type is computed server-side from the follow-up grant and the patient's "same issue" answer. Any id the LLM passes (doctor, slot, appointment) must be one offered in this session, and `confirm_booking()` takes no arguments at all; it books exactly what was read back. A prompt injection can make the model say odd things, but it cannot book for someone else, change the price or touch a slot it was not shown. The unit tests check every LLM-facing schema for these fields.

### Guardrails

Every user message passes Layer 1 (compiled regex, English plus romanised Hindi and Kannada) before the LLM. An emergency or self-harm hit adds a soft note with the emergency numbers (or the Tele-MANAS helpline) and the message carries on to the LLM; a medication or off-topic hit gets a fixed reply instead, and the node stays. Otherwise the message goes to the main LLM while Layer 2 (a one-label classifier on a smaller model) runs in parallel. Button clicks skip Layer 2 to save rate limit: if the message is exactly the text of a button the server offered since the patient's last message (menu, quick replies, doctor cards, slot or appointment buttons), it is server-written, so it gets a `NONE` verdict without a classifier call. The server checks this itself, never a flag from the browser, and Layer 1 still runs. The OutputGate holds the LLM's text until the verdict; function handlers wait for it before any side effect. On a blocking verdict the held text is dropped, the in-flight response is interrupted, and the dropped text never enters the context. A classifier timeout, error or 429 after one retry counts as `NONE`, since Layer 1 already ran.

Regex has no negation handling by design: "no chest pain, just a cough" matches. Every emergency or self-harm flag shows one soft line ("If this is an emergency, please call 108 or 112, or go to the nearest hospital."), then the bot answers normally and the booking carries on. There is no banner, check question or chat end, so a false positive costs one line, and the emergency numbers are never hidden.

## Evaluation

### Red-flag eval

The dev set (`server/eval/red_flags.dev.jsonl`, 62 items) was committed before `patterns.py` existed; the git history shows the order. The holdout set (20 items) was written afterwards by a different model given only the category list, and was never used to tune patterns. A red flag means emergency or self-harm; medication and off-topic count as "not" here.

Results from `make eval` (classifier `gemini-3.5-flash-lite`, Oct 2026; full report with per-category recall and every miss in `server/eval/results.md`):

| Set | Layer | Recall | Precision | FP rate | TP | FN | FP | TN |
|---|---|---|---|---|---|---|---|---|
| dev (62) | Layer 1 regex | 0.97 | 0.84 | 0.28 | 36 | 1 | 7 | 18 |
| dev (62) | Layer 2 classifier | 1.00 | 1.00 | 0.00 | 37 | 0 | 0 | 25 |
| dev (62) | OR of both | 1.00 | 0.84 | 0.28 | 37 | 0 | 7 | 18 |
| holdout (20) | Layer 1 regex | 0.36 | 0.50 | 0.44 | 4 | 7 | 4 | 5 |
| holdout (20) | Layer 2 classifier | 1.00 | 1.00 | 0.00 | 11 | 0 | 0 | 9 |
| holdout (20) | OR of both | 1.00 | 0.73 | 0.44 | 11 | 0 | 4 | 5 |

The gap between dev and holdout is the honest result: regex generalises poorly to new phrasings ("everyone would be better off without me", "his whole body is jerking", Kannada phrasing outside the authored list). That is the reason Layer 2 runs on every typed message. All Layer 1 false positives on both sets are negated or historical mentions, which cost only the one soft note line.

The OR of both layers reaches recall 1.00 on dev (SPEC target: at least 0.95) and on the holdout. Every false positive of the OR comes from Layer 1's negated or historical matches; the classifier had none. `make eval` needs `GOOGLE_API_KEY` and paces classifier calls at 12 per minute (`--rpm`), so a run takes about 7 minutes; `make eval-l1` runs Layer 1 alone without a key. A first run scored Layer 2 at 0.70 on dev because cut-off classifier replies counted as `NONE` (see "Classifier output" below); the numbers above are after that fix.

### Latency (server side, excluding LLM time)

Measured with `eval/measure_latency.py` (frozen clock, real PostgreSQL in Docker, real fastembed and pgvector; 50 runs after warm-up, 1000 for the regex; it reseeds the `clinic_test` database):

| Step | Budget p95 | p50 ms | p95 ms |
|---|---|---|---|
| Regex precheck | < 1 ms | 0.06 | 0.08 |
| verify_patient (DB write) | < 20 ms | 7.44 | 8.99 |
| get_free_slots (DB) | < 20 ms | 3.88 | 5.31 |
| Upcoming appointments (DB) | < 20 ms | 3.03 | 3.66 |
| RAG query (embed + pgvector) | < 40 ms | 8.23 | 10.83 |

A classifier error of any kind counts as `NONE` and never stalls a turn. If the main model errors (for example a 429), the turn is retried once after a short backoff; a second failure sends the fixed "busy" message.

Each live session also logs p50/p95 for regex, classifier, every tool, mapper, LLM first token, server overhead per turn and the share of turns where the classifier finished before the first bot token. Those numbers need a real LLM and are not reported here yet.

### Tests

231 backend tests: domain and policy unit tests, services against in-memory fakes, repository contract suites (chatbot and staff) run against both the fakes and PostgreSQL, seeding tests (an existing database is kept, the slot window moves), a concurrency test (two simultaneous confirms on one slot, exactly one wins), WebSocket integration tests that drive the real pipeline with a scripted LLM over the same RTVI protobuf protocol the widget uses, chat-summary tests, the `/stt` speech socket with a scripted STT, button clicks skipping the classifier, and staff API tests (login, lockout, roles, appointments, consultations, admin screens). Widget tests cover the reducer (UI after its sentence, stale buttons disabled, handoff ends the chat), the UI registry, speaker settings and the voice draft; portal tests cover the API client and the routes.

### Manual checks (SPEC 12.4)

| Check | Status |
|---|---|
| Fee asked before verification → tool call, never a guess | Automated: `test_fee_question_before_verification_uses_the_doctor_table` |
| Two tabs pick the same slot → second gets SLOT_TAKEN and a re-offer | Automated: `test_two_tabs_same_slot` |
| "No chest pain" in pre-talk → soft note, normal reply, booking continues | Automated: `test_layer1_emergency_adds_a_soft_note_and_the_chat_goes_on` |
| Hindi-script complaint → English reply, correct routing | Not run: needs the real Gemini model |

## Decisions made while building

These were not fixed by the SPEC, or the SPEC and the pinned libraries disagreed. Each is a small call; none changes a locked decision in SPEC §1.

- **Pipecat version.** The standalone `pipecat-ai-flows` package is frozen at 1.4.0 and requires `pipecat-ai` 1.4.x. Flows now ships inside `pipecat-ai`, so this pins `pipecat-ai==1.12.0` and imports `pipecat.flows`. The import-linter contract forbids `pipecat` (which covers it) instead of `pipecat_flows`.
- **Global functions.** Flows' own `global_functions` adds them to every node, including terminal ones. The SPEC excludes terminal nodes, so `BaseNode` adds the two globals per node instead.
- **Function names.** Extra LLM-facing functions the flow needed: `change_time` and `change_doctor` (for "change → pick_slot | suggest_doctor" in confirm) and `select_appointment` (to move from `cancel_list` to `cancel_confirm`).
- **Fixed text.** Greeting, verification failure, lockout, FAQ no-match, the confirm read-back, the booked message with the specialty prep sheet, the cancel confirmation and all safety text are fixed strings from `messages.en.json`, sent without the LLM. Added catalog keys: `cancel.done`, `handoff.no_ticket`.
- **Verification.** An unreadable phone or date asks again and does not count as a failed attempt. The lockout starts at the fifth failure within 15 minutes and lasts 15 minutes; failures before a successful verification do not count. New patients register in the chat with name, mobile, DOB and sex (`register_patient`, no OTP); re-registering a number already on file signs in only on a full match and otherwise fails like a wrong DOB, counted toward the lockout. Fee amounts are not shown in the chat (cards, suggestions, read-back, confirmation); the bot quotes a fee only when the patient asks about cost. Fees are still computed from the `doctors` table and stored on each appointment. A handoff after failed verification shows the desk number without creating a callback, since the caller's identity is unconfirmed.
- **Emergency handling.** The first build asked a check question and could end the chat. It was replaced (owner decision) by one soft note with 108/112, or Tele-MANAS 14416 for self-harm, after which the chat carries on; there is no check node any more.
- **Classifier output.** The label is the first field of the classifier's JSON reply, so it is read even when a long reason is cut off at the token limit; the classifier and mapper get 150 output tokens. Before this fix, cut-off replies on vivid emergencies counted as `NONE`.
- **Button clicks skip the classifier.** On the Gemini free tier the per-minute limit ran out quickly, and about half the messages in a booking are button clicks whose text the server wrote itself. Those skip Layer 2 (SPEC §6.1); typed messages are always classified.
- **Layer 1 hits.** Medication and off-topic hits keep the user's message out of the LLM context. Emergency and self-harm hits only add the soft note.
- **Date window.** "Next 7 days" is today through today + 7 inclusive, so naming today's weekday can still reach next week's.
- **Slot chips** for another doctor's slot (from alternatives) send "Tue 7 Oct, 6:15 PM with Dr. X" so the text stays unambiguous.
- **Handoff** ends the chat in the widget with a "Start new chat" button.
- **Widget transport.** The default WebSocket media manager opens an AudioContext, which browsers keep suspended until a user gesture, and the client waits on it before `client-ready`. The chat connection keeps a no-op media manager (text only). Voice input uses its own short-lived `/stt` socket (`transport/speechClient.ts`) with an AudioWorklet mic recorder, so the chat never waits on audio permission and a Gemini Live session is open only while the mic is on. The server serializer sends only RTVI messages, because the JS deserializer rejects raw text and interruption frames.
- **Vector store.** The RAG index moved from Chroma (a folder baked into the image) to pgvector in the same PostgreSQL (owner decision). Chunking, the cosine cut-offs, top-3 and the `kind` filters are unchanged, and the same questions return the same chunks with the same scores. The chunk tables sit outside the ORM models, so `make reseed` and the admin table browser leave them alone, as they did the Chroma folder. Search is exact (no ANN index): there are only a few dozen chunks.
- **Embeddings backends.** `EMBED_BACKEND=openai|gemini` go through LiteLLM (`LiteLLMEmbedder`) rather than a separate OpenAI class. `EMBED_API_KEY` (optional) gives them their own key; Gemini limits are per project, so it only adds quota when the key comes from a different Google account. On Render's free plan (512 MB) use hosted embeddings: with fastembed the backend was killed for running out of memory while building the index at startup.
- **RAG cut-offs per embedding model.** The 0.35 cut-off was tuned for MiniLM; Gemini embeddings score unrelated questions around 0.55 to 0.67, so with 0.35 the bot never said "I don't have that information". The FAQ and checklist cut-offs are now separate and set per model (Gemini: 0.60 for both), measured with `eval/tune_rag_threshold.py`. Gemini's scores for answerable and unanswerable questions overlap, so its cut-off keeps all 26 answerable test questions (refusing "what are your timings" would be the worse mistake) and rejects 6 of 16 unanswerable ones; `FAQ_THRESHOLD` / `CHECKLIST_THRESHOLD` override them. Gemini embeddings (`EMBED_BACKEND=gemini`, `EMBED_MODEL=gemini-embedding-001`) are supported: hosted calls go in batches of at most 100 texts (Gemini's batch limit). On the free tier Gemini allows 100 embedded texts per minute per model, and every text counts: an index rebuild is one per chunk (57 today), plus one per FAQ question and one per checklist lookup. If a rebuild is rate limited at startup, the server starts with the index it has and logs `index_sync_failed`; the next start or admin save rebuilds it.
- **Idempotency index.** SPEC §9 lists `UNIQUE(session_id, slot_id)`. It is a partial unique index on booked rows, like the slot index, so a patient who cancels a slot can book it again in the same session.
- **MedlinePlus gating.** Inside `answer_faq`, MedlinePlus is tried only when the turn's classifier label was a real `NONE` (not a timeout default) and no medication pattern matches the question, so a medicine question cannot reach it even if Layer 1 misses it.
- **Import contract.** "Only the container wires adapters" ignores exactly one edge, `api.app → container`, because the app factory builds the composition root for `uvicorn clinic_bot.api.app:app`.
- **Seed details.** Doctor names "Dr. Rao" and "Dr. Rao S" as written in the SPEC; the closure day is three days after "today" (skipping Sunday); about a quarter of future slots are pre-booked under one synthetic patient so availability looks real.
- **Files beyond the SPEC layout**: `cli.py` (reseed, index build, embedding model and MedlinePlus pre-warm), `seed/demo_data.py` (the synthetic doctors and patients, kept apart from the seeder), `services/transcripts.py` (the TranscriptWriter from §16.7), `services/chat_summaries.py` (end-of-chat summaries, §9.2), `conversation/io.py` (the interface the pipeline implements for nodes), `conversation/views.py` (domain to UI/LLM formatting), `eval/measure_latency.py`, `docker-compose.yml` (with `docker/postgres/init-test-db.sql`), `Makefile`, `.pre-commit-config.yaml` and `.github/workflows/ci.yml` (the §16.9 gates), and the widget's `TryItPanel` (in `components/DemoNotice.tsx`), `lib/text.ts` and `config.ts`.

## Not verified in this build

- Automated tests drive every flow with a scripted LLM through the real pipeline. Gemini itself was only tried by hand locally (chat, Layer 2 eval, voice input); the OpenAI and Anthropic provider paths are wired but have not been run with real keys.
- The mic and read-aloud were checked against the server with a recorded WAV file, not across browsers.
- The Docker image builds; it has not been run on Render yet.
- Not deployed to Render or Vercel.

## Later (not built in v1)

From SPEC §14: staff portal extras (callback queue, editing consulting hours, audit log), abuse controls for the public demo, session resume by phone, reschedule (book new, then cancel old), dependants, an OTP step for registration, SMS/WhatsApp confirmations, a full voice conversation (Daily/Twilio transport, Deepgram STT, Cartesia TTS, `prompts/voice.md` is already written), Kannada and Hindi replies, production PHI controls, and soft slot holds.
