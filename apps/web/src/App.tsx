import { ServiceStatus } from "./components/ServiceStatus";

export function App() {
  return (
    <main>
      <p className="eyebrow">AI Production Evaluation Platform</p>
      <h1>Investigate model quality and system performance.</h1>
      <p>
        The application shell is ready. Chat, evaluation, and monitoring features
        can now be implemented independently.
      </p>
      <ServiceStatus label="Platform scaffold" status="ready" />
    </main>
  );
}
