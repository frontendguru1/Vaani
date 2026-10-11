import * as Dialog from "@radix-ui/react-dialog";
import { AnimatePresence, motion } from "motion/react";
import { X } from "lucide-react";
import type { ReactNode } from "react";
import { spring, transition } from "../motion/tokens";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  children: ReactNode;
  wide?: boolean;
  /** Block closing (e.g. while a job is running). */
  locked?: boolean;
}

export function Modal({ open, onOpenChange, title, description, children, wide, locked }: Props) {
  return (
    <Dialog.Root open={open} onOpenChange={(o) => !locked && onOpenChange(o)}>
      <AnimatePresence>
        {open && (
          <Dialog.Portal forceMount>
            <Dialog.Overlay asChild forceMount>
              <motion.div
                className="fixed inset-0 z-40 bg-[rgb(4_3_14/0.7)] backdrop-blur-sm"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1, transition: transition.enter }}
                exit={{ opacity: 0, transition: transition.exit }}
              />
            </Dialog.Overlay>
            <Dialog.Content asChild forceMount onEscapeKeyDown={(e) => locked && e.preventDefault()}
              onPointerDownOutside={(e) => locked && e.preventDefault()}>
              <motion.div
                className={`glass fixed top-1/2 left-1/2 z-50 max-h-[90dvh] w-[calc(100vw-1.5rem)] overflow-y-auto p-6 !bg-surface-1/90 sm:p-8 ${wide ? "max-w-3xl" : "max-w-md"}`}
                initial={{ opacity: 0, scale: 0.96, x: "-50%", y: "-46%" }}
                animate={{ opacity: 1, scale: 1, x: "-50%", y: "-50%", transition: spring.gentle }}
                exit={{ opacity: 0, scale: 0.97, x: "-50%", y: "-48%", transition: transition.exit }}
              >
                <div className="mb-6 flex items-start justify-between gap-4">
                  <div>
                    <Dialog.Title className="text-xl font-semibold tracking-tight">{title}</Dialog.Title>
                    {description ? (
                      <Dialog.Description className="mt-1 text-sm text-muted">{description}</Dialog.Description>
                    ) : (
                      <Dialog.Description className="sr-only">{title}</Dialog.Description>
                    )}
                  </div>
                  {!locked && (
                    <Dialog.Close className="rounded-full p-2 text-faint transition-colors hover:bg-white/[0.06] hover:text-ink" aria-label="Close">
                      <X size={18} />
                    </Dialog.Close>
                  )}
                </div>
                {children}
              </motion.div>
            </Dialog.Content>
          </Dialog.Portal>
        )}
      </AnimatePresence>
    </Dialog.Root>
  );
}
