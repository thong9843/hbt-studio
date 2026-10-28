import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import { api } from '../../api/endpoints';
import { useProjectEditor } from '../../hooks/projectEditor';
import { vi } from '../../i18n/vi';
import { ErrorNote } from '../ErrorNote';
import { creditOf, libraryMoods } from '../../utils/audio';
import { UploadIcon } from '../icons';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { Card } from '../ui/Card';
import { Chip } from '../ui/Chip';
import { Input } from '../ui/Field';
import { Skeleton } from '../ui/Skeleton';
import { ClipButton } from './clip';
import { UploadTrackDialog } from './UploadTrackDialog';

const T = vi.audio.music;

/** Thẻ Nhạc nền: lọc tâm trạng, danh sách bài, ghi công, Tải nhạc, Không nhạc. */
export function MusicCard() {
  const editor = useProjectEditor();
  const { project } = editor;
  const music = project.music;
  const queryClient = useQueryClient();
  const library = useQuery({ queryKey: ['music'], queryFn: api.listMusic });
  const [mood, setMood] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);

  const attach = useMutation({
    mutationFn: async (id: string) => {
      await editor.flush();
      return api.attachLibraryMusic(project.slug, id);
    },
    onSuccess: (res) => editor.applyServer((p) => ({ ...p, music: res.music })),
  });

  const entries = useMemo(() => library.data ?? [], [library.data]);
  const moods = useMemo(() => libraryMoods(entries), [entries]);
  const shown = mood ? entries.filter((e) => e.moods.includes(mood)) : entries;
  const currentCredit = music?.file ? music.credit : null;

  return (
    <Card as="section" aria-label={T.title} className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-h2 font-bold">{T.title}</h2>
        <div className="flex items-center gap-2">
          <Button
            tone="soft"
            size="sm"
            icon={<UploadIcon size={18} />}
            onClick={() => setUploading(true)}
          >
            {T.upload}
          </Button>
          <Chip
            selected={!music?.file}
            onClick={() => editor.update((p) => ({ ...p, music: null }))}
          >
            {T.noMusic}
          </Chip>
        </div>
      </div>

      {moods.length > 0 && (
        <div role="group" aria-label={T.moods} className="flex flex-wrap gap-2">
          <Chip small selected={mood === null} onClick={() => setMood(null)}>
            {T.all}
          </Chip>
          {moods.map((m) => (
            <Chip key={m} small selected={mood === m} onClick={() => setMood(m)}>
              {m}
            </Chip>
          ))}
        </div>
      )}

      {library.isPending && <Skeleton height={56} />}
      {library.isSuccess && entries.length === 0 && (
        <p className="text-small text-muted">{T.libraryEmpty}</p>
      )}
      {library.isSuccess && entries.length > 0 && shown.length === 0 && (
        <p className="text-small text-muted">{T.noMatch}</p>
      )}
      <ul className="space-y-2">
        {shown.map((entry) => {
          const active = currentCredit === creditOf(entry);
          return (
            <li
              key={entry.id}
              data-active={active}
              className={`ui-inner flex items-center gap-3 border-2 p-3 ${
                active ? 'border-accent' : 'border-transparent'
              }`}
            >
              <ClipButton
                src={api.libraryMusicUrl(entry.id)}
                label={T.listen(entry.title)}
                stopLabel={T.stop(entry.title)}
              />
              <div className="min-w-0 flex-1">
                <p className="truncate text-body font-bold">{entry.title}</p>
                <p className="truncate text-small text-muted">
                  {entry.artist} · {entry.source}
                </p>
                {entry.moods.length > 0 && (
                  <p className="mt-1 flex flex-wrap gap-1">
                    {entry.moods.map((m) => (
                      <Badge key={m}>{m}</Badge>
                    ))}
                  </p>
                )}
              </div>
              {active ? (
                <Badge tone="ok">{T.using}</Badge>
              ) : (
                <Button
                  tone="soft"
                  size="sm"
                  disabled={attach.isPending}
                  onClick={() => attach.mutate(entry.id)}
                  aria-label={`${T.choose} ${entry.title}`}
                >
                  {T.choose}
                </Button>
              )}
            </li>
          );
        })}
      </ul>
      <ErrorNote error={library.error ?? attach.error} />

      {music?.file ? (
        <Input
          label={T.credit}
          hint={<p className="mt-1 text-small text-muted">{T.creditHelp}</p>}
          value={music.credit}
          onChange={(e) =>
            editor.update((p) =>
              p.music ? { ...p, music: { ...p.music, credit: e.target.value } } : p,
            )
          }
        />
      ) : (
        <p className="text-small text-muted">{T.noMusicNote}</p>
      )}

      <UploadTrackDialog
        open={uploading}
        onClose={() => setUploading(false)}
        onAdded={(entry) => {
          void queryClient.invalidateQueries({ queryKey: ['music'] });
          attach.mutate(entry.id);
        }}
      />
    </Card>
  );
}
