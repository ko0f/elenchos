import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { RunLauncher } from "../components/RunLauncher";
import type { SuiteDetail } from "../api/types";

const baseSuite: SuiteDetail = {
  id: "text-reasoning-v1",
  version: 1,
  type: "text",
  description: "Basic text reasoning tasks.",
  defaults: { params: { temperature: 0.0, max_tokens: 1024 } },
  tasks: [],
  requires_code_exec: false,
  requires_judge: false,
};

vi.mock("../api/client", () => ({
  api: {
    listProviders: vi.fn(async () => [
      { name: "ollama", base_url: "http://127.0.0.1:11434/v1", healthy: true },
    ]),
    listProviderModels: vi.fn(async () => ({ models: ["llama3.1:8b"] })),
    createRun: vi.fn(async () => ({ job_id: "job-1", run_id: "run-1" })),
  },
  queryKeys: {
    providers: ["providers"],
    providerModels: (name: string) => ["providers", name, "models"],
  },
}));

function renderLauncher(suite: SuiteDetail, onLaunch = vi.fn()) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const view = render(
    <QueryClientProvider client={client}>
      <RunLauncher suite={suite} onLaunch={onLaunch} />
    </QueryClientProvider>,
  );
  return { ...view, root: view.container as HTMLElement };
}

async function selectModel(root: HTMLElement) {
  const modelSelect = within(root).getByLabelText("Model");
  await waitFor(() => {
    expect(modelSelect).not.toBeDisabled();
  });
  await userEvent.selectOptions(modelSelect, "llama3.1:8b");
}

describe("RunLauncher", () => {
  it("disables submit until model is selected", async () => {
    const { root } = renderLauncher(baseSuite);

    const submit = await screen.findByRole("button", { name: "Launch run" });
    expect(submit).toBeDisabled();

    await selectModel(root);
    expect(submit).toBeEnabled();
  });

  it("requires code-exec toggle for unit_test suites", async () => {
    const { root } = renderLauncher({ ...baseSuite, id: "coding-basics-v1", requires_code_exec: true });

    await selectModel(root);
    const submit = within(root).getByRole("button", { name: "Launch run" });
    expect(submit).toBeDisabled();

    await userEvent.click(within(root).getByLabelText("Allow code execution"));
    expect(submit).toBeEnabled();
  });

  it("requires judge model for judge_rubric suites", async () => {
    const { root } = renderLauncher({ ...baseSuite, requires_judge: true });

    await selectModel(root);
    const submit = within(root).getByRole("button", { name: "Launch run" });
    expect(submit).toBeDisabled();

    await userEvent.type(within(root).getByLabelText("Judge model"), "ollama/llama3.1:8b");
    expect(submit).toBeEnabled();
  });
});
