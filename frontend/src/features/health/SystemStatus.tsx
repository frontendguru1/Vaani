import { motion } from "motion/react";
import { useEffect, useState } from "react";
import { variants } from "../../motion/tokens";
import { getHealth, type Health } from "./api";

type State = { kind: "loading" } | { kind: "ok"; health: Health } | { kind: "error" };

interface Row {
  label: string;
  value: string;
  ok: boolean;
}

function rows(h: Health): Row[] {
  const d = h.device;
  return [
    { label: "Backend", value: `v${h.version}`, ok: true },
    { label: "Database", value: h.database ? "SQLite · migrated" : "unreachable", ok: h.database },
    {
      label: "ffmpeg",
      value: h.ffmpeg.available ? h.ffmpeg.version ?? "found" : "missing",
      ok: h.ffmpeg.available,
    },
    {
      label: "Compute",
      value: d.torch_installed
        ? `${d.preferred.toUpperCase()} · torch ${d.torch_version}`
        : "torch not installed yet",
      ok: d.torch_installed,
    },
  ];
}

export function SystemStatus() {
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    let alive = true;
    getHealth()
      .then((health) => alive && setState({ kind: "ok", health }))
      .catch(() => alive && setState({ kind: "error" }));
    return () => {
      alive = false;
    };
  }, []);

  return (
    <section className="glass p-6 sm:p-7" aria-labelledby="status-title">
      <div className="mb-5 flex items-center justify-between">
        <h2 id="status-title" className="text-sm font-medium tracking-wide text-muted uppercase">
          System
        </h2>
        <StatusPill state={state} />
      </div>

      <div aria-live="polite">
        {state.kind === "loading" && <Skeleton />}
        {state.kind === "error" && (
          <motion.p variants={variants.shake} animate="shake" className="text-sm text-poor">
            Can’t reach the backend. Start it with <code className="font-mono">uv run vaani-dev</code>{" "}
            — see README.
          </motion.p>
        )}
        {state.kind === "ok" && (
          <motion.ul variants={variants.list} initial="hidden" animate="show" className="space-y-2">
            {rows(state.health).map((r) => (
              <motion.li
                key={r.label}
                variants={variants.fadeUp}
                className="flex items-center justify-between rounded-md bg-surface-2/60 px-4 py-3"
              >
                <span className="flex items-center gap-3 text-sm">
                  <span
                    aria-hidden
                    className={`size-2 rounded-full ${r.ok ? "bg-good" : "bg-okay"}`}
                    style={{ boxShadow: `0 0 10px ${r.ok ? "var(--color-good)" : "var(--color-okay)"}` }}
                  />
                  {r.label}
                </span>
                <span className="font-mono text-xs text-muted">{r.value}</span>
              </motion.li>
            ))}
          </motion.ul>
        )}
      </div>
    </section>
  );
}

function StatusPill({ state }: { state: State }) {
  const [text, color] =
    state.kind === "loading"
      ? ["checking", "var(--color-text-faint)"]
      : state.kind === "error"
        ? ["offline", "var(--color-poor)"]
        : state.health.status === "ok"
          ? ["ready", "var(--color-good)"]
          : ["degraded", "var(--color-okay)"];
  return (
    <motion.span
      key={text}
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      className="rounded-full border border-line px-3 py-1 font-mono text-xs"
      style={{ color }}
    >
      {text}
    </motion.span>
  );
}

function Skeleton() {
  return (
    <ul className="space-y-2" aria-label="Loading system status">
      {[0, 1, 2, 3].map((i) => (
        <li key={i} className="h-11 animate-pulse rounded-md bg-surface-2/60" />
      ))}
    </ul>
  );
}
