import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { createBrowserRouter, RouterProvider } from 'react-router-dom';
import { App } from './app/App';
import { ToastProvider } from './components/Toast';
import './index.css';

const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false } },
});

// Data router: cần cho `useBlocker` (cảnh báo rời Cài đặt khi chưa Lưu). `App` giữ `<Routes>` bên trong.
const router = createBrowserRouter(
  [
    {
      path: '*',
      element: (
        <ToastProvider>
          <App />
        </ToastProvider>
      ),
    },
  ],
  {
    future: {
      v7_relativeSplatPath: true,
    },
  },
);

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} future={{ v7_startTransition: true }} />
    </QueryClientProvider>
  </StrictMode>,
);
