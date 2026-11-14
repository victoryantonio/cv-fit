import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * The token pairs the design promises, checked as arithmetic rather than by
 * eye. DESIGN.md §5.1 says the verdict-on-tint and dark-mode pairs "must be
 * verified with a contrast checker in CI", so this file reads `tokens.css`
 * itself: a palette edit that dims a caption is a failing test, and a renamed
 * token cannot quietly drop out of the check.
 */
const CSS = readFileSync(join(import.meta.dirname, "tokens.css"), "utf8");

type Palette = Record<string, string>;

function palette(selector: RegExp): Palette {
  const body = CSS.match(selector)?.[1];
  if (!body) throw new Error(`tokens.css has no block matching ${selector}`);
  const tokens: Palette = {};
  for (const [, name, hex] of body.matchAll(
    /--([a-z-]+):\s*(#[0-9a-fA-F]{6})/g,
  )) {
    if (name && hex) tokens[name] = hex;
  }
  return tokens;
}

const LIGHT = palette(/^:root\s*\{([^}]*)\}/m);
const DARK = palette(/^\[data-theme="dark"\]\s*\{([^}]*)\}/m);

/** WCAG 2.x relative luminance of an sRGB channel. */
function channel(value: number): number {
  const ratio = value / 255;
  return ratio <= 0.03928 ? ratio / 12.92 : ((ratio + 0.055) / 1.055) ** 2.4;
}

function luminance(hex: string): number {
  const value = Number.parseInt(hex.slice(1), 16);
  return (
    0.2126 * channel((value >> 16) & 0xff) +
    0.7152 * channel((value >> 8) & 0xff) +
    0.0722 * channel(value & 0xff)
  );
}

function contrast(one: string, other: string): number {
  const [light, dark] =
    luminance(one) > luminance(other)
      ? [luminance(one), luminance(other)]
      : [luminance(other), luminance(one)];
  return (light + 0.05) / (dark + 0.05);
}

type Pair = { fg: string; bg: string; min: number; why: string };

/** Text, and the tinted surfaces it is printed on. */
const TEXT: Pair[] = [
  { fg: "text", bg: "bg", min: 4.5, why: "body text" },
  { fg: "text", bg: "bg-subtle", min: 4.5, why: "body text on panels" },
  { fg: "text-muted", bg: "bg", min: 4.5, why: "captions and meta" },
  { fg: "text-muted", bg: "bg-subtle", min: 4.5, why: "captions on panels" },
  { fg: "accent", bg: "bg", min: 4.5, why: "links" },
  { fg: "accent", bg: "bg-subtle", min: 4.5, why: "links on panels" },
  { fg: "accent-hover", bg: "bg", min: 4.5, why: "hovered links" },
  { fg: "on-accent", bg: "accent", min: 4.5, why: "primary button label" },
  { fg: "strong-fg", bg: "strong-bg", min: 4.5, why: "strong verdict" },
  { fg: "partial-fg", bg: "partial-bg", min: 4.5, why: "partial verdict" },
  { fg: "gap-fg", bg: "gap-bg", min: 4.5, why: "gap verdict" },
  { fg: "unstable-fg", bg: "unstable-bg", min: 4.5, why: "low-agreement flag" },
  { fg: "danger", bg: "bg", min: 4.5, why: "error text" },
];

/** Non-text UI: the focus ring has to be visible against both surfaces. */
const NON_TEXT: Pair[] = [
  { fg: "accent", bg: "bg", min: 3, why: "focus ring on the page" },
  { fg: "accent", bg: "bg-subtle", min: 3, why: "focus ring on a panel" },
];

const PALETTES: Record<string, Palette> = { light: LIGHT, dark: DARK };

describe("design tokens", () => {
  it("defines the same tokens in both palettes", () => {
    // A token added to one theme and forgotten in the other renders as nothing,
    // which is invisible until someone opens the app in that theme.
    expect(Object.keys(DARK).sort()).toEqual(Object.keys(LIGHT).sort());
  });

  for (const [theme, tokens] of Object.entries(PALETTES)) {
    for (const pair of [...TEXT, ...NON_TEXT]) {
      it(`${theme}: ${pair.fg} on ${pair.bg} reaches ${pair.min}:1 (${pair.why})`, () => {
        const fg = tokens[pair.fg];
        const bg = tokens[pair.bg];
        expect(
          fg,
          `${pair.fg} is missing from the ${theme} palette`,
        ).toBeDefined();
        expect(
          bg,
          `${pair.bg} is missing from the ${theme} palette`,
        ).toBeDefined();
        if (!fg || !bg) return;
        expect(contrast(fg, bg)).toBeGreaterThanOrEqual(pair.min);
      });
    }
  }
});
