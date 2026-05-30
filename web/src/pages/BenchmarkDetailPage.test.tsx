import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { BenchmarkDetailPage } from "../pages/BenchmarkDetailPage";

const suiteDetail = {
  id: "text-reasoning-v1",
  version: 1,
  type: "text",
  description: "Basic text reasoning tasks.",
  defaults: { params: { temperature: 0.0, max_tokens: 1024 } },
  tasks: [
    {
      id: "arithmetic",
      type: "text",
      prompt: "What is 2+2?",
      scorers: ["exact_match"],
    },
    {
      id: "capital",
      type: "text",
      prompt: "Capital of France?",
      scorers: ["contains_all"],
    },
  ],
  requires_code_exec: false,
  requires_judge: false,
};

vi.mock("../api/client", () => ({
  api: {
    getBenchmark: vi.fn(async () => suiteDetail),
  },
  queryKeys: {
    benchmark: (id: string) => ["benchmarks", id],
  },
}));

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/benchmarks/text-reasoning-v1"]}>
        <Routes>
          <Route path="/benchmarks/:id" element={<BenchmarkDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("BenchmarkDetailPage", () => {
  it("renders tasks and scorer chips", async () => {
    renderPage();

    expect(await screen.findByRole("heading", { name: "text-reasoning-v1" })).toBeInTheDocument();
    expect(screen.getByText("What is 2+2?")).toBeInTheDocument();
    expect(screen.getByText("Capital of France?")).toBeInTheDocument();
    expect(screen.getByText("exact_match")).toBeInTheDocument();
    expect(screen.getByText("contains_all")).toBeInTheDocument();
    expect(screen.getByText("arithmetic")).toBeInTheDocument();
    expect(screen.getByText("capital")).toBeInTheDocument();
  });
});
