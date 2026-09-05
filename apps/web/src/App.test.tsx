import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, vi } from "vitest";

import { App } from "./App";
import { createDemoAnswer } from "./api/platformFixtures";

afterEach(() => {
  vi.unstubAllGlobals();
});

test("opens on the investigation workspace", () => {
  render(<App />);

  expect(screen.getByRole("heading", { name: "Ask the system" })).toBeInTheDocument();
  expect(screen.getByText("Start an investigation")).toBeInTheDocument();
  expect(screen.queryByText("Demo data")).not.toBeInTheDocument();
  expect(screen.getByRole("navigation", { name: "Primary navigation" })).toBeInTheDocument();
});

test("moves between evaluation and monitoring workspaces", () => {
  render(<App />);

  fireEvent.click(screen.getByRole("button", { name: "Evaluations" }));
  expect(screen.getByRole("heading", { name: "Evaluation lab" })).toBeInTheDocument();
  expect(screen.queryByText("#1838")).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "View evidence" }));
  expect(screen.getByText("Why this recommendation?")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "View all runs" }));
  expect(screen.getByText("#1838")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Monitoring" }));
  expect(screen.getByRole("heading", { name: "System monitoring" })).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "6h" }));
  expect(screen.getByRole("button", { name: "6h" })).toHaveAttribute("aria-pressed", "true");
});

test("submits a live investigation question", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify(createDemoAnswer("cache")), {
        headers: { "Content-Type": "application/json" },
      }),
    ),
  );
  render(<App />);

  fireEvent.change(screen.getByRole("textbox", { name: "Ask a question" }), {
    target: { value: "Compare cached and uncached retrieval" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Send question" }));

  expect(await screen.findByText(/Cached retrieval reduces p95/)).toBeInTheDocument();
});
