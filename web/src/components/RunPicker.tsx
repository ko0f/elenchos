import type { RunSummary } from "../api/types";
import "./RunPicker.css";

interface RunPickerProps {
  runs: RunSummary[];
  selected: string[];
  onChange: (runIds: string[]) => void;
}

export function RunPicker({ runs, selected, onChange }: RunPickerProps) {
  function toggle(runId: string) {
    if (selected.includes(runId)) {
      onChange(selected.filter((id) => id !== runId));
      return;
    }
    onChange([...selected, runId]);
  }

  return (
    <table className="runs-table run-picker">
      <thead>
        <tr>
          <th aria-label="Select" />
          <th>Run ID</th>
          <th>Benchmark</th>
          <th>Model</th>
        </tr>
      </thead>
      <tbody>
        {runs.map((run) => (
          <tr key={run.run_id}>
            <td>
              <input
                type="checkbox"
                aria-label={`Select ${run.run_id}`}
                checked={selected.includes(run.run_id)}
                onChange={() => toggle(run.run_id)}
              />
            </td>
            <td>{run.run_id}</td>
            <td>{run.benchmark?.id ?? "—"}</td>
            <td>{run.model}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
