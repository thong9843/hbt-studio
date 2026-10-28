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

function setup(initial: Project) {
  const mock = stubFetch({
    'GET /api/projects/muoi': initial,
    'PUT /api/projects/muoi': (_u: string, init?: RequestInit) =>
      new Response(String(init?.body), { headers: { 'Content-Type': 'application/json' } }),
    'POST /api/projects/muoi/thumbnail/preview.jpg': jpg,
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

  it('keeps the thumbnail editor: add, lines, scene chip, remove — without download links', async () => {
    const user = userEvent.setup();
    setup(project());
    const drawer = await screen.findByRole('dialog', { name: 'Bìa & đăng' });
    expect(within(drawer).queryByRole('link')).not.toBeInTheDocument();
    expect(within(drawer).queryByText(/Chưa có file ảnh bìa/)).not.toBeInTheDocument();
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
