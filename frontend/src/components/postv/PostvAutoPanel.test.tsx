import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { PostvProject } from '../../api/types';
import { PostvEditorContext, type PostvEditor } from '../../hooks/postvEditor';
import { vi as t } from '../../i18n/vi';
import { FakeEventSource, json, stubFetch } from '../../test/fakes';
import { renderWithProviders } from '../../test/render';
import { PostvAutoPanel } from './PostvAutoPanel';

beforeEach(() => {
  FakeEventSource.instances = [];
  vi.stubGlobal('EventSource', FakeEventSource);
});
afterEach(() => vi.unstubAllGlobals());

const baseProject = (): PostvProject =>
  ({
    version: 1,
    kind: 'postv',
    slug: 'bai-auto',
    title: 'Dự án Auto',
    series: '',
    theme: 'dark' as const,
    template: 'story_cards' as const,
    source: { url: '', note: '', pasted_at: null },
    post: {
      handle: 'tac_gia',
      age: '1h',
      text: 'Bài viết test auto',
      card_text: null,
      views: null,
      likes: null,
      replies: null,
      reposts: null,
      shares: null,
    },
    comments: [],
    segments: [],
    hook: { text: '', accent: '' },
    background: { mode: 'auto', clip_ids: [], seed: 1, start_offset: null },
    style: { caption: { preset: 'hbt', highlight_color: null } },
    voice: { engine: 'vieneu', voice_id: null, file: null, trim_end: null, cast: {}, seed: 1 },
    music: null,
    settings: {
      fps: 60,
      captions: true,
      aligner: 'auto',
      outro: true,
      card_animation: 'smooth',
      censor: { enabled: true, sfx: 'bleep', blur_card: true, text: 'blur' },
    },
    publish: { hook: '', hashtags: [] },
    thumbnail: null,
    auto: { style: 'ke-chuyen', comment_count: 2 },
  }) as unknown as PostvProject;

describe('PostvAutoPanel', () => {
  it('calls applyServer when auto job completes', async () => {
    const user = userEvent.setup();
    const project = baseProject();
    const updatedProject = {
      ...project,
      hook: { text: 'Hook mới từ auto', accent: '' },
      segments: [{ role: 'hook', card: 'hook', voice: 'Hook mới', ref: null }],
    };

    stubFetch({
      'GET /api/postv/styles': [
        { id: 'ke-chuyen', label: 'Kể chuyện', description: 'Phong cách kể chuyện' },
      ],
      'POST /api/projects/bai-auto/postv/auto': () => json({ job_id: 'j-auto-1' }, 202),
      'GET /api/jobs/j-auto-1': {
        id: 'j-auto-1',
        project: 'bai-auto',
        status: 'done',
        progress: 100,
        step: 'Xong',
        output: { project: updatedProject },
      },
      'GET /api/projects/bai-auto/renders': [],
    });

    const applyServer = vi.fn();
    const flush = vi.fn().mockResolvedValue(undefined);
    const editor: PostvEditor = {
      project,
      update: vi.fn(),
      applyServer,
      flush,
      status: 'idle',
      saveError: null,
      savedCount: 0,
    };

    renderWithProviders(
      <PostvEditorContext.Provider value={editor}>
        <PostvAutoPanel project={project} />
      </PostvEditorContext.Provider>,
    );

    const submitBtn = await screen.findByRole('button', { name: t.postv.auto.submit });
    await user.click(submitBtn);

    await waitFor(() => expect(flush).toHaveBeenCalled());
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));

    FakeEventSource.instances[0].emit('end', { status: 'done' });

    await waitFor(() => expect(applyServer).toHaveBeenCalled());
    expect(screen.getByText('Đã tạo tự động hoàn tất!')).toBeVisible();
    expect(screen.getByRole('button', { name: t.postv.auto.goToPreview })).toBeVisible();
  });
});
