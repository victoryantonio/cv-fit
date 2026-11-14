import * as Dialog from "@radix-ui/react-dialog";
import { useId, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { errorMessage } from "@/api/client";
import { useStartAnalysis } from "@/api/analysis";
import { useCvs } from "@/api/cvs";
import { Button } from "@/components/Button";

type Props = { jobTitle: string; snapshotId: string };

/**
 * Starts a packet for one stored job text. The CV is picked here because an
 * analysis is always a pair: one CV version against one job text.
 */
export function RunAnalysisDialog({ jobTitle, snapshotId }: Props) {
  const cvs = useCvs();
  const start = useStartAnalysis();
  const navigate = useNavigate();
  const selectId = useId();
  const [open, setOpen] = useState(false);
  const [cvId, setCvId] = useState("");

  const usable = (cvs.data ?? []).filter((cv) => cv.latest_version_id);
  const chosen =
    usable.find((cv) => cv.id === cvId) ??
    (usable.length === 1 ? usable[0] : undefined);

  function run() {
    if (!chosen?.latest_version_id) return;
    start.mutate(
      { cvVersionId: chosen.latest_version_id, snapshotId },
      {
        onSuccess: (started) => {
          setOpen(false);
          navigate(
            started.kind === "packet"
              ? `/analyses/${started.packet.id}`
              : `/tasks/${started.taskId}`,
          );
        },
      },
    );
  }

  return (
    <Dialog.Root
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) start.reset();
      }}
    >
      <Dialog.Trigger asChild>
        <Button variant="primary">Run analysis</Button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-ink/40" />
        <Dialog.Content className="fixed left-1/2 top-1/2 w-[min(520px,92vw)] -translate-x-1/2 -translate-y-1/2 rounded-lg border border-line bg-bg p-5 shadow-lg">
          <Dialog.Title className="text-section">
            Analyze “{jobTitle}”
          </Dialog.Title>
          <Dialog.Description className="mt-1 text-dense text-muted">
            The latest version of the CV you pick and the job text you pasted
            are sent to the model. Contact details are redacted first.
          </Dialog.Description>

          {cvs.isPending ? (
            <p className="mt-4 text-dense text-muted">Loading</p>
          ) : cvs.isError ? (
            <p role="alert" className="mt-4 text-dense text-gap-fg">
              {errorMessage(cvs.error)}
            </p>
          ) : usable.length === 0 ? (
            <p className="mt-4 text-dense text-muted">
              No CV has a file yet.{" "}
              <Link to="/cvs" className="text-accent underline">
                Upload one first
              </Link>
              .
            </p>
          ) : (
            <>
              <label
                htmlFor={selectId}
                className="mt-4 block text-dense font-medium"
              >
                CV to analyze
              </label>
              <select
                id={selectId}
                value={chosen?.id ?? ""}
                onChange={(event) => setCvId(event.target.value)}
                className="mt-1 w-full rounded-sm border border-line bg-bg px-2 py-1.5 text-dense"
              >
                {usable.length > 1 ? (
                  <option value="">Choose a CV</option>
                ) : null}
                {usable.map((cv) => (
                  <option key={cv.id} value={cv.id}>
                    {cv.label}
                  </option>
                ))}
              </select>
              <p className="mt-2 text-caption text-muted">
                Its latest version is used; earlier versions stay as they are.
              </p>
            </>
          )}

          {start.isError ? (
            <p role="alert" className="mt-3 text-dense text-gap-fg">
              {errorMessage(start.error)}
            </p>
          ) : null}

          <div className="mt-4 flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              busy={start.isPending}
              disabled={!chosen}
              onClick={run}
            >
              {start.isPending ? "Starting…" : "Run analysis"}
            </Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
