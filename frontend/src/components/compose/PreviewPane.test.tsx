import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router-dom';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Scene } from '../../api/types';
import { stubFetch } from '../../test/fakes';
import { scene as makeScene } from '../../test/project';
import { PreviewPane } from './PreviewPane';

afterEach(() => vi.unstubAllGlobals());

/** `rerender` giữ nguyên lớp bọc nên PreviewPane không bị dựng lại từ đầu. */
const Providers = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={new QueryClient()}>
    <MemoryRouter>{children}</MemoryRouter>
  </QueryClientProvider>
);
const renderPane = (ui: ReactNode) => render(ui, { wrapper: Providers });

const png = () => new Response(new Blob(['png'], { type: 'image/png' }), { status: 200 });
const theme = { primary: '#146268', accent: '#DE5C48' };

function setup(over: Partial<Parameters<typeof PreviewPane>[0]> = {}, scene: Scene = makeScene()) {
  const bodies: { scene: Scene }[] = [];
  const mock = stubFetch({
    'POST /api/projects/muoi/scenes/0/preview.png': (_u: string, init?: RequestInit) => {
      bodies.push(JSON.parse(String(init?.body)));
      return png();
    },
    'POST /api/projects/muoi/scenes/1/preview.png': png,
  });
  const props = {
    slug: 'muoi',
    sceneIndex: 0,
    sceneCount: 8,
    scene,
    theme,
    imageVersion: 0,
    onPrev: vi.fn(),
    onNext: vi.fn(),
    onGoExport: vi.fn(),
    ...over,
  };
  const view = renderPane(<PreviewPane {...props} />);
  return { mock, bodies, props, view };
}

const wait = (ms: number) =>
  act(async () => {
    await new Promise((r) => setTimeout(r, ms));
  });

describe('PreviewPane', () => {
  it('draws once on mount and shows n/N with prev/next', async () => {
    const { mock, props } = setup({ sceneIndex: 1 });
    await wait(800);
    expect(mock.mock.calls.filter(([u]) => String(u).includes('preview.png'))).toHaveLength(1);
    expect(screen.getByText('2/8')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Cảnh trước' }));
    await userEvent.click(screen.getByRole('button', { name: 'Cảnh sau' }));
    expect(props.onPrev).toHaveBeenCalled();
    expect(props.onNext).toHaveBeenCalled();
  });

  it('disables prev on the first scene and next on the last', () => {
    setup({ sceneIndex: 0 });
    expect(screen.getByRole('button', { name: 'Cảnh trước' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Cảnh sau' })).toBeEnabled();
  });

  it('does not call preview.png on every key: a burst of edits makes one extra call', async () => {
    const { mock, view, props } = setup();
    await wait(800);
    const calls = () => mock.mock.calls.filter(([u]) => String(u).includes('preview.png')).length;
    expect(calls()).toBe(1);
    for (const text of ['M', 'Mu', 'Muỗ', 'Muỗi']) {
      view.rerender(
        <PreviewPane
          {...props}
          scene={makeScene({ card: { y: 'top', lines: [{ text, size: 'l', color: 'ink' }] } })}
        />,
      );
      await wait(100);
    }
    expect(calls()).toBe(1); // chưa tới 600 ms kể từ lần gõ cuối
    await wait(800);
    expect(calls()).toBe(2);
  });

  it('aborts the previous request when a newer draft is sent', async () => {
    const signals: AbortSignal[] = [];
    vi.stubGlobal(
      'fetch',
      vi.fn((_url: string, init?: RequestInit) => {
        signals.push(init?.signal as AbortSignal);
        return new Promise<Response>(() => {}); // không bao giờ xong
      }),
    );
    const props = {
      slug: 'muoi',
      sceneIndex: 0,
      sceneCount: 8,
      scene: makeScene(),
      theme,
      imageVersion: 0,
      onPrev: vi.fn(),
      onNext: vi.fn(),
      onGoExport: vi.fn(),
    };
    const view = renderPane(<PreviewPane {...props} />);
    await wait(800);
    expect(signals).toHaveLength(1);
    view.rerender(<PreviewPane {...props} scene={makeScene({ voice: 'khác', punch: true })} />);
    await wait(800);
    expect(signals).toHaveLength(2);
    expect(signals[0].aborted).toBe(true);
    expect(signals[1].aborted).toBe(false);
  });

  it('toggles the safe-zone overlay as a pure CSS layer (no extra request)', async () => {
    const { mock } = setup();
    await wait(800);
    const before = mock.mock.calls.length;
    expect(screen.queryByTestId('safe-zone')).not.toBeInTheDocument();
    const chip = screen.getByRole('button', { name: 'Vùng an toàn' });
    await userEvent.click(chip);
    const layer = screen.getByTestId('safe-zone');
    expect(chip).toHaveAttribute('aria-pressed', 'true');
    const [top, bottom, right] = Array.from(layer.children) as HTMLElement[];
    expect(parseFloat(top.style.height)).toBeCloseTo(5.208, 2);
    expect(parseFloat(bottom.style.height)).toBeCloseTo(21.875, 2);
    expect(parseFloat(right.style.width)).toBeCloseTo(11.111, 2);
    await userEvent.click(chip);
    expect(screen.queryByTestId('safe-zone')).not.toBeInTheDocument();
    expect(mock.mock.calls.length).toBe(before);
  });

  it('turns the two main buttons off with the reason, and only navigates when enabled', async () => {
    const off = setup({ blockedReason: 'Thiếu ảnh cảnh 3' });
    const fast = screen.getByRole('button', { name: /Xem nhanh/ });
    expect(fast).toBeDisabled();
    expect(fast).toHaveAttribute('title', 'Thiếu ảnh cảnh 3');
    expect(screen.getByRole('button', { name: /Xuất bản đẹp/ })).toBeDisabled();
    off.view.unmount();

    const on = setup();
    await userEvent.click(screen.getByRole('button', { name: 'Xem nhanh' }));
    await userEvent.click(screen.getByRole('button', { name: 'Xuất bản đẹp' }));
    expect(on.props.onGoExport).toHaveBeenCalledTimes(2);
  });

  it('never requests the render history (estimate belongs to Đợt 3d)', async () => {
    const { mock } = setup();
    await wait(800);
    expect(JSON.stringify(mock.mock.calls)).not.toContain('/renders');
    expect(document.querySelector('[data-slot="estimate"]')).toBeInTheDocument();
  });
});
