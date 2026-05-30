import type { JobStreamStatus } from "../hooks/useJobStream";

export function jobStatusLabel(
  streamStatus: JobStreamStatus | null,
  pollingOnly: boolean,
): string {
  if (streamStatus === "streaming") {
    return "Live";
  }
  if (streamStatus === "polling") {
    return "Polling";
  }
  if (streamStatus === "connecting") {
    return "Connecting…";
  }
  if (pollingOnly) {
    return "Live";
  }
  return "";
}
