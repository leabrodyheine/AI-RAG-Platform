interface ServiceStatusProps {
  label: string;
  status: "healthy" | "degraded" | "offline";
}

export function ServiceStatus({ label, status }: ServiceStatusProps) {
  return (
    <div className="status" role="status">
      <span aria-hidden="true" className={`status__dot status__dot--${status}`} />
      <span>{label}</span>
      <strong className="sr-only">{status}</strong>
    </div>
  );
}
