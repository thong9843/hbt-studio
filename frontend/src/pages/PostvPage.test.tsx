import { screen, within } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ToastProvider } from '../components/Toast';
import { NewProjectProvider } from '../components/NewProjectDialog';
import { stubFetch } from '../test/fakes';
import { project } from '../test/project';
import { renderWithProviders } from '../test/render';
import { ComposePage } from './ComposePage';
import { HomePage } from './HomePage';
import { PostvPage } from './PostvPage';

afterEach(() => vi.unstubAllGlobals());

const postv = (over: Record<string, unknown> = {}) => ({
  version: 1,
  kind: 'postv',
  slug: 'bai-dem-khuya',
  title: 'Bài đêm khuya',
  series: '',
  segments: [],
  comments: [],
  ...over,
});

function page(path: string) {
  return renderWithProviders(
    <ToastProvider>
      <NewProjectProvider>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/projects" element={<p>trang dự án</p>} />
          <Route path="/postv/:slug" element={<PostvPage />} />
          <Route path="/p/:slug" element={<ComposePage />}>
            <Route index element={<p>trình soạn cảnh</p>} />
          </Route>
        </Routes>
      </NewProjectProvider>
    </ToastProvider>,
    path,
  );
}

describe('PostvPage', () => {
  it('shows the title, the PostV badge and the five steps as "sắp có"', async () => {
    stubFetch({ 'GET /api/projects/bai-dem-khuya': postv() });
    page('/postv/bai-dem-khuya');
    expect(await screen.findByRole('heading', { level: 1, name: 'Bài đêm khuya' })).toBeVisible();
    expect(screen.getAllByText('PostV').length).toBeGreaterThan(0);
    const steps = within(screen.getByRole('region', { name: 'Các bước' })).getAllByRole('listitem');
    expect(steps.map((li) => li.textContent)).toEqual([
      '1Nhập nguồnSắp có',
      '2Chọn đoạnSắp có',
      '3Kịch bản và giọngSắp có',
      '4Xem trước và dựngSắp có',
      '5XuấtSắp có',
    ]);
    expect(screen.getByRole('link', { name: /Tất cả dự án/ })).toHaveAttribute('href', '/projects');
  });

  it('sends a video project to the scene editor instead of crashing', async () => {
    stubFetch({ 'GET /api/projects/muoi': project({ slug: 'muoi', title: 'Muỗi' }) });
    page('/postv/muoi');
    expect(await screen.findByText('trình soạn cảnh')).toBeVisible();
  });

  it('shows the error and a way back when the project cannot be read', async () => {
    stubFetch({
      'GET /api/projects/khong-co': () =>
        new Response('{"detail":"Không có project"}', {
          status: 404,
          headers: { 'Content-Type': 'application/json' },
        }),
    });
    page('/postv/khong-co');
    expect(await screen.findByRole('alert')).toBeVisible();
    expect(screen.getByRole('link', { name: /Tất cả dự án/ })).toBeVisible();
  });
});

describe('opening a PostV project from other screens', () => {
  it('/p/:slug redirects a PostV project to its own screen', async () => {
    stubFetch({ 'GET /api/projects/bai-dem-khuya': postv() });
    page('/p/bai-dem-khuya');
    expect(await screen.findByRole('heading', { level: 1, name: 'Bài đêm khuya' })).toBeVisible();
    expect(screen.queryByText('trình soạn cảnh')).toBeNull();
  });

  it('Home "Tiếp tục làm" links to /postv and does not read it as a video project', async () => {
    const getOne = vi.fn(() => new Response(JSON.stringify(postv()), { status: 200 }));
    stubFetch({
      'GET /api/projects': [
        {
          slug: 'bai-dem-khuya',
          title: 'Bài đêm khuya',
          kind: 'postv',
          updated_at: '2026-10-29T10:00:00',
          thumb: null,
          cover: null,
          last_render: null,
          last_final: null,
          error: null,
        },
      ],
      'GET /api/projects/bai-dem-khuya': getOne,
    });
    page('/');
    const region = await screen.findByRole('region', { name: 'Tiếp tục làm' });
    expect(within(region).getByRole('link', { name: 'Mở dự án' })).toHaveAttribute(
      'href',
      '/postv/bai-dem-khuya',
    );
    expect(getOne).not.toHaveBeenCalled();
  });
});
