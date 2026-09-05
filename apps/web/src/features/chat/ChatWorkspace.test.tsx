import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { createDemoAnswer } from "../../api/platformFixtures";
import { ChatWorkspace } from "./ChatWorkspace";

afterEach(() => {
  vi.unstubAllGlobals();
});

test("shows progress and renders a live answer with evidence", async () => {
  let finishRequest: ((response: Response) => void) | undefined;
  const fetchMock = vi.fn().mockImplementation(
    () =>
      new Promise<Response>((resolve) => {
        finishRequest = resolve;
      }),
  );
  vi.stubGlobal("fetch", fetchMock);
  render(<ChatWorkspace />);

  fireEvent.change(screen.getByRole("textbox", { name: "Ask a question" }), {
    target: { value: "  Compare cached retrieval  " },
  });
  fireEvent.click(screen.getByRole("button", { name: "Send question" }));

  expect(screen.getByRole("status", { name: "" })).toHaveTextContent(
    "Retrieving evidence",
  );
  expect(screen.getByRole("textbox", { name: "Ask a question" })).toBeDisabled();
  expect(fetchMock).toHaveBeenCalledWith(
    "http://localhost:8000/chat",
    expect.objectContaining({ body: JSON.stringify({ question: "Compare cached retrieval" }) }),
  );

  await act(async () => {
    finishRequest?.(
      new Response(JSON.stringify(createDemoAnswer("cache")), {
        headers: { "Content-Type": "application/json" },
      }),
    );
  });

  expect(await screen.findByText(/Cached retrieval reduces p95/)).toBeInTheDocument();
  expect(screen.getAllByText("Retrieval benchmark · run #1842")).toHaveLength(2);
  expect(screen.getByText("518 ms")).toBeInTheDocument();
});

test("shows a correlated error and retries without duplicating the question", async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          code: "agent_unavailable",
          message: "The agent service is temporarily unavailable.",
          requestId: "request-retry",
        }),
        { status: 503, headers: { "Content-Type": "application/json" } },
      ),
    )
    .mockResolvedValueOnce(
      new Response(JSON.stringify(createDemoAnswer("latency")), {
        headers: { "Content-Type": "application/json" },
      }),
    );
  vi.stubGlobal("fetch", fetchMock);
  render(<ChatWorkspace />);

  const question = "What is driving latency?";
  fireEvent.change(screen.getByRole("textbox", { name: "Ask a question" }), {
    target: { value: question },
  });
  fireEvent.click(screen.getByRole("button", { name: "Send question" }));

  const alert = await screen.findByRole("alert");
  expect(alert).toHaveTextContent("The agent service is temporarily unavailable.");
  expect(alert).toHaveTextContent("Request ID: request-retry");

  fireEvent.click(screen.getByRole("button", { name: "Try again" }));

  expect(await screen.findByText(/Retrieval is the primary bottleneck/)).toBeInTheDocument();
  expect(screen.getAllByText(question)).toHaveLength(1);
  expect(fetchMock).toHaveBeenCalledTimes(2);
});

test("submits with Enter while preserving Shift+Enter for multiline input", async () => {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify(createDemoAnswer("latency")), {
      headers: { "Content-Type": "application/json" },
    }),
  );
  vi.stubGlobal("fetch", fetchMock);
  render(<ChatWorkspace />);

  const composer = screen.getByRole("textbox", { name: "Ask a question" });
  fireEvent.change(composer, { target: { value: "Trace latency" } });
  fireEvent.keyDown(composer, { key: "Enter", shiftKey: true });
  expect(fetchMock).not.toHaveBeenCalled();

  fireEvent.keyDown(composer, { key: "Enter" });
  expect(await screen.findByText(/Retrieval is the primary bottleneck/)).toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledTimes(1);
});
