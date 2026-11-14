import * as Tabs from "@radix-ui/react-tabs";
import type { ReactNode } from "react";
import { Link, useParams } from "react-router-dom";

import { errorMessage } from "@/api/client";
import { useParserView } from "@/api/cvs";
import { Button } from "@/components/Button";
import { formatDateTime, count } from "@/lib/format";
import {
  explainWarning,
  orderedSections,
  sectionLabel,
} from "@/lib/parserWarnings";
import { redactionLabel } from "@/lib/redaction";

function Meta({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="border-b border-line py-2 last:border-b-0">
      <dt className="text-caption text-muted">{label}</dt>
      <dd className="break-words text-dense">{children}</dd>
    </div>
  );
}

const TABS = [
  { value: "sent", label: "Sent to LLM (redacted)" },
  { value: "sections", label: "Sections" },
] as const;

function TextBlock({ text }: { text: string }) {
  if (text.trim() === "") {
    return (
      <p className="text-dense text-muted">No text was stored for this part.</p>
    );
  }
  return (
    <pre className="whitespace-pre-wrap break-words rounded-md border border-line bg-bg p-3 font-mono text-quote text-ink">
      {text}
    </pre>
  );
}

export function ParserView() {
  const { versionId } = useParams<{ versionId: string }>();
  const view = useParserView(versionId);

  if (view.isPending) {
    return <p className="text-dense text-muted">Loading</p>;
  }

  if (view.isError) {
    return (
      <div className="space-y-3">
        <h1 className="text-title">Parser View</h1>
        <p className="text-dense text-muted">{errorMessage(view.error)}</p>
        <div className="flex gap-3">
          <Button onClick={() => void view.refetch()}>Try again</Button>
          <Link
            to="/cvs"
            className="self-center text-dense text-accent underline"
          >
            Back to CVs
          </Link>
        </div>
      </div>
    );
  }

  const version = view.data;
  const sections = orderedSections(version.section_texts);
  const redactions = Object.entries(version.redaction).filter(
    ([, hits]) => hits > 0,
  );

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <nav aria-label="Breadcrumb" className="text-caption text-muted">
          <Link to="/cvs" className="underline">
            CVs
          </Link>{" "}
          / version {version.version_no}
        </nav>
        <h1 className="text-title">{version.file_name}</h1>
        <p className="text-dense text-muted">
          Version {version.version_no} of this CV, uploaded{" "}
          {formatDateTime(version.uploaded_at)}.
        </p>
      </header>

      {version.warnings.length > 0 ? (
        <section
          aria-labelledby="warnings"
          className="rounded-lg border border-partial-line bg-partial-bg p-4 text-partial-fg"
        >
          <h2 id="warnings" className="text-dense font-medium">
            {count(version.warnings.length, "warning")} from the parser
          </h2>
          <ul className="mt-2 space-y-1">
            {version.warnings.map((code) => {
              const explained = explainWarning(code);
              return (
                <li key={code} className="text-dense">
                  {explained.text}{" "}
                  <span className="text-caption opacity-80">
                    {explained.severity === "warning"
                      ? "Check before analyzing"
                      : "Note"}
                  </span>
                </li>
              );
            })}
          </ul>
        </section>
      ) : null}

      <div className="grid gap-6 md:grid-cols-[240px_1fr]">
        <section
          aria-labelledby="file-info"
          className="rounded-lg border border-line bg-panel p-4"
        >
          <h2 id="file-info" className="mb-2 text-section">
            File
          </h2>
          <dl>
            <Meta label="Name">{version.file_name}</Meta>
            <Meta label="Version">{version.version_no}</Meta>
            <Meta label="Uploaded">{formatDateTime(version.uploaded_at)}</Meta>
            {version.note ? <Meta label="Note">{version.note}</Meta> : null}
            <Meta label="Sections found">
              {count(version.sections.length, "section")}
            </Meta>
            <Meta label="Text sent to a model">
              {count(version.redacted_chars, "character")}
            </Meta>
            <Meta label="File SHA-256">
              <span className="font-mono text-caption">
                {version.file_sha256.slice(0, 16)}…
              </span>
            </Meta>
          </dl>

          <h3 className="mt-4 text-dense font-medium">
            Redacted before sending
          </h3>
          {redactions.length === 0 ? (
            <p className="mt-1 text-caption text-muted">
              Nothing matched the redaction rules in this version.
            </p>
          ) : (
            <ul className="mt-1 space-y-1">
              {redactions.map(([kind, hits]) => (
                <li
                  key={kind}
                  className="flex justify-between gap-2 text-dense"
                >
                  <span className="text-muted">{redactionLabel(kind)}</span>
                  <span className="tabular">{hits}</span>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section aria-labelledby="cv-text">
          <h2 id="cv-text" className="sr-only">
            Text of this version
          </h2>
          <Tabs.Root defaultValue="sent">
            <Tabs.List
              className="flex gap-1 border-b border-line"
              aria-label="Text views"
            >
              {TABS.map((tab) => (
                <Tabs.Trigger
                  key={tab.value}
                  value={tab.value}
                  className="-mb-px border-b-2 border-transparent px-3 py-2 text-dense text-muted data-[state=active]:border-accent data-[state=active]:font-medium data-[state=active]:text-ink"
                >
                  {tab.label}
                </Tabs.Trigger>
              ))}
            </Tabs.List>

            <Tabs.Content value="sent" className="pt-3">
              <p className="mb-2 text-caption text-muted">
                This is the stored text after redaction. It is what a model
                would receive, unchanged.
              </p>
              <TextBlock text={version.text} />
            </Tabs.Content>

            <Tabs.Content value="sections" className="space-y-4 pt-3">
              {sections.length === 0 ? (
                <p className="text-dense text-muted">
                  No sections were recognised in this file.
                </p>
              ) : (
                sections.map(([key, text]) => (
                  <div key={key}>
                    <h3 className="text-dense font-medium">
                      {sectionLabel(key)}
                    </h3>
                    <div className="mt-1">
                      <TextBlock text={text} />
                    </div>
                  </div>
                ))
              )}
            </Tabs.Content>
          </Tabs.Root>
        </section>
      </div>
    </div>
  );
}
