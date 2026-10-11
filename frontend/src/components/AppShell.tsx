import { useQuery } from "@tanstack/react-query";
import { motion } from "motion/react";
import { AudioLines, History, Layers, Library, SpellCheck } from "lucide-react";
import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { getHealth } from "../features/health/api";
import { spring } from "../motion/tokens";
import { Aurora } from "./Aurora";
import { Logo } from "./Logo";

const nav = [
  { to: "/voices", label: "Voices", icon: Library },
  { to: "/generate", label: "Generate", icon: AudioLines },
  { to: "/batch", label: "Batch", icon: Layers },
  { to: "/history", label: "History", icon: History },
  { to: "/pronunciation", label: "Pronunciation", icon: SpellCheck },
];

function NavItem({ to, label, icon: Icon, compact }: (typeof nav)[number] & { compact?: boolean }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        `relative flex items-center rounded-xl transition-colors ${
          compact ? "flex-1 flex-col gap-1 py-2 text-[11px]" : "gap-3 px-3 py-2.5 text-sm"
        } ${isActive ? "text-ink" : "text-muted hover:text-ink"}`
      }
    >
      {({ isActive }) => (
        <>
          {isActive && (
            <motion.span
              layoutId={compact ? "nav-pill-m" : "nav-pill"}
              className="absolute inset-0 rounded-xl border border-line bg-white/[0.06]"
              transition={spring.gentle}
            />
          )}
          <Icon size={compact ? 20 : 18} className="relative" />
          <span className="relative">{label}</span>
        </>
      )}
    </NavLink>
  );
}

function SystemLine() {
  const { data, isError } = useQuery({ queryKey: ["health"], queryFn: getHealth, refetchInterval: 15000 });
  const ok = data?.status === "ok";
  const text = isError
    ? "Backend offline"
    : !data
      ? "Connecting…"
      : data.device.torch_installed
        ? `Running locally on ${data.device.preferred === "mps" ? "Apple GPU" : "CPU"}`
        : "Running locally";
  return (
    <p className="flex items-center gap-2 px-3 text-xs text-faint" aria-live="polite">
      <span
        className={`size-1.5 rounded-full ${isError ? "bg-poor" : ok ? "bg-good" : "bg-okay"}`}
        style={{ boxShadow: `0 0 8px ${isError ? "var(--color-poor)" : ok ? "var(--color-good)" : "var(--color-okay)"}` }}
      />
      {text}
    </p>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <>
      <Aurora />
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:rounded-lg focus:bg-surface-2 focus:px-3 focus:py-2">
        Skip to content
      </a>
      <div className="mx-auto flex min-h-dvh max-w-[1400px]">
        <aside className="sticky top-0 hidden h-dvh w-60 shrink-0 flex-col justify-between py-7 pl-6 md:flex">
          <div>
            <div className="mb-10 px-3">
              <Logo />
            </div>
            <nav className="flex flex-col gap-1 pr-4" aria-label="Main">
              {nav.map((n) => (
                <NavItem key={n.to} {...n} />
              ))}
            </nav>
          </div>
          <SystemLine />
        </aside>

        <main id="main" className="min-w-0 flex-1 px-4 pt-6 pb-28 sm:px-8 md:pt-10 md:pb-12">
          <div className="mb-6 md:hidden">
            <Logo />
          </div>
          {children}
        </main>
      </div>

      <nav
        aria-label="Main"
        className="glass fixed inset-x-3 bottom-3 z-30 flex !rounded-2xl p-1.5 md:hidden"
      >
        {nav.map((n) => (
          <NavItem key={n.to} {...n} compact />
        ))}
      </nav>
    </>
  );
}

export function PageHeader({ title, sub, action }: { title: string; sub?: string; action?: ReactNode }) {
  return (
    <header className="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight sm:text-[2.5rem] sm:leading-[1.1]">
          <span className="text-gradient">{title}</span>
        </h1>
        {sub && <p className="mt-2 max-w-xl text-[15px] text-muted">{sub}</p>}
      </div>
      {action}
    </header>
  );
}
