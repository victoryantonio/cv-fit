/**
 * Parser warning codes come from the backend as short identifiers. The screen
 * has to say what each one means, and a code it has never seen must still be
 * visible: a silently dropped warning is worse than an ugly one.
 */
export type WarningSeverity = "warning" | "note";

type Explanation = { severity: WarningSeverity; text: string };

const KNOWN: Record<string, Explanation> = {
  no_text_layer: {
    severity: "warning",
    text: "No selectable text was found. Scanned pages and images arrive as empty text.",
  },
  empty_document: {
    severity: "warning",
    text: "The file contained no text at all.",
  },
  text_short: {
    severity: "warning",
    text: "Less than 300 characters were read. Content inside tables or images may be missing.",
  },
  multi_column_suspected: {
    severity: "warning",
    text: "Looks like two columns; the text order may be scrambled.",
  },
  no_sections_detected: {
    severity: "note",
    text: 'No section headings were recognised, so everything is filed under "other".',
  },
};

export function explainWarning(code: string): Explanation {
  return (
    KNOWN[code] ?? { severity: "note", text: `The parser reported "${code}".` }
  );
}

const SECTION_LABELS: Record<string, string> = {
  summary: "Summary",
  experience: "Experience",
  education: "Education",
  skills: "Skills",
  projects: "Projects",
  certifications: "Certifications",
  other: "Other",
};

/** Sections arrive as machine keys; the UI shows a label, never the key alone. */
export function sectionLabel(key: string): string {
  return SECTION_LABELS[key] ?? key;
}

const ORDER = Object.keys(SECTION_LABELS);

/**
 * Sections in reading order, then anything the backend added that this build
 * does not know about. Nothing is dropped: an unknown section still renders.
 */
export function orderedSections(
  texts: Record<string, string>,
): [string, string][] {
  return Object.keys(texts)
    .sort((left, right) => {
      const leftIndex = ORDER.indexOf(left);
      const rightIndex = ORDER.indexOf(right);
      if (leftIndex === -1 && rightIndex === -1)
        return left.localeCompare(right);
      if (leftIndex === -1) return 1;
      if (rightIndex === -1) return -1;
      return leftIndex - rightIndex;
    })
    .map((key) => [key, texts[key] ?? ""]);
}
