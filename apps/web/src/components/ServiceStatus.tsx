interface ServiceStatusProps {
  label: string;
  status: "ready" | "unavailable";
}

export function ServiceStatus({ label, status }: ServiceStatusProps) {
  return (
    <div className="status" role="status">
      <span aria-hidden="true" className={`status__dot status__dot--${status}`} />
      <span>{label}</span>
      <strong>{status}</strong>
    </div>
  );
}
