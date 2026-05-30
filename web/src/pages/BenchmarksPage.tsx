import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, queryKeys } from "../api/client";
import { SuiteCard } from "../components/SuiteCard";

export function BenchmarksPage() {
  const [query, setQuery] = useState("");
  const { data, isLoading, isError, error } = useQuery({
    queryKey: queryKeys.benchmarks,
    queryFn: api.listBenchmarks,
  });

  const filtered = useMemo(() => {
    if (!data) {
      return [];
    }
    const needle = query.trim().toLowerCase();
    if (!needle) {
      return data;
    }
    return data.filter(
      (suite) =>
        suite.id.toLowerCase().includes(needle) ||
        suite.description.toLowerCase().includes(needle) ||
        suite.type.toLowerCase().includes(needle),
    );
  }, [data, query]);

  if (isLoading) {
    return <div className="page-state">Loading benchmarks…</div>;
  }

  if (isError) {
    return (
      <div className="page-state page-state--error">
        {error instanceof Error ? error.message : "Failed to load benchmarks"}
      </div>
    );
  }

  return (
    <>
      <header className="page-header">
        <h1>Benchmarks</h1>
        <p className="page-header__subtitle">
          Browse benchmark suite templates — built-in and user-defined.
        </p>
      </header>

      <input
        type="search"
        className="search-input"
        placeholder="Search by id, type, or description…"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        aria-label="Search benchmarks"
      />

      {filtered.length === 0 ? (
        <div className="page-state">No benchmarks match your search.</div>
      ) : (
        <div className="suite-grid">
          {filtered.map((suite) => (
            <SuiteCard key={suite.id} suite={suite} />
          ))}
        </div>
      )}
    </>
  );
}
