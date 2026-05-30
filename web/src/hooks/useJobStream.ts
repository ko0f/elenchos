import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { JobStatus, ProgressEvent } from "../api/types";

export type JobStreamStatus = "connecting" | "streaming" | "polling" | "done" | "error";

export interface JobStreamState {
  events: ProgressEvent[];
  status: JobStreamStatus;
  runId: string | null;
  summary: Record<string, unknown> | null;
  error: string | null;
}

const POLL_INTERVAL_MS = 2000;

function parseEventData(raw: string): Record<string, unknown> {
  try {
    return JSON.parse(raw) as Record<string, unknown>;
  } catch {
    return {};
  }
}

function summaryFromFinished(data: Record<string, unknown> | undefined): Record<string, unknown> | null {
  if (!data) {
    return null;
  }
  if (data.summary && typeof data.summary === "object") {
    return data.summary as Record<string, unknown>;
  }
  return data;
}

function deriveStateFromJob(job: JobStatus): Pick<JobStreamState, "runId" | "summary" | "error"> {
  const runFinished = job.progress.find((item) => item.event === "run_finished");
  return {
    runId: job.run_id ?? null,
    summary: summaryFromFinished(runFinished?.data) ?? (job.result as Record<string, unknown> | null) ?? null,
    error: job.error ?? null,
  };
}

export function useJobStream(jobId: string | null): JobStreamState {
  const [state, setState] = useState<JobStreamState>({
    events: [],
    status: jobId ? "connecting" : "done",
    runId: null,
    summary: null,
    error: null,
  });
  const seenRef = useRef(0);

  useEffect(() => {
    if (!jobId) {
      return;
    }

    seenRef.current = 0;
    let cancelled = false;
    let pollTimer: ReturnType<typeof setInterval> | null = null;
    let source: EventSource | null = null;

    const appendEvents = (incoming: ProgressEvent[]) => {
      if (incoming.length === 0) {
        return;
      }
      seenRef.current += incoming.length;
      setState((prev) => {
        const merged = [...prev.events, ...incoming];
        const runStarted = merged.find((item) => item.event === "run_started");
        const runFinished = merged.find((item) => item.event === "run_finished");
        return {
          ...prev,
          events: merged,
          runId: (runStarted?.data.run_id as string | undefined) ?? prev.runId,
          summary: summaryFromFinished(runFinished?.data) ?? prev.summary,
        };
      });
    };

    const finish = (status: JobStreamStatus, error: string | null = null) => {
      setState((prev) => ({ ...prev, status, error: error ?? prev.error }));
    };

    const startPolling = () => {
      if (pollTimer) {
        return;
      }
      setState((prev) => ({ ...prev, status: "polling" }));

      const poll = async () => {
        if (cancelled) {
          return;
        }
        try {
          const job = await api.getJob(jobId);
          if (cancelled) {
            return;
          }
          const newEvents = job.progress.slice(seenRef.current);
          appendEvents(newEvents);
          const derived = deriveStateFromJob(job);
          setState((prev) => ({
            ...prev,
            runId: derived.runId ?? prev.runId,
            summary: derived.summary ?? prev.summary,
            error: derived.error,
          }));
          if (job.status === "done") {
            finish("done");
            if (pollTimer) {
              clearInterval(pollTimer);
            }
          } else if (job.status === "error") {
            finish("error", derived.error ?? "Job failed");
            if (pollTimer) {
              clearInterval(pollTimer);
            }
          }
        } catch (exc) {
          if (!cancelled) {
            finish("error", exc instanceof Error ? exc.message : "Polling failed");
          }
        }
      };

      void poll();
      pollTimer = setInterval(() => void poll(), POLL_INTERVAL_MS);
    };

    if (typeof EventSource !== "undefined") {
      source = new EventSource(`/api/jobs/${encodeURIComponent(jobId)}/events`);

      source.onopen = () => {
        if (!cancelled) {
          setState((prev) => ({ ...prev, status: "streaming" }));
        }
      };

      source.onmessage = (message) => {
        appendEvents([
          {
            event: "message",
            data: parseEventData(message.data),
          },
        ]);
      };

      const handleNamedEvent = (eventName: string) => (message: MessageEvent) => {
        appendEvents([
          {
            event: eventName,
            data: parseEventData(message.data),
          },
        ]);
        if (eventName === "run_finished") {
          finish("done");
          source?.close();
        }
      };

      source.addEventListener("run_started", handleNamedEvent("run_started"));
      source.addEventListener("task_done", handleNamedEvent("task_done"));
      source.addEventListener("run_finished", handleNamedEvent("run_finished"));

      source.onerror = () => {
        source?.close();
        source = null;
        if (!cancelled) {
          startPolling();
        }
      };
    } else {
      startPolling();
    }

    return () => {
      cancelled = true;
      source?.close();
      if (pollTimer) {
        clearInterval(pollTimer);
      }
    };
  }, [jobId]);

  return state;
}
