import { fireEvent, screen, within } from '@testing-library/react';
import type { ReactNode } from 'react';
import { Route, Routes } from 'react-router-dom';
import type { ScriptCheck } from '../../api/types';
import { ComposePage } from '../../pages/ComposePage';
import { stubFetch } from '../../test/fakes';
import { project } from '../../test/project';
import { renderWithProviders } from '../../test/render';

/** Dùng chung cho test hộp Dán JSON và Bản sao lưu: ComposePage thật + một phần tử con. */
export const checkResult = (over: Partial<ScriptCheck> = {}): ScriptCheck => ({
  ok: true,
  base_hash: 'h1',
  counts: { json: 3, project: 3, after: 3 },
  errors: [],
  warnings: [],
  diff: [],
  realign_scenes: [],
  ...over,
});

export function setup(child: ReactNode, routes: Record<string, unknown> = {}) {
  const mock = stubFetch({
    'GET /api/projects/muoi': project(),
    'PUT /api/projects/muoi': (_u: string, init?: RequestInit) =>
      new Response(String(init?.body), { headers: { 'Content-Type': 'application/json' } }),
    ...routes,
  });
  renderWithProviders(
    <Routes>
      <Route path="/p/:slug" element={<ComposePage />}>
        <Route index element={child} />
      </Route>
    </Routes>,
    '/p/muoi',
  );
  return mock;
}

export async function paste(text: string) {
  const dialog = await screen.findByRole('dialog', { name: 'Dán JSON kịch bản' });
  fireEvent.change(within(dialog).getByLabelText('JSON kịch bản'), { target: { value: text } });
  return dialog;
}

export const bodiesTo = (mock: ReturnType<typeof stubFetch>, suffix: string) =>
  mock.mock.calls
    .filter((c) => String(c[0]).endsWith(suffix))
    .map((c) => JSON.parse(String((c[1] as RequestInit).body)));
