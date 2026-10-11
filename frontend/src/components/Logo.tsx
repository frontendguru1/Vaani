import { motion } from "motion/react";
import { spring } from "../motion/tokens";

const bars = [0.4, 0.75, 1, 0.55];

export function Logo() {
  return (
    <div className="flex items-center gap-3">
      <motion.div
        className="flex h-9 w-9 items-center justify-center gap-[3px] rounded-[11px] border border-line bg-surface-2"
        whileHover="hover"
      >
        {bars.map((h, i) => (
          <motion.span
            key={i}
            className="w-[3px] rounded-full"
            style={{ height: `${h * 20}px`, background: "var(--gradient-primary)", originY: 0.5 }}
            variants={{ hover: { scaleY: [1, 0.5, 1.15, 1], transition: { ...spring.snappy, delay: i * 0.04 } } }}
          />
        ))}
      </motion.div>
      <div className="leading-tight">
        <span className="block text-lg font-semibold tracking-tight">Vaani</span>
        <span lang="hi" className="block text-xs text-muted">
          वाणी
        </span>
      </div>
    </div>
  );
}
