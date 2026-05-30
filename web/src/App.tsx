import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { BenchmarkDetailPage } from "./pages/BenchmarkDetailPage";
import { BenchmarksPage } from "./pages/BenchmarksPage";
import { PromptPage } from "./pages/PromptPage";
import { RunDetailPage } from "./pages/RunDetailPage";
import { RunPage } from "./pages/RunPage";
import { RunsPage } from "./pages/RunsPage";

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Navigate to="/benchmarks" replace />} />
        <Route path="benchmarks" element={<BenchmarksPage />} />
        <Route path="benchmarks/:id" element={<BenchmarkDetailPage />} />
        <Route path="run" element={<RunPage />} />
        <Route path="prompt" element={<PromptPage />} />
        <Route path="runs" element={<RunsPage />} />
        <Route path="runs/:runId" element={<RunDetailPage />} />
      </Route>
    </Routes>
  );
}
