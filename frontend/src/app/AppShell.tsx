import { clsx } from "clsx";
import {
  Briefcase,
  FileText,
  Home as HomeIcon,
  Moon,
  Settings as SettingsIcon,
  Sun,
  type LucideIcon,
} from "lucide-react";
import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";

import { applyTheme, readTheme, type Theme } from "./theme";

type NavItem = { to: string; label: string; icon: LucideIcon; end?: boolean };

/**
 * Routes appear here in the same commit as the screen they point at, so the
 * rail never offers a link to a page that does not exist yet.
 */
const NAV_ITEMS: NavItem[] = [
  { to: "/", label: "Home", icon: HomeIcon, end: true },
  { to: "/jobs", label: "Jobs", icon: Briefcase },
  { to: "/cvs", label: "CVs", icon: FileText },
  { to: "/settings", label: "Settings", icon: SettingsIcon },
];

function RailLink({ item }: { item: NavItem }) {
  const Icon = item.icon;
  return (
    <NavLink
      to={item.to}
      end={item.end}
      // The text label disappears at narrow widths, so the name is explicit.
      aria-label={item.label}
      className={({ isActive }) =>
        clsx(
          "flex items-center gap-3 rounded-md px-3 py-2 text-dense transition-colors duration-fast",
          isActive
            ? "bg-accent-subtle font-medium text-accent"
            : "text-muted hover:bg-panel hover:text-ink",
        )
      }
    >
      <Icon aria-hidden size={20} strokeWidth={1.5} />
      <span className="hidden xl:inline">{item.label}</span>
    </NavLink>
  );
}

function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(() => readTheme());
  const next: Theme = theme === "dark" ? "light" : "dark";
  const Icon = theme === "dark" ? Sun : Moon;
  return (
    <button
      type="button"
      onClick={() => {
        applyTheme(next);
        setTheme(next);
      }}
      aria-label={`Switch to ${next} theme`}
      className="rounded-md p-2 text-muted hover:bg-panel hover:text-ink"
    >
      <Icon aria-hidden size={20} strokeWidth={1.5} />
    </button>
  );
}

export function AppShell() {
  return (
    <div className="min-h-screen bg-bg text-ink">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-3 focus:z-dialog focus:rounded-sm focus:bg-bg focus:px-3 focus:py-2 focus:text-dense"
      >
        Skip to content
      </a>

      <header className="sticky top-0 z-header flex h-14 items-center justify-between border-b border-line bg-bg px-4">
        <div className="flex items-center gap-3">
          <span className="text-dense font-medium">CV to job fit</span>
          <nav
            aria-label="Sections"
            className="flex items-center gap-1 md:hidden"
          >
            {NAV_ITEMS.map((item) => (
              <RailLink key={item.to} item={item} />
            ))}
          </nav>
        </div>
        <ThemeToggle />
      </header>

      <div className="flex">
        <nav
          aria-label="Sections"
          className="hidden shrink-0 border-r border-line px-2 py-4 md:block md:w-16 xl:w-60"
        >
          <ul className="space-y-1">
            {NAV_ITEMS.map((item) => (
              <li key={item.to}>
                <RailLink item={item} />
              </li>
            ))}
          </ul>
        </nav>

        <main
          id="main"
          className="mx-auto w-full max-w-content px-4 py-6 sm:px-6 lg:px-8"
        >
          <Outlet />
        </main>
      </div>
    </div>
  );
}
