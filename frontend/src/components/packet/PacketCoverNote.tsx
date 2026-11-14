import { useEffect, useState } from "react";

import {
  useRegenerateCoverNote,
  useSaveCoverNote,
  type CoverNote,
} from "@/api/analysis";
import { errorMessage } from "@/api/client";
import { Button } from "@/components/Button";
import { guardExplanation } from "@/lib/packet";

/**
 * Always a draft. The guard can refuse to produce one at all; that refusal is
 * shown in place of the text, with the reason, because an empty box would look
 * like a bug.
 */
export function PacketCoverNote({
  analysisId,
  note,
}: {
  analysisId: string;
  note: CoverNote;
}) {
  const [text, setText] = useState(note.text ?? "");
  const [copied, setCopied] = useState(false);
  const save = useSaveCoverNote(analysisId);
  const regenerate = useRegenerateCoverNote(analysisId);
  const passed = note.guard_status === "pass" && note.generated;

  useEffect(() => {
    setText(note.text ?? "");
  }, [note.text]);

  const dirty = text !== (note.text ?? "");

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  return (
    <section aria-labelledby="cover-heading" className="space-y-3">
      <div className="flex flex-wrap items-baseline gap-x-2">
        <h2 id="cover-heading" className="text-section">
          Cover note
        </h2>
        {passed ? (
          <span className="rounded-sm border border-partial-line bg-partial-bg px-1.5 text-caption text-partial-fg">
            Draft. Review before sending.
          </span>
        ) : null}
      </div>

      {!passed ? (
        <div className="space-y-2 rounded-md border border-gap-line bg-gap-bg px-3 py-2 text-dense text-gap-fg">
          <p className="font-medium">
            No draft could be verified for this job.
          </p>
          <p>{guardExplanation(note.guard_status ?? "")}</p>
          {note.guard_reason ? (
            <p className="text-caption opacity-90">{note.guard_reason}</p>
          ) : null}
          <Button
            variant="primary"
            busy={regenerate.isPending}
            onClick={() => regenerate.mutate()}
          >
            {regenerate.isPending ? "Trying again…" : "Try again"}
          </Button>
          {regenerate.isError ? (
            <p role="alert" className="text-caption">
              {errorMessage(regenerate.error)}
            </p>
          ) : null}
        </div>
      ) : (
        <>
          <label htmlFor="cover-text" className="block text-dense font-medium">
            The draft
          </label>
          <textarea
            id="cover-text"
            value={text}
            onChange={(event) => setText(event.target.value)}
            rows={10}
            className="w-full rounded-sm border border-line bg-panel p-3 text-dense"
          />
          <p className="text-caption text-muted">
            {note.word_count === 1 ? "1 word" : `${note.word_count} words`}
            {note.edited ? " · you edited this" : ""} · It may only claim
            requirements marked as strong.
          </p>

          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="primary"
              busy={save.isPending}
              disabled={!dirty}
              onClick={() => save.mutate(text)}
            >
              {save.isPending ? "Saving…" : "Save draft"}
            </Button>
            <Button variant="ghost" onClick={() => void copy()}>
              {copied ? "Copied" : "Copy"}
            </Button>
            <Button
              variant="ghost"
              busy={regenerate.isPending}
              onClick={() => regenerate.mutate()}
            >
              {regenerate.isPending ? "Rewriting…" : "Rewrite"}
            </Button>
          </div>
          {save.isError ? (
            <p role="alert" className="text-dense text-gap-fg">
              {errorMessage(save.error)}
            </p>
          ) : null}
          {regenerate.isError ? (
            <p role="alert" className="text-dense text-gap-fg">
              {errorMessage(regenerate.error)}
            </p>
          ) : null}
        </>
      )}
    </section>
  );
}
