import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, queryKeys } from "../api/client";
import type { TaskDoneData } from "../api/types";
import { useJobStream } from "../hooks/useJobStream";
import { BaselineScoreBadge } from "./BaselineScoreBadge";
import "./RunProgress.css";
import "./RunTableProgressCell.css";

const LIVE_POLL_MS = 2000;
const MAX_JOB_LOOKUP_POLLS = 3;

interface RunTableProgressCellProps {
  runId: string;
  finishedAt?: string | null;
  benchmarkId?: string | null;
  baselineScore?: number | null;
  isBaseline?: boolean;
}

export function RunTableProgressCell({
  runId,
  finishedAt,
  benchmarkId,
  baselineScore,
  isBaseline,
}: RunTableProgressCellProps) {
  const queryClient = useQueryClient();
  const isLive = !finishedAt;
  const [jobLookupCount, setJobLookupCount] = useState(0);

  useEffect(() => {
    setJobLookupCount(0);
  }, [runId]);

  const { data: runJob } = useQuery({
    queryKey: queryKeys.runJob(runId),
    queryFn: async () => {
      const job = await api.getRunJob(runId);
      if (job == null) {
        setJobLookupCount((count) => count + 1);
      }
      return job;
    },
    enabled: isLive && jobLookupCount < MAX_JOB_LOOKUP_POLLS,
    retry: false,
    refetchInterval: (query) => {
      if (!isLive || query.state.data?.job_id) {
        return false;
      }
      return jobLookupCount < MAX_JOB_LOOKUP_POLLS ? LIVE_POLL_MS : false;
    },
  });

  const jobLookupExhausted =
    isLive && runJob == null && jobLookupCount >= MAX_JOB_LOOKUP_POLLS;
  const shouldPollLive = isLive && (Boolean(runJob?.job_id) || !jobLookupExhausted);

  const { events, status } = useJobStream(shouldPollLive ? (runJob?.job_id ?? null) : null);

  const { data: benchmark } = useQuery({
    queryKey: queryKeys.benchmark(benchmarkId ?? ""),
    queryFn: () => api.getBenchmark(benchmarkId!),
    enabled: shouldPollLive && Boolean(benchmarkId),
  });

  useEffect(() => {
    if (status === "done") {
      void queryClient.invalidateQueries({ queryKey: queryKeys.runs });
      void queryClient.invalidateQueries({ queryKey: queryKeys.run(runId) });
    }
  }, [status, queryClient, runId]);

  if (!isLive) {
    return (
      <BaselineScoreBadge score={baselineScore} isBaseline={isBaseline} />
    );
  }

  if (jobLookupExhausted) {
    return (
      <span className="run-table-progress run-table-progress--orphaned">
        Interrupted
      </span>
    );
  }

  const taskEvents = events.filter((item) => item.event === "task_done");
  const lastTaskEvent = taskEvents[taskEvents.length - 1]?.data as unknown as
    | TaskDoneData
    | undefined;
  const total = lastTaskEvent?.total ?? benchmark?.tasks.length;
  const completed = taskEvents.length;
  const progressPct =
    total != null && total > 0 ? Math.round((completed / total) * 100) : 0;

  return (
    <div className="run-table-progress" aria-label="Run progress">
      {total != null ? (
        <>
          <div className="run-progress__bar-wrap run-table-progress__bar-wrap">
            <div
              className="run-progress__bar"
              style={{ width: `${progressPct}%` }}
            />
          </div>
          <span className="run-table-progress__count">
            {completed}/{total}
          </span>
        </>
      ) : (
        <span className="run-table-progress__count">Starting…</span>
      )}
    </div>
  );
}
