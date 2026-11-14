import * as Dialog from "@radix-ui/react-dialog";
import { useId, useState } from "react";

import { errorMessage } from "@/api/client";
import { useCreateJob } from "@/api/jobs";
import { Button } from "@/components/Button";

type FieldName = "title" | "company" | "location" | "url";
type Field = { name: FieldName; label: string; hint?: string };

const FIELDS: Field[] = [
  { name: "title", label: "Job title" },
  { name: "company", label: "Company" },
  { name: "location", label: "Location" },
  {
    name: "url",
    label: "Link",
    hint: "Optional. Kept for your reference only; nothing here fetches it.",
  },
];

type Values = Partial<Record<FieldName, string>>;

export function NewJobDialog() {
  const ids = useId();
  const [open, setOpen] = useState(false);
  const [values, setValues] = useState<Values>({});
  const create = useCreateJob();

  function close() {
    setOpen(false);
    setValues({});
    create.reset();
  }

  function value(name: FieldName): string {
    return values[name] ?? "";
  }

  const title = value("title").trim();

  return (
    <Dialog.Root
      open={open}
      onOpenChange={(next) => {
        if (next) setOpen(true);
        else close();
      }}
    >
      <Dialog.Trigger asChild>
        <Button variant="primary">Add a job</Button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-ink/40" />
        <Dialog.Content className="fixed left-1/2 top-1/2 w-[min(560px,92vw)] -translate-x-1/2 -translate-y-1/2 rounded-lg border border-line bg-bg p-5 shadow-lg">
          <Dialog.Title className="text-section">Add a job</Dialog.Title>
          <Dialog.Description className="mt-1 text-dense text-muted">
            Use this for a post you found yourself. Alerts arrive through the
            sync button.
          </Dialog.Description>

          <form
            className="mt-4 space-y-3"
            onSubmit={(event) => {
              event.preventDefault();
              create.mutate(
                {
                  title,
                  company: value("company").trim() || null,
                  location: value("location").trim() || null,
                  url: value("url").trim() || null,
                },
                { onSuccess: () => close() },
              );
            }}
          >
            {FIELDS.map((field) => (
              <div key={field.name}>
                <label
                  htmlFor={`${ids}-${field.name}`}
                  className="block text-dense font-medium"
                >
                  {field.label}
                </label>
                <input
                  id={`${ids}-${field.name}`}
                  value={value(field.name)}
                  onChange={(event) => {
                    const next = event.target.value;
                    setValues((previous) => ({
                      ...previous,
                      [field.name]: next,
                    }));
                  }}
                  required={field.name === "title"}
                  maxLength={field.name === "url" ? 1000 : 200}
                  className="mt-1 w-full rounded-sm border border-line bg-bg px-2 py-1.5 text-dense"
                />
                {field.hint ? (
                  <p className="mt-1 text-caption text-muted">{field.hint}</p>
                ) : null}
              </div>
            ))}

            {create.isError ? (
              <p role="alert" className="text-dense text-gap-fg">
                {errorMessage(create.error)}
              </p>
            ) : null}

            <div className="flex justify-end gap-2 pt-1">
              <Button variant="ghost" onClick={close}>
                Cancel
              </Button>
              <Button
                type="submit"
                variant="primary"
                busy={create.isPending}
                disabled={!title}
              >
                {create.isPending ? "Saving…" : "Save"}
              </Button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
