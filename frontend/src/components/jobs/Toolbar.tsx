import { JOB_STATUSES, statusLabel } from "@/api/jobs";

/** Sentinel for "no filter". A select cannot hold `undefined`, so it holds this. */
export const ANY = "any";

type ToolbarProps = {
  status: string;
  filtered: string;
  onStatus: (value: string) => void;
  onFiltered: (value: string) => void;
};

export function JobsToolbar({
  status,
  filtered,
  onStatus,
  onFiltered,
}: ToolbarProps) {
  return (
    <div className="flex flex-wrap items-end gap-3">
      <div>
        <label
          htmlFor="filter-status"
          className="block text-caption text-muted"
        >
          Status
        </label>
        <select
          id="filter-status"
          value={status}
          onChange={(event) => onStatus(event.target.value)}
          className="mt-1 rounded-sm border border-line bg-bg px-2 py-1.5 text-dense"
        >
          <option value={ANY}>Any status</option>
          {JOB_STATUSES.map((value) => (
            <option key={value} value={value}>
              {statusLabel(value)}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label htmlFor="filter-kept" className="block text-caption text-muted">
          Pre-filter
        </label>
        <select
          id="filter-kept"
          value={filtered}
          onChange={(event) => onFiltered(event.target.value)}
          className="mt-1 rounded-sm border border-line bg-bg px-2 py-1.5 text-dense"
        >
          <option value={ANY}>Everything</option>
          <option value="kept">Kept</option>
          <option value="filtered">Filtered out</option>
        </select>
      </div>
    </div>
  );
}
