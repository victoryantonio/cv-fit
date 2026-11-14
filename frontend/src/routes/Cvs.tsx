import { useId, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { errorMessage, isApiError } from "@/api/client";
import {
  useCreateCv,
  useCvs,
  useUploadVersion,
  type CvListItem,
} from "@/api/cvs";
import { Button } from "@/components/Button";
import { FileDropzone } from "@/components/FileDropzone";
import { count, formatDate } from "@/lib/format";

type Notice = { kind: "ok" | "error"; text: string; versionId?: string };

function NoticeBar({ notice }: { notice: Notice }) {
  if (notice.text === "") return null;
  return (
    <div
      role={notice.kind === "error" ? "alert" : "status"}
      className={
        notice.kind === "error"
          ? "rounded-md border border-gap-line bg-gap-bg px-3 py-2 text-dense text-gap-fg"
          : "rounded-md border border-strong-line bg-strong-bg px-3 py-2 text-dense text-strong-fg"
      }
    >
      {notice.text}
      {notice.versionId ? (
        <>
          {" "}
          <Link to={`/cv-versions/${notice.versionId}`} className="underline">
            Open that version
          </Link>
        </>
      ) : null}
    </div>
  );
}

function NewCvForm({ onNotice }: { onNotice: (notice: Notice) => void }) {
  const fieldId = useId();
  const [label, setLabel] = useState("");
  const [targetRole, setTargetRole] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const create = useCreateCv();
  const upload = useUploadVersion();
  const busy = create.isPending || upload.isPending;

  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      const cv = await create.mutateAsync({
        label: label.trim(),
        target_role: targetRole.trim() || null,
      });
      if (!file) {
        onNotice({
          kind: "ok",
          text: `"${cv.label}" created. Add a file to it below.`,
        });
        setLabel("");
        setTargetRole("");
        return;
      }
      try {
        const version = await upload.mutateAsync({ cvId: cv.id, file });
        onNotice({
          kind: "ok",
          text: `"${cv.label}" created with version ${version.version_no}.`,
        });
        setLabel("");
        setTargetRole("");
        setFile(null);
      } catch (error) {
        // The CV exists now; say so, or the user will create a second one.
        onNotice({
          kind: "error",
          text: `"${cv.label}" was created, but the file was not stored: ${errorMessage(error)}`,
        });
      }
    } catch (error) {
      onNotice({ kind: "error", text: errorMessage(error) });
    }
  }

  return (
    <form onSubmit={submit} className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label
            htmlFor={`${fieldId}-label`}
            className="block text-dense font-medium"
          >
            Label
          </label>
          <input
            id={`${fieldId}-label`}
            value={label}
            onChange={(event) => setLabel(event.target.value)}
            required
            maxLength={60}
            placeholder="Backend CV"
            className="mt-1 w-full rounded-sm border border-line bg-bg px-2 py-1.5 text-dense"
          />
        </div>
        <div>
          <label
            htmlFor={`${fieldId}-role`}
            className="block text-dense font-medium"
          >
            Target role (optional)
          </label>
          <input
            id={`${fieldId}-role`}
            value={targetRole}
            onChange={(event) => setTargetRole(event.target.value)}
            maxLength={120}
            placeholder="Backend engineer"
            className="mt-1 w-full rounded-sm border border-line bg-bg px-2 py-1.5 text-dense"
          />
        </div>
      </div>

      <FileDropzone
        id={`${fieldId}-file`}
        label={file ? file.name : "Choose the CV file, or drop it here"}
        hint="PDF or DOCX, up to 5 MB. The file is optional here; you can add it after creating the CV."
        disabled={busy}
        onFile={setFile}
      />

      <div className="flex flex-wrap items-center gap-3">
        <Button
          type="submit"
          variant="primary"
          busy={busy}
          disabled={label.trim() === ""}
        >
          {busy ? "Saving…" : "Add CV"}
        </Button>
        <span className="text-caption text-muted">
          The text is parsed on this machine and redacted before any model sees
          it.
        </span>
      </div>
    </form>
  );
}

function CvRow({
  cv,
  onNotice,
}: {
  cv: CvListItem;
  onNotice: (notice: Notice) => void;
}) {
  const inputId = useId();
  const upload = useUploadVersion();

  async function uploadFile(file: File) {
    try {
      const version = await upload.mutateAsync({ cvId: cv.id, file });
      onNotice({
        kind: "ok",
        text: `"${cv.label}" now has version ${version.version_no}.`,
      });
    } catch (error) {
      const duplicateVersionId =
        isApiError(error) && error.code === "CONFLICT"
          ? (error.details.version_id as string | undefined)
          : undefined;
      onNotice({
        kind: "error",
        text: errorMessage(error),
        versionId: duplicateVersionId,
      });
    }
  }

  return (
    <li className="rounded-lg border border-line bg-panel p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-dense font-medium">{cv.label}</h3>
          <p className="text-caption text-muted">
            {cv.target_role ? `${cv.target_role} · ` : ""}
            {count(cv.version_count, "version")} · created{" "}
            {formatDate(cv.created_at)}
          </p>
        </div>
        {cv.latest_version_id ? (
          <Link
            to={`/cv-versions/${cv.latest_version_id}`}
            className="text-dense text-accent underline"
          >
            Open latest version
          </Link>
        ) : (
          <span className="text-caption text-muted">No file yet</span>
        )}
      </div>

      <div className="mt-3">
        <FileDropzone
          id={inputId}
          label="Add a version"
          hint="PDF or DOCX, up to 5 MB. A file with the same contents is rejected as a duplicate."
          disabled={upload.isPending}
          onFile={(file) => void uploadFile(file)}
        />
        {upload.isPending ? (
          <p role="status" className="mt-2 text-caption text-muted">
            Uploading and parsing…
          </p>
        ) : null}
      </div>
    </li>
  );
}

export function Cvs() {
  const cvs = useCvs();
  const [notice, setNotice] = useState<Notice>({ kind: "ok", text: "" });

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-title">CVs</h1>
        <p className="text-dense text-muted">
          Each upload becomes a version. Analyses record which version they
          used, so an edit never rewrites an old result.
        </p>
      </header>

      <section
        aria-labelledby="new-cv"
        className="rounded-lg border border-line bg-panel p-4"
      >
        <h2 id="new-cv" className="mb-3 text-section">
          Add a CV
        </h2>
        <NewCvForm onNotice={setNotice} />
      </section>

      <NoticeBar notice={notice} />

      <section aria-labelledby="cv-list" className="space-y-3">
        <h2 id="cv-list" className="text-section">
          Your CVs
        </h2>

        {cvs.isPending ? (
          <p className="text-dense text-muted">Loading</p>
        ) : cvs.isError ? (
          <div className="space-y-3">
            <p className="text-dense text-muted">{errorMessage(cvs.error)}</p>
            <Button onClick={() => void cvs.refetch()}>Try again</Button>
          </div>
        ) : cvs.data.length === 0 ? (
          <p className="rounded-lg border border-dashed border-line px-4 py-6 text-center text-dense text-muted">
            No CVs yet. Use the form above to add your first one.
          </p>
        ) : (
          <ul className="space-y-3">
            {cvs.data.map((cv) => (
              <CvRow key={cv.id} cv={cv} onNotice={setNotice} />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
