import { AnimatePresence, motion } from "motion/react";
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { Check, CircleAlert, Info, X } from "lucide-react";
import { spring, transition } from "../motion/tokens";

type Tone = "success" | "error" | "info";
interface Toast {
  id: number;
  title: string;
  body?: string;
  tone: Tone;
}

const ToastCtx = createContext<(t: Omit<Toast, "id">) => void>(() => {});
export const useToast = () => useContext(ToastCtx);

const icons = { success: Check, error: CircleAlert, info: Info };
const colors = { success: "var(--color-good)", error: "var(--color-poor)", info: "var(--color-violet-soft)" };

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const dismiss = useCallback((id: number) => setToasts((ts) => ts.filter((t) => t.id !== id)), []);
  const push = useCallback(
    (t: Omit<Toast, "id">) => {
      const id = Date.now() + Math.random();
      setToasts((ts) => [...ts.slice(-3), { ...t, id }]);
      setTimeout(() => dismiss(id), t.tone === "error" ? 7000 : 4000);
    },
    [dismiss],
  );
  const value = useMemo(() => push, [push]);

  return (
    <ToastCtx.Provider value={value}>
      {children}
      <div
        aria-live="polite"
        className="pointer-events-none fixed right-4 bottom-20 z-50 flex w-[min(360px,calc(100vw-2rem))] flex-col gap-2 md:bottom-6"
      >
        <AnimatePresence initial={false}>
          {toasts.map((t) => {
            const Icon = icons[t.tone];
            return (
              <motion.div
                key={t.id}
                layout
                initial={{ opacity: 0, x: 40, scale: 0.96 }}
                animate={{ opacity: 1, x: 0, scale: 1, transition: spring.gentle }}
                exit={{ opacity: 0, x: 40, transition: transition.exit }}
                role={t.tone === "error" ? "alert" : "status"}
                className="glass pointer-events-auto flex items-start gap-3 !rounded-2xl p-4"
              >
                <Icon size={18} style={{ color: colors[t.tone] }} className="mt-0.5 shrink-0" />
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium">{t.title}</p>
                  {t.body && <p className="mt-0.5 text-xs text-muted">{t.body}</p>}
                </div>
                <button
                  type="button"
                  onClick={() => dismiss(t.id)}
                  aria-label="Dismiss"
                  className="rounded-full p-1 text-faint hover:text-ink"
                >
                  <X size={14} />
                </button>
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>
    </ToastCtx.Provider>
  );
}
