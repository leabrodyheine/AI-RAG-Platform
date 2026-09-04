import { useState } from "react";
import {
  Activity,
  ArrowDown,
  ArrowUp,
  Boxes,
  CheckCircle2,
  Cpu,
  Database,
  Gauge,
  HardDrive,
  Radio,
  RefreshCw,
  Server,
  TimerReset,
  Zap,
} from "lucide-react";

const latencyBars = [38, 42, 36, 49, 43, 55, 47, 62, 58, 51, 66, 71, 59, 52, 64, 77, 69, 83, 72, 68, 74, 61, 57, 63];

const services = [
  { name: "API gateway", detail: "2 replicas", latency: "18 ms", load: 42, status: "Healthy" },
  { name: "Agent service", detail: "2 replicas", latency: "64 ms", load: 57, status: "Healthy" },
  { name: "Retrieval", detail: "3 replicas", latency: "118 ms", load: 78, status: "Healthy" },
  { name: "Inference · vLLM", detail: "1 × A10G", latency: "416 ms", load: 71, status: "Healthy" },
];

const traces = [
  { id: "7f3a91", route: "POST /chat", duration: "849 ms", spans: 14, status: "ok" },
  { id: "a8240e", route: "POST /chat", duration: "1.21 s", spans: 17, status: "slow" },
  { id: "b9174c", route: "POST /retrieve", duration: "104 ms", spans: 6, status: "ok" },
  { id: "c18dd2", route: "POST /chat", duration: "782 ms", spans: 13, status: "ok" },
];

export function MonitoringWorkspace() {
  const [timeRange, setTimeRange] = useState("1h");
  const [refreshing, setRefreshing] = useState(false);

  function refresh() {
    setRefreshing(true);
    window.setTimeout(() => setRefreshing(false), 700);
  }

  return (
    <div className="workspace-page">
      <header className="page-header">
        <div>
          <div className="page-kicker"><Radio size={13} /> Live telemetry</div>
          <h1>System monitoring</h1>
          <p>Follow request health from the gateway through retrieval and GPU inference.</p>
        </div>
        <div className="header-actions">
          <div className="segmented-control" aria-label="Monitoring time range">
            {["15m", "1h", "6h", "24h"].map((range) => (
              <button aria-pressed={timeRange === range} key={range} onClick={() => setTimeRange(range)} type="button">{range}</button>
            ))}
          </div>
          <button aria-label="Refresh metrics" className="secondary-button" onClick={refresh} type="button">
            <RefreshCw className={refreshing ? "spin" : undefined} size={15} />
          </button>
        </div>
      </header>

      <div className="metric-strip">
        <TelemetryMetric icon={TimerReset} label="p95 latency" value="849" unit="ms" trend="8.4%" direction="down" />
        <TelemetryMetric icon={Zap} label="Throughput" value="28.4" unit="req/s" trend="12.1%" direction="up" />
        <TelemetryMetric icon={Activity} label="Error rate" value="0.18" unit="%" trend="0.06%" direction="down" />
        <TelemetryMetric icon={Database} label="Cache hit rate" value="63" unit="%" trend="4.2%" direction="up" />
      </div>

      <div className="monitoring-grid">
        <section className="telemetry-card telemetry-card--wide">
          <div className="card-heading-row card-heading-row--compact">
            <div>
              <span className="section-label">End-to-end requests</span>
              <h2>Latency profile</h2>
            </div>
            <div className="chart-legend"><span><i className="legend-dot" />p95</span><span><i className="legend-dot legend-dot--muted" />target</span></div>
          </div>
          <div className="latency-chart" role="img" aria-label={`Request latency over the last ${timeRange}`}>
            <div className="chart-target"><span>1,000 ms target</span></div>
            {latencyBars.map((height, index) => <i key={index} style={{ height: `${height}%` }} />)}
          </div>
          <div className="chart-axis"><span>60 minutes ago</span><span>30 minutes ago</span><span>Now</span></div>
        </section>

        <section className="telemetry-card">
          <div className="card-heading-row card-heading-row--compact">
            <div><span className="section-label">Accelerator</span><h2>GPU runtime</h2></div>
            <span className="healthy-chip"><CheckCircle2 size={12} />Healthy</span>
          </div>
          <div className="gauge-layout">
            <div className="radial-gauge"><span><strong>71</strong>%</span></div>
            <div className="gauge-copy"><strong>NVIDIA A10G</strong><span>vLLM · meta-llama/8B</span></div>
          </div>
          <dl className="resource-list">
            <div><dt><HardDrive size={13} />VRAM</dt><dd>17.2 / 24 GB</dd></div>
            <div><dt><Cpu size={13} />Temperature</dt><dd>68 °C</dd></div>
            <div><dt><Gauge size={13} />Tokens / sec</dt><dd>84.6</dd></div>
          </dl>
        </section>

        <section className="telemetry-card telemetry-card--services">
          <div className="card-heading-row card-heading-row--compact">
            <div><span className="section-label">Kubernetes</span><h2>Service health</h2></div>
            <span className="muted-meta"><Boxes size={13} />8 pods</span>
          </div>
          <div className="service-list">
            {services.map((service) => (
              <div className="service-row" key={service.name}>
                <span className="service-icon"><Server size={15} /></span>
                <span><strong>{service.name}</strong><small>{service.detail}</small></span>
                <div className="load-meter"><i style={{ width: `${service.load}%` }} /></div>
                <code>{service.latency}</code>
                <span className="healthy-chip"><CheckCircle2 size={12} />{service.status}</span>
              </div>
            ))}
          </div>
        </section>

        <section className="telemetry-card telemetry-card--traces">
          <div className="card-heading-row card-heading-row--compact">
            <div><span className="section-label">OpenTelemetry</span><h2>Recent traces</h2></div>
            <span className="muted-meta">4 sampled traces</span>
          </div>
          <div className="trace-table">
            {traces.map((trace) => (
              <div className="trace-row" key={trace.id}>
                <code>{trace.id}</code><strong>{trace.route}</strong><span>{trace.spans} spans</span>
                <span className={trace.status === "slow" ? "trace-duration trace-duration--slow" : "trace-duration"}>{trace.duration}</span>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}

interface TelemetryMetricProps {
  icon: typeof Activity;
  label: string;
  value: string;
  unit: string;
  trend: string;
  direction: "up" | "down";
}

function TelemetryMetric({ icon: Icon, label, value, unit, trend, direction }: TelemetryMetricProps) {
  const favorable = (label === "p95 latency" || label === "Error rate") ? direction === "down" : direction === "up";
  return (
    <article className="metric-summary telemetry-metric">
      <span><Icon size={14} />{label}</span>
      <div><strong>{value}</strong><small>{unit}</small></div>
      <p className={favorable ? "metric-trend" : "metric-trend metric-trend--negative"}>
        {direction === "up" ? <ArrowUp size={11} /> : <ArrowDown size={11} />}{trend} vs prior
      </p>
    </article>
  );
}
