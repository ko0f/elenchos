import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, queryKeys } from "../api/client";
import { SuiteTaskPanel } from "../components/SuiteTaskPanel";

export function BenchmarkDetailPage() {
  const { id = "" } = useParams();
  const { data, isLoading, isError, error } = useQuery({
    queryKey: queryKeys.benchmark(id),
    queryFn: () => api.getBenchmark(id),
    enabled: Boolean(id),
  });

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
          <Link to="/benchmarks">Benchmarks</Link> / {data.id}
        </p>
        <h1>{data.id}</h1>
        <p className="page-header__subtitle">
          v{data.version} · {data.type} · {data.tasks.length} task
          {data.tasks.length === 1 ? "" : "s"}
        </p>
        <p className="page-header__subtitle">{data.description}</p>
        {(data.requires_code_exec || data.requires_judge) && (
          <div className="hint-badges">
            {data.requires_code_exec && (
              <span className="hint-badge hint-badge--warn">Requires code exec</span>
            )}
            {data.requires_judge && (
              <span className="hint-badge hint-badge--info">Requires judge</span>
            )}
          </div>
        )}
      </header>

      <div className="task-list">
        {data.tasks.map((task) => (
          <SuiteTaskPanel key={task.id} task={task} />
        ))}
      </div>
    </>
  );
}
