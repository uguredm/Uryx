/** Renderer giriş noktası. */

import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { App } from '@/App';
import { applyAccentTheme, peekCachedAccent } from '@/lib/theme';
import { tNow } from '@/lib/tNow';
import '@/index.css';

applyAccentTheme(peekCachedAccent());

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 15_000,
    },
  },
});

const container = document.getElementById('root');
if (!container) {
  throw new Error(tNow('app.rootMissing'));
}

createRoot(container).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);
