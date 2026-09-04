import { FormEvent, useState } from "react";
import {
  ArrowUp,
  BookOpen,
  Check,
  ChevronRight,
  Clock3,
  Copy,
  Database,
  Gauge,
  LoaderCircle,
  RotateCcw,
  Sparkles,
} from "lucide-react";

import { askQuestion, isDemoMode } from "../../api/platform";
import { initialAnswer, suggestedQuestions } from "../../api/platformFixtures";
import type { ChatMessage, Citation, TraceStep } from "../../types/platform";

const initialMessages: ChatMessage[] = [
  {
    id: "question-1",
    role: "user",
    content: "What is the biggest bottleneck in the latest high-concurrency run?",
  },
  {
    id: "answer-1",
    role: "assistant",
    content: initialAnswer.content,
    citations: initialAnswer.citations,
  },
];

export function ChatWorkspace() {
  const [messages, setMessages] = useState(initialMessages);
  const [trace, setTrace] = useState<TraceStep[]>(initialAnswer.trace);
  const [duration, setDuration] = useState(initialAnswer.totalDurationMs);
  const [question, setQuestion] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedCitation, setSelectedCitation] = useState<Citation | null>(
    initialAnswer.citations[0],
  );
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null);

  async function submitQuestion(nextQuestion: string) {
    const trimmedQuestion = nextQuestion.trim();
    if (!trimmedQuestion || isSubmitting) return;

    setError(null);
    setQuestion("");
    setIsSubmitting(true);
    setMessages((current) => [
      ...current,
      { id: `question-${Date.now()}`, role: "user", content: trimmedQuestion },
    ]);

    try {
      const answer = await askQuestion(trimmedQuestion);
      setMessages((current) => [
        ...current,
        {
          id: `answer-${Date.now()}`,
          role: "assistant",
          content: answer.content,
          citations: answer.citations,
        },
      ]);
      setTrace(answer.trace);
      setDuration(answer.totalDurationMs);
      setSelectedCitation(answer.citations[0] ?? null);
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "The request failed.");
    } finally {
      setIsSubmitting(false);
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void submitQuestion(question);
  }

  function resetInvestigation() {
    setMessages(initialMessages);
    setTrace(initialAnswer.trace);
    setDuration(initialAnswer.totalDurationMs);
    setSelectedCitation(initialAnswer.citations[0]);
    setError(null);
    setQuestion("");
  }

  async function copyAnswer(message: ChatMessage) {
    await navigator.clipboard?.writeText(message.content);
    setCopiedMessageId(message.id);
    window.setTimeout(() => setCopiedMessageId(null), 1500);
  }

  return (
    <div className="workspace-page">
      <header className="page-header">
        <div>
          <div className="page-kicker">
            <span className="live-dot" /> Live investigation
            {isDemoMode && <span className="demo-badge">Demo data</span>}
          </div>
          <h1>Ask the system</h1>
          <p>Trace performance regressions and compare model behavior with cited evidence.</p>
        </div>
        <button className="secondary-button" onClick={resetInvestigation} type="button">
          <RotateCcw size={15} />
          New investigation
        </button>
      </header>

      <div className="investigation-layout">
        <section className="conversation-card" aria-label="Investigation conversation">
          <div className="conversation-card__meta">
            <span>Investigation #1842</span>
            <span><Clock3 size={14} /> Updated just now</span>
          </div>

          <div className="conversation">
            {messages.map((message) => (
              <article className={`message message--${message.role}`} key={message.id}>
                <div className="message__avatar" aria-hidden="true">
                  {message.role === "assistant" ? <Sparkles size={15} /> : "LB"}
                </div>
                <div className="message__body">
                  <div className="message__label">
                    <strong>{message.role === "assistant" ? "RAG Control" : "You"}</strong>
                    {message.role === "assistant" && <span>Evidence-backed</span>}
                  </div>
                  <p>{message.content}</p>
                  {message.citations && (
                    <div className="citation-list">
                      {message.citations.map((citation, index) => (
                        <button
                          className="citation"
                          key={citation.id}
                          onClick={() => setSelectedCitation(citation)}
                          type="button"
                        >
                          <span className="citation__number">{index + 1}</span>
                          <span>
                            <strong>{citation.title}</strong>
                            <small>{citation.source}</small>
                          </span>
                          <ChevronRight size={15} />
                        </button>
                      ))}
                    </div>
                  )}
                  {message.role === "assistant" && (
                    <button
                      className="icon-text-button"
                      onClick={() => void copyAnswer(message)}
                      type="button"
                    >
                      {copiedMessageId === message.id ? <Check size={14} /> : <Copy size={14} />}
                      {copiedMessageId === message.id ? "Copied" : "Copy answer"}
                    </button>
                  )}
                </div>
              </article>
            ))}

            {isSubmitting && (
              <div className="thinking-state" role="status">
                <LoaderCircle className="spin" size={17} />
                Retrieving evidence and checking traces…
              </div>
            )}
          </div>

          <div className="composer-area">
            {error && <p className="error-banner">{error}</p>}
            <div className="suggestion-row" aria-label="Suggested questions">
              {suggestedQuestions.map((suggestion) => (
                <button key={suggestion} onClick={() => void submitQuestion(suggestion)} type="button">
                  {suggestion}
                </button>
              ))}
            </div>
            <form className="composer" onSubmit={handleSubmit}>
              <textarea
                aria-label="Ask a question"
                onChange={(event) => setQuestion(event.target.value)}
                placeholder="Ask about latency, quality, retrieval, or infrastructure…"
                rows={2}
                value={question}
              />
              <div className="composer__footer">
                <span><Database size={14} /> Evaluation index · 1,284 documents</span>
                <button aria-label="Send question" disabled={!question.trim() || isSubmitting} type="submit">
                  <ArrowUp size={17} />
                </button>
              </div>
            </form>
          </div>
        </section>

        <aside className="evidence-panel" aria-label="Request evidence and trace">
          <section className="panel-section">
            <div className="panel-heading">
              <span><Gauge size={16} /> Request trace</span>
              <strong>{duration} ms</strong>
            </div>
            <div className="trace-list">
              {trace.map((step) => (
                <div className="trace-step" key={step.label}>
                  <span className="trace-step__check"><Check size={12} /></span>
                  <span>
                    <strong>{step.label}</strong>
                    <small>{step.detail}</small>
                  </span>
                  <code>{step.durationMs} ms</code>
                </div>
              ))}
            </div>
          </section>

          <section className="panel-section">
            <div className="panel-heading">
              <span><BookOpen size={16} /> Active configuration</span>
            </div>
            <dl className="configuration-list">
              <div><dt>Strategy</dt><dd>Agentic RAG</dd></div>
              <div><dt>Inference</dt><dd>vLLM</dd></div>
              <div><dt>Retrieval</dt><dd>pgvector</dd></div>
              <div><dt>Cache</dt><dd className="positive-text">Enabled</dd></div>
            </dl>
          </section>

          {selectedCitation && (
            <section className="panel-section citation-detail" aria-live="polite">
              <div className="panel-heading">
                <span><BookOpen size={16} /> Selected evidence</span>
                <strong>{Math.round(selectedCitation.relevance * 100)}% match</strong>
              </div>
              <strong>{selectedCitation.title}</strong>
              <p>{selectedCitation.excerpt}</p>
              <code>{selectedCitation.source}</code>
            </section>
          )}

          <section className="insight-card">
            <span className="insight-card__icon"><Sparkles size={16} /></span>
            <div>
              <strong>Optimization opportunity</strong>
              <p>Cache coverage is 63%. Raising it could reduce end-to-end p95 by another 11–16%.</p>
            </div>
          </section>
        </aside>
      </div>
    </div>
  );
}
