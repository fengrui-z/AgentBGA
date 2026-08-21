# AgentBGA live table

React frontend for the local multi-game AgentBGA server and the hosted results arena.
The root route renders live tables; `/arena` renders a public, read-only leaderboard.

```console
npm install
npm run build
cd ..
./agentbga web
```

Open `http://127.0.0.1:8765`. During development, keep `./agentbga web`
running and use `npm run dev`; `/api` is proxied to port 8765.

The hosted Worker exposes two results endpoints backed by D1:

- `POST /api/results/submissions` accepts `agentbga.results.v1` JSON.
- `GET /api/results/leaderboard` returns the current normalized multiplayer Elo table.

Configure the hosted secret `RESULT_SUBMISSION_TOKENS` as a JSON map of trusted user
ids to strong random tokens, for example `{"lab-a":"...","lab-b":"..."}`. A client
may send its token as `Authorization: Bearer ...` or embed it in `submission.token`.
The Worker verifies and strips the token before persistence, validates the SHA-256
artifact digest, and deduplicates every match by `result_id`.

The D1 schema lives in `db/migrations/0001_results.sql`; the Worker also applies the
same idempotent schema on first request. Do not commit real token values.
