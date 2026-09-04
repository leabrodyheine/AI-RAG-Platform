# RAG Control web application

React and TypeScript working surface for investigating RAG responses, comparing
evaluation runs, and monitoring the serving stack.

## Run locally

```bash
npm install
npm run dev
```

The app uses representative demo data by default because the API gateway's chat
endpoint is not implemented yet. Copy `.env.example` to `.env.local` and set
`VITE_USE_DEMO_DATA=false` when the gateway can serve `POST /chat`.

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
