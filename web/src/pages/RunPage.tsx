import { useCallback } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, queryKeys } from "../api/client";
import { RunLauncher } from "../components/RunLauncher";

export function RunPage() {
  const [searchParams] = useSearchParams();
  const benchmarkId = searchParams.get("benchmark") ?? "";
  const navigate = useNavigate();

  const { data, isLoading, isError, error } = useQuery({
    queryKey: queryKeys.benchmark(benchmarkId),
    queryFn: () => api.getBenchmark(benchmarkId),
    enabled: Boolean(benchmarkId),
  });

  const handleLaunch = useCallback(
    (runId: string) => {
      void navigate(`/runs/${runId}`);
    },
    [navigate],
  );

  if (!benchmarkId) {
    return (
      <div className="page-state page-state--error">
        Missing benchmark query parameter.{" "}
        <Link to="/benchmarks">Pick a benchmark</Link>.
      </div>
    );
  }

  if (isLoading) {
    return <div className="page-state">Loading benchmark…</div>;
  }

  if (isError) {
    return (
      <div className="page-state page-state--error">
        {error instanceof Error ? error.message : "Failed to load benchmark"}
      </div>
    );
  }

  if (!data) {
    return null;
  }

  return (
    <>
      <header className="page-header">
        <p className="page-header__subtitle">
          <Link to={`/benchmarks/${data.id}`}>{data.id}</Link> / Run
        </p>
        <h1>Launch run</h1>
        <p className="page-header__subtitle">
          {data.tasks.length} task{data.tasks.length === 1 ? "" : "s"} · {data.type}
        </p>
      </header>

      <RunLauncher suite={data} onLaunch={handleLaunch} />
    </>
  );
}
