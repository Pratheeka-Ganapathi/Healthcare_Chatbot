# City Care Clinic Front Desk Bot: Technical Spec

Pipecat Flows text chatbot for a multi-specialty clinic in Bangalore. It verifies the patient, takes the complaint in a short pre-talk, suggests a doctor, books a slot, answers clinic FAQs, and cancels appointments. English replies only in v1. A separate staff portal (§17) lets doctors record consultations and follow-ups and lets an admin manage the clinic. Patients can speak a message instead of typing it and hear replies read aloud (§10.1). A full voice conversation and Kannada/Hindi replies come later; v1 leaves room for them.

Build window: 24 hours. Deliverables: hosted demo (React widget on Vercel, Python backend on Render), README with architecture and eval results, red-flag eval report.

This is the single source of truth for the design. `CLAUDE.md` is a short index into it. Section 1 records every locked decision. Do not change a locked decision without asking the owner first.

---

## 1. Locked decisions

| Area | Decision | Why |
|---|---|---|
| Runtime | Pipecat + Pipecat Flows. FastAPI server; each `/ws` connection builds its own pipeline and `FlowManager` via `FastAPIWebsocketTransport` | Concurrent sessions (needed for slot-race test and a public demo). Voice later is a transport + STT/TTS swap |
| Code architecture | Layered ports-and-adapters OOP: `domain` → `services` → `conversation` / `pipeline` → `api`, wired in one composition root. Layer rules enforced by import-linter; strict typing; every external system behind an interface. See §16 | Expert-level, testable without an LLM or DB; provider/storage swaps touch only adapters |
| LLM provider | Provider-agnostic. Every model is chosen by env per role (main, classifier, mapper). v1 runs on Gemini free tier; moving to a paid model or another vendor is an env change, no code change | Free demo now, paid later |
| Data | PostgreSQL via SQLAlchemy + asyncpg, own schema. Demo data is seeded only into an empty database; data persists across restarts, `make reseed` resets it (owner decision, Oct 2026; replaces SQLite reseeded on every start) | Patients, bookings and chat summaries survive restarts; same engine locally (Docker), in CI and on Render |
| Channel | Custom React widget, `@pipecat-ai/client-js` + `client-react`, WebSocket transport (RTVI) | Full control of cards and buttons; same SDK for voice later |
| Voice input and read-aloud | Mic button in the widget: Pipecat transcribes the speech (Gemini Live STT over its own `/stt` WebSocket, open only while the mic is on) into the message box. Nothing is sent until the patient presses Enter, so spoken text takes the same guarded text path as typed text. Replies are read aloud by the browser's built-in speech; mute and volume sit top right (owner decision, Oct 2026) | Voice with the existing Gemini key and no TTS credential; the guardrails see exactly what the patient chose to send |
| Rich UI | Tools emit structured `ui` payloads; the LLM never writes JSON for the UI | Deterministic rendering; ignored in voice |
| Mid-booking FAQ | Global `answer_faq` function; LLM calls it and stays on the node | Flows has no push/pop |
| Identity | Phone + DOB verification before pre-talk. The opening message and intent are carried through verification so the patient never repeats themselves | Intake attaches to a known patient; no repeated "how can I help" |
| Verification abuse | Generic failure message (same for wrong phone and wrong DOB). Per-phone lockout: 5 failures in 15 min, across sessions. Per-session: 3 failures → handoff | Stops phone-number probing and refresh bypass |
| Unknown patient | Registers in chat: full name, mobile, DOB, sex via `register_patient`, then books straight away. No OTP. Offered up front in verify and again after a failed check. A phone already on file signs in only if name + DOB match; otherwise the generic failure, counted toward the lockout (owner decision, Oct 2026) | New patients can book online; without OTP, an existing number is revealed only by a failed registration, which the lockout rate-limits |
| Booking for others | Not supported | Dependant model out of scope |
| Booking arguments | State-carried. `choose_doctor`, `select_slot`, `submit_intake` write to flow state; confirm node exposes only `confirm_booking()` with no arguments | LLM cannot change details between read-back and write |
| Duplicate rules | Enforced in `confirm_booking`: one appointment per doctor per day, no overlapping times across doctors, max 3 upcoming | Realistic front-desk rules |
| Slot race | Optimistic; DB unique on `appointments.slot_id` (active); `SLOT_TAKEN` → re-fetch | Simplest correct behaviour |
| Dates | Server resolves relative dates ("tomorrow", "Saturday") in Asia/Kolkata. LLM passes day tokens, never computes dates | Small models get date math wrong |
| Clock | All time comes from `clock.now()`. Real IST clock by default; `CLINIC_NOW` env overrides for tests and golden runs | Fresh demo data + deterministic tests |
| Follow-up | Doctor decides: ticking "follow-up required" on the consultation form in the staff portal creates the grant (§17.2). The chatbot reads it through `followup_grants`, `check_followup` and the fee logic in `confirm_booking`. LLM never sets visit type or fee | Matches real clinic practice |
| Red flags | Layer 1 regex (pre-LLM, includes romanised Hindi/Kannada phrases) + Layer 2 LLM classifier on every typed turn, run in parallel with the main LLM (skipped only for an exact click on a live, server-offered button; §6.1). Either triggers | Recall over precision; covers mid-booking paraphrases |
| Red-flag response | Soft, non-alarming note: "If this is an emergency, please call 108 or 112, or go to the nearest hospital." Shown every time either layer flags EMERGENCY, then the chat carries on as usual (no banner, no check question, no chat end). Supersedes the earlier check-and-terminate flow (owner decision, Oct 2026) | Emergency numbers are always offered without disrupting the conversation, including on false positives like "no chest pain" |
| Self-harm | Detected by the guardrail only. Soft note with Tele-MANAS 14416 and 112, shown every time, then the chat carries on as usual (owner decision, Oct 2026) | Helpline always offered without stopping the chat |
| Medication | Complete refusal of every medication question: dose, timing, interactions, side effects, "what is X used for", "should I take X before my test". Fixed refusal + booking offer. No drug API, no drug info, no exceptions | No liability surface |
| Off-topic | Handled in the guardrail (classifier label + regex for code requests). Fixed scope reply; node unchanged | Keeps the main prompt clean |
| Non-English input | No guardrail. LLM understands Hindi/Kannada/code-mixed input and always replies in English | v1 is English-out only |
| Human handoff | Front desk number + `request_human` callback ticket | No live agent UI |
| SMS/WhatsApp | Dropped. Bot never claims to send a message | Not building it |
| Staff/doctor view | Built as a separate app, `admin/` (its own Vercel project), on the same backend under `/staff`: email + password login, doctor accounts created by the admin only; doctors see their appointments, edit outcome and visit details, write the consultation (notes, diagnosis, medication) and tick follow-up; the admin sees every table and edits doctors, accounts, clinic FAQ docs and closures. See §17 (owner decision, Oct 2026; replaces "not in v1") | Doctors and the front office work on the same data the bot books into |
| PHI | Synthetic patients only. Transcripts + intake stored for debugging. When a verified patient's chat ends, a 3 to 5 sentence summary is stored on their record in `chat_summaries` (owner decision, Oct 2026). Widget shows a demo notice | Debuggability; a per-patient history for later reference |
| Session | In-memory per connection; refresh starts over | Time |
| Context | Flows `APPEND` within a task; `RESET_WITH_SUMMARY` on entering `booked` (which then acts as the router) and when returning to `router` after a cancellation. Key facts live in flow state, not context | Bounded context, FAQ-then-return still works |
| RAG | `all-MiniLM-L6-v2` via fastembed (ONNX, no torch) + pgvector in the app's PostgreSQL over authored clinic docs. Index built on first start and rebuilt only when the docs or the embedding model change. `EMBED_BACKEND` env makes it swappable. Replaced Chroma (owner decision, Oct 2026) | Small image, one database for app data and the index, survives redeploys |
| General health | MedlinePlus free-text health-topic search (tests, conditions) only, disk-cached. No openFDA | MedlinePlus Connect needs codes; openFDA lacks Indian brands; medication is refused anyway |
| Cancel | Full flow, 2-hour cutoff enforced in tool. Reschedule = stub | Scope |
| Fees in chat | The amount is never shown unprompted: no fee on doctor cards, doctor suggestions, the confirm read-back or the confirmation card. The bot quotes a fee only when the patient asks about cost (`answer_faq` returns fees only for cost questions). Visit type (new / follow-up) is still read back. Fees are still computed and stored on the appointment (owner decision, Oct 2026) | Keeps the chat focused on booking; the amount stays available on request and for the staff view |
| Old buttons | Every interactive UI block disables when a newer bot message arrives. Buttons send unambiguous text | Stale clicks can't misfire |
| Hosting | Widget on Vercel. Backend as Docker web service on Render (Railway as fallback) | Vercel can't hold WebSockets |
| Rate limits | Classifier on a smaller model (separate quota). Main LLM: on any non-fatal LLM error, one retry after ~1.5 s, then the fixed "busy" message. Classifier failure (after one retry on a rate limit) → regex verdict stands, turn continues | Gemini free tier |
| Eval | Red-flag dev set (~60) frozen and committed before any regex is written; 20-item holdout written afterwards by someone/something else; both reported per layer | Avoids overfit recall numbers |

---

## 2. Architecture

```
┌───────────────────┐  WSS (RTVI)   ┌──────────────────────────────────────────────────┐
│ React widget      │◄─────────────►│ FastAPI  /ws  (one pipeline per connection)       │
│ Vercel            │ text + ui     │                                                  │
│ bubbles, chips,   │ frames        │  FastAPIWebsocketTransport.input                 │
│ cards, mic, TTS   │               │  → RTVIProcessor (send-text → user text frame)   │
└───────────────────┘               │  → GuardrailInput   regex (sync) + classifier    │
                                    │                     task started (async)          │
                                    │  → user context aggregator                       │
                                    │  → LLM service (factory, role=main) + FlowManager │
                                    │  → OutputGate      holds bot text until verdict   │
                                    │  → UIFrameEmitter  tool ui payload → RTVI msg     │
                                    │  → assistant context aggregator                  │
                                    │  → transport.output                              │
                                    └──────┬───────────────┬───────────────┬───────────┘
                                           │ tools         │ RAG           │ side LLM calls
                                    ┌──────▼──────┐ ┌──────▼───────┐ ┌─────▼───────────┐
                                    │ PostgreSQL  │ │ pgvector     │ │ classifier      │
                                    │ (asyncpg)   │ │ (same        │ │ mapper          │
                                    │             │ │ PostgreSQL)  │ │ (StructuredLLM) │
                                    └─────────────┘ └──────────────┘ └─────────────────┘
```

Also on the FastAPI app: `WS /stt` (voice input, §10.1; no LLM, no database), `GET /healthz` (widget pings it on load to wake the Render instance), `GET /config/demo` (test patient credentials for the widget's "Try it" panel), and the staff portal's JSON API under `/staff` (§17.5), used by the separate `admin/` app.

### 2.1 Repo layout

Layering and dependency rules are in §16. Arrows in comments show which port an adapter implements.

```
clinic-bot/
  server/
    pyproject.toml                 # pinned deps, ruff, mypy, import-linter contracts
    src/clinic_bot/
      config.py                    # Settings (pydantic-settings), all env vars (§3)
      container.py                 # composition root: builds singletons + per-session objects
      cli.py                       # clinic-reseed, clinic-build-index, clinic-prewarm-embedder, clinic-prewarm-health,
                                   # clinic-create-admin
      domain/                      # pure Python, no I/O, no framework imports
        enums.py                   # Specialty, VisitType, TimePref, AppointmentStatus, Intent, GuardrailLabel
        values.py                  # PhoneNumber, PersonName, DateOfBirth, Money, TimeWindow, DayToken (frozen value objects)
        entities.py                # Patient, Doctor, Slot, Appointment, FollowupGrant, IntakeSummary
        errors.py                  # ErrorCode enum + DomainError hierarchy
        policies.py                # BookingPolicy, FeePolicy, CancellationPolicy, LockoutPolicy
        day_resolver.py            # DayResolver: DayToken + now → date(s)
        staff.py                   # EmailAddress, StaffUser, StaffSession, ConsultationNote,
                                   # Consultation, ClinicDoc (§17)
      ports/                       # interfaces (typing.Protocol), owned by the core
        clock.py                   # Clock
        repositories.py            # PatientRepo, DoctorRepo, SlotRepo, ClosureRepo, AppointmentRepo,
                                   # FollowupRepo, VerifyAttemptRepo, CallbackRepo, ChatSummaryRepo,
                                   # TranscriptRepo
        staff.py                   # StaffUserRepo, StaffSessionRepo, ConsultationRepo, ClinicDocRepo,
                                   # TableBrowser
        unit_of_work.py            # UnitOfWork (async context manager, commit/rollback), UnitOfWorkFactory
        llm.py                     # StructuredLLM: classify / write
        embeddings.py              # Embedder
        vector_store.py            # VectorStore, DocIndexer
        health_info.py             # HealthInfoProvider
        messages.py                # MessageCatalog
      services/                    # application use cases; depend on domain + ports only
        verification.py            # VerificationService
        directory.py               # DoctorDirectory (in-memory cache), SpecialtyMapper
        scheduling.py              # SchedulingService (free slots, alternatives)
        booking.py                 # BookingService (confirm, list, cancel)
        intake.py                  # ChecklistRetriever
        faq.py                     # FaqService (retriever + health provider)
        callback.py                # CallbackService
        transcripts.py             # TranscriptWriter (queue + batched inserts)
        chat_summaries.py          # ChatSummaryService (§9.2)
        staff/                     # portal use cases (§17): auth, accounts, records,
                                   # consultations, clinic admin, clinic docs
        guardrails/
          base.py                  # Guard (ABC), Verdict
          patterns.py              # compiled pattern sets per label
          regex_guard.py           # RegexGuard
          llm_guard.py             # LLMClassifierGuard
          pipeline.py              # GuardPipeline: sync regex, async classifier future
      adapters/                    # infrastructure; implement ports
        db/
          engine.py                # async engine (asyncpg), session factory, write lock
          orm.py                   # SQLAlchemy 2.0 mapped classes
          mappers.py               # ORM ↔ domain
          repositories.py          # booking core: patients, doctors, slots, closures, appointments
          record_repositories.py   # follow-ups, verify attempts, callbacks, chat summaries, transcripts
          staff_repositories.py    # staff users, sessions, consultations, clinic docs → ports.staff
          browser.py               # SqlTableBrowser (admin table view) → ports.staff
          uow.py                   # SqlUnitOfWork(Factory) → ports.unit_of_work
        llm/
          litellm_client.py        # LiteLLMStructuredLLM → ports.llm
          retry.py                 # RetryingLLM decorator (429 backoff)
          pipecat_factory.py       # PipecatLLMFactory: role → Pipecat LLM service
          stt_factory.py           # GeminiSTTFactory: speech-to-text for voice input (§10.1)
        embeddings/                # FastEmbedEmbedder, LiteLLMEmbedder (openai, gemini) → ports.embeddings
        vector/
          pgvector_store.py        # PgVectorStore (doc_chunks, doc_index_state) → ports.vector_store
          build_index.py           # chunking, PgDocIndexer → ports.vector_store.DocIndexer
        health/
          medlineplus.py           # MedlinePlusProvider → ports.health_info
          cached.py                # CachedHealthInfo decorator (LRU + disk)
        clock.py                   # SystemClock, FrozenClock → ports.clock
        messages.py                # JsonMessageCatalog → ports.messages
      conversation/                # Pipecat Flows layer; depends on services
        state.py                   # FlowState (§4.2)
        result.py                  # ToolResult, UIPayload (discriminated union)
        registry.py                # FunctionRegistry + @llm_function decorator, HandlerContext
        io.py                      # ConversationIO: say / ui, implemented by the pipeline layer
        views.py                   # domain objects → LLM-facing data and UI payloads
        functions/                 # thin handlers grouped by concern
          identity.py  doctors.py  scheduling.py  booking.py  faq.py  safety.py
        nodes/
          base.py                  # BaseNode (template method → Flows NodeConfig)
          greet.py verify.py router.py pre_talk.py suggest_doctor.py pick_slot.py
          confirm.py booked.py cancel.py faq_only.py handoff.py
          factory.py               # NodeFactory
          catalog.py               # standard_nodes() → NodeFactory with every node
        prompts/                   # PromptLibrary (__init__.py); role.md, text.md, voice.md (voice unused v1)
      pipeline/
        processors/
          guardrail_input.py       # GuardrailInputProcessor
          output_gate.py           # OutputGateProcessor
          ui_emitter.py            # UIEmitterProcessor
          turn_metrics.py          # TurnMetricsObserver (latency spans)
        builder.py                 # PipelineBuilder
        session.py                 # ChatSession: per-connection lifecycle
        speech.py                  # SpeechSession: /stt mic audio → transcript (§10.1)
      api/
        app.py                     # create_app(container)
        routes.py                  # /ws, /stt, /healthz, /config/demo
        staff/                     # /staff HTTP API for the portal (§17.5): auth, doctor, admin
      seed/
        seeder.py                  # Seeder (relative to Clock)
        demo_data.py               # synthetic doctors and patients (pure data)
    data/
      docs/                        # clinic_info.md, insurance.md, services.md, prep_sheets.md,
                                   # specialty_guide.md, intake/*.md
      messages.en.json             # every patient-facing fixed string
    eval/
      red_flags.dev.jsonl          # ~60, frozen before patterns.py exists
      red_flags.holdout.jsonl      # 20, written after
      run_red_flag_eval.py
      measure_latency.py           # latency budgets (§16.7)
    tests/
      fakes/                       # InMemory*Repo, ScriptedLLMService, FakeStructuredLLM, fake STT
      unit/                        # domain + services against fakes
      contract/                    # same repo test suite against Sql*Repo; concurrency test
      integration/                 # real server over WebSocket/HTTP with scripted LLMs
  web/
    src/
      transport/chatClient.ts      # RTVI client wrapper
      transport/speechClient.ts    # /stt voice input client (transport/ is the only SDK user)
      voice/                       # useVoiceInput, useSpeaker, voice draft helpers
      lib/micCapture.ts            # mic → 16 kHz PCM (AudioWorklet)
      lib/speaker.ts               # browser read-aloud, saved volume/mute
      state/chatReducer.ts         # useReducer state machine for messages + ui blocks
      ui/registry.ts               # ui.type → component map
      ui/types.ts                  # discriminated union mirroring conversation/result.py
      components/                  # Bubble, MenuOptions, QuickReplies, SlotChips, DoctorCard,
                                   # AppointmentButtons, ConfirmationCard, HandoffCard, DemoNotice,
                                   # MicButton, VolumeControl
  admin/                           # staff portal (§17.6): React + Vite, separate Vercel project
    src/api/client.ts              # the only module that calls fetch
  docker/postgres/init-test-db.sql # creates clinic_test on first start of the db volume
  Dockerfile                       # bakes in the embedding model and MedlinePlus cache
  docker-compose.yml               # db, backend, web, admin
  render.yaml
  README.md
  CLAUDE.md
  SPEC.md
```

---

## 3. Configuration and provider abstraction

All behaviour that may change between the free demo and a paid deployment is env-driven. No provider names appear outside `config.py`, `adapters/llm/` and `adapters/embeddings/`.

| Variable | Default (demo) | Notes |
|---|---|---|
| `LLM_PROVIDER` | `google` | `google` \| `openai` \| `anthropic`; default for every role |
| `MAIN_MODEL` | a Gemini Flash model | Conversation + function calling. Check the current free-tier model names at build time |
| `CLASSIFIER_MODEL` | a Gemini Flash-Lite model | Separate quota bucket from main |
| `MAPPER_MODEL` | same as main | Specialty mapping |
| `SUMMARY_MODEL` | same as classifier | End-of-chat summary (§9.2); off the turn path |
| `<ROLE>_PROVIDER` | `LLM_PROVIDER` | Per-role override, e.g. `CLASSIFIER_PROVIDER=openai` |
| `<ROLE>_TEMPERATURE` | main 0.3, classifier 0, mapper 0, summary 0.2 | |
| `<ROLE>_MAX_TOKENS` | main 300, classifier 150, mapper 150, summary 250 | |
| `GOOGLE_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | | Only the active ones are required |
| `EMBED_BACKEND` | `fastembed` | `fastembed` \| `openai` \| `gemini`; the index stamp records backend + model, so a change rebuilds it |
| `EMBED_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | e.g. `gemini-embedding-001` with `gemini` |
| `FAQ_THRESHOLD` / `CHECKLIST_THRESHOLD` | per backend (§7) | Override the RAG cut-offs; leave unset to use the measured defaults |
| `CLINIC_NOW` | unset | ISO datetime with +05:30; freezes the clock |
| `CLASSIFIER_TIMEOUT_S` | 4 | Timeout → regex verdict stands |
| `MAX_INPUT_CHARS` | 500 | Longer input truncated with a notice |
| `ALLOWED_ORIGINS` | `http://localhost:5173`, `http://127.0.0.1:5173` | Comma-separated or JSON list; the Vercel domain is set by env. Checked on the `/ws` and `/stt` upgrade and allowed through CORS (with `STAFF_ORIGINS`). An empty list turns the check off |
| `DATABASE_URL` | `postgresql+asyncpg://clinic:clinic@localhost:5432/clinic` | `postgres://` / `postgresql://` and `sslmode=` (as hosts hand them out) are rewritten for asyncpg. The server must offer the pgvector extension; the app runs `CREATE EXTENSION IF NOT EXISTS vector` on start |
| `RESEED_ON_START` | `false` | `true` drops and reloads demo data on every start |
| `TEST_DATABASE_URL` | `…/clinic_test` | Tests and `measure_latency.py` only; reseeded freely |
| `HEALTH_CACHE_DIR` | `server/.cache/medlineplus` | MedlinePlus disk cache; the Docker image sets `/app/cache/medlineplus` |
| `DATA_DIR` | `server/data` | Clinic docs and `messages.en.json` |
| `LOG_LEVEL` | `INFO` | |
| `STAFF_ORIGINS` | `http://localhost:5174`, `http://127.0.0.1:5174` | Staff portal origins allowed through CORS (§17.1) |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | unset | First admin, created on startup if no account has that email; never overwrites |
| `ADMIN_NAME` | `Clinic admin` | Name of that admin |
| `STAFF_SESSION_HOURS` | 12 | Staff login lifetime |
| `STT_MODEL` | a Gemini Live transcription model | Voice input (§10.1); uses `GOOGLE_API_KEY` whatever `LLM_PROVIDER` is |
| `STT_MAX_SECONDS` | 60 | A `/stt` connection is closed after this long |

`adapters/llm/pipecat_factory.py` maps `(provider, model)` to the Pipecat service class (`GoogleLLMService`, `OpenAILLMService`, `AnthropicLLMService`) through a registry dict, not an if-chain. `adapters/llm/litellm_client.py` implements the `StructuredLLM` port for out-of-pipeline calls (classifier, mapper, summaries) with JSON/enum output, wrapped by `RetryingLLM`. Adding a provider means one registry entry in the factory; no other file changes.

---

## 4. Conversation flow (Pipecat Flows)

### 4.1 Global functions (on every node except terminal ones)

| Function | Behaviour |
|---|---|
| `answer_faq(question)` | RAG (§7) or the doctor directory for doctor/fee questions (fees included only when the question is about cost); node unchanged. Prompt: answer, then restate where the flow was ("Shall we continue with the 6:15 slot with Dr. Rao?") |
| `request_human(reason)` | Creates a callback ticket, transition to `handoff` |

### 4.2 Flow state

```python
@dataclass(slots=True)
class FlowState:
    session_id: str
    verified_patient_id: int | None = None
    patient: PatientInfo | None = None     # (name, age, sex); age from DOB
    initial_intent: Intent | None = None   # book | cancel | faq
    initial_message: str | None = None     # carried into pre_talk
    verify_failures: int = 0
    intake: IntakeSummary | None = None    # §4.5
    checklist: Checklist | None = None     # retrieved for pre_talk
    specialty_hint: Specialty | None = None
    listed_doctor_ids: list[int] = field(default_factory=list)
    selected_doctor_id: int | None = None
    offered_slots: dict[int, int] = field(default_factory=dict)   # slot_id → doctor_id
    selected_slot_id: int | None = None
    last_day: str | None = None            # last day token and time_pref asked for
    last_time_pref: TimePref = TimePref.ANY
    followup_grant_id: int | None = None
    same_issue: bool | None = None
    quote: Quote | None = None             # doctor, slot, visit type, fee for the read-back
    offered_appointments: dict[int, str] = field(default_factory=dict)  # id → label (cancel)
    selected_appointment_id: int | None = None
    notice: str | None = None              # one-shot hint for the next node: booked | slot_taken | cancelled
    notice_data: dict[str, str] = field(default_factory=dict)
    handoff_ticket: str | None = None
    entry_ui: UIPayload | None = None      # shown when the next node becomes active
    verdict: asyncio.Future[Verdict] | None = None  # current turn's guardrail verdict
    current_node: str = "greet"
    turns: list[dict[str, str]] = field(default_factory=list)            # last 40, for transcript + summary
    guardrail_events: list[dict[str, str]] = field(default_factory=list)
```

`offered_slot_ids` is a property over `offered_slots`. `reset_booking()` clears the booking fields after a booking or cancellation.

### 4.3 Nodes

```
greet                 fixed greeting + `menu` (book / cancel / FAQ); route_intent(intent, complaint?) stores initial_intent + initial_message
 ├─ book / cancel → verify
 └─ faq → faq_only
verify                verify_patient(phone, dob) | register_patient(name, phone, dob, sex) for new patients
 ├─ ok → by initial_intent: book → pre_talk (complaint prefilled) | cancel → cancel_list | none → router
 ├─ fail (generic msg); 3 in session → handoff
 └─ LOCKED → handoff
router                "How can I help?" → pre_talk | cancel_list | faq_only
pre_talk              acknowledge complaint if prefilled; ≤3 checklist follow-ups; submit_intake(...)
 └─ → suggest_doctor
suggest_doctor        on entry (server-side): map_specialty; doctor cards for the hinted specialty,
                      their ids added to listed_doctor_ids; the bot proposes one
                      patient names a doctor → list_doctors(name=...) (adds to listed_doctor_ids); mismatch rule (§4.6)
                      choose_doctor(doctor_id) (must be in listed_doctor_ids)
                      check_followup(); no grant → pick_slot
                      grant found → ask "same issue as last visit?" → set_same_issue(bool) → pick_slot
pick_slot             ask day + morning/evening → get_free_slots(day, time_pref)
                      select_slot(slot_id) (must be in offered_slot_ids)
 ├─ NO_SLOTS → find_alternatives() → patient picks
 └─ → confirm
confirm               fixed read-back template from state + visit type from tool (no fee amount)
                      quick replies: Confirm | Change time | Change doctor
 ├─ confirm_booking() ok → booked
 ├─ SLOT_TAKEN → pick_slot (re-fetch, with a "slot just taken" note)
 ├─ DUPLICATE_SAME_DAY | OVERLAP | CAP_REACHED → explain, offer to cancel one; yes → route_intent(cancel) → cancel_list
 └─ change_time() → pick_slot | change_doctor() → suggest_doctor
booked                RESET_WITH_SUMMARY on entry; confirmation card + prep instructions for the specialty,
                      "anything else?"; then acts as the router (route_intent, reschedule_appointment)
cancel_list           on entry: loads upcoming appointments → buttons; select_appointment(id) → cancel_confirm
cancel_confirm        cancel_appointment(appointment_id) → router (RESET_WITH_SUMMARY, "cancelled" note)
                      CUTOFF_VIOLATION → explain 2h rule, offer handoff
faq_only              loop; after each answer offer booking → verify
handoff               terminal: desk number, ticket id
```

Reschedule: `reschedule_appointment` returns `NOT_IMPLEMENTED`; prompt tells the patient it can cancel the old one and book a new one.

### 4.4 Node prompt rules

- `task_messages` state what to collect, which functions to call, and "if the patient asks an unrelated clinic question, call `answer_faq`, then return to this step."
- Never state a fee, timing, date or availability except from a tool result in this turn's context.
- Two to three short sentences. No markdown (widget also strips it).
- Always reply in English. If the patient writes in Hindi, Kannada or a mix, understand it and reply in English.
- Patient-facing fixed strings come from `messages.en.json`. Flow and tool code contain no literal patient strings.
- Never mention internal ids, function names or error codes.

### 4.5 Pre-talk

1. Chief complaint (prefilled from `initial_message` when present; bot acknowledges it instead of asking again).
2. Retrieve the matching checklist from the vector store (`kind=intake`). Below the checklist cut-off (§7) → `intake/general.md` (duration, severity 1–10, new or recurring).

   Each `intake/*.md` file uses the same structure so it chunks and parses predictably:

   ```markdown
   # <symptom>              e.g. Fever, Skin rash, Joint pain
   ## Matches               comma-separated phrasings and synonyms (helps retrieval)
   ## Questions             ordered list, most useful first; the bot asks at most 3
   ## Red flags             symptoms to ask about; positive or ambiguous answers go through §6.3
   ## Likely specialty      hint for the mapper (§4.6), not binding
   ```

   v1 ships 6 checklists: fever, cough/cold, skin, joint/back pain, ear/nose/throat, and `general.md`.
3. Ask at most 3 follow-ups. Checklist questions about red-flag symptoms are allowed; negated answers are handled by §6.3, not by avoiding the questions.
4. `submit_intake` with a strict schema:

```json
{"chief_complaint": "str", "duration": "str|null", "severity": "int 1-10|null",
 "answers": [{"q": "str", "a": "str"}], "red_flags_checked": ["str"]}
```

Diagnosis requests ("what do I have?") → fixed "I can't diagnose, but I can help you see the right doctor", stay in pre_talk.

### 4.6 Specialty mapping

- Server-side call on entering `suggest_doctor`: `map_specialty(intake, age, sex)` via `MAPPER_MODEL` with `specialty_guide.md` in context, output constrained to the enum of seeded specialties.
- Age and sex are soft hints in the prompt. One code rule: `paediatrics` with age ≥ 18 becomes `general_medicine`. No hard block on gynaecology; the bot says the doctor can refer onward.
- Ambiguous or multi-system → `general_medicine` + "the doctor can refer you onward".
- Mapping always runs on entry. A patient who names a doctor gets `list_doctors(name=...)`; the hint is then used only for the mismatch note: if that doctor's specialty doesn't match the hint, say so once, offer both, patient decides.
- Name lookup is fuzzy; more than one match → doctor cards to pick from.

### 4.7 Follow-up foundation

- `followup_grants(patient_id, doctor_id, source_appointment_id, valid_until, created_by)`. Doctors create these from the staff portal by ticking follow-up on a consultation (§17.2). The seed adds one grant for the demo.
- `check_followup()` uses `selected_doctor_id` from state; returns an active grant (`valid_until >= today`) or none.
- If a grant exists the bot asks whether this visit is about the same issue; `set_same_issue(bool)`.
- `confirm_booking` sets `visit_type=followup` and `followup_fee` only if an active grant exists and `same_issue` is true. Otherwise `new` and `fee`. Grant marked used on booking.

---

## 5. Tools

The "tools" below are LLM-facing functions registered in `FunctionRegistry` (§16.4). Each is a thin handler in `conversation/functions/` that validates args with a pydantic model, reads ids from `FlowState`, calls one service method, and returns a `ToolResult` (`{ok, data | error_code, ui?}`). Business rules live in `domain/policies.py` and services, never in handlers. The LLM-facing schemas never include `patient_id`; handlers read it from `state.verified_patient_id`.

| Tool (LLM-facing args) | Behaviour | Errors | UI |
|---|---|---|---|
| `route_intent(intent, complaint?)` | Store in state | | |
| `verify_patient(phone, dob)` | §8 | `BAD_PHONE`, `BAD_DOB`, `NO_MATCH` (generic), `LOCKED` | |
| `register_patient(name, phone, dob, sex)` | §8; creates the patient and signs them in | `BAD_NAME`, `BAD_PHONE`, `BAD_DOB`, `NO_MATCH` (phone on file, details differ), `LOCKED` | |
| `list_doctors(specialty? , name?)` | Returns id, name, specialty, days, hours (no fees); stores `listed_doctor_ids` | `NO_DOCTORS` | `doctor_cards` |
| `choose_doctor(doctor_id)` | Must be in `listed_doctor_ids` | `INVALID_CHOICE` | |
| `check_followup()` | §4.7 | | |
| `set_same_issue(same: bool)` | | | |
| `submit_intake(...)` | Validates schema, stores | `INVALID` | |
| `get_free_slots(day, time_pref)` | §5.1; uses `selected_doctor_id`; ≤3 slots; stores `offered_slot_ids` | `NO_SLOTS`, `BAD_DAY`, `CLOSED` | `slot_buttons` |
| `find_alternatives()` | Same doctor next 2 available days + same-specialty doctors on the requested day | `NONE` | `slot_buttons` |
| `select_slot(slot_id)` | Must be in `offered_slot_ids` | `INVALID_CHOICE` | `quick_replies` (confirm) |
| `confirm_booking()` | Reads everything from state; checks verification, duplicates, cap, overlap, slot unique; computes fee + visit type; idempotent on `(session_id, slot_id)` | `NOT_VERIFIED`, `SLOT_TAKEN`, `DUPLICATE_SAME_DAY`, `OVERLAP`, `CAP_REACHED` | `confirmation_card` |
| `change_time()` | Clears the selected slot → `pick_slot` | | |
| `change_doctor()` | Clears doctor, slot and follow-up choice → `suggest_doctor` | | |
| `list_appointments()` | Upcoming, booked only; stores `offered_appointments` | | `appointment_buttons` |
| `select_appointment(appointment_id)` | Must be in `offered_appointments` → `cancel_confirm` | `INVALID_CHOICE` | |
| `cancel_appointment(appointment_id)` | Must be the selected appointment; owner check, 2h cutoff | `INVALID_CHOICE`, `NOT_OWNER`, `CUTOFF_VIOLATION` | |
| `reschedule_appointment(...)` | Stub | `NOT_IMPLEMENTED` | |
| `answer_faq(question)` | §7 | `NO_MATCH` | |
| `request_human(reason)` | Callback ticket; summary built server-side from state + last turns | | `handoff_card` |

Server-side only (not LLM-callable): `map_specialty`, classifier, callback summary builder.

Any function called while this turn's verdict is `MEDICATION` or `OFF_TOPIC` returns `BLOCKED` with no side effect (§6.1).

Invariants enforced in code:
- No patient data read or written before `verify_patient` or `register_patient` succeeds (registration writes only the new `patients` row).
- In the chatbot, `confirm_booking` and `cancel_appointment` are the only writes to `appointments`. The staff portal changes only an appointment's status and intake details (§17.2).
- Fees come only from the `doctors` table.
- The LLM cannot pass an id that wasn't offered in this session.

### 5.1 Date resolution

- `day` accepts: `today`, `tomorrow`, `day_after_tomorrow`, a weekday name (next occurrence; today counts if slots remain), `YYYY-MM-DD`, `next_available`.
- Resolved in Asia/Kolkata from `clock.now()`. Window: next 7 days; beyond → `BAD_DAY` with the allowed range.
- `time_pref`: `morning` (before 13:00), `evening` (16:00 onwards), `any`.
- Drops slots starting within 30 minutes of now. Checks `closures` table → `CLOSED` with the reason.
- Result includes `resolved_date` and a label like `Tue 7 Oct` so the bot reads back the real date.

---

## 6. Guardrails

### 6.1 Per-turn pipeline

1. **Input cap**: a longer message is truncated to `MAX_INPUT_CHARS` and the fixed `input_truncated` notice is shown; the truncated text goes on through the checks below.
2. **Layer 1 regex** (sync, `GuardrailInput`), in priority order: self-harm → emergency → medication → off-topic (code requests). Emergency and self-harm matches emit the soft note (§6.3, §6.4) and the message carries on to the LLM; the message is then re-checked for medication and off-topic only. Medication and off-topic matches bypass the LLM and emit their fixed reply.
3. **Layer 2 classifier** (async, started in parallel with the main LLM). One call returns one label: `EMERGENCY | SELF_HARM | MEDICATION | OFF_TOPIC | NONE` + one-line reason. It sees the patient's message and the bot's previous message (so a short answer like "yes" is read in context). Uses the authored red-flag list; multilingual by nature. Runs on every turn in every non-terminal node. The one exception is a button click: when the message is exactly the text of a button the server offered and that is still live (sent since the patient's last message, as the widget shows it), Layer 2 is skipped and the verdict is `NONE` with source `button`. That text is server-written (menu options, quick replies, doctor cards, slot and appointment buttons), so classifying it only spends rate limit. Layer 1 still runs on it, a typed message matching a retired button is classified as usual, and a browser flag is never trusted for this (owner decision, Oct 2026).
4. **OutputGate** holds the main LLM's bot text frames until the verdict resolves. Function handlers `await state.verdict` before any side effect. The classifier usually returns before the main model's first token, so the added latency is close to zero.
5. Verdict `NONE`, `EMERGENCY` or `SELF_HARM` → release (the soft note, §6.3 and §6.4, is already out). `MEDICATION` or `OFF_TOPIC` → drop held output, cancel the in-flight LLM response, keep the dropped text out of context, emit the fixed reply; the node does not change.
6. Classifier timeout, error or 429 after one retry → treat as `NONE` (Layer 1 already ran), log it.

### 6.2 Layer 1 patterns

English: chest pain/tightness/pressure; can't/difficulty/trouble breathing; unconscious/fainted/passed out/not responding; heavy/uncontrolled bleeding; stroke signs (face droop, slurred speech, one side weak); seizure/fits; severe allergic reaction/throat swelling; poisoning/overdose; severe burn; snake bite.

Romanised Hindi/Kannada (~15): e.g. "seene mein dard", "chhati mein dard", "saans nahi aa rahi", "saans lene mein taklif", "behosh", "khoon band nahi ho raha", "dora pad raha", "edhe novu", "usiru kattide", "prajne illa". Final list authored in `patterns.py` and covered by the `code_mixed` eval category.

Self-harm: suicidal and self-harm phrasing in English and romanised Hindi.

Medication: dose/dosage/mg/tablet(s)/how many, can I take, should I take/stop, with food, side effect, interaction, used for (with a drug-like token), prescribe, plus common Indian brand names (Dolo, Crocin, Calpol, Combiflam, Pan-D, etc.).

Off-topic: write/generate/debug code, programming languages, essays, poems, jokes. Everything else off-topic is the classifier's job.

No negation handling in regex by design. A false positive costs only one soft note (§6.3).

### 6.3 Emergency: soft note, chat carries on

On `EMERGENCY` (either layer), every time:
1. Emit the fixed `emergency.note` as its own bot message: "If this is an emergency, please call 108 or 112, or go to the nearest hospital."
2. No node change, no banner, no check question; the bot's normal reply follows. Function handlers go ahead (the verdict does not block).
3. Layer 1 hit: the note is sent, then the message is re-checked for medication and off-topic only (a medicine question is still refused), and otherwise goes to the LLM as usual. Layer 2 hit: the note is sent before the turn's verdict resolves, so it always appears ahead of the held reply. If Layer 1 already showed the same note this turn, Layer 2 does not repeat it.
4. The role prompt tells the model not to repeat or dwell on the note.

### 6.4 Self-harm

Same mechanics as §6.3 with the fixed `self_harm.note`: "If you're having thoughts of harming yourself, you don't have to face it alone. Tele-MANAS is free and open 24x7 at 14416, or call 112 if you are in immediate danger." Shown every time; the chat carries on.

### 6.5 Medication: complete refusal

Any medication question gets the fixed refusal + booking offer, from any node, no exceptions:

> I'm not able to give any advice about medicines, including doses, timing or what a medicine is for. A doctor can help with that. Would you like me to book a consultation?

No API call, no RAG, no partial answer. Prep questions that involve medication ("should I take my tablets before the fasting test?") are refused too. `prep_sheets.md` contains no medication guidance.

### 6.6 Off-topic and non-English

- Off-topic → fixed: "I can help with appointments and questions about City Care Clinic." Node unchanged.
- Non-English input is not a guardrail case; LLM replies in English (§4.4).

---

## 7. RAG and health info

- Corpus: `clinic_info.md`, `insurance.md`, `services.md`, `prep_sheets.md`, `specialty_guide.md`, `intake/*.md`. One chunk per `# ` section of each document; each `intake/*.md` file is one chunk. Metadata `{doc, section, kind: faq|specialty|intake|prep}`.
- Embeddings: fastembed `all-MiniLM-L6-v2`, stored with pgvector in the app's PostgreSQL (`doc_chunks`, §9). Exact cosine search (`<=>`), filtered on `kind` in the query; a few dozen chunks need no ANN index, and an unsized `vector` column fits any embedding model. At startup the backend enables the `vector` extension and creates the tables if missing, then rebuilds the index if it is empty or if the stored stamp (embedding backend and model + digest of the documents, `doc_index_state`) differs, for example after a `clinic_docs` edit (§17.3) or a model change; again after each admin save. A rebuild swaps every chunk in one transaction, so queries see the old set until it commits.
- Cut-offs (top-1 cosine) depend on the embedding model, because models score differently: Gemini rates unrelated text around 0.55 to 0.67, MiniLM around 0.1 to 0.5. Defaults in `config.py`, as (FAQ, checklist): fastembed MiniLM (0.35, 0.35), Gemini `gemini-embedding-001` (0.60, 0.60), OpenAI (0.35, 0.35, untuned). Measured with `eval/tune_rag_threshold.py` on `eval/rag_threshold.jsonl` (26 questions the docs answer, 16 clinic-style questions they don't, 18 complaints): MiniLM at 0.35 answers 25/26 and rejects 9/16; Gemini at 0.60 answers 26/26 and rejects 6/16; both pick the right checklist 18/18. Gemini's scores overlap (answerable 0.60 to 0.83, unanswerable 0.54 to 0.67), so its cut-off favours never refusing a question the docs answer: a false match only hands the LLM clinic passages it must answer from, while a false refusal tells the patient the clinic doesn't know its own opening hours. Separate retrieval task types (`RETRIEVAL_DOCUMENT` / `RETRIEVAL_QUERY`) were tried and did not separate the two groups better. `FAQ_THRESHOLD` / `CHECKLIST_THRESHOLD` override them. Gemini embeddings (`EMBED_BACKEND=gemini`, `EMBED_MODEL=gemini-embedding-001`) are supported: hosted calls go in batches of at most 100 texts (Gemini's batch limit). On the free tier Gemini allows 100 embedded texts per minute per model, and every text counts: an index rebuild is one per chunk (57 today), plus one per FAQ question and one per checklist lookup. If a rebuild is rate limited at startup, the server starts with the index it has and logs `index_sync_failed`; the next start or admin save rebuilds it.
- `answer_faq`: top-3 chunks with `kind in (faq, prep)` at or above the FAQ cut-off; below → `NO_MATCH` → fixed "I don't have that information. The front desk can help at ..." + handoff offer. LLM answers only from returned chunks.
- Doctor, day and fee questions go to the doctor directory inside `answer_faq`, never RAG. Fees are included only when the question is about cost. `clinic_info.md` holds doctor bios only, no fees or days.
- General health (what is an HbA1c test, what is thyroid): MedlinePlus health-topics free-text search, top result summary trimmed to 2–3 sentences + source link. Responses cached on disk by normalised query; demo queries pre-warmed in the image. Medication questions never reach this path (§6.5).
- Routing inside `answer_faq` (in `FaqService`, not the LLM): doctor/fee questions → doctor directory. Otherwise query clinic chunks. If the top score is at or above threshold, answer from clinic docs. If not, and the question looks like a general health-topic question (a test, condition or procedure name, checked with a small keyword list), try MedlinePlus, but only when this turn's classifier verdict actually resolved to `NONE` (not the timeout default) and no Layer 1 pattern matches the question. If neither returns anything, `NO_MATCH`. The LLM only passes `question`; it never picks the source.
- The answer prompt says: use only the returned text; if it doesn't answer the question, say you don't know and offer the front desk.

---

## 8. Identity and verification

- Phone normalised: strip every non-digit, drop a leading `91` (12 digits) or `0` (11 digits), must be 10 digits starting 6–9.
- DOB: ISO `YYYY-MM-DD`, otherwise parsed day-first (`dateparser`, `DATE_ORDER=DMY`): accepts `05/06/1990`, `5 June 1990`, `5-6-90`. Future dates and years before 1900 are rejected. DOB is never read back.
- Unparseable input (`BAD_PHONE`, `BAD_DOB`, `BAD_NAME`) is not logged as an attempt and counts toward neither limit; the bot asks again.
- Wrong phone and wrong DOB return the same message: "Those details don't match our records."
- `verify_attempts(phone_norm, ts, success)` logged for every parsed attempt, whether or not the phone exists. 5 failures for a phone in 15 minutes → `LOCKED` for 15 minutes → "Please call the front desk" + handoff. Only failures after the latest success count.
- 3 failures in one session → handoff.
- Unknown patient: after failure the message offers registration in the chat.
- Registration (`register_patient`): name is letters/marks in any script plus space . ' -, 2 to 80 chars (`BAD_NAME` otherwise); phone and DOB parse as above; sex is female, male or other. A new phone creates the patient (no verify attempt logged). A phone already on file is treated as a verification: name (case- and space-insensitive), phone and DOB must all match, the attempt is logged, and a mismatch returns the generic `NO_MATCH` and counts toward the lockout and the 3-per-session handoff. The lockout is checked before either path.

---

## 9. Data model (PostgreSQL, SQLAlchemy)

```
patients         (id, name, phone UNIQUE, dob, sex, created_at)
doctors          (id, name, specialty, bio, consulting_days, hours, fee, followup_fee)
slots            (id, doctor_id, start, end, UNIQUE(doctor_id, start))
closures         (id, date UNIQUE, reason)
appointments     (id, patient_id, doctor_id, slot_id, visit_type: new|followup, fee,
                  status: booked|cancelled|completed|no_show, intake_summary JSON, session_id,
                  followup_grant_id NULL, created_at, cancelled_at)
                  partial UNIQUE(slot_id) WHERE status='booked'
                  partial UNIQUE(session_id, slot_id) WHERE status='booked'   -- idempotency
followup_grants  (id, patient_id, doctor_id, source_appointment_id NULL, valid_until,
                  created_by, used_appointment_id NULL)
verify_attempts  (id, phone_norm, ts, success)
transcripts      (id, session_id, patient_id NULL, turns JSON, guardrail_events JSON, created_at)
callbacks        (id, patient_id NULL, reason, summary, priority, created_at)
chat_summaries   (id, patient_id, session_id, summary, created_at)   -- one per verified chat

-- RAG index (pgvector; outside the ORM models, so reseed and the table browser skip it)
doc_chunks       (id TEXT PK, doc, section, kind, text, embedding VECTOR)
doc_index_state  (id = 1, stamp)   -- embedding backend:model + digest of the indexed documents
```

Staff portal tables (`staff_users`, `staff_sessions`, `consultations`, `clinic_docs`) are in §17.4. `clinic_docs` is seeded from `data/docs` when empty, like the demo data.

### 9.1 Seed (relative to `clock.now()`)

On startup `Seeder.ensure_seeded()` creates missing tables and fills the database only if it has no patients. On a database that is already seeded it only tops up slots, so the 7-day booking window keeps moving forward (`INSERT … ON CONFLICT DO NOTHING`; existing slots and bookings are untouched). `make reseed` (or `RESEED_ON_START=true`, which tests use) drops every table and starts from the demo data below. Tables are created with `create_all`; there are no migrations in v1, so a schema change needs `make reseed`.


- 8 doctors: general medicine (2), dermatology, orthopaedics, paediatrics, gynaecology, ENT, plus one more general medicine named "Dr. Rao" vs "Dr. Rao S" for the fuzzy-name case.
- 15-minute slots for the next 7 days, morning/evening per doctor's days. Some slots pre-booked so availability looks real.
- One closure day within the window.
- 6 synthetic patients with sex and DOB; one under 18.
- 2 patients with past appointments; one active follow-up grant with Dr. Rao.
- One booked appointment at now + 60 min (cutoff demo).
- One patient already at 2 upcoming appointments (cap demo is one booking away).
- `/config/demo` exposes 3 test patients' phone + DOB for the widget.

### 9.2 Chat summaries

When the WebSocket closes, `ChatSession` hands the transcript record to `ChatSummaryService` as well as `TranscriptWriter`. Only chats where `verify_patient` or `register_patient` succeeded are summarised; the rest are skipped. A background task sends the kept turns (last 40) to `SUMMARY_MODEL` with a fixed prompt (3 to 5 plain sentences: reason, symptoms shared, what was booked or cancelled, questions answered, anything open; no phone or DOB) and writes one `chat_summaries` row. The call retries twice on a rate limit (20s, then 40s). If the model is still unavailable, a fallback row is written (a note pointing at the transcript's session id plus the last three bot replies, never patient text). Nothing on the turn path waits for it. On shutdown, in-flight summaries get 10s before they are dropped. Rows persist across restarts (§1 Data); `make reseed` clears them.

---

## 10. Widget (React + Vite, Vercel)

- `@pipecat-ai/client-js` + `client-react` with WebSocket transport. Text sent via RTVI send-text. Pings `/healthz` on load and shows "Waking up the demo server..." until it answers (Render cold start). If it never answers or the connection fails, an error line with a "try again" link replaces it.
- Header notice: "Demo with synthetic data. Do not enter real health information." Collapsible "Try it" panel with test patients from `/config/demo`.
- Renders streamed bot text, typing indicator, markdown stripped.
- UI payloads arrive as RTVI server messages. They are queued and rendered after the bot text of the same turn finishes, so cards never appear before the sentence that introduces them. If no bot text arrives within 1.2 s, the queued blocks render anyway.
- When a newer bot message arrives, all earlier interactive blocks disable. Interactive blocks and the message box are also disabled while the chat is not ready.
- A `handoff_card` ends the chat: the message box is replaced by a "Start new chat" button.

| `ui.type` | Render | Click sends |
|---|---|---|
| `quick_replies` | ≤3 buttons | button label |
| `menu` | ≤4 stacked full-width options under the greeting (Book an appointment, Cancel an appointment, FAQ) | the option's text, e.g. `I want to book an appointment` |
| `doctor_cards` | name, specialty, days and hours, "Choose" | `I'd like to see Dr. X` |
| `slot_buttons` | chips grouped by date and doctor under a date header, label `6:15 PM`; the doctor's name is shown when the slots span more than one doctor | `Tue 7 Oct, 6:15 PM` |
| `appointment_buttons` | upcoming list | `Cancel my appointment with Dr. X on Tue 7 Oct at 6:15 PM` |
| `confirmation_card` | appointment reference (`A-00012`), doctor, specialty, date, time, visit type | none |
| `handoff_card` | desk number, ticket id | none |

Clicks are plain user text so the path is identical whether typed or tapped.

### 10.1 Voice input and read-aloud

- **Mic button** beside Send. The first press asks the browser for microphone permission. If it is refused, or there is no mic or no support, a one-line note under the box says so and typing still works.
- While listening, the widget streams 16 kHz mono PCM as Pipecat protobuf audio frames to `/stt`, a separate WebSocket opened per press (origin-checked like `/ws`, closed after `STT_MAX_SECONDS`). The server pipeline is `transport → SpeechControl → STT → TranscriptRelay → transport`; it has no LLM, no RTVI and no database access.
- The server sends `{"type": "transcript", "text", "final"}` messages. Interim text replaces the live part of the box; final phrases are kept. Text typed before pressing the mic is kept in front. The box is read-only while listening.
- Pressing the mic again stops the mic. If words are still pending (not final), the widget sends `{"type": "speech-end"}`, the STT finalizes the last phrase, and the widget waits at most 2.5 s for it before closing; otherwise it closes at once. Listening stops by itself after 60 s. Pressing Enter sends what is in the box at once and drops any late words.
- If the STT fails, the server sends `{"type": "speech-error"}`; the widget closes the socket and shows a one-line "voice input isn't available right now" note. Typing still works.
- **Nothing is sent automatically.** The patient reviews the text and presses Enter; it then goes over `/ws` as ordinary send-text, through Layer 1, Layer 2 and the OutputGate. Transcripts are never logged.
- **Read-aloud**: each new bot reply is spoken by the browser (`speechSynthesis`, an Indian English voice if the device has one). Interactive cards are not read. Browsers block speech until the user has interacted with the page, so the greeting is shown but not spoken. Speech stops when the patient presses the mic or sends a message. A reply that arrives while the patient is speaking is not read aloud.
- **Volume control** top right of the header: a speaker button (mute/unmute) and a slider. Both are saved in the browser's local storage; the default is on at 80%. The control is hidden when the browser has no `speechSynthesis`.

---

## 11. Deployment

- **Backend**: Docker web service on Render (Railway fallback). Image installs deps, downloads the embedding model, pre-warms the MedlinePlus cache (best effort: a network failure at build time skips it and does not fail the image). The blueprint also creates a Render PostgreSQL database and wires `DATABASE_URL` from it; the first start enables pgvector, seeds it and builds the RAG index. Render's free database expires after 30 days, so for a longer-lived demo point `DATABASE_URL` at any other PostgreSQL with the pgvector extension available (Neon, Supabase) instead. Free tier spins down when idle; widget handles the wake-up.
- **Widget**: Vercel static build; `VITE_WS_URL=wss://<render-host>/ws`, `VITE_API_URL`. Voice input uses `wss://<render-host>/stt`, derived from `VITE_WS_URL` (override with `VITE_STT_URL`); the mic needs HTTPS (or localhost).
- **Staff portal**: a second Vercel project with root directory `admin/`; `VITE_API_URL=https://<render-host>`. Its URL goes in `STAFF_ORIGINS` on Render, and `ADMIN_EMAIL` / `ADMIN_PASSWORD` create the first admin.
- WebSocket upgrade rejects origins not in `ALLOWED_ORIGINS`.
- Secrets only in Render env. Nothing provider-specific in the widget.
- Local: `docker compose up` runs `db` (`pgvector/pgvector:pg18`, PostgreSQL 18 with pgvector; `docker/postgres/init-test-db.sql` creates `clinic_test` on the first start of the volume), `backend` on 8000, `web` on 5173 and `admin` on 5174. `make db` starts only the database.

---

## 12. Evaluation

### 12.1 Red-flag eval (required)

- `red_flags.dev.jsonl` (~60): written and committed before `patterns.py` exists; git history shows the order. Items `{text, label: emergency|self_harm|not, category}`.
- Categories: direct, paraphrase, negation ("no chest pain, just cough"), historical ("had chest pain last year"), third-party ("my father isn't breathing properly"), code_mixed (romanised Hindi/Kannada), self_harm, non-emergency symptoms, FAQ questions.
- `red_flags.holdout.jsonl` (20): written after the patterns are done, by a different author (another person or a different LLM with only the category list). Never used to tune patterns.
- `run_red_flag_eval.py` runs Layer 1 only, Layer 2 only, and OR, on dev and holdout separately. Output: recall, precision, FP rate per layer per set, per-category recall, list of misses.
- Target: OR recall ≥ 0.95 on dev. Holdout reported as is. `eval/results.md` holds the full run (Oct 2026: OR recall 1.00 on dev and holdout); CI writes `eval/results.layer1.md` with `--layer1-only`, since Layer 2 needs an API key. README discusses recall/precision, why regex ignores negation, and how §6.3 recovers false positives.
- README also explains why tools, not prompts, carry authorisation: LLM-facing schemas take no `patient_id`, fee or visit type, and ids must come from what was offered this session, so a prompt injection cannot book for another patient or change the price.

### 12.2 Unit tests

- Tools: date resolver (relative days, past slots, closures), duplicate/overlap/cap rules, cutoff, follow-up fee, verification normalisation and lockout, id-not-offered rejection.
- Guardrail patterns: medication refusal and off-topic regex on a small fixed list.
- All with `CLINIC_NOW` frozen.

### 12.3 Golden conversations (not built in v1)

Planned as a stretch, not built: 6 YAML scripts with frozen clock: happy booking, doctor override, no slots → alternative, FAQ detour mid-booking, follow-up grant path, cancel inside cutoff, asserting tool-call sequence and final DB state, not response text. The WebSocket integration tests (§16.10) cover some of these paths (happy booking, follow-up grant, FAQ detour, cancel inside cutoff) with scripted LLM calls instead.

### 12.4 Manual checks logged in README

- Fee asked before verification → tool call or "I don't know", never a guess.
- Two browser tabs pick the same slot → second gets `SLOT_TAKEN` and a re-offer.
- "No chest pain" in pre-talk → soft emergency note, then the normal reply; booking continues.
- Hindi-script complaint → English reply, correct routing.

---

## 13. Build plan (24h) and cut line

| Hour | Work |
|---|---|
| 0–2 | Package skeleton, import-linter contracts, ports, domain (enums, values, entities, errors, policies, DayResolver), container stub. Write and commit `red_flags.dev.jsonl`. Author clinic docs, specialty guide, 6 intake checklists, `messages.en.json` |
| 2–4 | DB adapters + UoW, seeder, services, in-memory fakes, unit + contract tests. fastembed + vector-store adapters and index (Chroma in the 24-hour build, later pgvector) |
| 4–8 | FastAPI per-connection pipeline, LLM factory, Flows nodes for the booking path (greet → booked). Test with a CLI WebSocket client |
| 8–11 | Guardrails: patterns, classifier, GuardrailInput, OutputGate, emergency_check, self_harm, medication, off-topic. `answer_faq` + MedlinePlus |
| 11–14 | Widget: bubbles, chips, confirmation card, emergency soft note, disable-old-buttons, cold-start state |
| 14–16 | Cancel flow, follow-up grant path, alternatives, handoff |
| 16–18 | Holdout set, eval script, results table |
| 18–20 | Deploy to Render + Vercel, smoke test hosted |
| 20–22 | Doctor cards, polish, demo recording |
| 22–24 | README |

Voice input and read-aloud (§10.1) and the staff portal (§17) were added after this 24-hour plan.

**Cut order if behind at hour 16:** doctor cards (fall back to quick replies) → follow-up grant path (keep table and fee logic) → MedlinePlus (clinic docs only) → cancel node (keep tool) → golden conversations.

**Never cut:** booking path, Layer 1 + Layer 2 + OutputGate, emergency check, medication refusal, FAQ detour, red-flag eval with holdout, deployment, README.

---

## 14. Later (document in README, do not build in v1)

- **Staff portal, next steps** (§17 is built): callback queue with status, editing consulting days and hours (slot generation still reads the seed), audit log of staff edits, password reset by email.
- **Abuse controls for a public demo**: per-IP session/message limits, daily token budget kill-switch, access code.
- **Paid model switch**: env change only (§3).
- **Session resume by phone**: persist flow state JSON + node name per patient on each transition. After verification, if a non-terminal saved state under 24 hours old exists, offer "You were booking with Dr. Rao. Continue?" Restore with `FlowManager.set_node(saved_node)` and replay the summary into context.
- **Reschedule**: book new slot first, cancel original only on success; duplicate check excludes the appointment being replaced.
- **Dependants**: `patients.guardian_id`, "for yourself or someone else?", paediatrics keyed on dependant age.
- **Registration OTP**: v1 registers in chat without OTP (§8); add OTP once SMS exists.
- **SMS/WhatsApp confirmation**: notifier interface, Twilio/Gupshup backend.
- **Voice conversation** (beyond §10.1's mic input and browser read-aloud): Daily/Twilio transport, Deepgram STT, Cartesia TTS, `prompts/voice.md` (short replies, no lists, times spelled out as spoken, ≤2 slots read aloud), VAD interruptions; UI frames ignored.
- **Kannada/Hindi replies**: `messages.{kn,hi}.json`, translated docs with `lang` metadata, language stored in state, per-language STT/TTS.
- **Production PHI**: encryption at rest, retention window, audit log per tool call, consent line before pre-talk, no transcript storage without consent, BAA/DPA with the LLM vendor.
- **Golden conversations** (§12.3): YAML scripts asserting tool-call sequence and final DB state.
- **Soft slot holds**: `slot_holds(slot_id, session_id, expires_at)` with 3-minute TTL.

---

## 15. Open risks

- **Pipecat / Flows version churn**: pin exact versions in `pyproject.toml`. Verify against the pinned version: global functions, context strategy names, function handler signature, RTVI send-text handling.
- **OutputGate in Pipecat**: dropping held frames and cancelling an in-flight response without leaving the dropped text in context needs care. Spike this at hour 8 before building the rest of the guardrails. Fallback: gate the main LLM on the verdict (sequential, +300–600 ms).
- **Gemini free tier**: low RPM and daily caps; function-calling reliability on small models in Flows. Mitigation: classifier on a separate model, 429 handling, `MAIN_MODEL` swap by env.
- **LLM forgets to return after `answer_faq`**: explicit instruction in every node; check in manual tests.
- **Render cold start**: first WebSocket connect can fail while waking; widget waits on `/healthz`.
- **Regex false positives**: by design; §6.3 recovers, eval reports them.
- **Model names**: Gemini model ids change; set them in env, never in code.

---

## 16. Code architecture and quality

Target: code an expert reviewer reads as deliberate. Object-oriented where objects own state and invariants, plain functions where they don't. Each pattern below is used because it handles a real point of change in this project. Don't add a pattern unless something actually varies.

### 16.1 Layers and the dependency rule

```
api ──► pipeline ──► conversation ──► services ──► ports ──► domain
                                                     ▲
                              adapters ──────────────┘   (implement ports)
container.py  (composition root: the only module that imports adapters)
```

- `domain`: entities, value objects, policies, errors. Pure Python. No I/O, no framework, no `datetime.now()`.
- `ports`: `typing.Protocol` interfaces the core needs (repositories, staff repositories and table browser in `ports/staff.py`, UoW, LLM, embeddings, vector store and `DocIndexer`, health info, clock, messages).
- `services`: use cases. Orchestrate domain objects through ports. No SQLAlchemy, Pipecat, HTTP or vendor SDK imports.
- `adapters`: SQLAlchemy, pgvector, fastembed, LiteLLM, MedlinePlus, system clock, JSON catalog. Translate infrastructure errors into domain errors.
- `conversation`: Pipecat Flows nodes and LLM-facing function handlers. Thin; calls services.
- `pipeline`: Pipecat processors, pipeline builder, per-connection session.
- `api`: FastAPI routes only.

Enforced in CI with import-linter:

```toml
[tool.importlinter]
root_package = "clinic_bot"
include_external_packages = true

[[tool.importlinter.contracts]]
name = "Layered architecture"
type = "layers"
layers = [
  "clinic_bot.api",
  "clinic_bot.pipeline",
  "clinic_bot.conversation",
  "clinic_bot.services",
  "clinic_bot.ports",
  "clinic_bot.domain",
]

[[tool.importlinter.contracts]]
name = "Core is framework-free"
type = "forbidden"
source_modules = ["clinic_bot.domain", "clinic_bot.ports", "clinic_bot.services"]
forbidden_modules = ["pipecat", "sqlalchemy", "fastapi", "pgvector",
                     "fastembed", "litellm", "httpx", "clinic_bot.adapters"]

[[tool.importlinter.contracts]]
name = "Only the container wires adapters"
type = "forbidden"
source_modules = ["clinic_bot.api", "clinic_bot.pipeline", "clinic_bot.conversation"]
forbidden_modules = ["clinic_bot.adapters"]
# The app factory builds the composition root; that one edge is the only way in.
ignore_imports = ["clinic_bot.api.app -> clinic_bot.container"]
```

Flows ships inside `pipecat` (`pipecat.flows`), so forbidding `pipecat` covers it.

### 16.2 Domain model

- Value objects: `@dataclass(frozen=True, slots=True)`, validated in a `parse`/`__post_init__`, impossible to hold in an invalid state. Money is integer paise, never float.
- Entities own their invariants. Behaviour lives on the object that has the data (tell, don't ask).
- Policies are small stateless classes with one public method, configured through the constructor (cap, cutoff hours, lockout window), so rules are testable without a DB.

```python
@dataclass(frozen=True, slots=True)
class PhoneNumber:
    digits: str

    @classmethod
    def parse(cls, raw: str) -> PhoneNumber:
        d = _NON_DIGIT.sub("", raw)
        if len(d) == 12 and d.startswith("91"):
            d = d[2:]
        elif len(d) == 11 and d.startswith("0"):
            d = d[1:]
        if not _INDIAN_MOBILE.fullmatch(d):
            raise InvalidInput(ErrorCode.BAD_PHONE)
        return cls(d)

    def masked(self) -> str:
        return f"******{self.digits[-4:]}"


@dataclass(frozen=True, slots=True, order=True)
class Money:
    paise: int


@dataclass(slots=True)
class Appointment:
    id: int | None
    patient_id: int
    doctor_id: int
    slot: Slot
    visit_type: VisitType
    fee: Money
    status: AppointmentStatus
    intake: IntakeSummary

    def cancel(self, now: datetime, policy: CancellationPolicy) -> None:
        if self.status is not AppointmentStatus.BOOKED:
            raise NotFound(ErrorCode.NOT_FOUND)
        policy.ensure_cancellable(self.slot.start, now)   # raises CutoffViolation
        self.status = AppointmentStatus.CANCELLED


class BookingPolicy:
    def __init__(self, max_upcoming: int = 3) -> None:
        self._max_upcoming = max_upcoming

    def check(self, slot: Slot, upcoming: Sequence[Appointment]) -> None:
        if len(upcoming) >= self._max_upcoming:
            raise BookingRejected(ErrorCode.CAP_REACHED)
        for appt in upcoming:
            if appt.doctor_id == slot.doctor_id and appt.slot.day == slot.day:
                raise BookingRejected(ErrorCode.DUPLICATE_SAME_DAY)
            if appt.slot.window.overlaps(slot.window):
                raise BookingRejected(ErrorCode.OVERLAP)


class FeePolicy:
    def price(self, doctor: Doctor, grant: FollowupGrant | None,
              same_issue: bool | None) -> tuple[VisitType, Money]:
        if grant is not None and same_issue:
            return VisitType.FOLLOWUP, doctor.followup_fee
        return VisitType.NEW, doctor.fee
```

`DayResolver` is a pure class: `resolve(token: DayToken, now: datetime, window_days: int) -> date`. It has no clock of its own, so it is fully deterministic in tests.

### 16.3 Ports, adapters, unit of work

```python
class AppointmentRepo(Protocol):
    async def get(self, appointment_id: int) -> Appointment | None: ...
    async def by_session_slot(self, session_id: str, slot_id: int) -> Appointment | None: ...
    async def upcoming_for_patient(self, patient_id: int, now: datetime) -> list[Appointment]: ...
    async def add(self, appointment: Appointment, session_id: str) -> Appointment: ...  # SlotTaken
    async def save(self, appointment: Appointment) -> None: ...


class UnitOfWork(Protocol):
    patients: PatientRepo
    doctors: DoctorRepo
    slots: SlotRepo
    closures: ClosureRepo
    appointments: AppointmentRepo
    followups: FollowupRepo
    verify_attempts: VerifyAttemptRepo
    callbacks: CallbackRepo
    transcripts: TranscriptRepo
    chat_summaries: ChatSummaryRepo
    staff_users: StaffUserRepo
    staff_sessions: StaffSessionRepo
    consultations: ConsultationRepo
    clinic_docs: ClinicDocRepo

    async def __aenter__(self) -> Self: ...
    async def __aexit__(self, *exc: object) -> None: ...   # rollback if not committed
    async def commit(self) -> None: ...


class UnitOfWorkFactory(Protocol):
    def __call__(self, *, write: bool = False) -> UnitOfWork: ...
```

- `SqlUnitOfWork` opens one `AsyncSession` per use case. Write use cases (`confirm`, `cancel`, `verify`, staff edits) open it with `write=True`, which takes one transaction-level advisory lock (`pg_advisory_xact_lock`, 5s `lock_timeout`), so PostgreSQL serialises them like a single writer; a timeout becomes `Unavailable(BUSY)`. The policy checks and the insert then happen in one transaction with no race, and the unique index still backs up the slot rule.
- Repositories map ORM rows to domain objects in `mappers.py`. ORM classes never leave `adapters/db`.
- `IntegrityError` on the active-slot index becomes `SlotTaken` inside `SqlAppointmentRepo.add`.
- Services take a `UnitOfWorkFactory`, never a session.

```python
class BookingService:
    def __init__(self, uow: UnitOfWorkFactory, clock: Clock, booking: BookingPolicy,
                 fees: FeePolicy, cancellation: CancellationPolicy) -> None:
        self._uow, self._clock = uow, clock
        self._booking, self._fees, self._cancellation = booking, fees, cancellation

    async def confirm(self, cmd: ConfirmBooking) -> Appointment:
        async with self._uow(write=True) as uow:
            if existing := await uow.appointments.by_session_slot(cmd.session_id, cmd.slot_id):
                return existing                                      # idempotent retry
            slot = await uow.slots.require(cmd.slot_id)
            upcoming = await uow.appointments.upcoming_for_patient(cmd.patient_id, self._clock.now())
            self._booking.check(slot, upcoming)
            doctor = await uow.doctors.require(slot.doctor_id)
            grant = await uow.followups.active(cmd.patient_id, doctor.id, self._clock.today())
            visit_type, fee = self._fees.price(doctor, grant, cmd.same_issue)
            appt = await uow.appointments.add(
                Appointment.book(cmd.patient_id, slot, visit_type, fee, cmd.intake), cmd.session_id)
            if grant and visit_type is VisitType.FOLLOWUP:
                grant.mark_used(appt.id)
                await uow.followups.save(grant)
            await uow.commit()
            return appt
```

`ConfirmBooking` is a frozen command dataclass built by the handler from `FlowState`.

### 16.4 Conversation layer

**ToolResult and UI payloads**: pydantic models. `UIPayload` is a discriminated union on `type` (`QuickReplies`, `DoctorCards`, `SlotButtons`, ...). The widget's `ui/types.ts` is generated from its JSON schema (`make types`), so server and client can't drift.

**FunctionRegistry**: a module-level `@llm_function` decorator declares each LLM-facing function with its args model, description and transition; `FunctionRegistry.from_modules(...)` collects the declarations from the `functions/` modules. The registry builds the Flows function schemas, bound to one session's `HandlerContext`, and wraps every handler in the same pipeline:

1. validate args with the pydantic model (`INVALID` on failure)
2. `await state.verdict` (no side effects before the guardrail verdict, §6.1); a blocking verdict (medication, off-topic) → `BLOCKED`, no call
3. call the handler
4. map `DomainError` → `ToolResult.failure(code)`; anything else → log + `INTERNAL`
5. push `ui` through `ConversationIO`, record a metrics span
6. resolve the transition → next node via `NodeFactory` (which runs the node's async `prepare` first)

```python
@llm_function(
    name="select_slot",
    description="Select one of the slots just offered to the patient.",
    args=SelectSlotArgs,
    transition=lambda result, state: "confirm" if result.ok else None,
)
async def select_slot(args: SelectSlotArgs, ctx: HandlerContext) -> ToolResult:
    doctor_id = ctx.state.require_offered_slot(args.slot_id)   # raises InvalidChoice
    ctx.state.select_doctor(doctor_id)                         # alternatives may be another doctor
    ctx.state.selected_slot_id = args.slot_id
    return ToolResult.success(ui=QuickReplies.confirm(ctx.messages))
```

Handlers are at most ~15 lines. A handler that grows logic means the logic belongs in a service or policy.

**Nodes**: `BaseNode` is a template method that builds the Flows `NodeConfig`. Subclasses declare their name and function names as class attributes, implement `task()`, and override hooks only when needed: async `prepare()` (load what the task text needs into state), async `on_enter()` (fixed text or UI when the node becomes active), `respond_immediately()` and `context_strategy()`. The FAQ-detour line is appended to every task text when globals are included. `NodeFactory` maps names to node objects in a dict; `catalog.standard_nodes()` builds it with every node.

```python
class BaseNode(ABC):
    name: ClassVar[str]
    functions: ClassVar[tuple[str, ...]] = ()
    include_globals: ClassVar[bool] = True

    def __init__(self, prompts: PromptLibrary, registry: FunctionRegistry,
                 messages: MessageCatalog) -> None:
        self._prompts, self._registry, self._messages = prompts, registry, messages

    async def prepare(self, ctx: HandlerContext) -> None: ...
    async def on_enter(self, ctx: HandlerContext) -> None: ...

    @abstractmethod
    def task(self, state: FlowState) -> str: ...

    def respond_immediately(self, state: FlowState) -> bool:
        return True

    def context_strategy(self, state: FlowState) -> ContextStrategyConfig | None:
        return None

    def build(self, ctx: HandlerContext) -> NodeConfig:
        state = ctx.state
        names = self.functions + (GLOBAL_FUNCTIONS if self.include_globals else ())
        config: NodeConfig = {
            "name": self.name,
            "role_message": self._prompts.role(),
            "task_messages": [{"role": "system", "content": self._task_text(state)}],  # + FAQ_DETOUR
            "functions": list(self._registry.schemas(names, ctx)),
            "pre_actions": [self._enter_action(ctx)],     # sets current_node, runs on_enter
            "respond_immediately": self.respond_immediately(state),
        }
        if strategy := self.context_strategy(state):
            config["context_strategy"] = strategy
        return config
```

**FlowState** is a mutable dataclass with guard methods (`require_verified()`, `require_offered_slot()`, `require_listed_doctor()`, `require_offered_appointment()`) so handlers can't skip the checks.

### 16.5 Guardrails as objects

```python
@dataclass(frozen=True, slots=True)
class Verdict:
    label: GuardrailLabel
    source: Literal["regex", "classifier", "default"]
    reason: str = ""


class Guard(ABC):
    @abstractmethod
    async def check(self, text: str, ctx: GuardContext) -> Verdict: ...


class GuardPipeline:
    def __init__(self, regex: RegexGuard, classifier: Guard, timeout_s: float) -> None: ...

    def precheck(self, text: str) -> Verdict: ...            # sync, compiled patterns, label priority
    def start_classifier(self, text: str, ctx: GuardContext) -> asyncio.Task[Verdict]: ...
    # The task never raises: timeout, 429 after retry, or parse error → Verdict(NONE, "default")
```

- `RegexGuard` holds one precompiled, case-insensitive alternation per label, built once at import from `patterns.py`, checked in priority order (self-harm, emergency, medication, off-topic).
- `LLMClassifierGuard` depends only on the `StructuredLLM` port. Its prompt and label enum are versioned constants so eval runs are reproducible.
- The eval script uses the same `RegexGuard` and `LLMClassifierGuard` classes as production, so no logic is duplicated.

### 16.6 Composition root and lifecycles

```python
class Container:
    @classmethod
    async def build(cls, settings: Settings,
                    overrides: Overrides | None = None) -> Container: ...  # FastAPI lifespan startup
    def new_session(self, websocket: WebSocket) -> ChatSession: ...         # per /ws connection
    def new_speech_session(self, websocket: WebSocket) -> SpeechSession: ... # per /stt connection
    async def aclose(self) -> None: ...                                   # lifespan shutdown
```

| Lifetime | Objects |
|---|---|
| Process (singleton) | Settings, Clock, async engine + UoW factory, DoctorDirectory cache, Embedder (model loaded once), VectorStore + DocIndexer, StructuredLLM per role, HealthInfoProvider, shared `httpx.AsyncClient`, MessageCatalog, PromptLibrary, FunctionRegistry, NodeFactory, GuardPipeline, all services, TranscriptWriter, ChatSummaryService, StaffServices (with the in-memory `LoginThrottle`), SpeechDeps with the STT factory |
| Per `/ws` connection | FlowState, Pipecat LLM service instance, processors, pipeline, FlowManager, ChatSession |
| Per `/stt` connection | SpeechSession, STT service instance |
| Per use case | UnitOfWork |

No module-level mutable state and no global singletons. Everything is constructor-injected. Tests build a container with fakes through the same `build` path (`Container.for_tests(settings, overrides)`; `Overrides` holds the test seams).

### 16.7 Performance

Budgets (excluding LLM time), measured by `TurnMetricsObserver` and reported p50/p95 in the README:

| Step | Budget p95 |
|---|---|
| Regex precheck | < 1 ms |
| Tool DB use case | < 20 ms |
| RAG query (embed + pgvector) | < 40 ms |
| Server overhead per turn | < 100 ms |
| Classifier verdict | before main LLM first token in most turns |

How:
- Async end to end. No blocking I/O on the event loop. CPU-bound embedding runs via `asyncio.to_thread`.
- PostgreSQL: asyncpg, pool of 5 (+5 overflow) with pre-ping; reads at READ COMMITTED; only write units of work take the advisory lock.
- Indexes: `slots(doctor_id, start)`, `appointments(patient_id, status)`, partial unique `appointments(slot_id) WHERE status='booked'`, partial unique `appointments(session_id, slot_id) WHERE status='booked'`, `verify_attempts(phone_norm, ts)`, `followup_grants(patient_id, doctor_id, valid_until)`.
- Free slots come from a single query: window filter + anti-join on booked appointments + `ORDER BY start LIMIT 3`. No loading all slots into Python.
- Doctors are static per seed: `DoctorDirectory` loads them once into immutable dicts keyed by id and specialty. Fuzzy name match uses `rapidfuzz`. Reloaded after reseed.
- Vector queries filter on `kind` inside the SQL query, not after it.
- Classifier: temperature 0, ≤50 output tokens, enum output, short static prompt prefix (cache-friendly), runs in parallel.
- Transcripts and guardrail events go through `TranscriptWriter` (asyncio.Queue, batched inserts, flushed on disconnect). The turn path never waits on logging writes.
- MedlinePlus: shared HTTP client, 3 s timeout, in-memory LRU (256) in front of a disk cache.
- Docker: multi-stage slim image, no torch, embedding model and MedlinePlus cache baked in at image build; the index is built in PostgreSQL on first start.
- Don't optimise past the budgets at the cost of readability.

### 16.8 Errors and logging

- `DomainError(code: ErrorCode)` hierarchy: `InvalidInput`, `InvalidChoice`, `NotVerified`, `Locked`, `NotFound`, `NotOwner`, `BookingRejected`, `SlotTaken`, `CutoffViolation`, and for the staff API and infrastructure `Unauthorized`, `Forbidden`, `Conflict`, `Unavailable`. `ErrorCode` is a `StrEnum` shared by tools, eval and the widget.
- Adapters translate infrastructure exceptions into domain errors. Services never catch `Exception`.
- The only broad `except` is in the registry wrapper and the pipeline session boundary. Both log with the session id and return a safe fixed message + handoff offer.
- `structlog` JSON logs with `session_id` and `node` bound per session. Phone is logged masked, DOB never, message text only as a hash.

### 16.9 Typing, style, quality gates

- Python 3.12, `uv`, pinned versions.
- `mypy --strict` on `domain`, `ports`, `services`, `conversation`. No `Any` in public signatures.
- Domain types are frozen slotted dataclasses. Pydantic v2 only at boundaries (settings, LLM args, UI payloads, API).
- `ruff` (rules E, F, I, B, UP, SIM, RUF, ASYNC, PL subset) + `ruff format`.
- import-linter contracts (§16.1).
- Size limits: functions ≤ 40 lines, classes ≤ 200 lines, modules ≤ 300 lines. Inheritance depth ≤ 1: subclasses exist only for `BaseNode`, `Guard`, `DomainError`, Pipecat processors, frames and the serializer, and pydantic boundary models; ports have implementers. Pydantic models at the API boundary may nest two levels (e.g. `api/staff/views.py`, where a detail view extends a summary view). Prefer composition.
- Docstrings on public classes and service methods: what it does and which errors it raises. No comments restating code.
- pre-commit runs ruff, mypy and import-linter. GitHub Actions has three jobs: `server` (lint, types, contracts, tests against a `pgvector/pgvector:pg18` service with `clinic_test`, and the Layer 1 eval: no LLM, so free and deterministic), and `web` and `admin` (lint, typecheck, Vitest, build).
- All time via the `Clock` port. No patient-facing literal strings in Python (use `MessageCatalog` keys). No provider names or model ids outside `config.py` and `adapters/llm`. LLM-facing schemas never take `patient_id`, fee or visit type.

### 16.10 Testing strategy

| Level | What | Uses |
|---|---|---|
| Unit | Value objects, policies, DayResolver, services | In-memory fakes from `tests/fakes`, `FrozenClock` |
| Contract | One `RepoContract` suite run against both `InMemory*Repo` and `Sql*Repo` | Proves the fakes behave like the real adapters |
| Integration | A real uvicorn server with `/ws` flow paths (booking, follow-up, cancel, guardrails, summaries) driven by a `ScriptedLLMService` that emits scripted text and function calls; the `/stt` endpoint with a fake STT; the staff HTTP API | Real PostgreSQL (`clinic_test`) |
| Concurrency | Two concurrent `confirm` calls on one slot → exactly one succeeds (`tests/contract/test_concurrency.py`) | Real PostgreSQL (`clinic_test`) |
| Eval | Red-flag dev + holdout (§12.1) | Production guard classes |

Golden conversations (§12.3) are not built in v1.

Coverage target: ≥ 90% lines on `domain` and `services`. It is a target only: there is no coverage tooling and CI does not measure it.

### 16.11 Web code structure

- TypeScript `strict`, React function components and hooks (idiomatic React; no class components).
- Only modules in `transport/` (`chatClient.ts`, `speechClient.ts`) import the Pipecat SDK; ESLint enforces it.
- `state/chatReducer.ts`: a typed reducer state machine (`waking | connecting | ready | ended | error`) owning messages, pending UI blocks and the disable-old-buttons rule.
- `ui/registry.ts` maps `ui.type` to a component through an exhaustive switch over the generated union, so the compiler catches an unhandled type.
- ESLint + Prettier. Vitest in `web/` for the reducer, registry, `speaker` and `voiceDraft`; in `admin/` for `api/client` and `routing/routes`.
- `admin/` ESLint forbids the global `fetch` (`no-restricted-globals`) everywhere except `src/api/client.ts` and its test.

### 16.12 Patterns in use (and only these)

| Pattern | Where | Change it absorbs |
|---|---|---|
| Ports and adapters | `ports/` + `adapters/` | LLM vendor, DB, vector store, embedder, health source |
| Repository + Unit of Work | DB access | Swappable storage (in-memory fakes, PostgreSQL); transactional booking |
| Strategy | LLM providers, embedders, guards | Free → paid model by env |
| Decorator | `RetryingLLM`, `CachedHealthInfo` | Cross-cutting retry and caching without touching clients |
| Factory + Registry | `PipecatLLMFactory`, `GeminiSTTFactory`, `NodeFactory`, `FunctionRegistry` | New provider, node or function = one registration |
| Template Method | `BaseNode` | Nodes differ only in task text and functions |
| Value Object | `PhoneNumber`, `DateOfBirth`, `PersonName`, `EmailAddress`, `Money`, `TimeWindow`, `DayToken` | Validation in one place |
| Command | `ConfirmBooking`, `CancelAppointment` | Clear use-case inputs; easy to log and replay |

---

## 17. Staff portal (admin and doctor)

Owner decision, Oct 2026: the staff view moves out of §14 and is built now as a separate web app, `admin/` (React + Vite, its own Vercel project). It talks to the same FastAPI backend over plain HTTPS + JSON under `/staff`. The chatbot widget and the portal share nothing in the browser.

### 17.1 Roles and login

- Two roles: `admin` and `doctor`. Every `/staff` route except login needs `Authorization: Bearer <token>`.
- Login is email + password. Passwords are hashed with scrypt (stdlib `hashlib.scrypt`, random 16-byte salt), compared in constant time, 8 to 128 characters. Staff names are 2 to 80 characters.
- A login returns an opaque random token. Only its SHA-256 is stored (`staff_sessions`), with a 12-hour expiry (`STAFF_SESSION_HOURS`). Logout deletes it. Deactivating an account or resetting its password deletes its sessions.
- Wrong email and wrong password give the same 401 "Invalid email or password." 5 failures for one email in 15 minutes lock that email for 15 minutes (in memory, per process; the backend runs as one instance) → 429.
- The first admin comes from env: if `ADMIN_EMAIL` and `ADMIN_PASSWORD` are set and no account has that email, startup creates it. `clinic-create-admin` (CLI) creates an admin, or resets an existing admin's password and reactivates the account; it refuses an email that belongs to a doctor account. There is no sign-up.
- Doctor accounts are created only by an admin, one account per doctor, linked to a `doctors` row. A doctor sees and changes only their own appointments (anything else is 404).
- The portal keeps the token and the signed-in user in `sessionStorage`. CORS allows both `ALLOWED_ORIGINS` and `STAFF_ORIGINS`; the chat and voice WebSockets still accept only `ALLOWED_ORIGINS`.

### 17.2 Doctor

- Appointments list: today, upcoming (tomorrow through the next 60 days), or past (last 90 days), for the signed-in doctor.
- Appointment page: patient (name, age, sex, phone, DOB), visit type, status, the intake the bot collected, the patient's chat summaries (§9.2), and the patient's earlier consultations with any doctor.
- Edit: status (`booked`, `completed`, `no_show`; never `cancelled`, which only the patient does through the bot) and the visit details from intake (chief complaint, duration, severity 1 to 10).
- Consultation form: consultation notes, diagnosis, medication (free text, as the doctor writes it), "follow-up required" tick box with a follow-up window in days (1 to 90, default 14). Submit saves it and marks the appointment `completed`. The doctor can edit and submit again; the latest submission wins.
- Ticking follow-up creates the `followup_grants` row the chatbot already reads (§4.7): valid until visit date + days, `created_by` = doctor name, `source_appointment_id` = this appointment. Resubmitting updates that grant; unticking deletes it, unless the patient has already booked the follow-up with it (then it stays).
- Outcome, visit details and consultation are allowed only for appointments on or before today and never for cancelled ones (409). Moving a visit back to `booked` is refused (409) if another booking now holds that slot.

### 17.3 Admin

- Overview counts. All appointments for a day; any appointment page (read-only, same view as the doctor's).
- Doctors: edit name, bio, fee and follow-up fee. The chatbot's doctor directory reloads on save. Consulting days and hours stay as seeded in v1 (slot generation reads them from the seed).
- Accounts: lists every staff account (admins and doctors). Create a doctor login (email, name, initial password, doctor); reset any account's password; deactivate/activate any account except your own (an admin cannot deactivate themselves). The API's `PATCH` also renames.
- Clinic information: edit the FAQ documents (`clinic_info.md`, `services.md`, `insurance.md`, `prep_sheets.md`). They live in `clinic_docs`, seeded from `data/docs` when empty. Saving re-embeds the documents and swaps the chunks in pgvector (one transaction), so `answer_faq` uses the new text from the next question on. Startup rebuilds the index when the stored documents differ from what was indexed. Sections are split on `# ` headings, as before; a document with no `# ` heading is refused (400), and content is capped at 50,000 characters.
- Closures: list, add (today or later, one per day), remove. The list shows how many booked appointments fall on each day; adding a closure does not cancel them.
- Database: every table with its row count, and a read-only, paginated view of rows (50 per page). `staff_users.password_hash` and the whole `staff_sessions` table are never shown.

### 17.4 Data

```
staff_users     (id, email UNIQUE, name, role: admin|doctor, doctor_id NULL UNIQUE → doctors,
                 password_hash, active, created_at, last_login_at NULL)
staff_sessions  (token_hash PK, user_id → staff_users, created_at, expires_at)
consultations   (id, appointment_id UNIQUE → appointments, doctor_id, patient_id, notes,
                 diagnosis, medication, followup_required, followup_in_days NULL,
                 followup_grant_id NULL, submitted_by → staff_users, created_at, updated_at)
clinic_docs     (name PK, content, updated_at, updated_by NULL)
```

`appointments.status` gains `completed` and `no_show`. The chatbot never reads `consultations` (medication refusal, §6.5, is unaffected) and still only books and cancels.

### 17.5 HTTP API

JSON in and out. Times are ISO 8601 with the IST offset; the server also sends display labels (`Tue 7 Oct`, `6:15 PM`) so the portal does no timezone math. Errors are `{"detail": "<message>"}` (400, 401, 403, 404, 409, 429, and 503 when the database is busy); request validation errors are FastAPI's 422 `{"detail": [{"loc": [...], "msg": "..."}]}`. Money is whole rupees in the API.

Types:

```
StaffUser   {id, email, name, role: "admin"|"doctor", doctor_id: int|null, doctor_name: str|null,
             active: bool, created_at: str, last_login_at: str|null}
PatientRef  {id, name, age: int, sex: "female"|"male"|"other"}
AppointmentSummary {id, start, end, date_label, time_label, doctor_id, doctor_name,
             patient: PatientRef, visit_type: "new"|"followup",
             status: "booked"|"cancelled"|"completed"|"no_show",
             chief_complaint: str|null, has_consultation: bool}
Intake      {chief_complaint: str, duration: str|null, severity: int|null,
             answers: [{q, a}], red_flags_checked: [str]}
Consultation {notes, diagnosis, medication, followup_required: bool,
             followup_in_days: int|null, followup_valid_until: str|null (date),
             submitted_by: str, created_at, updated_at}
HistoryItem {appointment_id, date_label, doctor_name, diagnosis, notes, medication,
             followup_required: bool}
AppointmentDetail = AppointmentSummary + {fee_rupees: int,
             patient: PatientRef + {phone: str, dob: str (date)},
             intake: Intake|null, consultation: Consultation|null,
             chat_summaries: [{id, summary, created_at}], history: [HistoryItem],
             can_record: bool}      // false when cancelled or on a later day
Doctor      {id, name, specialty, specialty_label, bio, consulting_days: [int] (0 = Mon),
             days_label, hours, fee_rupees, followup_fee_rupees,
             account: {id, email, active}|null}
ClinicDoc   {name, title, content, updated_at: str|null, updated_by: str|null}
Closure     {id, date, date_label, reason, booked_appointments: int}
TableInfo   {name, row_count}
TablePage   {name, columns: [str], rows: [[str|number|boolean|null]], total, offset, limit}
```

| Method and path | Role | Body | Returns |
|---|---|---|---|
| `POST /staff/auth/login` | none | `{email, password}` | `{token, expires_at, user: StaffUser}` |
| `POST /staff/auth/logout` | any | | 204 |
| `GET /staff/me` | any | | `StaffUser` |
| `POST /staff/me/password` | any | `{current_password, new_password}` | 204 (the user's other sessions end) |
| `GET /staff/doctor/appointments?scope=today\|upcoming\|past` | doctor | | `[AppointmentSummary]` (past: newest first, last 90 days) |
| `GET /staff/doctor/appointments/{id}` | doctor | | `AppointmentDetail` |
| `PATCH /staff/doctor/appointments/{id}` | doctor | `{status?, intake?: {chief_complaint, duration, severity}}` | `AppointmentDetail` |
| `PUT /staff/doctor/appointments/{id}/consultation` | doctor | `{notes, diagnosis, medication, followup_required, followup_in_days}` | `AppointmentDetail` |
| `GET /staff/admin/overview` | admin | | `{patients, doctors, appointments_today, upcoming_appointments, consultations, chat_summaries, callbacks}` |
| `GET /staff/admin/appointments?day=YYYY-MM-DD` | admin | | `[AppointmentSummary]` (default today) |
| `GET /staff/admin/appointments/{id}` | admin | | `AppointmentDetail` |
| `GET /staff/admin/doctors` | admin | | `[Doctor]` |
| `PUT /staff/admin/doctors/{id}` | admin | `{name, bio, fee_rupees, followup_fee_rupees}` | `Doctor` |
| `GET /staff/admin/accounts` | admin | | `[StaffUser]` |
| `POST /staff/admin/accounts` | admin | `{email, name, password, doctor_id}` | 201 `StaffUser` (409 if email or doctor taken) |
| `PATCH /staff/admin/accounts/{id}` | admin | `{name?, active?, password?}` | `StaffUser` |
| `GET /staff/admin/clinic-docs` | admin | | `[ClinicDoc]` |
| `PUT /staff/admin/clinic-docs/{name}` | admin | `{content}` | `ClinicDoc` |
| `GET /staff/admin/closures` | admin | | `[Closure]` (today onwards) |
| `POST /staff/admin/closures` | admin | `{date, reason}` | 201 `Closure` (400 past day, 409 exists) |
| `DELETE /staff/admin/closures/{id}` | admin | | 204 |
| `GET /staff/admin/tables` | admin | | `[TableInfo]` |
| `GET /staff/admin/tables/{name}?offset=0&limit=50` | admin | | `TablePage` (limit ≤ 200) |

### 17.6 Portal app (`admin/`)

- React + Vite + TypeScript strict, same toolchain and versions as `web/`. No router or UI library: hash routes, plain CSS. Routes: `#/login`; `#/account` (own password, both roles); `#/doctor/appointments?scope=today|upcoming|past`, `#/doctor/appointments/12`; `#/admin/appointments?day=YYYY-MM-DD`, `#/admin/appointments/12`; `#/admin/overview`, `#/admin/doctors`, `#/admin/accounts`, `#/admin/clinic-info`, `#/admin/closures`, `#/admin/database`.
- `src/api/client.ts` is the only module that calls `fetch`; it adds the bearer token and turns a 401 into a sign-out. `src/api/types.ts` mirrors §17.5.
- After login the app routes by role. Admin and doctor screens never mix.
- Env: `VITE_API_URL`. Dev server on port 5174. Deploy: a second Vercel project with root directory `admin/`; add its URL to `STAFF_ORIGINS` on Render.
