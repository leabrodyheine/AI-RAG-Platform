import { fireEvent, render, screen, within } from "@testing-library/react";
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
  expect(screen.getByRole("main")).toBeInTheDocument();
});

test("moves between evaluation and monitoring workspaces", () => {
  render(<App />);

  fireEvent.click(screen.getByRole("button", { name: "Evaluations" }));
  expect(screen.getByRole("heading", { name: "Evaluation lab" })).toBeInTheDocument();
  expect(screen.queryByText("#1838")).not.toBeInTheDocument();
  const comparisonTable = screen.getByRole("table", { name: "Evaluation comparison" });
  expect(within(comparisonTable).getAllByRole("columnheader")).toHaveLength(4);
  expect(within(comparisonTable).getAllByRole("cell")).toHaveLength(24);
  const recentRunsTable = screen.getByRole("table", { name: "Recent evaluation runs" });
  expect(within(recentRunsTable).getAllByRole("columnheader")).toHaveLength(5);
  expect(within(recentRunsTable).getAllByRole("cell")).toHaveLength(15);

  const evidenceButton = screen.getByRole("button", { name: "View evidence" });
  expect(evidenceButton).toHaveAttribute("aria-controls", "evaluation-evidence");
  expect(evidenceButton).toHaveAttribute("aria-expanded", "false");
  fireEvent.click(evidenceButton);
  expect(screen.getByRole("button", { name: "Hide evidence" })).toHaveAttribute(
    "aria-expanded",
    "true",
  );
  expect(screen.getByText("Why this recommendation?")).toBeInTheDocument();

  const runsButton = screen.getByRole("button", { name: "View all runs" });
  expect(runsButton).toHaveAttribute("aria-controls", "recent-evaluation-runs");
  expect(runsButton).toHaveAttribute("aria-expanded", "false");
  fireEvent.click(runsButton);
  expect(screen.getByRole("button", { name: "Show recent" })).toHaveAttribute(
    "aria-expanded",
    "true",
  );
  expect(screen.getByText("#1838")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Monitoring" }));
  expect(screen.getByRole("heading", { name: "System monitoring" })).toBeInTheDocument();
  expect(screen.getByRole("group", { name: "Monitoring time range" })).toBeInTheDocument();
  expect(screen.getByRole("table", { name: "Recent traces" })).toBeInTheDocument();
  expect(screen.getAllByRole("columnheader")).toHaveLength(4);
  expect(screen.getAllByRole("cell")).toHaveLength(16);

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
