import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Project } from '../../api/types';
import { ComposePage } from '../../pages/ComposePage';
import { stubFetch } from '../../test/fakes';
import { project } from '../../test/project';
import { renderWithProviders } from '../../test/render';
import { useProjectEditor } from '../../hooks/projectEditor';
import { PublishDrawer } from './PublishDrawer';

afterEach(() => vi.unstubAllGlobals());

const jpg = () => new Response(new Blob(['jpg'], { type: 'image/jpeg' }));

function Host() {
  const { project: p } = useProjectEditor();
  return (
    <>
      <PublishDrawer open onClose={() => {}} />
      <output data-testid="json">
        {JSON.stringify({ publish: p.publish, thumbnail: p.thumbnail })}
      </output>
    </>
  );
}

function setup(initial: Project, renders: unknown[] = []) {
  const mock = stubFetch({
    'GET /api/projects/muoi': initial,
    'PUT /api/projects/muoi': (_u: string, init?: RequestInit) =>
      new Response(String(init?.body), { headers: { 'Content-Type': 'application/json' } }),
    'POST /api/projects/muoi/thumbnail/preview.jpg': jpg,
    'GET /api/projects/muoi/renders': renders,
  });
  renderWithProviders(
    <Routes>
      <Route path="/p/:slug" element={<ComposePage />}>
        <Route index element={<Host />} />
      </Route>
    </Routes>,
    '/p/muoi',
  );
  return mock;
}
const state = () => JSON.parse(screen.getByTestId('json').textContent ?? '{}');

describe('PublishDrawer ("Bìa & đăng")', () => {
  it('edits the hook and hashtags (leading # dropped when saved)', async () => {
    const user = userEvent.setup();
    setup(project({ publish: { hook: '', hashtags: ['cu'] } }));
    const drawer = await screen.findByRole('dialog', { name: 'Bìa & đăng' });
    const tags = within(drawer).getByLabelText('Hashtag');
    expect(tags).toHaveValue('#cu');
    await user.clear(tags);
    await user.type(tags, '#muoi #khoahoc');
    await user.type(within(drawer).getByLabelText('Câu mở đầu'), 'Bạn biết chưa?');
    expect(state().publish).toEqual({ hook: 'Bạn biết chưa?', hashtags: ['muoi', 'khoahoc'] });
  });

  it('offers both cover files from the newest render that has them', async () => {
    setup(project({ thumbnail: { scene: 1, lines: ['A', 'B'], series: '', accent: '#FFD43B' } }), [
      { job_id: 'new', created_at: '2026-10-02T10:00:00Z', cover: null, youtube_cover: null },
      {
        job_id: 'old',
        created_at: '2026-10-01T10:00:00Z',
        cover: '/api/files/projects/muoi/renders/old/cover_9x16.jpg',
        youtube_cover: '/api/files/projects/muoi/renders/old/youtube_3x2.jpg',
      },
    ]);
    const drawer = await screen.findByRole('dialog', { name: 'Bìa & đăng' });
    const jpg916 = await within(drawer).findByRole('link', { name: /cover_9x16\.jpg/ });
    expect(jpg916).toHaveAttribute('href', '/api/files/projects/muoi/renders/old/cover_9x16.jpg');
    expect(jpg916).toHaveAttribute('download', 'cover_9x16.jpg');
    expect(within(drawer).getByRole('link', { name: /youtube_3x2\.jpg/ })).toBeInTheDocument();
  });

  it('says there is no cover file yet when no render has one', async () => {
    setup(project({ thumbnail: { scene: 1, lines: ['A', 'B'], series: '', accent: '#FFD43B' } }));
    const drawer = await screen.findByRole('dialog', { name: 'Bìa & đăng' });
    expect(await within(drawer).findByText(/Chưa có file ảnh bìa/)).toBeInTheDocument();
    expect(within(drawer).queryByRole('link')).not.toBeInTheDocument();
  });

  it('keeps the thumbnail editor: add, lines, scene chip, remove', async () => {
    const user = userEvent.setup();
    setup(project());
    const drawer = await screen.findByRole('dialog', { name: 'Bìa & đăng' });
    await user.click(within(drawer).getByRole('button', { name: 'Thêm ảnh bìa' }));
    await user.type(within(drawer).getByLabelText('Dòng 1'), 'MUỖI');
    await user.type(within(drawer).getByLabelText('Dòng 2'), 'THÍCH BẠN');
    await user.click(within(drawer).getByRole('button', { name: 'Cảnh 3' }));
    await waitFor(() =>
      expect(state().thumbnail).toMatchObject({ scene: 3, lines: ['MUỖI', 'THÍCH BẠN'] }),
    );
    await user.click(within(drawer).getByRole('button', { name: 'Bỏ ảnh bìa' }));
    expect(state().thumbnail).toBeNull();
  });
});
