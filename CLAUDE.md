# CLAUDE.md — excise-mcp-dashboard

Master rules for coding sessions on this repo. Read this, then `ARCHITECTURE.md`,
`EVALUATION.md`, and the doc for whichever component you are touching
(`DATA_PIPELINE.md`, `MCP_ENGINES.md`, `SECURITY.md`). `ROADMAP.md` has the
milestone checklist and the current position in it.

Status: **Phase 4 approved; build underway.** Milestone 0, the database half
of Milestone 1, and Milestone 2 (the orchestrator's one-shot pipeline) are
done — the `web/` Laravel skeleton is merged, `excise_bank` is provisioned and
role-verified live, and `orchestrator/`'s `/query` ran a real question
end-to-end against real seed data (SQL -> Postgres -> a sandboxed Plotly
render -> a narrated summary), tested green (`ruff` / `mypy --strict` /
`pytest`, 32 tests including live `bwrap` runs). Static chart export
(`chart.png`/`svg`/`pdf`) never runs Plotly's own `fig.write_image()` inside
the per-script sandbox — that repeatedly OOM-killed the render's cgroup
launching a fresh headless Chrome. A matplotlib script still calls
`plt.savefig()` directly, inside the sandbox. A Plotly script only ever
calls `fig.write_json()`; `engines/static_render.py` then derives any
requested static format from that JSON afterward, outside the sandbox, via
one persistent, isolated browser kept running for the orchestrator's whole
lifetime — it never executes LLM-authored code, only rasterizes an
already-produced chart spec. The `excise-sandbox`
uid-separation layer is also still off (`bwrap`'s own confinement covers the
same ground meanwhile) — `loginctl enable-linger excise-sandbox` turned out
insufficient on its own; the sudoers fallback in `SECURITY.md` §2 is the
untried real path. `OLLAMA_KEEP_ALIVE`/`OLLAMA_NUM_PARALLEL`/
`OLLAMA_MAX_LOADED_MODELS` (`EVALUATION.md` §2) are now actually applied to
the Ollama service, found missing after a loaded model sat resident well past
its documented 30s. Milestone 3's retrieval plumbing is done — `etl/sources/
pdf_pipeline.py` syncs the pdf-markdown-pipeline corpus (verified live against
the real `pdf_markdown_pipeline_local`: 334 public+verified Excise rows) into
`kb.documents`/`kb.chunks` via `etl/chunk.py`'s heading-aware chunker, with
withdrawal handling; `orchestrator/app/kb/retrieve.py` and `/kb/search` run
Postgres FTS over it, tested green (`ruff` / `mypy --strict` / `pytest`
against the real local Postgres, both packages). `db/kb_indexes.sql` is
written but not yet applied — needs `sudo -u postgres`, a pending
`OPERATOR_SETUP.md` §Data bank step. What Milestone 3 leaves for later
milestones: wiring `search_knowledge` into a chat tool loop (Milestone 5's
Phase 2/3, not built yet), and Google Docs/Drive into `kb.*` (waits on
Milestone 1's Google ingestion, not started) — the admin `.md` upload screen
itself is now built (Milestone 5's Phase 4). Milestone 4
(the Octave engine) is done — `engines/octave_engine.py` runs `octave-cli`
under the same `bwrap` sandbox as the Python engine, tested green (`ruff` /
`mypy --strict` / `pytest`, 45 tests) including a live render against the real
`octave-cli` on the box. That live run surfaced three gaps `MCP_ENGINES.md`
now documents: GNU Octave has no `table`/`readtable`, so the query result
hands off as generated Octave variables instead; a new figure doesn't inherit
the `graphics_toolkit` global default, fixed by pinning
`__graphics_toolkit__` on the figure object directly; and `print()`'s
`-dpng`/`-dpdf` route through Ghostscript, which fails inside the sandbox
namespace, so the engine uses gnuplot's own cairo terminals
(`-dpngcairo`/`-dsvg`/`-dpdfcairo`) instead. `matlab_engine.py` /
`wolfram_engine.py` are documented, unconfigured stubs behind
`ENABLE_MATLAB` / `ENABLE_WOLFRAM` (default off). Work follows the
`ROADMAP.md` milestone order; Milestone 5 (Laravel UI) is underway, built
against the full design in `web/plan/webui.md` (reuse map, RBAC and data
model, the Ask and Chat flows, the orchestrator `/chat` design, the model
picker, a security checklist). Phase 0 (shell, RBAC, auth), Phase 4
(admin — users, Google connect, knowledge base, activity log), Phase 1
(the Ask form), Phase 2 (the orchestrator `/chat` endpoint and bounded tool
loop), and Phase 3 (the Chat window) are merged into `dev`. Phase 0/4:
OTP-email login and onboarding ported from
`upexcise-stats-dashboard`, `SecurityHeaders`/`LogMutation`/privilege
middleware, the `designations`-backed RBAC model, and four full-page
Livewire admin screens, each gated by route middleware and a per-write
`abort_unless()` re-check, plus a new orchestrator `GET /kb/documents`
endpoint for the Knowledge base screen's browse view. Phase 1: the `queries`
ledger, `RunExciseQuery` queued job, and the Livewire `Ask` form, relaying
the orchestrator's stage events to the browser via `fetch()` polling of a
plain status route (not a held-open connection). Phase 2: `orchestrator/app/
chat/` (`tools.py`, `loop.py`, `prompts.py`) wires `search_knowledge`,
`run_sql_query`, and `make_chart` into a turn loop capped at
`CHAT_MAX_TOOL_CALLS`, reusing the one-shot pipeline's SQL guard, read-only
role, and sandbox — no parallel implementation. Phase 3: `conversations`/
`messages`/`message_tool_calls` hold the transcript, and a plain
`POST /chat/{conversation}/send` route (real streaming I/O, since a chat
token arrives too fast for a queued job) pipes the orchestrator's ndjson
stream straight to the browser while persisting it. Tested green throughout
— `pint`, 51 PHPUnit tests on `web/`; `ruff` / `mypy --strict` / `pytest`,
62 tests on `orchestrator/`. A live render also surfaced a second sandbox
fix this phase: Plotly's own static export (`fig.write_image`, via
kaleido's headless Chrome) was repeatedly OOM-killing the sandbox cgroup
instead of erroring, so the plot-planning prompt no longer offers it and
the Python engine now rejects a script that calls it anyway before a
sandboxed process runs — matplotlib's `plt.savefig` covers static export
without that dependency. Phase 5 (customization panel, brand assets) is
next. Two decisions from the design correct this file: the chat stream is
newline-delimited JSON (`application/x-ndjson`, matching `/query`'s
existing wire format), not `text/event-stream` — every "SSE" reference
below to `/chat`'s transport means that; and RBAC carries a `designations`
preset table (`role` + `privileges` + `designation_id` + free-text `post`)
— the pattern four sibling Laravel apps converged on independently.
Dependency installs so far: `web/`'s Composer + npm set, `etl/`'s venv
(`+aiomysql`), `orchestrator/`'s venv — each the current milestone's
`OPERATOR_SETUP.md` section at the time. A public `/` route now exists — a
placeholder landing page on the trimmed GIGW/UX4G track ported from
`upexcise-stats-dashboard` (identity strip, emblem header, skip link, no
policy footer), since every other route stayed behind `/login` with nothing
to land on. The department's brand assets (state emblem, favicons) moved
from `assets/brand/` into `web/public/`, wired into `<x-head>`. The app is
now live end to end on this box: the Apache vhost, the Cloudflare tunnel, the
`web/` queue worker, and the orchestrator itself all run as `systemd --user`
units (`OPERATOR_SETUP.md`'s per-milestone sections had each unit file
written but not installed until now) and were verified together —
`visualizer.exciseup.in` serves the home page, `/ask` redirects an
unauthenticated request to `/login`, and `/health` on both `web/` and
`orchestrator/` report `ok`. `OPERATOR_SETUP.md` also gained the bootstrap
step for an empty `users` table's first Admin account, and the recovery
command for the tunnel's one operational failure mode so far — a transient
DNS lookup tripping systemd's restart-rate-limit, which does not self-clear.
Hand-testing the live site past `/health` surfaced what its test suite
couldn't see, since `ChatTest` drives `ChatController::send()` directly and
never exercises the browser-side bridge to it: sending a first chat message
never reached the orchestrator at all. The thread panel's `wire:key` included
`$activeConversation->id`, which `send()` sets in the same request it
dispatches `chat-message-ready` — Livewire saw the key change and tore down
and rebuilt that DOM node, destroying the very Alpine listener meant to
catch that event before the browser's `fetch()` to `ChatController::send()`
ever fired. Keyed off a mount-time-only property instead. The same pass
found the composer clipped off-screen behind a hardcoded `calc(100vh-11rem)`
guess and `overflow-hidden` (moved it inside the scrolling area with
`sticky bottom-0`, immune to the guess being wrong), and the Users/Activity
log search boxes' left icon overlapping the input text — `field-input`'s own
padding, compiled via the Tailwind Play CDN's runtime `@apply`, was beating
a plain `pl-9` override in the cascade; `excise-budget-tracker` hit the same
thing and fixed it with Tailwind's `!` modifier, applied the same way here.
Two more turned up right after: a failed Ask query rendered its red error
box with nothing in it, traced to some httpx/httpcore exceptions (timeouts
especially) having an empty `str()` when raised without an explicit
message — `OllamaClient` wraps them as `OllamaUnreachableError(str(e))`, so
the wrapped error's own message came out empty too, all the way to the blade
view's `?? 'fallback'` (which only catches `null`, not `''`). Fixed at the
source (`OrchestratorError` falls back to the raising exception's class
name when the message is empty) and at the display (`?:` instead of `??`,
plus the stage and request_id shown in the box when `APP_DEBUG` is on). And
Chat's "New conversation" link stopped responding once a message had been
sent in the thread: `sendToOrchestrator()` moves the address bar with
`history.replaceState()` after a live send, which Livewire's `wire:navigate`
router never observes, so a `wire:navigate` click back to a path it still
thinks it's already on silently no-ops — the conversation-rail links are
plain navigation now.

A super-admin "System health" screen followed (Admin -> System health,
privilege `system.monitor`), Livewire-native with `wire:poll` — this app's
own convention for every screen. It shows orchestrator reachability, queue
depth, server vitals (load, memory, CPU temp, direct `/proc` reads matching
`pdf-markdown-pipeline`'s own health dashboard), recent error counts, and —
new this round — AI usage by model. The orchestrator now tracks prompt/
completion token counts per request (`TokenUsage` in `llm/client.py`,
accumulated across however many Ollama calls one turn makes and returned on
`QueryResponse` and the chat stream's `done` event), persisted onto
`queries`/`messages` and totalled on the health screen. Fixing this also
caught that `structlog` was never actually `.configure()`'d despite
`CLAUDE.md` already claiming JSON-to-stdout logging — it ran on plain-text
defaults; now configured for real, with an info-level line on every
successful `/query` and `/chat` turn, not just exceptions. Ask also gained a
minimal thumbs-up/down + note capture (`query_feedback`, one row per person
per query) — `ROADMAP.md` had this planned since Phase 1 but nothing built
it until the health screen needed something to show.

Laravel Pulse and Telescope are both installed, and both needed the same
fix before they were safe to leave running: each ships a default
authorization that allows anyone through — no login at all — when
`app()->environment('local')` is true, which is this box's real `APP_ENV`
while it's also genuinely public through the tunnel. `SECURITY.md`'s new
subsection under §3 has the full detail; the short version is both are now
locked to `isAdmin()` unconditionally, verified against real accounts
(non-admin 403, admin 200) rather than trusted from reading the source.
`telescope:prune` runs daily via `routes/console.php`'s new `Schedule::`
call — the first one in this app — and a `schedule:run` cron entry now
exists on this box to actually fire it (`OPERATOR_SETUP.md` §Monitoring).

A live Ask question surfaced a gap in the render step: the plot-planning
model occasionally writes a script Python rejects outright (an invalid
Plotly keyword argument, a column name that doesn't exist), and that
failure had no retry — the whole query failed on the model's first mistake.
`pipeline.py`'s `run_query` now retries once, the same pattern `guard_sql`
already uses for a rejected SQL statement: the render error and the failed
script go back to the model, and only a second failure surfaces to the
user. The chat `make_chart` tool had the same gap, fixed differently: its script
arrives directly as the tool call's own argument, with no separate planning
step to reprompt, so a render failure there comes back as a failed tool
result instead of ending the turn. The model sees why its script failed and
can call `make_chart` again within its own `CHAT_MAX_TOOL_CALLS` budget.
A zero-row result had the same hallucination risk the knowledge base's empty
corpus already guards against: the summarize step was handing the model an
empty result set and still asking for "a plain-language reading of the
numbers," and it obliged with an invented trend. `run_query` now skips that
call entirely on zero rows and returns a fixed "No rows matched this
question." instead.

`public/vendor/flasher/` — the toast-notification package's published JS and
CSS, referenced on every page by `@flasher_render` — was missing from the
repository since the original skeleton commit: the browser's request 404'd
and the browser refused to execute the HTML error page it got back instead,
on every single page load. `php artisan flasher:install` publishes it, and
it is committed the same way `public/vendor/tabler-icons/` already is.

The first real data import landed: an IESCMS shop-wise wholesale-to-retail
dispatch report for August 2026, Lucknow — a live-system export, one row per
transport pass, not the annual NITI reconciliation `sales_volumes` was built
for. It doesn't fit either existing fact table, so it gets two new ones,
`dispatches` and a `dispatch_strength_lines` child table for the
country-liquor report's per-strength breakdown (`DATA_PIPELINE.md`
§Dispatches). `license_categories` gained the specific retail/wholesale
codes the report actually uses (FL2, CL2, FL5DB, FL4A, FL4C, CL5C, CL5CC)
alongside the five broad kinds already there, and `financial_years` gained
FY2026-27. `etl/sources/iescms_dispatch.py` upserts the retail shop
dimension and the dispatch rows together, keyed on the report's own indent
number so a re-run changes nothing. The August 2026 Lucknow import has run:
9,322 dispatch rows and 25,200 country-liquor strength-line rows are live in
`analytics.dispatches` / `analytics.dispatch_strength_lines`, with one
trailing blank row correctly quarantined rather than inserted.

Hand-testing surfaced two more live bugs past what the merged test suites
covered. Chat's composer went missing on screen (the textarea and Send
button were still in the rendered HTML, just squeezed to a few pixels wide):
the model-picker `<select>` carries `w-auto` to keep its own width, but
`field-input`'s `@apply w-full` (`resources/views/components/head.blade.php`)
comes later in the Tailwind Play CDN's runtime stylesheet and wins the
cascade at equal specificity, so the select claimed close to the full row
width with `flex-shrink-0` refusing to give any of it back. Same fix as the
admin search boxes' padding override before it: Tailwind's `!` modifier,
`!w-auto` instead of `w-auto` (`chat.blade.php`).

Pulse and Telescope both started 401ing a genuinely logged-in admin,
underneath — not instead of — the `IsAdmin`/`Telescope::auth()` checks
already documented in `SECURITY.md` §3. Both packages now ship
`laravel/sentinel`, a bundled middleware that runs before session/auth even
starts and denies any request reaching them through a trusted reverse proxy
from a public IP while `APP_ENV=local` — a guard against a local-only
dashboard leaking through a forgotten tunnel. This box's Cloudflare Tunnel
exposure is deliberate and already gated by real login, so the heuristic was
a false positive: `AppServiceProvider::configureSentinel()` registers a
`Sentinel::extend()` driver for both `pulse` and `telescope` that always
authorizes, leaving the actual admin check — which the false positive ran
ahead of, not in place of — as the only gate.

A round of hands-on Chat testing surfaced four more fixes. The model
picker offered Qwen alongside Llama — `Chat::render()` filtered the
registry only by whether Ollama reported a model pulled, not by `role`, so
the coder model meant only for SQL/plot planning showed up as a
conversational choice; it now filters to `role: chat` first
(`MCP_ENGINES.md` §`ChatRequest`). A plain "hi" got back Llama's own
tool-call deliberation instead of a greeting — "No tool call is needed as
it's a greeting..." — since every token the model emits is streamed
straight to the user with nothing held back; `CHAT_SYSTEM_PROMPT` now tells
it directly not to narrate that decision (`MCP_ENGINES.md` §Tools). The
composer textarea stayed one fixed row regardless of message length —
it now grows with the message up to a capped height, and Enter sends while
Shift+Enter still inserts a newline, matching the composer conventions of
other chat products. And a new conversation had no title, staying
"New conversation" in the rail forever — `Chat::send()` now sets `title`
from the first message, truncated to 60 characters. Neither Claude,
ChatGPT, nor Gemini actually put a readable slug in the chat URL despite
that being the ask that prompted this — all three keep an opaque id there
too — so the URL itself stays the plain ULID (`CLAUDE.md`'s existing
ULID route-binding convention, restated below, is unchanged); only the
title was missing.

Live use past that round surfaced a real answer going wrong silently, and
chat going silent outright. Asking Ask "how many composite shops are in
Lucknow in August 2026" returned zero, because the generated SQL filtered
`analytics.shops` on `created_at` — when that row was last loaded into the
database, not a business date; `shops` is a present-day snapshot with no
time dimension at all, and `schema_card.py`'s `VIEW_NOTES` had no entry for
`analytics.dispatches`, the view that actually carries a real
`transport_pass_issued_at` date, even though it has held the live August
2026 IESCMS import since the dispatch-report milestone. `VIEW_NOTES` now
says so directly for both views (`MCP_ENGINES.md` §Pipeline stages). And a
plain "hi" in Chat sometimes got back nothing but a literal `"{}"` — Llama's
tool-calling degenerates a trivial message into a bare `{}` once
`CHAT_TOOL_SCHEMAS` is attached to the turn, confirmed directly against
Ollama (the identical prompt with no `tools=` replies normally);
`chat/loop.py` now holds back a brace-only reply instead of streaming it and
retries the turn once with `tools=[]` (`MCP_ENGINES.md` §Tools). Underneath
both: a real Postgres execution error — a hallucinated table, an ambiguous
column — had no recovery at all, unlike `guard_sql`'s own rejection, which
already got one re-plan. `run_query` now re-plans once on a `run_sql`
failure the same way, and the chat `run_sql_query` tool returns a failed
tool result instead of ending the turn, so the model can correct itself
within its own tool-call budget the way `make_chart` already could.

Continued live testing found three more failure modes in Chat and one in
Ask. `search_knowledge`'s `k` argument is a plain `int = 6` in its Pydantic
schema; Llama's tool-calling fills in every schema property rather than
omitting the ones it leaves unset, so it sent an explicit `k: null` — a
default only applies when a key is absent, not when it is `null` — and the
resulting validation error killed the whole turn, leaving Chat silent.
`run_sql_query` had a second failure from the same root: its schema let the
model supply raw `sql` directly, and a general chat model has never seen the
schema, so it hallucinated whole tables (`excise_data`,
`country_liquor_shop`) instead of using the schema-aware planner. And after
a tool call failed, Llama sometimes narrated a second call as literal text —
replying with `run_sql_query(question="...")` verbatim — instead of issuing
a real tool call or answering in prose, so the turn ended showing nothing
but a failed query card and no answer. `k` is now `int | None`;
`run_sql_query` takes only a plain-language `question`, always through the
same schema-aware planner `/query` uses; any tool-call argument error now
returns as a failed tool result instead of raising and ending the turn, the
same way a rejected or failing SQL statement already did; and
`chat/loop.py`'s bare-`{}` retry now also catches a narrated fake tool call,
on the same reasoning (`MCP_ENGINES.md` §Tools). Chat also had no visual
feedback for the gap before the first token or tool call arrived, now filled
with a three-dot typing indicator. Ask had its own version of a stuck turn:
`activeQueryId` lived only in the Livewire component's in-memory state, with
no URL behind it, so navigating away and back could leave the stage spinner
showing a query as still running after the orchestrator had actually
finished. Ask questions now live at their own URL (`/ask/{query}`, the same
pattern `/chat/{conversation}` already uses) and a "Recent questions" rail
lists the last 20, so leaving and returning always re-mounts from the
database instead of whatever was on screen when the user left.

Live testing also surfaced two more wrong-but-not-erroring SQL answers and a
slow-turn complaint. "How many composite/country-liquor shops in Lucknow in
August 2026" twice generated `SELECT ... FROM analytics.shops WHERE
created_at >= ...` — a syntactically valid query against the wrong table,
since `shops.created_at` is an ETL load timestamp, not a business date, and
silently returned zero instead of erroring. `schema_card.py`'s `VIEW_NOTES`
already said not to do this; `guard_sql` now rejects the pattern outright
(`analytics.shops` joined with a `created_at`/`updated_at` filter) and
reprompts, the same retry a rejected statement already gets
(`sql/guard.py`). Separately, a full chat turn needing a tool call was
taking 1–3 minutes: `OLLAMA_MAX_LOADED_MODELS=1` evicts the coder model to
load the chat model back in (or the reverse) on every swap within a single
turn. `EVALUATION.md` §2 already priced pinning both models at once
(~12–13 GB against this box's 30 GiB) as the fix for exactly this;
`OPERATOR_SETUP.md` §Ollama runtime settings has the command to apply it.

A desktop "application was stopped because the machine ran out of memory"
notification during this same testing traced back to two separate things,
not one. Most of it was `test_sandbox.py::test_memory_cap` doing exactly
what it is supposed to: it deliberately allocates past a 64 MB cap inside a
real sandbox cgroup to prove the memory limit actually kills a script, and
GNOME surfaces that real kernel OOM-kill the same way it would an accidental
one. The one genuine gap it surfaced alongside that: a `systemctl restart`
of the orchestrator while a chart render was in flight left that render's
`excise-sandbox-*.scope` running past the orchestrator's own death, holding
its memory cgroup until it happened to hit its cap on its own several
minutes later. `run_in_sandbox` now kills the sandboxed process immediately
on cancellation, and a startup sweep stops any `excise-sandbox-*.scope`
still active from a run that ended in a `SIGKILL` instead of a clean
shutdown (`SECURITY.md` §2 After the render).

Three usability gaps followed from hands-on use. Neither Chat nor Ask let a
message or a query result be copied — no message on either page ever had a
copy affordance, only the generated-SQL panel did. Both now carry a small
copy button, the same pattern the SQL panel already used. Chat also had no
way to stop a turn once sent, and stopping the browser's own `fetch()` alone
would not have been enough: `ChatController::send()` relays the
orchestrator's stream in a plain PHP loop with nothing checking whether the
browser was even still there, so it kept driving the (expensive, CPU-only)
Ollama call to completion regardless. The orchestrator's own turn-loop
cancellation already existed (`MCP_ENGINES.md` §Chat and retrieval) — this
was the missing link. The composer's send button now turns into a Stop
button mid-turn (an `AbortController` on the fetch), and `send()` checks
`connection_aborted()` on every relayed event and stops relaying the moment
the browser disconnects, which is what actually reaches the orchestrator as
a disconnect and cancels the in-flight call. And neither conversations nor
questions could be removed at all. Both now get a soft delete (reversible,
the Eloquent default) and a permanent delete from a per-item menu on their
rail — permanent delete also clears the chart artifact and its rendered
files, which carry no database-level foreign key to their owner and would
otherwise be left behind.

A live Chat turn surfaced one more shape of the tool-calling reliability gap:
a real `run_sql_query` call succeeded, but the model's follow-up turn came
back with no content at all, on both the tool-aware attempt and the
`tools=[]` retry — the user was left looking at a tool call card with no
answer and no chart, since `make_chart` is also the model's own choice and
it never got the chance to make one. `CHAT_SYSTEM_PROMPT` already says never
to let a tool result be the last thing in the turn, but that's a request the
model can silently fail, not a guarantee; `chat/loop.py` now falls back to
the tool result's own summary as the turn's answer when both attempts come
back empty (`MCP_ENGINES.md` §Tools).

Chat gained an explicit way to ask for a chart. `CHAT_SYSTEM_PROMPT` already
limits `make_chart` to a call the model makes "only when a chart would
help," so a single-number answer correctly gets no chart — but that leaves
the request to make one entirely up to the model's own judgment. The
composer's new chart toggle turns that judgment call into an explicit ask
for one turn: checking it appends "Please include a chart to visualize the
answer." to the copy of the message sent to the orchestrator; the message
that `messages` stores and the transcript shows stays exactly what was typed
(`ChatController::send`). The toggle first shipped on the same deferred
`wire:model` the composer's textarea uses, which left its own on/off state
invisible on click — a deferred binding only reaches the server on the next
network round trip, and a lone checkbox click causes none. `wire:model.live`
fixed that, and the active state is now a solid fill matching the send
button's own convention.

`shops` mutates in place from each IESCMS import, so nothing on the row
itself says which reporting month its current state reflects — only
`created_at`/`updated_at` (ETL load time, already the business date
`guard_sql` rejects, above). A future monthly source that carries no per-row
date at all — a shops roster, a monthly revenue/quota/enforcement figure —
would have no period to record. `etl.source_registry.requires_period`
and `etl.ingestion_runs.report_period` give such a source a place to state
its month explicitly (`etl sync --source NAME --period 2026-08`), recorded
on the run's own row instead of left to whenever the script happened to
execute; `etl/etl/run.py` refuses to run a `requires_period` source with no
`--period` given (`DATA_PIPELINE.md` §Periodic sources without a per-row
date). `iescms_dispatch` itself needs none of this, since its rows already
carry real dates — no source needs it yet, so this is groundwork for
whichever one lands first. The period-stamped history table a mutate-in-place
target would eventually need — `shop_years` already answers the equivalent
question at financial-year grain — gets built alongside that source, once
one is scoped.

The chart toggle's switch had a second bug past its wire:model one: Tailwind's
`peer-checked:*` only applies through a CSS sibling selector, which needs the
element carrying it to be a direct sibling of the `.peer`-marked checkbox —
the toggle's thumb `<span>` was nested inside its track `<span>` instead, a
sibling of a sibling, so clicking it tinted the track blue but never slid the
thumb. Both spans are now direct siblings of the checkbox under one
positioning wrapper. Separately, live testing found a fifth shape of Chat's
tool-calling reliability gap: asked for two metrics in one question (revenue
and volume together), Llama skipped `run_sql_query` and wrote its own guessed
SQL against a table that doesn't exist, narrated as "let me try running the
following query" — the same class of failure as the narrated-fake-call and
bare-`"{}"` cases, just a longer preamble before the fake content
(`MCP_ENGINES.md` §Tools). Fine-tuning the chat model on this app's own
transcripts came up as an alternative fix and is declined for now — every
shape of this failure so far has closed with a prompt-wording change plus a
matching `chat/loop.py` retry, not a retrain (`EVALUATION.md` §Right-sizing
item 16).

That fifth-shape fix immediately caused a live regression of its own: it
withheld the guessed SQL from the stream entirely while deciding whether to
retry, which meant sending nothing at all to the browser for the whole
length of that generation plus the retry — long enough on a real turn that
the connection dropped as interrupted before the correction ever streamed,
and the composer sat on its typing indicator the entire time with nothing
to show for it. A fenced sql block can't be told apart from ordinary prose
until most of it has arrived, unlike the bare-`"{}"` and narrated-call
checks either of which resolve within a few characters, so holding it back
costs a lot more silence for the same guard. `chat/loop.py` now only checks
for a fenced sql block once a turn's full text is in, deciding whether to
retry, and no longer withholds it from the live stream while that decision
is pending — the guessed SQL streams as it always did, and the correction
follows right after it (`MCP_ENGINES.md` §Tools).

Phase 5's last piece, the customization panel, is built: a FAB on every
authed screen opens a Display panel — theme, font, text size, line spacing,
content width, table density, accent, high contrast, reduce motion — applied
through `data-*` attributes and a handful of CSS custom properties, with
`users.ui_prefs` as the durable copy behind a `localStorage` + cookie fast
path. The Tailwind config routes the `govviolet` palette through `--accent-*`
CSS variables instead of literal hex, so an accent choice swaps which ramp of
values those ten variables hold, and every existing `govviolet-*` utility
across the app repaints with it — no change needed to the ~20 files that use
them. The two accent options, govviolet and govsaffron, are the department's
own two-tone palette, already part of the design system. Theme keeps its own
`color_scheme` key, separate from the `ui_prefs` JSON, so the sidebar's
light/dark toggle and the panel's three-way theme control read and write one
shared piece of state. Reduce motion is a single CSS rule keyed to a
`data-reduce-motion` attribute, so it also quiets Chat's bounce-dot typing
indicator with no extra code there.

Milestone 5's checklist is now fully built: money formatting, chart export,
the query ledger, and an admin ETL visibility screen. `App\Support\Money`
formats a rupee figure in rupees, thousands, lakh, or crore, with the
Indian digit grouping `number_format()` doesn't produce on its own;
`<x-money>` renders all four and switches between them with a plain Alpine
`x-show`, and `<x-currency-input>` (ported from `excise-budget-tracker`) is
the matching form input. Neither screen currently on `web/` shows a money
figure or takes one as input, so this ships as ready infrastructure with no
caller yet, the same position `Carbon::macro('ist')` was in before Phase 4's
admin screens started calling it. Chart export reuses
`engines/static_render.py`'s already-running persistent-browser renderer —
a new `POST /chart/render` hands it an already-produced Plotly figure and
returns PNG/SVG/PDF bytes, with no second render path and no LLM-authored
code anywhere near it. Ask's and Chat's chart cards both gained export
links. The query ledger replaces the placeholder `/ledger` route with a
real Livewire screen listing every past `/query`; an Analyst sees their own
questions, an Admin sees everyone's. The admin ETL screen
(`/admin/etl`, privilege `etl.view`) lists `etl.ingestion_runs` and a run's
`etl.quarantine` rows through two new orchestrator routes,
`GET /etl/runs` and `GET /etl/quarantine` — the same pattern
`GET /kb/documents` already established for a read-only admin browse
screen. `excise_ro` had no grant on schema `etl` at all before this
(`db/roles.sql`'s comment called it out explicitly: "excise_ro must not see
the base data or write anywhere," lumping `etl`'s bookkeeping tables in
with the base data it ingests into). The new grant covers only `etl.ingestion_runs` and `etl.quarantine` — the
audit trail of what a run wrote and skipped — and `db/roles.sql` now
includes it, but this box's database was already provisioned from an
earlier run of that file, so the grant is a pending `sudo -u postgres` step
(`OPERATOR_SETUP.md` §Data bank) rather than something already live. The new
screen shows a clear fallback banner until that step runs.

A compound Chat question — comparing two shop types' counts alongside their
sales in amount and volume in one turn — surfaced a connection-level failure
distinct from every earlier tool-calling gap: the browser's own `fetch()`
died mid-stream with no ndjson `{"error": ...}` line to show, since a
question needing several full `run_sql_query`/`make_chart` round trips can
run past 300 seconds before the orchestrator gets the chance to send one.
`OLLAMA_MAX_LOADED_MODELS=2` (above) was already live, confirming both
models stay resident through the turn — the delay is the turn's own length,
not a model reload. A single fixed request-duration cap has no right size
here: a genuinely compound question can always need one more tool call than
whatever ceiling was picked. `EVALUATION.md` already gives the matching
reasoning for right-sizing generally. `run_chat`
(`orchestrator/app/chat/loop.py`) now sends a `{"ping": true}` line every
15s a tool call is still running — `_dispatch_with_heartbeats` runs
`dispatch()` as a background task so the loop can keep yielding pings while
it's in flight — the same keep-alive pattern a streaming tool-calling API
relies on generally: the wire stays live off periodic bytes. A total-duration
guess is never sized right for every turn. `OrchestratorClient::chatStream()`'s
Guzzle timeout is uncapped to match, with `read_timeout` (45s) catching a
genuinely dead connection. Apache's `mod_php max_execution_time` (this app
has no FPM pool) becomes a backstop against a truly hung request instead of
the turn-length budget itself. `deploy/apache-vhost.conf` sets it with
`php_admin_value`, scoped to this app's own vhost: the shared
`/etc/php/8.5/apache2/php.ini` also serves the four sibling apps on this
same Apache instance, so an edit there would move their ceiling too — a
pending `sudo` step (`OPERATOR_SETUP.md` §Apache PHP execution timeout)
since Claude has no passwordless sudo on this box.

With the connection no longer dying first, the same compound question
surfaced the turn's actual next failure: every `make_chart` call rejected
itself with "data_ref must point at this conversation's last run_sql_query
result." `MakeChartArgs.data_ref` asked the model to restate the
conversation's own id as a match check against `conversation_id` — but the
model is never told that id anywhere, not in `CHAT_SYSTEM_PROMPT`, not in
the message history, so no real call could ever supply the one value that
would pass. The lookup was always scoped by the trusted `conversation_id`
`dispatch()` receives from the request itself, never by anything the model
supplies, so the check guarded nothing a mismatched value could actually
have exploited. `data_ref` is gone from `MakeChartArgs`; `make_chart` now
takes only the plot script (`MCP_ENGINES.md` §Tools).

Asked to find other tool arguments in the same shape — the model required to
supply something it was structurally never given — one more turned up: a gap
in what the model is told, milder than `data_ref`'s always-fails bug.
`/query`'s `plan_plot` stage hands its planning model an explicit capability
string per engine before it writes a line of script: a pandas `df` is
already loaded, the exact
`fig.write_json(...)` call, that `fig.write_image()` is forbidden
(`llm/prompts.py`'s `_ENGINE_CAPABILITIES`). `make_chart`'s tool description
said only "chart the most recent result" — the chat model authoring `spec`
had no equivalent contract, so a plausible chart script (matplotlib's
`plt.savefig()`, a real option `/query` itself offers) could pass through
looking reasonable and still produce nothing, since chat always fixes
`outputs=["plotly_json"]` and only ever collects that one file. The tool
description now states the same `df`/`OUT`/forbidden-`fig.write_image()`
facts `_ENGINE_CAPABILITIES` already gives `/query`, plus the one fact
specific to chat: only the `fig.write_json()` path is collected here.
`llm/prompts.py` notes the two must be kept in sync by hand if the sandbox
contract itself changes, since chat's fixed single output means it can't
reuse `_ENGINE_CAPABILITIES` text as-is.

A screenshot of the live Chat page surfaced three interface problems past
what the test suite checks for. The per-conversation menu (delete, permanent
delete) sat at `opacity-0` until hover, in a `p-1` hit target — invisible by
default and small once found, in both `chat.blade.php`'s rail and
`ask.blade.php`'s identical one. Both now keep it dimly visible at rest,
brighten on hover or focus, and give it a full `w-7 h-7` target. Chat's empty
state reused `.stat-card`, the bordered widget style the dashboard's stat
tiles use; sitting right above the composer's own "Ask anything..."
placeholder, it read as a second, self-contained input. It's unboxed now —
an icon and a line of text, no border — with copy that names the composer
directly: "Type a question below to begin." The Visualize toggle reset
itself the moment a message was sent, before there was any way to tell the
send had picked it up. `includeChart` (`Chat.php`) now holds its value the
way the model picker beside it does — a standing choice for the composer,
kept until the person using it changes it themselves.

The same rail's menu had two more bugs that visual opacity alone didn't fix.
It was `position: absolute` inside the rail's own `overflow-y-auto` div, so
opening it on a row near the bottom grew the rail's scrollable content
instead of showing a floating menu — the list visibly jumped to make room.
Both rails now put the menu in a `<template x-teleport="body">`, positioned
`fixed` from the trigger button's own `getBoundingClientRect()` at open
time, opening upward when there is not 90px of room below — it floats over
the page and never touches the rail's scroll height. Separately, the trigger
button sits on top of the row's own link with nothing stopping a click from
reaching past it, so the button's handler now carries `.stop.prevent`.
Neither row's `<div>` carried a `wire:key` before this either — every other
keyed Livewire loop in this app has one (`query-ledger.blade.php`'s rows,
for one) — and a teleported node makes that matter more than it already
did, so both loops key each row on the conversation/query id now.

A live report of the same conversation getting stuck again traced to a
different cause than any code bug: `excise-orchestrator.service` had been
running since 2026-09-19, well before all three of that day's orchestrator
fixes (the heartbeat pings, `data_ref`'s removal, `make_chart`'s script
contract) — a `systemd --user` service does not pick up new code on its own,
`web/`'s plain PHP files do on every request. The mismatch made the specific
symptom worse: the new PHP-side fix traded a blunt 300s total-duration cap
for a 45s *silence* cap, sized on the assumption the orchestrator's own
heartbeat would keep the wire fed — running the old code with no heartbeat,
a single slow step (the coder model planning SQL for a compound question)
could go quiet past 45s and get cut sooner than the old 300s cap would have
allowed. `OPERATOR_SETUP.md` gains no new step for this — restarting a
`systemd --user` service after an orchestrator code change is not itself a
milestone step, it is the standing operator action a code change like this
always needs; `systemctl --user restart excise-orchestrator` is a pending
`--user` service restart Claude documents rather than runs, per this file's
own hard constraint.

The five browser `confirm()` dialogs (`wire:confirm`, on conversation/query
permanent-delete, knowledge upload withdraw, Google disconnect, and user
deactivate) are now SweetAlert2 popups instead, matching the styled-confirm
convention the sibling apps already use. `php-flasher/flasher-sweetalert-laravel`
is the new dependency — a second php-flasher plugin package alongside the
toast one already installed, sharing the same `@flasher_render` bootstrap,
so it needed nothing beyond `composer require` + `php artisan flasher:install`
to publish its assets. `ConfirmsWithSweetAlert`
(`app/Livewire/Concerns/`) is the reusable half: a component calls
`confirm($method, $arg, $message)` from its own trigger method in place of
`wire:confirm`, and a trait-provided `#[On('sweetalert:confirmed')]` handler
calls `$method($arg)` once SweetAlert2's own confirm button is clicked — the
method name and its one argument ride through as `sweetalert()` options,
read back off the event's `envelope.options` on confirm. That exact wire
shape (`envelope.options`, not a top-level payload key) came from reading
the installed package's own JS and PHP source directly, not the docs, which
show the calling pattern but not the shape a listener actually receives.
Building it caught two bugs before either shipped: `sweetalert()->question()`
sets the dialog's icon and message but never queues the notification on its
own — only a terminal call like `warning()` does, ending its own internal
chain in `push()` — so `confirm()` had to end there instead, a mistake a
live click never would have surfaced as anything but "nothing happens";
and the trait's own `confirm()` needed to be `public`, not `protected`, to
be reachable from `wire:click` at all, the same visibility `wire:click`
already needs on every other component method. Both surfaced from a real
test exercising the actual installed package rather than a mocked one —
`Livewire::test()`'s own `->call()` never sets the `X-Livewire` header
`isLivewireRequest()` checks, so the bridge that turns a queued envelope
into a `flasher:render` browser event never fires under it; the test for
`confirm()` itself uses a plain object with the trait instead, sidestepping
that gap rather than working around it.

An admin data dictionary followed a request to make it easier to tell the SQL-planning
model what a table or column actually means, and to see the schema itself from the UI.
`schema_card.py`'s `VIEW_NOTES` already carried this kind of note, but as a fixed
table-level dict in the orchestrator's own source — changing one meant a code change and
a restart, and there was no per-column equivalent at all. Admin -> Data dictionary
(`schema.manage`) now lists every `analytics.*` table and column from a new
`GET /schema/tables` (the orchestrator's own read-only introspection of
`information_schema.columns`, the same query `render_schema_card` already ran), with an
editable note per table and per column. A note is saved to web/'s own `schema_notes`
table, since web/ has no Postgres connection of its own to write anywhere else. The
orchestrator reads them back over a new `GET /api/schema-notes` on web/ — every earlier
orchestrator/web/ call has run from web/ into the orchestrator, so this is the first one
running the opposite direction — gated by the same shared bearer token web/'s
`OrchestratorClient` already sends outbound, and
merged into `VIEW_NOTES` at the next `render_schema_card` call (`schema_card.py`'s
`fetch_note_overrides`). web/ being unreachable or the table empty degrades to `VIEW_NOTES`
alone, not a startup failure. "See the database" is `GET /schema/tables/{name}/sample`,
five rows from the named view — `table_name` is checked against `information_schema.tables`
first, so only a name that already exists in the schema this endpoint just listed can ever
reach the interpolated query after it. Notes reach the model only on the orchestrator's
next start; `OPERATOR_SETUP.md`'s existing restart-after-a-code-change guidance covers this
the same way it covers `VIEW_NOTES` itself.

A live retest of the earlier compound-question fix — heartbeat pings, an
uncapped Guzzle timeout, a generous `max_execution_time` — still dropped
mid-turn through the real Cloudflare Tunnel, on the same comparison-plus-
sales question that fix was written for. The Apache access log showed only a
couple KB delivered on a turn that ran over two minutes server-side; the
browser never saw the stream start at all. The shared php.ini's
`output_buffering = 4096` was the reason: `ChatController::send()`'s
`ob_flush()`/`flush()` calls only empty PHP's own buffer into that one, so a
15s heartbeat ping sits there instead of reaching the socket until 4KB
accumulates, and Cloudflare reads the resulting silence as a dead connection
regardless of how generous `max_execution_time` is. `output_buffering` is
`PHP_INI_PERDIR` — `ini_set()` in application code cannot turn it off, only
a php.ini, `.htaccess`, or vhost directive can — so `deploy/apache-vhost.conf`
now sets `php_admin_value output_buffering 0` alongside
`max_execution_time`, same scope, same reason (`OPERATOR_SETUP.md` §Apache
PHP execution timeout), applied live with `sudo bash deploy/root-setup.sh` —
the vhost and `/health` both confirmed the setting is live; the next
compound question through the real tunnel URL is the actual test of it.

That next question dropped the same way, on a fresh conversation — the
`output_buffering` fix was real but not the actual blocker. Timing raw event
arrival directly (a standalone script hitting the orchestrator with the
exact code `OrchestratorClient::chatStream()` ran) showed every single
event of a two-minute turn, pings included, landing at the same timestamp:
the whole response arrived in one burst when the connection closed, never
progressively. Guzzle's `stream => true` — the option the original
implementation relied on for this, in every handler it has (curl, its PHP
stream-wrapper fallback, with or without Laravel's own `Http` facade
wrapping it) — buffered the entire orchestrator response before releasing
any of it. A plain `curl` CLI call to the same endpoint streamed normally;
no PHP variant of the identical request did.
`app/Services/CurlOrchestratorStream.php` now drives PHP's own curl
extension directly instead — `CURLOPT_WRITEFUNCTION`, polled through
`curl_multi_exec`, delivers each chunk as it lands on the socket, the same
mechanism the curl binary itself uses. `OrchestratorClient::chatStream()`
and `runQuery()` (the same buffering bug sat in `/query`'s relay too, just
less visible — `RunExciseQuery` is a queued job with a 300s total-duration
cap, not a live browser connection with a heartbeat to defeat) both go
through it now, behind a small `OrchestratorStream` interface — the only
reason for the interface at all is that `Http::fake()` cannot intercept a
raw curl call, so a test binds a fake implementation in its place instead
(`MCP_ENGINES.md` §Streamed events). Verified against the real app end to
end, not just in isolation: a scripted request carrying a genuine
authenticated session, posted straight at `ChatController::send()` through
the live Apache vhost, showed a `tool_call` at 21.7s and pings at 36.7s and
51.7s — exactly the 15s cadence the design calls for, for the first time
confirmed the whole way from `run_chat` to the browser's own connection.

The connection fixed, the same live question surfaced a data-modeling gap
behind the SQL error underneath it: asking for a specific month's sales in
amount and volume by shop category kept failing on a hallucinated
`shop_id`/`dispatch_id` column against `analytics.sales_volumes`, since
that view (and `analytics.revenues`) has no shop-level or monthly
granularity at all — it's aggregated by district, financial year, and
license category only. `VIEW_NOTES` now says so for both and points at
`analytics.dispatches` instead, which already carries `duty_fee_inr` and
the `dispatched_*` volume columns at exactly the granularity a month- or
shop-scoped question needs (`DATA_PIPELINE.md` §Row visibility for the AI
path). Past that, a real `run_sql_query` failure surfaced a second gap in
the retry that was supposed to cover exactly this: the `tools=[]` retry
streamed every chunk unconditionally, with none of the bare-`"{}"`/
narrated-call holdback the first attempt already has, so when the retry
also narrated the same fake call after a failed SQL statement, nothing
caught it before it reached the user. The retry now gets the same per-chunk
check, and the fallback for a still-degenerate retry changed too: a failed
tool's raw `summary` (`column sv.shop_id does not exist`) meant nothing
shown as a stand-alone reply to someone who didn't ask a SQL question, so
`_tool_failure_fallback` states the failure in plain terms first and keeps
the technical detail after it — a successful call's summary is unchanged,
since it already reads fine on its own (`MCP_ENGINES.md` §Tools). Ask's own
failed-query box gets the same plain-terms-first treatment, with the
technical `error_message` kept as supporting detail underneath it.

Both Ask and Chat also gained a small set of example questions on their
empty state — three each, verified directly against the real August 2026
Lucknow import before being shown as "try an example," not written from
guessing what the data probably contains. Clicking one fills the composer
(and, on Chat, sets the chart toggle where the example calls for one)
without submitting it, so a first-time visitor sees the pipeline answer a
real question with one click and can still edit it first.

## What this project is

An on-premise conversational analytics tool for UP Excise departmental figures
(revenue, dispatches, shop quotas, enforcement). A user asks a question in
plain language; a local LLM turns it into a read-only SQL query against a
PostgreSQL copy of the excise data, runs a short analysis/plot script, and the
web UI shows the chart, the table, and the generated SQL.

Two more capabilities sit on the same LLM and UI:

- **A knowledge base.** The model can pull up UP Excise acts, rules,
  regulations, and policies — the verified Markdown already published in
  `~/Sites/pdf-markdown-pipeline` (`docsrepo.exciseup.in`, public + verified
  documents only) — and admins can upload further `.md` files (rule notes,
  circulars). Questions that are about the law rather than the numbers are
  answered from this corpus; questions that need both get both. See
  `DATA_PIPELINE.md` §Knowledge base and `MCP_ENGINES.md` §Chat and retrieval.
- **A general chat window**, OpenWebUI-style: streaming conversation with the
  local model, conversation history, markdown/code rendering. The model calls
  tools from inside the chat — `search_knowledge`, `run_sql_query`,
  `make_chart` — so the same data-lake and knowledge access is available
  conversationally, not only through the one-shot analytical form. Built
  natively in Livewire against the orchestrator's streaming endpoint; no
  Docker, no embedded OpenWebUI (`EVALUATION.md` §Chat integration).

It sits alongside the four existing departmental Laravel apps on the office AIO
(`~/Sites/infra-notes/laravel-apps-deploy.md`) and follows their deployment
pattern: Apache vhost on a private port, one named Cloudflare Tunnel, systemd
`--user` units for workers.

## Hard constraints (do not violate)

- **No DeepSeek models.** Any family, any quant, any purpose. The model is
  chosen in `EVALUATION.md` from Llama 3.1, Qwen 2.5, or Gemma 2 only. The
  embedding model is also local (Ollama), also not DeepSeek.
- **No unsandboxed code execution.** Every LLM-generated script (Python,
  Octave, anything) runs under the sandbox in `SECURITY.md` — non-root user,
  `bwrap` namespace, no network, writable path limited to one scratch dir,
  wall-clock and memory caps. A script never runs directly on the host.
- **No root or write access to Postgres for the AI path.** The orchestrator
  connects as a dedicated `LOGIN` role with `SELECT` only and
  `default_transaction_read_only = on`. `INSERT`/`UPDATE`/`DELETE`/`DDL` are
  refused by the database engine, not by a string filter in application code.
  This holds whether the SQL comes from the one-shot form or from a tool call
  inside the chat — same read-only role, same guard, same sandbox.
- **The knowledge base is read-only to the AI path too.** `kb.*` is granted
  `SELECT` to the read-only role. Ingestion (pdf-markdown-pipeline sync,
  admin `.md` uploads) writes through the ETL role only. The model retrieves
  from `kb.*`; it never writes to it.
- **No document or query leaves the box.** Retrieval, embedding, inference,
  and plotting are all local. The only outbound network is the Cloudflare
  Tunnel (serving the UI) and, when a user has connected Google, the Google
  Drive/Sheets/Docs API for ingestion — nothing else.
- **Google OAuth tokens are encrypted at rest and never logged.** Refresh
  tokens are stored `Crypt`-encrypted per user; access tokens are short-lived
  and in-memory. A disconnect deletes the stored token. See `SECURITY.md`
  §Google OAuth.
- **No secrets in `.env` for anything that can live elsewhere.** The
  Laravel↔orchestrator bearer token and the Postgres read-only password are the
  two required secrets; both go in the respective `.env` files, never
  committed. Perms differ by who reads the file: `orchestrator/.env` and
  `etl/.env` are read only by their own `subhan`-owned process, so `600`.
  `web/.env` is read by Apache (`www-data`), which is a secondary member of
  the `subhan` group on this box — `664` (group-read), matching every sibling
  Laravel app's live `.env`, not `600` (`600` blocks Apache from reading it
  at all — confirmed the hard way deploying this app's own vhost). Google
  service-account JSON is referenced by path, never inlined.
- **No new Cloudflare zone.** This box's `cert.pem` only covers `exciseup.in`.
  Use a subdomain of it.
- **Claude has no passwordless sudo here.** Anything under `/etc`, any
  `systemctl` beyond `--user`, any service restart: write the exact commands in
  the relevant doc and stop. Do not work around it with a copy-elsewhere hack.

## Repository layout

`web/` and `db/` exist; `orchestrator/`, `etl/`, `deploy/`, and
`OPERATOR_SETUP.md`'s later sections arrive with their milestones.

```
excise-mcp-dashboard/
  web/            Laravel 13 + Livewire 4 app (analytical form + chat window + admin)
  orchestrator/   Python 3.12 FastAPI service (MCP client, tool loop, engine router,
                  SQL + knowledge retrieval + streaming chat)
  etl/            Python ingestion jobs:
                    - Sheets / Drive / Docs / Excel / CSV -> Postgres data tables
                    - pdf-markdown-pipeline verified docs + admin .md uploads -> kb.*
  db/             SQL: schema (data + kb), read-only role grants, seed reference data
  deploy/         Apache vhost, cloudflared config, systemd --user units + timers
  docs/           this set of Markdown files
  OPERATOR_SETUP.md   every sudo / install / Google-console step, copy-pasteable
```

Three deployable units (`web`, `orchestrator`, `etl`) in one repo. Keep them in
one repo while the interfaces are still moving; split later only if a second
consumer appears.

## Decisions (why the build looks like this)

- **Chat window: native Livewire.** OpenWebUI is a separate Svelte app with
  its own database and needs Docker (absent). What is wanted is its UX —
  streaming, history, markdown/code rendering, a model picker — which Livewire
  + Alpine + a streamed ndjson response from the orchestrator cover. All LLM logic (chat
  loop, tool calls, retrieval, SQL) stays in the Python orchestrator; `web/`
  renders and streams. If the LLM logic ever moves to PHP, `prism-php/prism`
  is the package to use, replacing the Python orchestrator rather than running
  beside it. Running OpenWebUI itself in Docker against the orchestrator's
  OpenAI-compatible endpoint stays a documented backlog option.
- **Real-time transport: plain HTTP streaming now, Laravel Reverb the
  documented upgrade.** Chat already streams live token-by-token over a
  `fetch()` + `ReadableStream` reader against an ndjson response — no
  WebSocket server needed for that. A genuine broadcast need (two people
  watching the same conversation update live, say) is the trigger to add
  one, not before; the Cloudflare Tunnel this box runs behind is meant for
  testing and proof-of-concept work, with a dedicated server planned later,
  and standing up a WebSocket server through a tunnel today would be
  infrastructure ahead of any actual need. Reverb, specifically, over Pusher
  or Ably — self-hosted and first-party, so it stays inside the no-egress
  rule the same way everything else here does.
- **Retrieval: Postgres full-text search first, `pgvector` as the documented
  upgrade.** The policy/acts corpus is small (a few hundred verified docs).
  Built-in `tsvector` + `websearch_to_tsquery` needs no extension and no
  embedding model. Add `pgvector` + a local embedding model only if FTS recall
  proves weak on real questions — the `kb.chunks` table carries a nullable
  `embedding` column from day one so the switch is additive. `EVALUATION.md`
  §Retrieval.
- **Google access: OAuth (user-delegated) alongside the service account.** The
  service account covers server-owned sheets. OAuth via `laravel/socialite`
  lets an analyst connect their own Drive / Sheets / Docs. Both feed the same
  ETL adapters. `DATA_PIPELINE.md` §Google sources, `SECURITY.md` §Google OAuth.
- **Knowledge base lives in the Postgres data bank (`kb` schema), not in
  `web/`'s MariaDB.** The orchestrator already has a read-only Postgres
  connection; retrieval is one more `SELECT`. Keeps all model-facing data in
  one place behind one read-only role.
- **Multiple models, one orchestrator, no agent framework.** The build already
  runs more than one local model: `qwen2.5-coder:7b` plans and writes SQL and
  plot scripts, `llama3.1:8b` converses and summarises, and the
  `config/models.php` registry lets an admin add Gemma or another allowed tag
  and pick it per request. That is the multi-model need met — a config
  registry, a per-task default, and a validated picker. A multi-agent
  framework (CrewAI, AutoGen, Semantic Kernel, LangGraph) is declined: it adds
  a heavy dependency with default outbound telemetry against the no-egress
  rule, assumes cheap parallel API fan-out that one local Ollama with
  `OLLAMA_MAX_LOADED_MODELS=1` cannot give, and replaces a bounded, logged
  tool loop with an unbounded delegation graph over the same guard and sandbox
  surface. If a decompose-run-synthesise "research" mode is ever needed, it is
  a sequential loop inside the existing orchestrator with a step cap, reusing
  the one Ollama client and the existing tools. `EVALUATION.md` §Right-sizing
  item 13, `MCP_ENGINES.md` §Structured-output loop.
- **Memory: the stores already in the design; the model never writes memory.**
  The chat already has three memory spans — the in-process working set of
  recent turns, the durable resumable transcript in `web/` MariaDB
  (`conversations` / `messages` / `message_tool_calls`), and the `kb.*`
  knowledge corpus retrieved by FTS. A per-analyst `user_memory` table (a
  human-curated glossary and defaults, prepended to that user's chat prompt) is
  the one worthwhile addition and is a table plus a `SELECT`. Agent-memory
  frameworks (Letta/MemGPT, Mem0, Zep, cognee) are declined — a server or a
  heavy dependency, some with default telemetry, built around self-editing
  memory the model should not have. `EVALUATION.md` §Right-sizing item 14,
  `MCP_ENGINES.md` §Memory.
- **Tool-calling reliability: fix the prompt and add a retry, don't fine-tune
  the model.** Every tool-calling breakdown found in live chat use so far —
  a bare `"{}"`, a narrated fake call, a hallucinated `null` argument,
  guessed SQL written as prose — has closed with a `CHAT_SYSTEM_PROMPT`
  wording fix plus a matching `chat/loop.py` retry, not a retrain.
  LoRA/QLoRA fine-tuning is declined until that pattern stops working: it
  needs a labeled dataset (no real transcript volume yet), training-grade
  GPU headroom, and its own eval harness — a project on its own, for a
  problem that a one-line prompt change has closed every time so far.
  `EVALUATION.md` §Right-sizing item 16, `MCP_ENGINES.md` §Tools.
- **XLSX export: `openspout/openspout`, matching the sibling apps.** It is
  already the one Excel library across the Laravel fleet —
  `upexcise-stats-dashboard`'s `ExportService` writes `.xlsx` with it,
  `UP-excise-mailer`'s `RecipientImportParser` reads `.xlsx` with it — real
  OOXML streaming I/O, not an `.xls`/HTML-table export. `web/`'s own
  `ExportService` (Milestone 7, `DATA_PIPELINE.md` §Export) ports the
  sibling's `xlsx()` method rather than introducing PhpSpreadsheet or
  Maatwebsite Excel, neither of which appears anywhere in the fleet. `etl/`'s
  own `.xlsx` ingestion is a separate, already-settled choice: `openpyxl` on
  the Python side (`etl/etl/sources/excel.py`).
- **A periodic source states its reporting month explicitly, as a CLI flag.**
  `etl.source_registry.requires_period` + `etl.ingestion_runs.report_period`
  (`DATA_PIPELINE.md` §Periodic sources without a per-row date): `etl sync
  --source NAME --period 2026-08`, since this app's ETL is a scripted CLI
  (`etl sync`, argparse) run by systemd timers. `excise-budget-tracker`'s
  Livewire grant-import screen is the only sibling app with an equivalent
  period picker — its own free-text `as_of_month`, stamped straight onto the
  fact row it imports — and this port keeps the same idea of asking the
  operator outright, in the shape this app's own ETL already takes. No source
  needs this yet; it exists so the first one that does — a shops roster, a
  monthly revenue/quota/enforcement figure — has a place to put its period
  instead of falling back to `created_at`.

## Laravel conventions (`web/`)

Match the sibling apps — `~/Sites/upexcise-stats-dashboard`,
`~/Sites/UP-excise-mailer`, `~/Sites/excise-budget-tracker` — not generic
Laravel tutorials. Those apps are **Laravel 13 / Livewire 4 / PHP 8.5**, not
the 11/12 + Livewire 3 named in the original brief.

- **Livewire for every screen**, CRUD and admin included — the sibling apps
  (`upexcise-stats-dashboard`, `UP-excise-mailer`, `excise-budget-tracker`) are
  built on Livewire end to end. Full-page Livewire components back every routed
  page, and internal navigation goes through `wire:navigate` so moving between
  pages is an AJAX swap with no full reload.
- **Plain controllers** stay for the routes with nothing to render as a live
  component: the `/health` check, the Fortify email-OTP auth flow (ported from
  `upexcise-stats-dashboard`), file and report downloads, the Google OAuth
  redirect and callback, and cross-app links.
- **Route-model binding on a slug or ULID, never the numeric id.** Query rows
  in the ledger get a ULID (`conversations`, `messages`, `chart_artifacts`).
- **Clean path segments over query strings**, except where a value must be
  bookmarkable (a shared conversation link).
- **`db:provision` is MariaDB-only** (`subhanraj/laravel-db-provisioner`). This
  app's operational store is its own small MariaDB DB
  (`excise_mcp_dashboard_local`, scoped user = db name, never root) for
  sessions, users, the query ledger, and queued jobs. The excise **data bank**
  is separate — PostgreSQL, provisioned by the SQL scripts in `db/`, never by
  `db:provision`.
- **Auth**: Fortify + emailed-OTP login, magic-link onboarding and reset, copied
  from `~/Sites/upexcise-stats-dashboard`'s `App\Http\Controllers\Auth\*`. The
  site is served on a subdomain of `exciseup.in` through a named Cloudflare
  Tunnel, the same as the sibling apps — no Cloudflare Access. The app's own
  email-OTP login is the access gate: every route except the health check is
  behind `auth`, an unauthenticated request lands on `/login`.
- **Middleware**: port `SecurityHeaders` (CSP/HSTS/`X-Frame-Options`/noindex)
  and `LogMutation` (`activity_logs` row per non-GET) from the siblings. Add
  the FastAPI origin and every CDN this app uses to the CSP allowlist
  explicitly — Chart.js / Plotly, `marked` + highlighter, `cleave.js`, `dexie`,
  all from jsDelivr.
- **Data stores**: MariaDB (`excise_mcp_dashboard_local`, `db:provision`) is
  the operational store — sessions, users, `activity_logs`, the query ledger,
  chat history, `saved_analyses` / `analysis_runs` / `reports`, `kb_uploads`,
  `google_connections`, the `database`-driver queue. PostgreSQL is the data
  bank only. `web/` never connects to Postgres directly; the orchestrator does,
  read-only.
- **Audit**: every state change and AI action is recorded — `activity_logs`
  (auth events + every non-GET), the `queries` / `analysis_runs` ledger with
  `request_id`, export events, Google connect/disconnect, kb upload/withdraw,
  `etl.ingestion_runs`. Tokens, passwords, and full row sets are never logged.
  `SECURITY.md` §5.
- **Formatting**: store UTC; render every user-facing time in IST
  (`Asia/Kolkata`) via `Carbon::macro('ist')` ported from
  `~/Sites/upexcise-stats-dashboard`. Money shows `₹` with `en-IN` grouping and
  a rupees / thousands / lakh / crore switcher; counts render plain, no
  decimals. Money inputs reuse the sibling Cleave.js `currency-input`
  component (`excise-budget-tracker`).
- **Rate limiters** in `AppServiceProvider`: `login`, `two-factor`,
  `password-reset` as in the siblings, plus `ask` (the one-shot query endpoint)
  and `chat` (per message) keyed by user id — start at 10/min, tune from the
  ledger.
- **Chat UI**: a full-page Livewire `Chat` component. Conversation list in a
  left rail, the active thread in the main pane, a `fetch()` + `ReadableStream`
  reader (not `EventSource`, which is GET-only and would put the message in a
  query string) parsing the orchestrator's ndjson lines and appending
  assistant token deltas. Markdown + fenced code render client-side
  (`marked` + a highlighter from jsDelivr, on the CSP allowlist). Tool calls
  the model makes (`run_sql_query`, `search_knowledge`, `make_chart`) render
  as inline cards — the SQL, the retrieved snippets with links to
  `docsrepo.exciseup.in`, the chart. History persists in `conversations` /
  `messages` / `message_tool_calls`. No streaming LLM logic in PHP — `web/`
  reads the orchestrator's `/chat` ndjson stream and pipes it through.
- **Model picker**: a `config/models.php` registry (`key`, `label`, `role`,
  Ollama tag), mirroring `~/Sites/pdf-markdown-pipeline`'s `config/ocr.php` and
  its "Run OCR" dropdown. The chat composer shows a dropdown of the registry
  entries the orchestrator `/health` reports as pulled; the choice is sent as
  `model` on the `/chat` call and re-validated there. The one-shot form carries
  the same override in an advanced control next to `engine`. Default follows
  the task (coder model for SQL/plot, chat model for conversation); a
  mid-conversation switch costs a model reload
  (`OLLAMA_MAX_LOADED_MODELS=1`) and the UI says so. `EVALUATION.md` §2.
- **Google connect**: `laravel/socialite` + the Google provider with the
  Drive/Sheets/Docs read-only scopes and `access_type=offline` +
  `prompt=consent` for a refresh token. A `google_connections` row per user,
  refresh token `Crypt`-encrypted. An admin "Connected sources" screen lists
  Drive folders / Sheets / Docs to register as ETL sources. `SECURITY.md`
  §Google OAuth.
- **Knowledge**: an admin "Knowledge base" screen — upload `.md` files
  (validated: extension, `<= 2 MB`, filename sanitised, no path segments),
  browse the ingested corpus (pipeline docs + uploads), withdraw an upload.
  Uploads land on a dedicated disk the ETL reads; the screen does not write
  `kb.*` directly.
- **Queues**: `QUEUE_CONNECTION=database` on MariaDB, like the siblings. Long
  calls to the orchestrator run in a job (`RunExciseQuery`, `RefreshAnalysis`,
  report exports), not in the web worker. `--timeout` on the queue worker must
  exceed the orchestrator's own request timeout — follow the `--timeout=1900`
  reasoning in `laravel-apps-deploy.md`. Redis is the documented upgrade if the
  `jobs` table shows contention (`EVALUATION.md` §Right-sizing 10); Kafka /
  Temporal / Airflow are out of scope.
- **Offline (Milestone 7)**: no offline generation — the ask -> SQL -> sandbox
  path needs the server. A Dexie (IndexedDB) read cache keyed on `etl_epoch`,
  ported from the sibling shops-table pattern, holds the conversation list,
  recent messages, and an opened saved analysis / report for offline reading,
  with a "last synced" marker; a question typed offline queues and sends on
  reconnect.
- **Output store**: the data bank (Postgres) is raw data only; charts, tables,
  summaries, and the generated SQL are app artifacts, never written back to
  Postgres. Small and structured -> MariaDB: the chart spec (Plotly JSON in a
  `chart_artifacts.spec` column), `rows_preview`, the SQL, the summary, every
  `saved_analyses` / `reports` row. Large blobs -> the `local` disk: the
  rendered PNG / SVG / PDF and the report exports, with a pointer row. A run's
  files sweep after `ARTIFACT_TTL_DAYS` unless a `saved_analyses` row pins it. A saved analysis
  carries a `recipe` to re-run; each refresh (manual / scheduled / ETL-fired)
  adds an `analysis_runs` row — that history is the trend, shown with the
  sibling `Sparkline`. `reports` order saved analyses + Markdown blocks into a
  presentation. Export a chart (PNG/SVG/PDF/`plotly.json`), a result
  (CSV/XLSX via the sibling `ExportService`, `openspout`), or a report (dompdf PDF / XLSX /
  ZIP bundle, stamped with the ETL vintage). `DATA_PIPELINE.md` §Output store.
- **Tailwind + Alpine**: Tailwind Play CDN and Chart.js / Plotly from jsDelivr,
  same as the siblings. Add every CDN host to the CSP. Chart.js line colours
  follow `design-guidelines.md` §Charts (single series `#4a2bc2`, multi-series
  `#4a2bc2, #c47d00, #0f766e, #b91c1c, #1d4ed8, #7c3aed`).
- **Design system**: follow
  `~/Sites/upexcise-stats-dashboard/docs/design-guidelines.md` — the UX4G
  `govviolet` (`#4a2bc2`) / `govsaffron` palette, Inter, the `@apply` component
  classes and anti-flash theme script from its `head.blade.php`, and the
  Tabler-icon admin shell (`components/layout.blade.php` + `sidebar.blade.php`).
  This is an internal tool: keep the GIGW accessibility baseline (skip link,
  landmarks, one `h1`, `:focus-visible` outline, explicit empty states); leave
  out the sitemap / SEO / JSON-LD surface and the policy-page footer.
- **Customization panel**: a floating control (FAB) that opens a Display panel,
  combining the sibling's reader prefs with `~/Projects/chinese-intel-pipeline`'s
  `CustomizationPanel.tsx` set — theme (system / light / dark), font family
  (small curated catalogue, Inter default, loaded on demand from Google Fonts),
  text size, line spacing, content width, table density (comfortable / compact),
  accent colour (govviolet default + a sanctioned few), high contrast, and a
  "reduce motion" / streaming toggle for the chat. Applied via `data-*`
  attributes + one CSS var, `localStorage` + a cookie for the anti-flash script,
  and mirrored to `users.ui_prefs` (JSON) so it follows the login. A Reset
  button. `EVALUATION.md` §4.
- **Livewire write authorization**: route middleware gates a component's
  mount, but a `wire:click` / `wire:submit` that reaches `livewire/update`
  does not re-run route middleware. Every write method on an admin component
  (knowledge upload, Google connect/disconnect, user CRUD, source-registry
  edits) re-checks the privilege with `abort_unless(...)`, matching the sibling
  dashboard's publish and milestone gates. `SECURITY.md` §3.
- **Branding and chrome**: the brand kit is in `assets/brand/` — the State
  Emblem of Uttar Pradesh (`up-gov-emblem.svg` + the white PNG), the favicons,
  and the app icons. Move it into `web/public/` at Milestone 5. Port the GIGW
  / UX4G chrome from `~/Sites/upexcise-stats-dashboard`'s public layout: the
  "Government of Uttar Pradesh" identity strip, the A- / A / A+ text-size and
  high-contrast toggles (cookie-persisted, no library), the skip-to-main link,
  and the footer policy links. Regenerate the icons and the Open Graph card
  with that repo's `scripts/make-brand-assets.php`. The Department of Excise
  mark renders beside the emblem when
  `web/public/assets/img/excise-logo.{svg,png,webp}` is present.
  `EVALUATION.md` §4.
- **Styling/UX**: split-view is a two-pane flex layout, chat left, canvas
  right, stacking to one column under `lg`. Streaming stage updates
  (`Querying database -> Running analysis -> Rendering chart -> Complete`) come
  from a plain Laravel route the browser polls via `fetch()`, which itself
  polls the job's DB status; fall back to `wire:poll` if the tunnel handles
  the fetch-based polling badly.

## Python conventions (`orchestrator/`, `etl/`)

No FastAPI or Python-service code exists anywhere in `~/Sites` or `~/Projects`
to copy — this is the first. Set the house style here.

- **Python 3.12** (pyenv `3.12.8` is active on the box). One venv per
  deployable: `orchestrator/.venv`, `etl/.venv`. `requirements.txt` with pinned
  versions and a matching `requirements.lock` (`pip-compile` or `uv pip
  compile`). No Poetry/PDM unless a real need appears.
- **PEP 8**, enforced by `ruff` (lint + format — one tool, replaces
  black/isort/flake8). `ruff check` and `ruff format --check` pass before a
  change is done. Line length 100.
- **Type hints on every function signature and dataclass.** `mypy --strict` on
  `orchestrator/app` and `etl/`; a `# type: ignore[code]` needs a reason
  comment.
- **`async def` for all FastAPI route handlers and any I/O** (DB via `asyncpg`,
  outbound HTTP via `httpx.AsyncClient`, Ollama calls). CPU-bound plot
  execution goes through `asyncio.to_thread` or a subprocess, never inline in
  the event loop.
- **Pydantic v2 models** for every request body, response body, tool-call
  argument set, and config block. Tool outputs the LLM must produce are
  Pydantic models exported to JSON Schema and handed to Ollama as the
  `format` / tool schema — the LLM's structured output is validated against
  them on the way back in, and a validation failure is one retry then a clean
  error, never a raw string passed downstream.
- **Config** via `pydantic-settings` from environment / `.env`; no `os.getenv`
  scattered through the code. One `Settings` object, imported once.
- **Logging**: `structlog` to stdout as JSON lines (systemd's journal
  captures it). One request-id per incoming query, threaded through every log
  line and forwarded to Laravel in the response so a ledger row links to its
  logs. No `print`.
- **Errors**: every externally-triggered failure (bad SQL from the LLM,
  sandbox timeout, engine missing, Ollama down) maps to a typed exception and a
  documented HTTP status with a JSON `{error, request_id, stage}` body. The
  web app renders `stage` in the UI.
- **No broad `except Exception: pass`.** Catch what you can handle; let the rest
  surface to the request-id'd handler.
- **Streaming** (`/chat`): FastAPI `StreamingResponse` yielding newline-delimited
  JSON lines (`application/x-ndjson`, matching `/query`'s existing format, not
  `text/event-stream`) — `token`, `tool_call`, `tool_result`, `done`, `error`.
  Generation is cancellable — a client disconnect aborts the Ollama call and any in-flight
  tool.
- **Tool loop**: the chat agent loop lives in `orchestrator/app/chat/`. Tools
  are the same primitives the one-shot pipeline uses (`sql/`, `kb/`,
  `engines/`) — no parallel implementation. Hard cap on tool calls per turn
  (default 4); exceeding it ends the turn with a typed error.
- **Retrieval** (`orchestrator/app/kb/`): FTS query builder over `kb.chunks`
  by default; a `pgvector` code path guarded by `KB_EMBEDDINGS_ENABLED`,
  embeddings via the local Ollama embed model. Retrieval never calls out of
  the box.
- **Embeddings** (when enabled): one pinned Ollama embed model
  (`nomic-embed-text` or `bge-m3`), batched, run in `etl/` at ingestion time
  and in the orchestrator at query time. Dimensions pinned in config and in
  the `kb.chunks.embedding` column type.
- **Google API** (`etl/`): `google-api-python-client` + `google-auth`.
  Auth mode per source — `service_account` (key file path from env) or
  `oauth` (client id/secret + a per-connection refresh token read from the
  operational DB). `google-auth` handles access-token refresh; a
  refresh failure raises a typed "reconnect needed" error, never a silent
  skip.

## Docs, comments, commits

Use the `dev-docs-human` skill (`/dev-docs-human`) for every Markdown file,
code comment, and commit message here — same rule as `~/Sites/infra-notes` and
the sibling apps. State what the code does now; do not narrate how it changed
or frame choices as "X, not Y". Public-facing UI copy (empty states, error
text a non-technical user reads) uses `/general-english`.

Commit messages: imperative subject, body explains why when it is not obvious.
End with the co-author trailer the session is configured for.

## Tests required before a commit

**`web/` (PHPUnit, feature-test-first, model factories):**
- Auth: login, wrong password, wrong/expired OTP, the auth gate, onboarding
  link, password reset — port the sibling `tests/Feature/Auth/*`.
- `ask` flow: a submitted question creates a `conversations` + `messages` +
  `queries` row set; a mocked orchestrator response renders a chart artifact
  and a ledger entry; an orchestrator error renders the failed stage and still
  writes a ledger row.
- Chat flow: a message streams assistant tokens from a mocked orchestrator;
  a tool call in the stream (`run_sql_query`, `search_knowledge`,
  `make_chart`) is persisted and rendered; conversation history loads and
  resumes.
- Model picker: the dropdown lists only registry models the mocked `/health`
  reports pulled; a chosen model rides on the `/chat` call as `model`; a value
  outside the registry is refused.
- Rate limiting on `ask` and on chat message submit.
- Knowledge upload: a `.md` file uploads, is validated (extension, size, no
  path traversal), lands on the ingestion disk, and creates a pending
  `kb_uploads` row; a non-`.md` or oversize file is rejected.
- Google OAuth: the connect redirect carries the right scopes; the callback
  stores an encrypted token and a `google_connections` row; disconnect
  deletes it; a token is never written to logs or returned in a response.
- `SecurityHeaders` present on a sample route; `activity_logs` written on a
  non-GET; an unauthenticated request to a protected route redirects to
  `/login`.
- Customization panel: a changed preference persists across reload (cookie +
  `users.ui_prefs`) and Reset restores defaults; timestamps render in IST.
- The stage-polling endpoint returns the stage sequence for a running job.

**`orchestrator/` (pytest, `pytest-asyncio`):**
- Every tool schema round-trips: model -> JSON Schema -> sample LLM payload ->
  Pydantic validation.
- SQL guard: a generated statement containing anything but a single `SELECT`
  / `WITH ... SELECT` is rejected before it reaches the database; a `SELECT`
  that tries to write (`SELECT ... INTO`, a function with a side effect) is
  caught by the read-only transaction in an integration test against a real
  local Postgres.
- Engine router: an explicit `engine` value picks the right adapter; an
  unknown or unavailable engine returns the typed "engine unavailable" error;
  default is `python`.
- Sandbox: a script that sleeps past the wall-clock cap is killed and reported;
  a script that opens a socket fails; a script that writes outside the scratch
  dir fails; a script that allocates past the memory cap is killed.
- Ollama client: a malformed structured output triggers exactly one retry then
  a typed error.
- Model selection: a `model` in `OLLAMA_ALLOWED_MODELS` is used for that
  request; one outside the set is rejected before any Ollama call; the chat
  picker never changes which model plans `run_sql_query`.
- Retrieval: a question retrieves the expected `kb.chunks` rows by FTS rank;
  an empty corpus returns no context and the answer path says so rather than
  hallucinating; with `pgvector` enabled, vector and FTS results merge and
  de-duplicate.
- Chat tool loop: a chat turn that needs data emits a `run_sql_query` tool
  call routed through the same guard + read-only run + sandbox; a law question
  emits `search_knowledge`; a mixed question emits both; the loop terminates
  at a max tool-call count with a typed error.
- Streaming: `/chat` yields ndjson token-delta and tool-call lines in order;
  a client disconnect cancels the in-flight generation.

**`etl/` (pytest):**
- Each source adapter (Sheets, Drive, Docs, Excel, CSV) parses a fixture file
  into the normalized row shape.
- The loader upserts on each table's natural key — a re-run of the same fixture
  changes no row counts.
- A malformed / short row is quarantined, not inserted, and counted in the run
  summary.
- Google adapter auth mode: `service_account` and `oauth` both resolve to a
  working client against a mocked API; an expired access token refreshes from
  the stored refresh token; a revoked token surfaces a clear "reconnect
  needed" error.
- Knowledge ingestion: a fixture mirroring `pdf_markdown_pipeline_local.documents`
  (visibility `public`, status `verified`) plus its Markdown file produces
  `kb.documents` + chunked `kb.chunks` rows with correct metadata and source
  URL; a non-public or non-verified row is skipped; a re-run changes no
  counts; a removed upstream doc is marked withdrawn, not deleted.

**Cross-cutting:** `ruff`, `ruff format --check`, `mypy --strict` on the Python
trees; `vendor/bin/pint --dirty` on `web/`. All green before commit.

## Negative constraints, restated for grep

- NO DeepSeek (chat model or embedding model).
- NO raw / unsandboxed execution of generated code, including SQL/plot tool
  calls made from inside the chat.
- NO root DB access, NO write DB access, for the AI/orchestrator path —
  `analytics.*` and `kb.*` are `SELECT`-only to the read-only role.
- NO writes to `kb.*` except through the ETL role (sync + admin uploads).
- NO embedded OpenWebUI, NO Docker for the chat — native Livewire + the
  orchestrator stream (`EVALUATION.md` §Chat integration).
- NO `pgvector` / embedding model until FTS recall is shown insufficient
  (`EVALUATION.md` §Retrieval).
- NO Google OAuth token in a log line, a response body, or the repo.
- NO document, prompt, embedding, or query sent anywhere but the local Ollama
  and (ingestion only) the Google API.
- NO new dependency where an installed one or a few lines of stdlib do the job.
- NO speculative abstraction — one engine implemented until a second is
  actually needed (`EVALUATION.md` §Right-sizing).
- NO multi-agent framework (CrewAI / AutoGen / Semantic Kernel / LangGraph /
  …). The chat loop is a bounded in-orchestrator tool loop (cap 4 calls/turn);
  multi-*model* routing is the config registry + per-task default, not a
  framework (`EVALUATION.md` §Right-sizing item 13, `MCP_ENGINES.md`
  §Structured-output loop).
- NO model-written memory and NO agent-memory framework (Letta/MemGPT / Mem0 /
  Zep / cognee). Memory is the working set + the MariaDB transcript + `kb.*` +
  a human-curated per-analyst `user_memory`; the model reads memory, never
  writes it (`EVALUATION.md` §Right-sizing item 14, `MCP_ENGINES.md` §Memory).
- NO committing `.env`, service-account JSON, OAuth client secret, `cert.pem`,
  tunnel credentials.
- NO dependency install (`composer create-project`, venv, `pip` / `npm` add)
  outside what the current milestone's `OPERATOR_SETUP.md` section sanctions.
