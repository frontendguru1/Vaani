import { motion, useReducedMotion } from "motion/react";
import type { ReactNode } from "react";

/** Empty screens invite the next action; the bars idle gently (static under reduced motion). */
export function EmptyState({ title, body, action }: { title: string; body: string; action?: ReactNode }) {
  const reduced = useReducedMotion();
  return (
    <div className="flex flex-col items-center px-6 py-16 text-center">
      <div className="mb-6 flex h-14 items-center gap-1.5" aria-hidden>
        {[0.35, 0.7, 1, 0.6, 0.85, 0.45, 0.25].map((h, i) => (
          <motion.span
            key={i}
            className="w-1.5 rounded-full"
            style={{ height: `${h * 100}%`, background: "var(--gradient-primary)", opacity: 0.7 }}
            animate={reduced ? undefined : { scaleY: [1, 0.45, 1] }}
            transition={{ duration: 1.8, repeat: Infinity, delay: i * 0.12, ease: "easeInOut" }}
          />
        ))}
      </div>
      <h2 className="text-lg font-semibold">{title}</h2>
      <p className="mt-2 max-w-sm text-sm text-muted">{body}</p>
      {action && <div className="mt-6">{action}</div>}
    </div>
  );
}
