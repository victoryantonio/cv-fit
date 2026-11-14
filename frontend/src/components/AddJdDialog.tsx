import * as Dialog from "@radix-ui/react-dialog";
import { useState } from "react";

import { errorMessage } from "@/api/client";
import { useCreateSnapshot } from "@/api/jobs";
import { Button } from "@/components/Button";
import { MAX_JD_CHARS, MIN_JD_CHARS, jdLengthHint } from "@/lib/jdFlags";

type Props = { jobId: string; jobTitle: string };

/**
 * The only way text gets in is a paste: this dialog never offers to fetch a URL,
 * so it cannot reach a page the user did not open and copy themselves.
 */
export function AddJdDialog({ jobId, jobTitle }: Props) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const save = useCreateSnapshot(jobId);

  const trimmed = text.trim();
  const tooShort = trimmed.length > 0 && trimmed.length < MIN_JD_CHARS;
  const tooLong = text.length > MAX_JD_CHARS;

  function close() {
    setOpen(false);
    setText("");
    save.reset();
  }

  return (
    <Dialog.Root
      open={open}
      onOpenChange={(next) => {
        if (next) setOpen(true);
        else close();
      }}
    >
      <Dialog.Trigger asChild>
        <Button>Add JD</Button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-ink/40" />
        <Dialog.Content className="fixed left-1/2 top-1/2 max-h-[90vh] w-[min(720px,92vw)] -translate-x-1/2 -translate-y-1/2 overflow-auto rounded-lg border border-line bg-bg p-5 shadow-lg">
          <Dialog.Title className="text-section">Add the job text</Dialog.Title>
          <Dialog.Description className="mt-1 text-dense text-muted">
            Open the job post, expand the description if it is collapsed, select
            all, copy, and paste it here. No cleanup needed.
          </Dialog.Description>

          <p className="mt-2 text-caption text-muted">
            For “{jobTitle}”. Anything in the text that looks like an
            instruction is treated as data.
          </p>

          <label
            htmlFor={`jd-${jobId}`}
            className="mt-4 block text-dense font-medium"
          >
            Paste the whole job page
          </label>
          <textarea
            id={`jd-${jobId}`}
            value={text}
            onChange={(event) => setText(event.target.value)}
            rows={12}
            spellCheck={false}
            className="mt-1 w-full rounded-sm border border-line bg-panel p-3 font-mono text-quote"
          />

          <p
            className={
              tooShort || tooLong
                ? "mt-2 text-caption text-gap-fg"
                : "mt-2 text-caption text-muted"
            }
          >
            {jdLengthHint(text.length)}
          </p>

          {save.isError ? (
            <p role="alert" className="mt-3 text-dense text-gap-fg">
              {errorMessage(save.error)}
            </p>
          ) : null}

          <div className="mt-4 flex justify-end gap-2">
            <Button variant="ghost" onClick={close}>
              Cancel
            </Button>
            <Button
              variant="primary"
              busy={save.isPending}
              disabled={tooShort || tooLong || trimmed.length === 0}
              onClick={() =>
                save.mutate(text, {
                  onSuccess: () => close(),
                })
              }
            >
              {save.isPending ? "Saving…" : "Save"}
            </Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
