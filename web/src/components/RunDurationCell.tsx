import { useEffect, useState } from "react";
import { formatDuration, runDurationMs } from "../lib/format";

interface RunDurationCellProps {
  startedAt: string;
  finishedAt?: string | null;
}

export function RunDurationCell({ startedAt, finishedAt }: RunDurationCellProps) {
  const isLive = !finishedAt;
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!isLive) {
      return;
    }
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [isLive]);

  return formatDuration(runDurationMs(startedAt, finishedAt, now));
}
