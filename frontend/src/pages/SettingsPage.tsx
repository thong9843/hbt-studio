import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useContext, useEffect, useState } from 'react';
import { UNSAFE_DataRouterContext } from 'react-router-dom';
import { fetchHealth } from '../api/client';
import { api } from '../api/endpoints';
import type { AppSettings, SensitiveWords } from '../api/types';
import { ErrorNote } from '../components/ErrorNote';
import { LeaveGuard } from '../components/settings/LeaveGuard';
import {
  AdvancedModeCard,
  CloudflareAiCard,
  FpsCard,
  HEX,
  OnlineApiKeysCard,
  StudioEnginesCard,
  ThemeCard,
  WhisperCard,
} from '../components/settings/GeneralCards';
import { WordsCard, type WordGroup } from '../components/settings/WordsCard';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Skeleton } from '../components/ui/Skeleton';
import { vi } from '../i18n/vi';

const S = vi.settings;

function toGroups(words: SensitiveWords): WordGroup[] {
  return words.categories.map((c, i) => ({ ...c, key: `c${i}` }));
}

function toWords(groups: WordGroup[]): SensitiveWords {
  return {
    categories: groups.map((g) => ({
      id: g.id,
      level: g.level,
      words: g.words.map((w) => w.trim()).filter(Boolean),
      hint: g.hint,
    })),
  };
}

/** So sâu hai giá trị JSON (đối tượng, mảng, số, chuỗi); đủ cho cài đặt. */
function isDeepEqual(a: unknown, b: unknown): boolean {
  if (Object.is(a, b)) return true;
  if (typeof a !== 'object' || typeof b !== 'object' || a === null || b === null) return false;
  if (Array.isArray(a) !== Array.isArray(b)) return false;
  const ka = Object.keys(a);
  const kb = Object.keys(b);
  if (ka.length !== kb.length) return false;
  return ka.every(
    (k) =>
      Object.prototype.hasOwnProperty.call(b, k) &&
      isDeepEqual((a as Record<string, unknown>)[k], (b as Record<string, unknown>)[k]),
  );
}

function SettingsForm({ app, words }: { app: AppSettings; words: SensitiveWords }) {
  const queryClient = useQueryClient();
  const [value, setValue] = useState(app);
  const [groups, setGroups] = useState(() => toGroups(words));
  // Giá trị đã lưu (nạp từ máy chủ, đổi sau mỗi lần Lưu thành công). "Chưa lưu" = đang soạn khác
  // giá trị này (so sâu), nên sửa rồi trả về giá trị cũ thì không còn chưa lưu.
  const [saved, setSaved] = useState(() => ({ app, words: toWords(toGroups(words)) }));
  const dirty = !isDeepEqual(value, saved.app) || !isDeepEqual(toWords(groups), saved.words);
  // `useBlocker` chỉ chạy trong data router (main.tsx); test dùng MemoryRouter thì bỏ qua.
  const hasDataRouter = useContext(UNSAFE_DataRouterContext) !== null;
  const health = useQuery({ queryKey: ['health'], queryFn: () => fetchHealth() });

  const validColors = HEX.test(value.theme.primary) && HEX.test(value.theme.accent);
  const save = useMutation({
    mutationFn: async () => {
      const [savedApp, savedWords] = await Promise.all([
        api.saveAppSettings(value),
        api.saveSensitiveWords(toWords(groups)),
      ]);
      return { savedApp, savedWords };
    },
    onSuccess: ({ savedApp, savedWords }) => {
      queryClient.setQueryData(['app-settings'], savedApp);
      queryClient.setQueryData(['sensitive-words'], savedWords);
      setSaved({ app: savedApp, words: toWords(toGroups(savedWords)) });
    },
  });

  const change = (patch: Partial<AppSettings>) => {
    setValue((v) => ({ ...v, ...patch }));
    save.reset();
  };

  return (
    <form
      className="space-y-[18px]"
      onSubmit={(e) => {
        e.preventDefault();
        if (validColors) save.mutate();
      }}
    >
      <div className="grid gap-[18px] min-[900px]:grid-cols-2">
        <FpsCard value={value} onChange={change} />
        <ThemeCard value={value} onChange={change} />
      </div>
      <StudioEnginesCard health={health.data} />
      <CloudflareAiCard value={value} onChange={change} />
      <OnlineApiKeysCard value={value} onChange={change} />
      <AdvancedModeCard value={value} onChange={change} />
      <WhisperCard value={value} onChange={change} health={health.data} />
      <WordsCard
        groups={groups}
        onChange={(next) => {
          setGroups(next);
          save.reset();
        }}
      />
      <div className="flex flex-wrap items-center gap-3">
        <Button
          type="submit"
          tone="ink"
          size="lg"
          busy={save.isPending}
          disabled={!validColors}
          reason={validColors ? undefined : S.invalidColor}
        >
          {S.save}
        </Button>
        <span role="status" aria-live="polite">
          {save.isSuccess && <Badge tone="ok">{S.saved}</Badge>}
          {dirty && !save.isSuccess && !save.isPending && <Badge tone="yel">{S.dirty}</Badge>}
        </span>
      </div>
      <ErrorNote error={save.error} />
      {hasDataRouter && <LeaveGuard dirty={dirty} />}
    </form>
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
    <main className="mx-auto max-w-[940px] space-y-6 px-6 py-8">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-line pb-4">
        <div>
          <h1 className="text-h1 font-bold tracking-tight text-text uppercase">{S.title}</h1>
          <p className="mt-1 text-small text-muted">
            Quản lý tốc độ khung hình, khóa API trực tuyến, mô hình Whisper và bộ lọc từ nhạy cảm.
          </p>
        </div>
      </header>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[190px_1fr]">
        <aside aria-label="Danh mục cài đặt" className="space-y-1">
          <div className="rounded-card border border-line bg-card p-2 text-tiny font-bold text-text-2">
            <p className="px-2.5 py-1.5 text-[11px] font-extrabold uppercase tracking-wider text-muted">
              Danh mục
            </p>
            <p className="rounded-lg bg-[var(--accent-soft)] px-2.5 py-1.5 text-[var(--on-accent-soft)]">
              Khung hình & Giao diện
            </p>
            <p className="px-2.5 py-1.5 text-muted">Động cơ & Phần cứng</p>
            <p className="px-2.5 py-1.5 text-muted">API Keys Online</p>
            <p className="px-2.5 py-1.5 text-muted">Whisper & Từ nhạy cảm</p>
          </div>
        </aside>

        <div className="min-w-0 max-w-[700px] space-y-4">
          <ErrorNote error={app.error ?? words.error} />
          {!ready && !app.error && !words.error && (
            <div role="status" aria-label={vi.common.loading} className="space-y-4">
              <Skeleton height={96} />
              <Skeleton height={160} />
            </div>
          )}
          {ready && app.data && words.data && <SettingsForm app={app.data} words={words.data} />}
        </div>
      </div>
    </main>
  );
}
