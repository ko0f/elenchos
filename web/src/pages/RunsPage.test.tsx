import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { RunsPage } from "./RunsPage";

const mockNavigate = vi.fn();

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

const runs = [
  {
    run_id: "run-a",
    started_at: "2025-01-01T00:00:00Z",
    model: "ollama/a",
    benchmark: { id: "text-reasoning-v1", version: 1 },
    summary: { mean_score: 1.0 },
  },
  {
    run_id: "run-b",
    started_at: "2025-01-01T01:00:00Z",
    model: "ollama/b",
    benchmark: { id: "text-reasoning-v1", version: 1 },
    summary: { mean_score: 0.5 },
  },
];

vi.mock("../api/client", () => ({
  api: {
    listRuns: vi.fn(async () => runs),
  },
  queryKeys: {
    runs: ["runs"],
  },
}));

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <RunsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("RunsPage", () => {
  it("enables compare only for two same-benchmark runs", async () => {
    const user = userEvent.setup();
    renderPage();

    const compare = await screen.findByRole("button", { name: "Compare selected" });
    expect(compare).toBeDisabled();

    await user.click(screen.getByLabelText("Select run-a"));
    expect(compare).toBeDisabled();

    await user.click(screen.getByLabelText("Select run-b"));
    expect(compare).toBeEnabled();

    await user.click(compare);
    expect(mockNavigate).toHaveBeenCalledWith("/compare?runs=run-a,run-b");
  });
});
