/** Mirrors the limits the API enforces, so the count is never a surprise. */
export const MIN_JD_CHARS = 200;
export const MAX_JD_CHARS = 60_000;

export function jdLengthHint(chars: number): string {
  const counted = `${chars.toLocaleString()} characters`;
  if (chars < MIN_JD_CHARS) {
    return `${counted} · at least ${MIN_JD_CHARS} needed, or there is too little to match against`;
  }
  if (chars > MAX_JD_CHARS) {
    return `${counted} · over the ${MAX_JD_CHARS.toLocaleString()} limit, so cut it down`;
  }
  return counted;
}

/**
 * The API reports flags as short identifiers. Each one is shown as a sentence,
 * and an unknown identifier is still shown: a flag the UI hides is a flag the
 * user cannot judge.
 */
const INJECTION: Record<string, string> = {
  instruction_override:
    "Contains a phrase that tells a reader to ignore earlier instructions.",
  role_assignment: "Contains a phrase that assigns the reader a role.",
  delimiter_escape:
    "Contains markers that look like the delimiters used around pasted text.",
  output_command: "Contains a phrase that asks for a specific output format.",
  hidden_characters: "Contains invisible characters.",
  html_comment: "Contains an HTML comment, which can hide text in a page.",
};

export function explainInjection(flag: string): string {
  return INJECTION[flag] ?? `Reported as "${flag}".`;
}

const TRUNCATION: Record<string, string> = {
  collapsed_marker:
    'Ends with a "see more" marker, so the description was probably collapsed.',
  mid_sentence: "Stops in the middle of a sentence.",
  dangling_word: "Stops abruptly.",
};

export function explainTruncation(reason: string): string {
  return TRUNCATION[reason] ?? `Reported as "${reason}".`;
}

const SOURCE_KINDS: Record<string, string> = {
  page_paste: "Pasted from the page",
  text_paste: "Pasted as text",
  url_fetch: "Fetched from a link",
};

export function sourceKindLabel(kind: string): string {
  return SOURCE_KINDS[kind] ?? kind;
}
