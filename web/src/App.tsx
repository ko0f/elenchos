import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { BenchmarkDetailPage } from "./pages/BenchmarkDetailPage";
import { BenchmarksPage } from "./pages/BenchmarksPage";
import { ComparePage } from "./pages/ComparePage";
import { ComparisonDetailPage } from "./pages/ComparisonDetailPage";
import { DashboardPage } from "./pages/DashboardPage";
import { LeaderboardPage } from "./pages/LeaderboardPage";
import { PromptPage } from "./pages/PromptPage";
import { RunDetailPage } from "./pages/RunDetailPage";
import { RunPage } from "./pages/RunPage";
import { RunsPage } from "./pages/RunsPage";

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<DashboardPage />} />
        <Route path="benchmarks" element={<BenchmarksPage />} />
        <Route path="benchmarks/:id" element={<BenchmarkDetailPage />} />
        <Route path="run" element={<RunPage />} />
        <Route path="prompt" element={<PromptPage />} />
        <Route path="runs" element={<RunsPage />} />
        <Route path="runs/:runId" element={<RunDetailPage />} />
        <Route path="compare" element={<ComparePage />} />
        <Route path="comparisons/:comparisonId" element={<ComparisonDetailPage />} />
        <Route path="leaderboard" element={<LeaderboardPage />} />
        <Route path="home" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
