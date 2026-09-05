export type AppSection = "investigate" | "evaluations" | "monitoring";

export interface Citation {
  id: string;
  title: string;
  source: string;
  excerpt: string;
  relevance: number;
}

export interface TraceStep {
  label: string;
  detail: string;
  durationMs: number;
}

export interface AssistantAnswer {
  content: string;
  citations: Citation[];
  trace: TraceStep[];
  totalDurationMs: number;
}

export interface ChatErrorResponse {
  code: "validation_error" | "agent_unavailable" | "agent_timeout";
  message: string;
  requestId: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
}
