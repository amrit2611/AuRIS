# AuRIS web (Next.js 15 frontend)

Next.js 15 + TypeScript + Tailwind frontend consuming the FastAPI backend
at `src/auris/api.py`.

## Layout

```
web/
├── src/
│   ├── app/
│   │   ├── layout.tsx           # Root layout, dark mode default
│   │   ├── page.tsx             # Single-page UI: upload -> results
│   │   └── globals.css          # Tailwind entry + small utility rules
│   ├── components/
│   │   ├── UploadZone.tsx       # Drag-and-drop CSV picker
│   │   ├── PriorityQueueHero.tsx# Big-hero "N rows to look at first"
│   │   ├── MetricsRow.tsx       # Secondary metric tiles + per-check counts
│   │   ├── FindingsTable.tsx    # Scored triage queue with min-score slider
│   │   └── AiSummary.tsx        # Groq call + markdown render + download
│   └── lib/
│       ├── api.ts               # Fetch wrapper around the FastAPI backend
│       └── types.ts             # TS types mirroring the Pydantic models
├── tailwind.config.ts           # Validated dark palette matches Streamlit
├── next.config.mjs
├── tsconfig.json
└── package.json
```

## Local dev

Two terminals: one for the API, one for the frontend.

```bash
# Terminal 1 - FastAPI backend
uvicorn auris.api:app --port 8000 --reload

# Terminal 2 - Next.js frontend (from repo root)
cd web
cp .env.local.example .env.local
npm install
npm run dev
```

Frontend serves on <http://localhost:3000>, expects the backend on
<http://localhost:8000>. Both can be swapped via env var.

## Env

`NEXT_PUBLIC_API_URL` picks the FastAPI base URL. Only the `NEXT_PUBLIC_`
prefix leaks the value to the browser bundle; everything else stays server
side. Locally it defaults to `http://localhost:8000`. In production
(Vercel), set it to the Railway URL of the deployed backend.

## Design system

Colors use the validated dark-mode categorical palette from the dataviz
skill (see `references/palette.md`), matched in `tailwind.config.ts` so the
Next.js frontend looks visually consistent with the Streamlit dashboard.

## Deploy target

Vercel. Backend deploys to Railway. `AURIS_CORS_ORIGINS` on the backend
must include the Vercel URL to accept requests from the deployed frontend.

## Not shipped in this MVP

- No charts yet (findings table shows the data; charts follow in a future PR).
- No RiskConfig slider UI on the frontend (backend takes defaults). Sliders
  will be added in a follow-up once the layout is validated with real users.
- No authentication or run history (that's Level 4 in the roadmap).
