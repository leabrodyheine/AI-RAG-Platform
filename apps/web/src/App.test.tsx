import { render, screen } from "@testing-library/react";

import { App } from "./App";

test("renders the application shell", () => {
  render(<App />);

  expect(
    screen.getByRole("heading", {
      name: "Investigate model quality and system performance.",
    }),
  ).toBeInTheDocument();
  expect(screen.getByRole("status")).toHaveTextContent("ready");
});
