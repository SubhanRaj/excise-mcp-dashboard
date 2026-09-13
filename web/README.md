# web/ — Excise Data Visualization (Laravel)

The Laravel 13 / Livewire 4 app: the analytical form (Ask), the chat window,
and the admin screens. It talks to the FastAPI orchestrator over HTTP and
stores its own operational data (sessions, users, the query ledger, chat
history, queued jobs) in MariaDB. It never connects to PostgreSQL — the
excise data bank is the orchestrator's, read-only.

OTP-email login and onboarding, RBAC (`designations` + `privileges`), the
admin screens (users, Google connect, knowledge base, activity log), the Ask
form, and the chat window are built (`m5-phase-0-4-admin`, `CLAUDE.md`'s
Status paragraph has the detail). The customization panel and brand assets
(Milestone 5 Phase 5) are next.

## Docs

Everything is in the repo root, one level up:

- `../CLAUDE.md` — coding rules for this repo
- `../ARCHITECTURE.md` — how the pieces fit
- `../EVALUATION.md` — stack choices and the reusable-module inventory (§4)
- `../ROADMAP.md` — milestone checklist
- `../SECURITY.md` — threat model and the security baseline
- `../OPERATOR_SETUP.md` — the sudo / install / console steps, including the
  MariaDB database this app needs (`§web/ skeleton`)

## Local setup

```bash
composer install
cp .env.example .env && php artisan key:generate
# provision the MariaDB database — see ../OPERATOR_SETUP.md §web/ skeleton
php artisan migrate
npm install && npm run build
php artisan test
```

`GET /health` returns `{"app": "...", "status": "ok"}` and is the only route
open to an unauthenticated request — every other route redirects to `/login`.
