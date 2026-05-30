import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { useJobStream } from "./useJobStream";

const { getJob } = vi.hoisted(() => ({
  getJob: vi.fn(),
}));

vi.mock("../api/client", () => ({
  api: {
    getJob,
  },
}));

type Listener = (event: MessageEvent) => void;

class MockEventSource {
  static instances: MockEventSource[] = [];
  url: string;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  private listeners = new Map<string, Listener[]>();

  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: Listener) {
    const current = this.listeners.get(type) ?? [];
    current.push(listener);
    this.listeners.set(type, current);
  }

  emit(type: string, data: Record<string, unknown>) {
    const payload = { data: JSON.stringify(data) } as MessageEvent;
    for (const listener of this.listeners.get(type) ?? []) {
      listener(payload);
    }
  }

  close() {
    // noop
  }
}

function StreamProbe({ jobId }: { jobId: string }) {
  const { events, status, runId, summary } = useJobStream(jobId);
  return (
    <div>
      <div data-testid="status">{status}</div>
      <div data-testid="run-id">{runId ?? ""}</div>
      <div data-testid="summary">{summary ? "yes" : "no"}</div>
      <ul>
        {events.map((item, index) => (
          <li key={`${item.event}-${index}`}>{item.event}</li>
        ))}
      </ul>
    </div>
  );
}

describe("useJobStream", () => {
  beforeEach(() => {
    MockEventSource.instances = [];
    vi.stubGlobal("EventSource", MockEventSource);
    getJob.mockReset();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders task_done events and transitions on run_finished", async () => {
    render(<StreamProbe jobId="job-abc" />);

    const source = await waitFor(() => {
      expect(MockEventSource.instances.length).toBe(1);
      return MockEventSource.instances[0];
    });

    source.onopen?.();
    source.emit("run_started", { run_id: "run-abc" });
    source.emit("task_done", {
      task_id: "arithmetic",
      index: 1,
      total: 2,
      score: 1.0,
    });
    source.emit("task_done", {
      task_id: "capital",
      index: 2,
      total: 2,
      score: 0.5,
    });
    source.emit("run_finished", { summary: { mean_score: 0.75 } });

    await waitFor(() => {
      expect(screen.getByTestId("status")).toHaveTextContent("done");
    });
    expect(screen.getByTestId("run-id")).toHaveTextContent("run-abc");
    expect(screen.getByTestId("summary")).toHaveTextContent("yes");
    expect(screen.getByText("run_started")).toBeInTheDocument();
    expect(screen.getAllByText("task_done")).toHaveLength(2);
    expect(screen.getByText("run_finished")).toBeInTheDocument();
  });
});
