import { errorMessage } from "@/api/client";
import { useSyncAlerts, useSyncStatus } from "@/api/jobs";
import { Button } from "@/components/Button";
import { count, formatDateTime } from "@/lib/format";

export function SyncPanel() {
  const status = useSyncStatus();
  const sync = useSyncAlerts();

  return (
    <div className="flex flex-wrap items-center gap-3">
      <Button busy={sync.isPending} onClick={() => sync.mutate()}>
        {sync.isPending ? "Reading email…" : "Sync alerts"}
      </Button>
      <p className="text-caption text-muted">
        {status.data?.synced_at
          ? `Last sync ${formatDateTime(status.data.synced_at)}`
          : "No sync yet"}
      </p>
      {sync.isError ? (
        <p role="alert" className="text-caption text-gap-fg">
          {errorMessage(sync.error)}
        </p>
      ) : null}
      {sync.isSuccess ? (
        <p role="status" className="text-caption text-strong-fg">
          {count(sync.data.messages, "email read")} ·{" "}
          {count(sync.data.new, "new job")} ·{" "}
          {count(sync.data.duplicate, "duplicate")} ·{" "}
          {count(sync.data.parse_failed.length, "alert")} could not be read
        </p>
      ) : null}
    </div>
  );
}
