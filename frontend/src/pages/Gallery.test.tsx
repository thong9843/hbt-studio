import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { App } from '../app/App';
import appSource from '../app/App.tsx?raw';
import { ToastProvider } from '../components/Toast';
import { stubFetch } from '../test/fakes';
import { renderWithProviders } from '../test/render';
import UiKit from './Gallery';

afterEach(() => {
  vi.unstubAllGlobals();
  document.documentElement.removeAttribute('data-theme');
});

const withToast = (ui: React.ReactElement) => <ToastProvider>{ui}</ToastProvider>;

describe('UiKit page (/dev/ui)', () => {
  it('shows every component group', () => {
    renderWithProviders(withToast(<UiKit />));
    for (const name of [
      'Bộ thành phần',
      'Nút',
      'Chip và công tắc',
      'Thẻ và nhãn',
      'Ô nhập',
      'Tiến độ và khung xương',
      'Hộp thoại, ngăn kéo, menu, thông báo',
    ]) {
      expect(screen.getByRole('heading', { name })).toBeInTheDocument();
    }
  });

  it('forces light and dark with data-theme and restores system on leaving', async () => {
    const { unmount } = renderWithProviders(withToast(<UiKit />));
    const root = document.documentElement;
    expect(root).not.toHaveAttribute('data-theme');
    await userEvent.click(screen.getByRole('button', { name: 'Tối' }));
    expect(root).toHaveAttribute('data-theme', 'dark');
    await userEvent.click(screen.getByRole('button', { name: 'Sáng' }));
    expect(root).toHaveAttribute('data-theme', 'light');
    await userEvent.click(screen.getByRole('button', { name: 'Theo hệ thống' }));
    expect(root).not.toHaveAttribute('data-theme');
    await userEvent.click(screen.getByRole('button', { name: 'Tối' }));
    unmount();
    expect(root).not.toHaveAttribute('data-theme');
  });

  it('keeps the theme the user picked in the app: restores it on "Theo hệ thống" and on leaving', async () => {
    const root = document.documentElement;
    root.setAttribute('data-theme', 'dark'); // lựa chọn từ nút Sáng/Tối của app
    const { unmount } = renderWithProviders(withToast(<UiKit />));
    expect(root).toHaveAttribute('data-theme', 'dark');
    await userEvent.click(screen.getByRole('button', { name: 'Sáng' }));
    expect(root).toHaveAttribute('data-theme', 'light');
    await userEvent.click(screen.getByRole('button', { name: 'Theo hệ thống' }));
    expect(root).toHaveAttribute('data-theme', 'dark');
    await userEvent.click(screen.getByRole('button', { name: 'Sáng' }));
    unmount();
    expect(root).toHaveAttribute('data-theme', 'dark');
  });

  it('opens and closes the dialog and the drawer', async () => {
    renderWithProviders(withToast(<UiKit />));
    await userEvent.click(screen.getByRole('button', { name: 'Mở hộp thoại' }));
    expect(screen.getByRole('dialog', { name: 'Hộp thoại mẫu' })).toBeInTheDocument();
    await userEvent.keyboard('{Escape}');
    await userEvent.click(screen.getByRole('button', { name: 'Mở ngăn kéo' }));
    expect(await screen.findByRole('dialog', { name: 'Ngăn kéo mẫu' })).toBeInTheDocument();
  });

  it('shows disabled buttons with their reason', () => {
    renderWithProviders(withToast(<UiKit />));
    const disabled = screen.getAllByRole('button', { name: /Tắt/ });
    expect(disabled.length).toBeGreaterThan(0);
    expect(within(disabled[0]).getByText(/Thiếu ảnh cảnh 3/)).toBeInTheDocument();
  });
});

describe('/dev/ui route', () => {
  it('exists in dev (import.meta.env.DEV is true under Vitest)', async () => {
    stubFetch({
      'GET /api/health': { ok: true, ffmpeg: true, whisper: true, gpu: false, missing: [] },
    });
    renderWithProviders(withToast(<App />), '/dev/ui');
    expect(await screen.findByRole('heading', { name: 'Bộ thành phần' })).toBeInTheDocument();
  });

  it('is registered only behind import.meta.env.DEV, with a lazy import', () => {
    // Vite thay biểu thức này bằng `false` khi build nên trang bị loại khỏi dist/.
    // Bằng chứng trên bản build: `grep -ri gallery frontend/dist` rỗng (báo cáo Đợt 2).
    expect(appSource).toMatch(
      /import\.meta\.env\.DEV\s*\?\s*lazy\(\(\)\s*=>\s*import\('\.\.\/pages\/Gallery'\)\)\s*:\s*null/,
    );
    expect(appSource).not.toMatch(/^import .*pages\/Gallery/m);
  });
});
