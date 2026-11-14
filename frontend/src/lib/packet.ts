/**
 * Plain words for the analysis vocabulary.
 *
 * The API stores codes (`strong_fit`, `rejected_banned_phrase`, `s3_ground`),
 * not sentences, so every screen that shows one goes through this module. A
 * code with no entry falls back to the raw code: hiding it would leave the user
 * staring at a blank where a reason should be.
 */

const FIT_LABELS: Record<string, string> = {
  strong_fit: "Strong fit",
  reasonable_fit: "Reasonable fit",
  stretch: "Stretch",
};

export function fitLabel(label: string): string {
  return FIT_LABELS[label] ?? label;
}

const VERDICT_LABELS: Record<string, string> = {
  strong: "Strong",
  partial: "Partial",
  gap: "Gap",
};

export function verdictLabel(verdict: string | null | undefined): string {
  if (!verdict) return "Not matched";
  return VERDICT_LABELS[verdict] ?? verdict;
}

const IMPORTANCE_LABELS: Record<string, string> = {
  knockout: "Knockout",
  weight: "Must-have",
  nice: "Nice-to-have",
};

export function importanceLabel(importance: string): string {
  return IMPORTANCE_LABELS[importance] ?? importance;
}

const SCOPE_LABELS: Record<string, string> = {
  general: "General",
  job_specific: "This job",
};

/** `general` improves the master CV; `job_specific` only reorders or emphasizes. */
export function scopeLabel(scope: string): string {
  return SCOPE_LABELS[scope] ?? scope;
}

const TYPE_LABELS: Record<string, string> = {
  reword: "Reword",
  reorder: "Reorder",
  emphasize: "Emphasize",
  add_keyword: "Add keyword",
  gap_note: "Gap note",
};

export function suggestionTypeLabel(type: string): string {
  return TYPE_LABELS[type] ?? type;
}

const SECTION_LABELS: Record<string, string> = {
  summary: "Summary",
  experience: "Experience",
  skills: "Skills",
  projects: "Projects",
  education: "Education",
  certifications: "Certifications",
  other: "Other",
};

export function targetSectionLabel(section: string): string {
  return SECTION_LABELS[section] ?? section;
}

const DECISION_LABELS: Record<string, string> = {
  undecided: "Undecided",
  accepted: "Accepted",
  rejected: "Rejected",
};

export function decisionLabel(decision: string): string {
  return DECISION_LABELS[decision] ?? decision;
}

/**
 * Why a guard rejected a draft, in one sentence.
 *
 * Both guards store `rejected_<rule>`; the rule names are short on purpose, so
 * this is the only place that spells out what each one actually checked.
 */
const GUARD_REASONS: Record<string, string> = {
  numbers_not_in_cv: "It used a number that is nowhere in this CV.",
  unknown_vocabulary:
    "It named a tool, employer or credential that is not in this CV.",
  gap_note_has_rewrite:
    "It offered rewrite text for a gap, and a gap is not something a reword can close.",
  original_not_in_cv: "It rewrote a line that is not in this CV word for word.",
  banned_phrase: "It used an empty claim that reads as filler.",
  word_count_out_of_range: "The note was outside the allowed word range.",
  not_english: "The note was not written in English.",
  recommendation_language:
    "It told you whether to apply, and this tool never gives that verdict.",
  no_claims_asserted: "It did not assert a single verified match.",
  asserted_index_not_strong:
    "It asserted a requirement whose verdict is not strong.",
  claim_quote_not_in_cv:
    "One of the quotes behind its claims is not in this CV.",
  asserts_open_requirement:
    "It claimed a requirement that this CV has no evidence for.",
  invented_recipient: "It addressed someone whose name is nowhere in the post.",
  no_strong_matches:
    "No requirement had verified evidence, so no draft was requested.",
};

/** `pass`, `no_strong_matches` and anything unrecognised are handled by callers. */
export function guardExplanation(status: string): string {
  const code = status.startsWith("rejected_")
    ? status.slice("rejected_".length)
    : status;
  return GUARD_REASONS[code] ?? `The guard reported "${code}".`;
}

const MATCH_FLAGS: Record<string, string> = {
  unstable: "The repeated runs disagreed, so the weaker verdict was kept.",
  ungrounded_evidence:
    "The quote could not be found in this CV, so the verdict was lowered to a gap.",
  quote_trimmed: "Only part of the quoted line appears in this CV verbatim.",
  no_match: "No match was recorded for this requirement.",
};

export function matchFlagLabel(flag: string): string {
  return MATCH_FLAGS[flag] ?? flag;
}

const CONSTRAINT_STATUS_LABELS: Record<string, string> = {
  ok: "Matches",
  conflict: "Conflicts",
  review: "Needs a look",
  not_stated: "Not stated",
};

export function constraintStatusLabel(status: string): string {
  return CONSTRAINT_STATUS_LABELS[status] ?? status;
}

const CONSTRAINT_KIND_LABELS: Record<string, string> = {
  work_mode: "Work mode",
  locations: "Location",
  languages: "Language",
  salary: "Salary",
  work_authorization: "Work authorization",
};

export function constraintKindLabel(kind: string): string {
  return CONSTRAINT_KIND_LABELS[kind] ?? kind;
}

const STEP_LABELS: Record<string, string> = {
  s0_preflight: "Checking the CV and the job text",
  s1_extract: "Extracting the requirements",
  s2_match: "Comparing each requirement with the CV",
  s3_ground: "Checking every quote against the CV",
  s4_vote: "Reconciling the repeated runs",
  s5_suggest: "Writing CV suggestions",
  s6_fabrication_guard: "Checking suggestions for invented facts",
  s7_cover_note: "Writing the cover note draft",
  s8_cover_note_guard: "Checking the cover note",
  s9_persist: "Saving the packet",
};

/** `null` means the worker has not reported a step yet. */
export function stepLabel(step: string | null | undefined): string {
  if (!step) return "Waiting for the worker";
  return STEP_LABELS[step] ?? step;
}

const STEP_ORDER: readonly string[] = [
  "s0_preflight",
  "s1_extract",
  "s2_match",
  "s3_ground",
  "s4_vote",
  "s5_suggest",
  "s6_fabrication_guard",
  "s7_cover_note",
  "s8_cover_note_guard",
  "s9_persist",
];

/** Every step, so the progress list can show what is done and what is left. */
export function allSteps(): readonly string[] {
  return STEP_ORDER;
}

const TASK_STATUS_LABELS: Record<string, string> = {
  queued: "Queued",
  running: "Running",
  ok: "Finished",
  failed: "Failed",
  cancelled: "Cancelled",
};

export function taskStatusLabel(status: string): string {
  return TASK_STATUS_LABELS[status] ?? status;
}

/** "3/3 agree" or "2/3 agree"; the total is what the vote step actually ran. */
export function votesText(votes: Record<string, number>): string {
  const total = Object.values(votes).reduce((sum, n) => sum + n, 0);
  const winning = Math.max(0, ...Object.values(votes));
  return `${winning}/${total || 0} agree`;
}
