/**
 * Display formatting. Dates arrive as ISO strings with a UTC offset from the
 * backend (SQLite stores naive times, so the server attaches the zone); what
 * the reader wants is their own wall clock, so these use the local locale.
 */

const dateFormat = new Intl.DateTimeFormat(undefined, {
  year: "numeric",
  month: "short",
  day: "numeric",
});

const dateTimeFormat = new Intl.DateTimeFormat(undefined, {
  year: "numeric",
  month: "short",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

function parse(value: string): Date | null {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

/** "Nov 6, 2026". An unparseable string is shown as-is rather than hidden. */
export function formatDate(value: string): string {
  const date = parse(value);
  return date ? dateFormat.format(date) : value;
}

export function formatDateTime(value: string): string {
  const date = parse(value);
  return date ? dateTimeFormat.format(date) : value;
}

/** "1 version" / "3 versions" — counts are read aloud, so they must agree. */
export function count(
  n: number,
  singular: string,
  plural = `${singular}s`,
): string {
  return `${n} ${n === 1 ? singular : plural}`;
}
