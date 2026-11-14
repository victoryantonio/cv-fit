/**
 * Which packet section the reader is looking at, for the sticky nav's
 * `aria-current`. An observer beats scroll arithmetic here: sections change
 * height when a list is filtered or a `<details>` opens.
 */
import { useEffect, useState } from "react";

export function useActiveSection(ids: readonly string[]): string | null {
  const key = ids.join(" ");
  const [active, setActive] = useState<string | null>(ids[0] ?? null);

  useEffect(() => {
    if (typeof IntersectionObserver === "undefined") return;
    const elements = key
      .split(" ")
      .map((id) => document.getElementById(id))
      .filter((element): element is HTMLElement => element !== null);
    if (elements.length === 0) return;

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible.length > 0) setActive(visible[0]?.target.id ?? null);
      },
      // The top margin clears the app header, so a section counts as current
      // once its heading passes the header rather than the viewport edge.
      { rootMargin: "-96px 0px -55% 0px" },
    );
    elements.forEach((element) => observer.observe(element));
    return () => observer.disconnect();
  }, [key]);

  return active;
}
