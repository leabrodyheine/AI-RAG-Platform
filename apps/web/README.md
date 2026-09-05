# RAG Control web application

React and TypeScript working surface for investigating RAG responses, comparing
evaluation runs, and monitoring the serving stack.

## Run locally

```bash
npm install
npm run dev
```

The app sends investigation questions to the API gateway at
`http://localhost:8000` by default. Copy `.env.example` to `.env.local` to
change the gateway URL. Set `VITE_USE_DEMO_DATA=true` when you want to explore
the UI without running the backend services.

## Source layout

- `src/components/` contains shared application-shell components.
- `src/features/chat/` owns the investigation conversation and evidence panel.
- `src/features/evaluations/` owns quality and performance comparisons.
- `src/features/monitoring/` owns telemetry and service-health views.
- `src/api/` is the only layer that communicates with the API gateway.
- `src/types/` contains contracts shared across frontend features.

## Checks

```bash
npm test -- --run
npm run lint
npm run build
```
