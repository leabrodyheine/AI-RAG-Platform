import { useState } from "react";
import {
  ArrowDownRight,
  ArrowUpRight,
  Check,
  ChevronDown,
  CircleAlert,
  Clock3,
  FileCheck2,
  LoaderCircle,
  Play,
  Sparkles,
} from "lucide-react";

const metrics = [
  { label: "Answer correctness", baseline: "82.4%", candidate: "89.1%", delta: "+6.7%", positive: true },
  { label: "Retrieval recall", baseline: "76.8%", candidate: "91.3%", delta: "+14.5%", positive: true },
  { label: "Citation accuracy", baseline: "88.2%", candidate: "94.7%", delta: "+6.5%", positive: true },
  { label: "Hallucination rate", baseline: "7.9%", candidate: "3.2%", delta: "−4.7%", positive: true },
  { label: "End-to-end p95", baseline: "704 ms", candidate: "849 ms", delta: "+145 ms", positive: false },
  { label: "Cost / 1k requests", baseline: "$1.84", candidate: "$2.31", delta: "+25.5%", positive: false },
];

const recentRuns = [
  { id: "#1842", name: "Agentic vs basic RAG", dataset: "golden-set-v4", score: "89.1%", status: "Passed", time: "12 min ago" },
  { id: "#1841", name: "Cached retrieval", dataset: "perf-suite-v2", score: "87.8%", status: "Passed", time: "2 hr ago" },
  { id: "#1840", name: "Triton candidate", dataset: "golden-set-v4", score: "81.6%", status: "Review", time: "Yesterday" },
  { id: "#1839", name: "Chunk-size sweep", dataset: "retrieval-set-v3", score: "86.9%", status: "Passed", time: "2 days ago" },
  { id: "#1838", name: "No-rewrite baseline", dataset: "golden-set-v4", score: "79.4%", status: "Review", time: "3 days ago" },
];

export function EvaluationWorkspace() {
  const [isRunning, setIsRunning] = useState(false);
  const [lastRun, setLastRun] = useState("Completed 12 minutes ago");
  const [showEvidence, setShowEvidence] = useState(false);
  const [showAllRuns, setShowAllRuns] = useState(false);
  const [dataset, setDataset] = useState("golden-set-v4");

  function runEvaluation() {
    if (isRunning) return;
    setIsRunning(true);
    setLastRun("Running 124 test cases…");
    window.setTimeout(() => {
      setIsRunning(false);
      setLastRun("Completed just now");
    }, 1200);
  }

  return (
    <div className="workspace-page">
      <header className="page-header">
        <div>
          <div className="page-kicker"><FileCheck2 size={13} /> Quality gate</div>
          <h1>Evaluation lab</h1>
          <p>Measure quality and performance tradeoffs before changing production.</p>
        </div>
        <button className="primary-button" disabled={isRunning} onClick={runEvaluation} type="button">
          {isRunning ? <LoaderCircle className="spin" size={15} /> : <Play size={15} />}
          {isRunning ? "Running evaluation" : "Run evaluation"}
        </button>
      </header>

      <div className="metric-strip">
        <MetricSummary label="Overall score" value="89.1" suffix="/ 100" delta="+6.7" />
        <MetricSummary label="Test cases" value="124" suffix="cases" detail="120 passed · 4 review" />
        <MetricSummary label="Median latency" value="512" suffix="ms" delta="+83 ms" negative />
        <MetricSummary label="Evaluation cost" value="$2.31" suffix="/ 1k" detail="Within $3.00 budget" />
      </div>

      <section className="evaluation-card">
        <div className="card-heading-row">
          <div>
            <span className="section-label">Active comparison</span>
            <h2>Agentic RAG candidate</h2>
            <p>{lastRun}</p>
          </div>
          <label className="select-button">
            <span className="sr-only">Evaluation dataset</span>
            <select onChange={(event) => setDataset(event.target.value)} value={dataset}>
              <option value="golden-set-v4">Golden set · v4</option>
              <option value="perf-suite-v2">Performance suite · v2</option>
              <option value="retrieval-set-v3">Retrieval set · v3</option>
            </select>
            <ChevronDown size={14} />
          </label>
        </div>

        <div className="comparison-head">
          <span>Metric</span>
          <span><i className="comparison-dot comparison-dot--baseline" /> Basic RAG <small>Baseline</small></span>
          <span><i className="comparison-dot comparison-dot--candidate" /> Agentic RAG <small>Candidate</small></span>
          <span>Change</span>
        </div>
        <div className="comparison-table">
          {metrics.map((metric) => (
            <div className="comparison-row" key={metric.label}>
              <strong>{metric.label}</strong>
              <span>{metric.baseline}</span>
              <span>{metric.candidate}</span>
              <span className={metric.positive ? "delta delta--positive" : "delta delta--negative"}>
                {metric.positive ? <ArrowUpRight size={13} /> : <ArrowDownRight size={13} />}
                {metric.delta}
              </span>
            </div>
          ))}
        </div>

        <div className="recommendation-banner">
          <span><Sparkles size={17} /></span>
          <div>
            <strong>Recommendation: promote with a latency guardrail</strong>
            <p>The candidate improves every quality metric, but p95 is 20.6% slower. Promote after enabling the retrieval cache policy tested in run #1841.</p>
          </div>
          <button onClick={() => setShowEvidence((current) => !current)} type="button">
            {showEvidence ? "Hide evidence" : "View evidence"}
          </button>
        </div>
        {showEvidence && (
          <div className="evaluation-evidence">
            <strong>Why this recommendation?</strong>
            <p>120 of 124 cases pass the quality gate. All four review cases exceed the 1,000 ms latency target and share a retrieval cache miss, while correctness remains above the 85% promotion threshold.</p>
          </div>
        )}
      </section>

      <section className="runs-card">
        <div className="card-heading-row card-heading-row--compact">
          <div>
            <span className="section-label">History</span>
            <h2>Recent runs</h2>
          </div>
          <button className="text-button" onClick={() => setShowAllRuns((current) => !current)} type="button">
            {showAllRuns ? "Show recent" : "View all runs"}
          </button>
        </div>
        <div className="runs-table" role="table" aria-label="Recent evaluation runs">
          {recentRuns.slice(0, showAllRuns ? recentRuns.length : 3).map((run) => (
            <div className="run-row" role="row" key={run.id}>
              <code>{run.id}</code>
              <span><strong>{run.name}</strong><small>{run.dataset}</small></span>
              <strong>{run.score}</strong>
              <span className={run.status === "Passed" ? "run-status run-status--passed" : "run-status run-status--review"}>
                {run.status === "Passed" ? <Check size={12} /> : <CircleAlert size={12} />}{run.status}
              </span>
              <small><Clock3 size={12} />{run.time}</small>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

interface MetricSummaryProps {
  label: string;
  value: string;
  suffix: string;
  delta?: string;
  detail?: string;
  negative?: boolean;
}

function MetricSummary({ label, value, suffix, delta, detail, negative }: MetricSummaryProps) {
  return (
    <article className="metric-summary">
      <span>{label}</span>
      <div><strong>{value}</strong><small>{suffix}</small></div>
      {delta && <p className={negative ? "metric-trend metric-trend--negative" : "metric-trend"}>{delta} vs baseline</p>}
      {detail && <p>{detail}</p>}
    </article>
  );
}
