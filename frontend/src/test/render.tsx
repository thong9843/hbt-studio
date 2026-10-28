import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render } from '@testing-library/react';
import type { ReactElement } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { RenderJobProvider } from '../components/RenderJobProvider';

export function renderWithProviders(
  ui: ReactElement,
  route: string | { pathname: string; state?: unknown } = '/',
) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[route]}>
        <RenderJobProvider>{ui}</RenderJobProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
