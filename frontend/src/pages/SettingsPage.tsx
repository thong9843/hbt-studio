import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { api } from '../api/endpoints';
import type { AppSettings, Fps, SensitiveCategory, SensitiveWords } from '../api/types';
import { ErrorNote } from '../components/ErrorNote';
import { SaveIndicator } from '../components/SaveIndicator';
import { useAutosave } from '../hooks/useAutosave';
import { vi } from '../i18n/vi';

const S = vi.settings;
const HEX = /^#[0-9a-fA-F]{6}$/;
const FPS: Fps[] = [30, 50, 60];
const MODELS: AppSettings['whisper_model'][] = ['auto', 'small', 'medium', 'large-v3'];

function GeneralSection({ initial }: { initial: AppSettings }) {
  const queryClient = useQueryClient();
  const [value, setValue] = useState(initial);
  const { status, error, schedule } = useAutosave(async (v: AppSettings) => {
    const saved = await api.saveAppSettings(v);
    queryClient.setQueryData(['app-settings'], saved);
  });

  const change = (patch: Partial<AppSettings>) => {
    const next = { ...value, ...patch };
    setValue(next);
    // Màu chưa đủ #RRGGBB thì chưa gửi lên máy chủ.
    if (HEX.test(next.theme.primary) && HEX.test(next.theme.accent)) schedule(next);
  };

  const slow = value.whisper_model === 'medium' || value.whisper_model === 'large-v3';
  const G = S.general;
  return (
    <section className="space-y-5">
      <div className="flex items-center gap-4">
        <h2 className="text-2xl">{G.title}</h2>
        <SaveIndicator status={status} error={error} />
      </div>
      <div className="grid gap-5 sm:grid-cols-2">
        <div>
          <label className="label" htmlFor="set-fps">
            {G.fps}
          </label>
          <select
            id="set-fps"
            className="input"
            value={value.default_fps}
            onChange={(e) => change({ default_fps: Number(e.target.value) as Fps })}
          >
            {FPS.map((f) => (
              <option key={f} value={f}>
                {f}
              </option>
            ))}
          </select>
        </div>
        <div />
        {(
          [
            ['primary', G.primary],
            ['accent', G.accent],
          ] as const
        ).map(([key, text]) => (
          <div key={key}>
            <label className="label" htmlFor={`set-${key}`}>
              {text}
            </label>
            <div className="flex items-center gap-2">
              <input
                type="color"
                aria-label={text}
                className="h-9 w-12 shrink-0 cursor-pointer rounded-lg border border-border bg-bg p-0.5"
                value={HEX.test(value.theme[key]) ? value.theme[key] : '#000000'}
                onChange={(e) =>
                  change({ theme: { ...value.theme, [key]: e.target.value.toUpperCase() } })
                }
              />
              <input
                id={`set-${key}`}
                className="input font-mono"
                maxLength={7}
                value={value.theme[key]}
                onChange={(e) => change({ theme: { ...value.theme, [key]: e.target.value } })}
              />
            </div>
          </div>
        ))}
        <div>
          <label className="label" htmlFor="set-whisper">
            {G.whisperModel}
          </label>
          <select
            id="set-whisper"
            className="input"
            value={value.whisper_model}
            onChange={(e) =>
              change({ whisper_model: e.target.value as AppSettings['whisper_model'] })
            }
          >
            {MODELS.map((m) => (
              <option key={m} value={m}>
                {m === 'auto' ? G.whisperAuto : m}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="label" htmlFor="set-timeout">
            {G.whisperTimeout}
          </label>
          <input
            id="set-timeout"
            type="number"
            min={30}
            max={7200}
            className="input"
            value={value.whisper_timeout_seconds}
            onChange={(e) =>
              change({
                whisper_timeout_seconds: Math.min(
                  7200,
                  Math.max(30, Number(e.target.value) || 900),
                ),
              })
            }
          />
        </div>
      </div>
      {slow && (
        <p role="note" className="rounded-xl bg-warn-bg px-4 py-2 text-sm font-bold text-warn">
          {G.whisperSlowWarning}
        </p>
      )}
      <p className="text-xs text-muted">{G.whisperNote}</p>
    </section>
  );
}

function WordsSection({ initial }: { initial: SensitiveWords }) {
  const W = S.words;
  const queryClient = useQueryClient();
  // Mỗi nhóm giữ ô văn bản riêng để gõ xuống dòng thoải mái.
  const [categories, setCategories] = useState(
    initial.categories.map((c) => ({ ...c, text: c.words.join('\n') })),
  );
  const save = useMutation({
    mutationFn: () => {
      const body: SensitiveWords = {
        categories: categories.map<SensitiveCategory>(({ text, ...c }) => ({
          ...c,
          words: text
            .split('\n')
            .map((w) => w.trim())
            .filter(Boolean),
        })),
      };
      return api.saveSensitiveWords(body);
    },
    onSuccess: (saved) => queryClient.setQueryData(['sensitive-words'], saved),
  });
  const patch = (i: number, p: Partial<(typeof categories)[number]>) =>
    setCategories((cs) => cs.map((c, k) => (k === i ? { ...c, ...p } : c)));

  return (
    <section className="space-y-5">
      <h2 className="text-2xl">{W.title}</h2>
      <p className="text-sm text-muted">{W.help}</p>
      <ul className="space-y-4">
        {categories.map((c, i) => (
          <li key={i} className="card space-y-3 p-4">
            <div className="grid gap-3 sm:grid-cols-[1fr_180px_auto]">
              <div>
                <label className="label" htmlFor={`sw-id-${i}`}>
                  {W.id}
                </label>
                <input
                  id={`sw-id-${i}`}
                  className="input font-mono"
                  value={c.id}
                  onChange={(e) => patch(i, { id: e.target.value })}
                />
              </div>
              <div>
                <label className="label" htmlFor={`sw-level-${i}`}>
                  {W.level}
                </label>
                <select
                  id={`sw-level-${i}`}
                  className="input"
                  value={c.level}
                  onChange={(e) =>
                    patch(i, { level: e.target.value as SensitiveCategory['level'] })
                  }
                >
                  {(['info', 'warn', 'block'] as const).map((l) => (
                    <option key={l} value={l}>
                      {W.levels[l]}
                    </option>
                  ))}
                </select>
              </div>
              <button
                type="button"
                className="btn btn-ghost btn-sm self-end"
                onClick={() => setCategories((cs) => cs.filter((_, k) => k !== i))}
              >
                {W.removeCategory}
              </button>
            </div>
            <div>
              <label className="label" htmlFor={`sw-words-${i}`}>
                {W.list}
              </label>
              <textarea
                id={`sw-words-${i}`}
                rows={4}
                className="input"
                value={c.text}
                onChange={(e) => patch(i, { text: e.target.value })}
              />
            </div>
            <div>
              <label className="label" htmlFor={`sw-hint-${i}`}>
                {W.hint}
              </label>
              <input
                id={`sw-hint-${i}`}
                className="input"
                value={c.hint}
                onChange={(e) => patch(i, { hint: e.target.value })}
              />
            </div>
          </li>
        ))}
      </ul>
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          className="btn btn-secondary"
          onClick={() =>
            setCategories((cs) => [
              ...cs,
              { id: `nhom_${cs.length + 1}`, level: 'warn', words: [], hint: '', text: '' },
            ])
          }
        >
          + {W.addCategory}
        </button>
        <button
          type="button"
          className="btn btn-primary"
          disabled={save.isPending}
          onClick={() => save.mutate()}
        >
          {W.save}
        </button>
        {save.isSuccess && (
          <span role="status" className="chip chip-ok">
            {W.saved}
          </span>
        )}
      </div>
      <ErrorNote error={save.error} />
    </section>
  );
}

export function SettingsPage() {
  const app = useQuery({
    queryKey: ['app-settings'],
    queryFn: api.getAppSettings,
    staleTime: Infinity,
  });
  const words = useQuery({
    queryKey: ['sensitive-words'],
    queryFn: api.getSensitiveWords,
    staleTime: Infinity,
  });
  // Form tự giữ trạng thái sau khi nạp; không dựng lại khi dữ liệu cache đổi.
  const [ready, setReady] = useState(false);
  useEffect(() => {
    if (app.data && words.data) setReady(true);
  }, [app.data, words.data]);

  return (
    <main className="mx-auto max-w-3xl space-y-12 px-6 py-10">
      <h1 className="text-5xl leading-none">{S.title}</h1>
      <ErrorNote error={app.error ?? words.error} />
      {!ready && !app.error && !words.error && <p className="text-muted">{vi.common.loading}</p>}
      {ready && app.data && words.data && (
        <>
          <GeneralSection initial={app.data} />
          <WordsSection initial={words.data} />
        </>
      )}
    </main>
  );
}
