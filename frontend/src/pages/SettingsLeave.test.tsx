import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Link, RouterProvider, createMemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { AppSettings, SensitiveWords } from '../api/types';
import { stubFetch } from '../test/fakes';
import { SettingsPage } from './SettingsPage';

// Data router + jsdom: `Request` của Node từ chối `AbortSignal` của jsdom, nên bỏ `signal` ở đây.
beforeEach(() => {
  const NativeRequest = globalThis.Request;
  vi.stubGlobal(
    'Request',
    class extends NativeRequest {
      constructor(input: RequestInfo | URL, init?: RequestInit) {
        super(input, init ? { ...init, signal: undefined } : init);
      }
    },
  );
});
afterEach(() => vi.unstubAllGlobals());

const appSettings: AppSettings = {
  default_fps: 50,
  theme: { primary: '#146268', accent: '#DE5C48' },
  whisper_model: 'auto',
  whisper_timeout_seconds: 300,
};
const words: SensitiveWords = {
  categories: [{ id: 'alcohol', level: 'warn', words: ['bia'], hint: '' }],
};
const json = (body: unknown) =>
  new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } });

function open() {
  stubFetch({
    'GET /api/settings/app': appSettings,
    'GET /api/settings/sensitive-words': words,
    'PUT /api/settings/app': (_u: string, init?: RequestInit) =>
      json(JSON.parse(String(init?.body))),
    'PUT /api/settings/sensitive-words': (_u: string, init?: RequestInit) =>
      json(JSON.parse(String(init?.body))),
  });
  const router = createMemoryRouter(
    [
      {
        path: '/settings',
        element: (
          <>
            <Link to="/">Về trang chủ</Link>
            <SettingsPage />
          </>
        ),
      },
      { path: '/', element: <p>Trang chủ mẫu</p> },
    ],
    { initialEntries: ['/settings'] },
  );
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return router;
}

const beforeUnload = () => {
  const ev = new Event('beforeunload', { cancelable: true });
  window.dispatchEvent(ev);
  return ev.defaultPrevented;
};

describe('Cài đặt: cảnh báo khi rời mà chưa Lưu', () => {
  it('does not ask when nothing changed', async () => {
    const router = open();
    const user = userEvent.setup();
    await screen.findByRole('button', { name: '60 fps' });
    expect(beforeUnload()).toBe(false);
    await user.click(screen.getByRole('link', { name: 'Về trang chủ' }));
    expect(await screen.findByText('Trang chủ mẫu')).toBeInTheDocument();
    expect(screen.queryByRole('alertdialog')).toBeNull();
    expect(router.state.location.pathname).toBe('/');
  });

  it('asks inside the app when leaving with unsaved changes; staying keeps the screen', async () => {
    const router = open();
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: '60 fps' }));
    await user.click(screen.getByRole('link', { name: 'Về trang chủ' }));
    const dialog = await screen.findByRole('alertdialog', { name: 'Rời Cài đặt?' });
    expect(dialog).toHaveTextContent('Còn thay đổi chưa lưu');
    await user.click(screen.getByRole('button', { name: 'Ở lại' }));
    await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull());
    expect(router.state.location.pathname).toBe('/settings');
    expect(screen.getByRole('button', { name: '60 fps' })).toHaveAttribute('aria-pressed', 'true');

    await user.click(screen.getByRole('link', { name: 'Về trang chủ' }));
    await user.click(await screen.findByRole('button', { name: 'Rời đi' }));
    expect(await screen.findByText('Trang chủ mẫu')).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/');
  });

  it('attaches beforeunload only while dirty and removes it after Lưu', async () => {
    open();
    const user = userEvent.setup();
    expect(beforeUnload()).toBe(false);
    await user.click(await screen.findByRole('button', { name: '60 fps' }));
    expect(beforeUnload()).toBe(true);
    await user.click(screen.getByRole('button', { name: 'Lưu' }));
    expect(await screen.findByText('Đã lưu')).toBeInTheDocument();
    expect(beforeUnload()).toBe(false);
  });

  it('does not ask after Lưu', async () => {
    const router = open();
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: '60 fps' }));
    await user.click(screen.getByRole('button', { name: 'Lưu' }));
    expect(await screen.findByText('Đã lưu')).toBeInTheDocument();
    await user.click(screen.getByRole('link', { name: 'Về trang chủ' }));
    expect(await screen.findByText('Trang chủ mẫu')).toBeInTheDocument();
    expect(screen.queryByRole('alertdialog')).toBeNull();
    expect(router.state.location.pathname).toBe('/');
  });

  it('removes beforeunload when the screen is left', async () => {
    open();
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: '60 fps' }));
    await user.click(screen.getByRole('link', { name: 'Về trang chủ' }));
    await user.click(await screen.findByRole('button', { name: 'Rời đi' }));
    await screen.findByText('Trang chủ mẫu');
    expect(beforeUnload()).toBe(false);
  });
});
