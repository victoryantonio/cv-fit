import { clsx } from "clsx";
import { useState } from "react";

/**
 * One file, chosen by click or by drop. The input stays in the DOM and keeps
 * keyboard focus: a drop zone that only works with a mouse is not a control.
 */
type Props = {
  id: string;
  label: string;
  hint: string;
  accept?: string;
  disabled?: boolean;
  onFile: (file: File) => void;
};

export function FileDropzone({
  id,
  label,
  hint,
  accept = ".pdf,.docx",
  disabled = false,
  onFile,
}: Props) {
  const [dragging, setDragging] = useState(false);

  return (
    <div
      onDragOver={(event) => {
        if (disabled) return;
        event.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(event) => {
        event.preventDefault();
        setDragging(false);
        if (disabled) return;
        const file = event.dataTransfer.files[0];
        if (file) onFile(file);
      }}
      className={clsx(
        "rounded-lg border border-dashed px-4 py-4 transition-colors duration-fast focus-within:outline focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-accent",
        dragging ? "border-accent bg-accent-subtle" : "border-line bg-panel",
        disabled && "opacity-60",
      )}
    >
      <input
        id={id}
        type="file"
        accept={accept}
        disabled={disabled}
        onChange={(event) => {
          const file = event.target.files?.[0];
          // Reset first: choosing the same path twice must fire a change event.
          event.target.value = "";
          if (file) onFile(file);
        }}
        className="sr-only"
      />
      <label htmlFor={id} className="block cursor-pointer text-dense">
        <span className="font-medium text-ink">{label}</span>
        <span className="mt-1 block text-caption text-muted">{hint}</span>
      </label>
    </div>
  );
}
