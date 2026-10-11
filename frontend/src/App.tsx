import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AnimatePresence, MotionConfig, motion } from "motion/react";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { ToastProvider } from "./components/Toasts";
import { GeneratePage } from "./features/generate/GeneratePage";
import { HistoryPage } from "./features/history/HistoryPage";
import { PronunciationPage } from "./features/pronunciation/PronunciationPage";
import { VoicesPage } from "./features/voices/VoicesPage";
import { transition } from "./motion/tokens";

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 5_000, retry: 1, refetchOnWindowFocus: false } },
});

/** Page transitions: the exiting page keeps its own (frozen) location while it fades out. */
function AnimatedRoutes() {
  const location = useLocation();
  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={location.pathname}
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0, transition: transition.enter }}
        exit={{ opacity: 0, y: -6, transition: transition.exit }}
      >
        <Routes location={location}>
          <Route path="/" element={<Navigate to="/voices" replace />} />
          <Route path="/voices" element={<VoicesPage />} />
          <Route path="/generate" element={<GeneratePage />} />
          <Route path="/history" element={<HistoryPage />} />
          <Route path="/pronunciation" element={<PronunciationPage />} />
          <Route path="*" element={<Navigate to="/voices" replace />} />
        </Routes>
      </motion.div>
    </AnimatePresence>
  );
}

export default function App() {
  return (
    // reducedMotion="user": honours prefers-reduced-motion app-wide (transforms off, fades kept)
    <MotionConfig reducedMotion="user">
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <BrowserRouter>
            <AppShell>
              <AnimatedRoutes />
            </AppShell>
          </BrowserRouter>
        </ToastProvider>
      </QueryClientProvider>
    </MotionConfig>
  );
}
