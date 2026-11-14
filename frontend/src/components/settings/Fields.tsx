/**
 * Form primitives for the settings screen. They exist because every settings
 * section needs the same three things: a label wired to its control, a hint in
 * small text, and a value that survives being half-typed.
 */
import { useId, useState, type ReactNode } from "react";

const INPUT =
  "w-full rounded-sm border border-line bg-bg px-2 py-1.5 text-dense";

export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: (id: string) => ReactNode;
}) {
  const id = useId();
  return (
    <div>
      <label htmlFor={id} className="block text-dense font-medium">
        {label}
      </label>
      <div className="mt-1">{children(id)}</div>
      {hint ? <p className="mt-1 text-caption text-muted">{hint}</p> : null}
    </div>
  );
}

export function TextField({
  label,
  value,
  onChange,
  hint,
  placeholder,
  maxLength,
  type = "text",
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  hint?: string;
  placeholder?: string;
  maxLength?: number;
  type?: "text" | "password" | "url";
}) {
  return (
    <Field label={label} hint={hint}>
      {(id) => (
        <input
          id={id}
          type={type}
          value={value}
          placeholder={placeholder}
          maxLength={maxLength}
          onChange={(event) => onChange(event.target.value)}
          className={INPUT}
        />
      )}
    </Field>
  );
}

/**
 * Comma-separated list. The raw text is held locally: trimming on every
 * keystroke would fight the cursor, so parsing happens on the way up and the
 * save path drops the blanks.
 */
export function ListField({
  label,
  values,
  onChange,
  hint,
  placeholder,
}: {
  label: string;
  values: string[];
  onChange: (values: string[]) => void;
  hint?: string;
  placeholder?: string;
}) {
  const [text, setText] = useState(() => values.join(", "));
  return (
    <Field label={label} hint={hint}>
      {(id) => (
        <input
          id={id}
          value={text}
          placeholder={placeholder}
          onChange={(event) => {
            const next = event.target.value;
            setText(next);
            onChange(next.split(",").map((part) => part.trim()));
          }}
          className={INPUT}
        />
      )}
    </Field>
  );
}

export function NumberField({
  label,
  value,
  onChange,
  hint,
  placeholder,
  min,
  max,
  step,
}: {
  label: string;
  value: number | null;
  onChange: (value: number | null) => void;
  hint?: string;
  placeholder?: string;
  min?: number;
  max?: number;
  step?: number;
}) {
  const [text, setText] = useState(() => (value === null ? "" : String(value)));
  return (
    <Field label={label} hint={hint}>
      {(id) => (
        <input
          id={id}
          type="number"
          inputMode="decimal"
          value={text}
          min={min}
          max={max}
          step={step}
          placeholder={placeholder}
          onChange={(event) => {
            const next = event.target.value;
            setText(next);
            const parsed = next.trim() === "" ? null : Number(next);
            // A half-typed "1." must reach the field, not the draft.
            onChange(
              parsed !== null && Number.isFinite(parsed) ? parsed : null,
            );
          }}
          className={INPUT}
        />
      )}
    </Field>
  );
}
