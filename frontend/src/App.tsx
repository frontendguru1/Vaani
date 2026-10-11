import { MotionConfig, motion } from "motion/react";
import { Aurora } from "./components/Aurora";
import { Logo } from "./components/Logo";
import { SystemStatus } from "./features/health/SystemStatus";
import { press, variants } from "./motion/tokens";

export default function App() {
  return (
    // reducedMotion="user": honours prefers-reduced-motion app-wide (transforms off, fades kept)
    <MotionConfig reducedMotion="user">
      <Aurora />
      <div className="mx-auto flex min-h-screen max-w-5xl flex-col px-5 py-6 sm:px-8">
        <header className="flex items-center justify-between">
          <Logo />
          <span className="font-mono text-xs text-faint">local · offline</span>
        </header>

        <motion.main
          variants={variants.list}
          initial="hidden"
          animate="show"
          className="grid flex-1 content-center gap-6 py-12 md:grid-cols-[1.3fr_1fr] md:gap-10"
        >
          <motion.div variants={variants.fadeUp} className="flex flex-col justify-center">
            <p className="mb-4 font-mono text-xs tracking-[0.2em] text-violet-soft uppercase">
              Phase 0 · scaffolding
            </p>
            <h1 className="text-4xl leading-[1.1] font-semibold tracking-tight sm:text-5xl">
              <span className="text-gradient">Voices you love,</span>
              <br />
              kept on your Mac.
            </h1>
            <p className="mt-5 max-w-md text-base text-muted">
              Clone a voice from a few clean clips, then turn any English or Hindi script into
              speech — nothing ever leaves this machine.
            </p>
            <p lang="hi" className="mt-3 text-sm text-faint">
              आपकी आवाज़, आपके पास।
            </p>
            <div className="mt-8">
              <motion.button
                type="button"
                disabled
                {...press}
                className="btn-primary px-6 py-3 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-60"
                title="Voice creation arrives in Phase 3"
              >
                Create a voice — soon
              </motion.button>
            </div>
          </motion.div>

          <motion.div variants={variants.fadeUp}>
            <SystemStatus />
          </motion.div>
        </motion.main>
      </div>
    </MotionConfig>
  );
}
