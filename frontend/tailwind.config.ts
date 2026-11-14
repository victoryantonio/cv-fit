import type { Config } from "tailwindcss";

/**
 * Tailwind maps design tokens by name; it never defines colors of its own.
 * Every value here resolves to a CSS variable set in `src/styles/tokens.css`,
 * so light and dark themes come from one place and no component holds a hex.
 */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "var(--bg)",
        panel: "var(--bg-subtle)",
        line: "var(--border)",
        ink: "var(--text)",
        muted: "var(--text-muted)",
        accent: {
          DEFAULT: "var(--accent)",
          hover: "var(--accent-hover)",
          subtle: "var(--accent-subtle)",
        },
        // Text placed on a filled accent surface: white in light mode, the
        // dark teal in dark mode, where the accent itself is light.
        onaccent: "var(--on-accent)",
        strong: {
          fg: "var(--strong-fg)",
          bg: "var(--strong-bg)",
          line: "var(--strong-border)",
        },
        partial: {
          fg: "var(--partial-fg)",
          bg: "var(--partial-bg)",
          line: "var(--partial-border)",
        },
        gap: {
          fg: "var(--gap-fg)",
          bg: "var(--gap-bg)",
          line: "var(--gap-border)",
        },
        unstable: { fg: "var(--unstable-fg)", bg: "var(--unstable-bg)" },
        danger: "var(--danger)",
      },
      fontFamily: {
        sans: [
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
        mono: [
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "Consolas",
          "monospace",
        ],
      },
      fontSize: {
        title: ["24px", { lineHeight: "32px", fontWeight: "600" }],
        section: ["18px", { lineHeight: "28px", fontWeight: "600" }],
        body: ["16px", { lineHeight: "24px" }],
        dense: ["14px", { lineHeight: "20px" }],
        caption: ["12px", { lineHeight: "16px" }],
        quote: ["13px", { lineHeight: "20px" }],
      },
      borderRadius: { sm: "4px", md: "6px", lg: "8px" },
      maxWidth: { content: "960px", wide: "1440px" },
      transitionDuration: { fast: "120ms", base: "200ms" },
      zIndex: {
        header: "10",
        drawer: "20",
        popover: "30",
        dialog: "40",
        toast: "50",
      },
    },
  },
  plugins: [],
} satisfies Config;
