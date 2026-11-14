/**
 * Redaction categories are tokens in the text itself (`[EMAIL_1]`), so the
 * count table has to use the same words. An unknown category is shown as-is:
 * a new rule should be visible in the UI the moment it starts matching.
 */
const LABELS: Record<string, string> = {
  EMAIL: "Email addresses",
  PHONE: "Phone numbers",
  URL: "Personal links",
  ID: "ID numbers",
  ADDRESS: "Street addresses",
};

export function redactionLabel(kind: string): string {
  return LABELS[kind] ?? kind;
}
