import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useContext, useEffect, useState } from 'react';
import { UNSAFE_DataRouterContext } from 'react-router-dom';
import { fetchHealth } from '../api/client';
import { api } from '../api/endpoints';
import type { AppSettings, SensitiveWords } from '../api/types';
import { ErrorNote } from '../components/ErrorNote';
import { LeaveGuard } from '../components/settings/LeaveGuard';
import { FpsCard, HEX, ThemeCard, WhisperCard } from '../components/settings/GeneralCards';
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

function SettingsForm({ app, words }: { app: AppSettings; words: SensitiveWords }) {
  const queryClient = useQueryClient();
  const [value, setValue] = useState(app);
  const [groups, setGroups] = useState(() => toGroups(words));
  const [dirty, setDirty] = useState(false);
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
      setDirty(false);
    },
  });

  const change = (patch: Partial<AppSettings>) => {
    setValue((v) => ({ ...v, ...patch }));
    setDirty(true);
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
      <WhisperCard value={value} onChange={change} health={health.data} />
      <WordsCard
        groups={groups}
        onChange={(next) => {
          setGroups(next);
          setDirty(true);
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
    <main className="mx-auto max-w-3xl space-y-6 px-6 py-8">
      <h1 className="text-h1 font-extrabold uppercase">{S.title}</h1>
      <ErrorNote error={app.error ?? words.error} />
      {!ready && !app.error && !words.error && (
        <div role="status" aria-label={vi.common.loading} className="space-y-4">
          <Skeleton height={96} />
          <Skeleton height={160} />
        </div>
      )}
      {ready && app.data && words.data && <SettingsForm app={app.data} words={words.data} />}
    </main>
  );
}
