import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { DraftDoc, DraftScene } from '../api/types';
import { ToastProvider } from '../components/Toast';
import { stubFetch } from '../test/fakes';
import { project, scene } from '../test/project';
import { renderWithProviders } from '../test/render';
import { ComposePage } from './ComposePage';
import { ImagesTab } from './ImagesTab';

afterEach(() => vi.unstubAllGlobals());

const dscene = (over: Partial<DraftScene> = {}): DraftScene => ({
  image_prompt: 'a mosquito on skin, vertical 9:16',
  image_prompt_ok: true,
  full_prompt: 'a mosquito on skin, vertical 9:16. no text, no letters',
  forbidden: [],
  image_approved: false,
  ...over,
});
const draft = (scenes: DraftScene[], approved = false): DraftDoc => ({
  draft: 1,
  topic: 'Muỗi',
  series_hint: '',
  music_mood: '',
  sources: [],
  scenes,
  images_approved: approved,
});
const full = () =>
  project({ scenes: [1, 2, 3].map((n) => scene({ image: `images/scene-0${n}.png` })) });

function open(doc: DraftDoc, proj = full(), extra: Record<string, unknown> = {}) {
  const mock = stubFetch({
    'GET /api/projects/muoi': proj,
    'GET /api/projects/muoi/draft/exists': { exists: true },
    'GET /api/projects/muoi/draft': doc,
    'PUT /api/projects/muoi': (_u: string, init?: RequestInit) =>
      new Response(String(init?.body), { headers: { 'Content-Type': 'application/json' } }),
    ...extra,
  });
  renderWithProviders(
    <ToastProvider>
      <Routes>
        <Route path="/p/:slug" element={<ComposePage />}>
          <Route path="images" element={<ImagesTab />} />
        </Route>
      </Routes>
    </ToastProvider>,
    '/p/muoi/images',
  );
  return mock;
}

const bodiesTo = (mock: ReturnType<typeof stubFetch>, method: string, suffix: string) =>
  mock.mock.calls
    .filter((c) => String(c[0]).endsWith(suffix) && (c[1] as RequestInit)?.method === method)
    .map((c) => (c[1] as RequestInit).body);

describe('ImagesTab — bước Ảnh', () => {
  it('lists every scene with its prompt, an image status and the counters', async () => {
    open(draft([dscene({ image_approved: true }), dscene(), dscene()]), full());
    expect(await screen.findByText('Cảnh 1')).toBeInTheDocument();
    expect(screen.getByText('Cảnh 3')).toBeInTheDocument();
    expect(screen.getAllByText('a mosquito on skin, vertical 9:16')).toHaveLength(3);
    expect(screen.getByText('Ảnh 3/3 · Đã duyệt 1/3')).toBeInTheDocument();
    expect(screen.getByText('Đã duyệt')).toBeInTheDocument();
    expect(screen.getAllByText('Chưa duyệt')).toHaveLength(2);
  });

  it('copies the FULL prompt (with the negative part) to the clipboard', async () => {
    const user = userEvent.setup();
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
    open(draft([dscene(), dscene(), dscene()]));
    await screen.findByText('Cảnh 1');
    await user.click(screen.getAllByRole('button', { name: /Sao chép prompt/ })[0]);
    expect(writeText).toHaveBeenCalledWith(
      'a mosquito on skin, vertical 9:16. no text, no letters',
    );
    expect(await screen.findByText('Đã sao chép prompt')).toBeInTheDocument();
  });

  it('flags forbidden words but still lets you copy', async () => {
    open(draft([dscene({ forbidden: ['map'] }), dscene(), dscene()]));
    expect(await screen.findByText('Có từ cấm: map')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /Sao chép prompt/ })).toHaveLength(3);
  });

  it('asks for a hand-written prompt on a K18 scene and saves it', async () => {
    const user = userEvent.setup();
    const saved = draft([dscene(), dscene(), dscene({ image_prompt: 'a pond' })]);
    const mock = open(
      draft([dscene(), dscene(), dscene({ image_prompt: '', image_prompt_ok: false })]),
      full(),
      { 'PUT /api/projects/muoi/draft/scenes/2/prompt': saved },
    );
    expect(
      await screen.findByText('Cảnh này chưa có prompt. Tự viết prompt rồi lưu.'),
    ).toBeVisible();
    const box = screen.getByLabelText(/Tự viết prompt · Cảnh 3/);
    const save = screen.getByRole('button', { name: 'Lưu prompt' });
    expect(save).toBeDisabled();
    await user.type(box, 'a pond');
    await user.click(save);
    await waitFor(() =>
      expect(bodiesTo(mock, 'PUT', '/draft/scenes/2/prompt')).toEqual([
        JSON.stringify({ image_prompt: 'a pond' }),
      ]),
    );
    expect(await screen.findByTestId('prompt-2')).toHaveTextContent('a pond');
  });

  it('uploads a picked image into the right scene', async () => {
    const mock = open(draft([dscene(), dscene(), dscene()]), project());
    await screen.findByText('Cảnh 1');
    const file = new File(['x'], 'a.png', { type: 'image/png' });
    fireEvent.change(screen.getByTestId('image-file-2'), { target: { files: [file] } });
    await waitFor(() =>
      expect(
        mock.mock.calls.some(
          (c) => String(c[0]).endsWith('/assets') && (c[1] as RequestInit)?.method === 'POST',
        ),
      ).toBe(true),
    );
    const call = mock.mock.calls.find((c) => String(c[0]).endsWith('/assets'));
    expect(((call?.[1] as RequestInit).body as FormData).get('scene_index')).toBe('2');
  });

  it('keeps Duyệt ảnh off until every scene has an image, and says which is missing', async () => {
    open(draft([dscene(), dscene(), dscene()]), project());
    const btn = await screen.findByRole('button', { name: /^Duyệt ảnh/ });
    expect(btn).toBeDisabled();
    expect(btn).toHaveTextContent('Còn thiếu ảnh cảnh 3');
  });

  it('approves when complete, then offers Bỏ duyệt', async () => {
    const user = userEvent.setup();
    const approved = draft(
      [1, 2, 3].map(() => dscene({ image_approved: true })),
      true,
    );
    const mock = open(draft([dscene(), dscene(), dscene()]), full(), {
      'PUT /api/projects/muoi/draft/images-approved': approved,
    });
    await user.click(await screen.findByRole('button', { name: 'Duyệt ảnh' }));
    expect(await screen.findByRole('button', { name: 'Bỏ duyệt' })).toBeInTheDocument();
    expect(screen.getByText('Ảnh 3/3 · Đã duyệt 3/3')).toBeInTheDocument();
    expect(bodiesTo(mock, 'PUT', '/draft/images-approved')).toEqual([
      JSON.stringify({ approved: true }),
    ]);
  });

  it('shows a scene whose image changed after approval as Chưa duyệt', async () => {
    // Máy chủ đã tính: cảnh 2 đổi ảnh nên không còn khớp dấu, cả bộ chưa duyệt.
    open(
      draft([dscene({ image_approved: true }), dscene(), dscene({ image_approved: true })], false),
    );
    expect(await screen.findByRole('button', { name: 'Duyệt ảnh' })).toBeEnabled();
    const rows = screen.getAllByRole('listitem');
    expect(within(rows[0]).getByText('Đã duyệt')).toBeInTheDocument();
    expect(within(rows[1]).getByText('Chưa duyệt')).toBeInTheDocument();
    expect(within(rows[2]).getByText('Đã duyệt')).toBeInTheDocument();
  });
});
