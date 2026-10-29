import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { api } from '../../api/endpoints';
import type { Job, PostvProject, ProjectVoice, VoiceEntry, VoiceJobOutput } from '../../api/types';
import { usePostvEditor } from '../../hooks/postvEditor';
import { useJob } from '../../hooks/useJob';
import { vi } from '../../i18n/vi';
import { AudioDrop } from '../audio/AudioDrop';
import { ErrorNote } from '../ErrorNote';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { Card } from '../ui/Card';
import { Chip } from '../ui/Chip';
import { Input } from '../ui/Field';
import { Progress } from '../ui/Progress';

const T = vi.postv.voice;
const A = vi.audio.voice;

const seconds = (n: number) => (Math.round(n * 10) / 10).toString().replace('.', ',');

function trimValue(raw: string): number | null {
  const n = Number(raw);
  return raw.trim() !== '' && Number.isFinite(n) && n > 0 ? n : null;
}

/** Tên người đọc để hiện: người dẫn, bài gốc, hoặc tên tài khoản của bình luận. */
function speakerName(project: PostvProject, speaker: string): string {
  if (speaker === 'narrator') return T.narrator;
  if (speaker === 'post') return project.post.handle || T.post;
  return project.comments.find((c) => c.id === speaker)?.handle || speaker;
}

/** Hộp chọn giọng cho một người; "Tự động" = mặc định hoặc bốc theo `voice.seed`. */
function SpeakerRow({
  name,
  voiceId,
  manual,
  voices,
  onPick,
}: {
  name: string;
  voiceId: string;
  manual: boolean;
  voices: VoiceEntry[];
  onPick: (id: string | null) => void;
}) {
  const label = voices.find((v) => v.id === voiceId)?.label ?? voiceId;
  return (
    <li className="ui-inner flex flex-wrap items-center gap-3 p-3">
      <span className="min-w-0 flex-1 truncate text-small font-bold">{name}</span>
      <select
        aria-label={T.voiceOf(name)}
        className="ui-input w-auto max-w-full"
        value={manual ? voiceId : ''}
        onChange={(e) => onPick(e.target.value || null)}
      >
        <option value="">{T.autoPick(label)}</option>
        {voices.map((v) => (
          <option key={v.id} value={v.id}>
            {v.label}
          </option>
        ))}
      </select>
    </li>
  );
}

/** Thẻ Giọng (bước 3): chọn VieNeu hoặc nhập file; mỗi người một giọng; sinh giọng như một job. */
export function PostvVoiceCard() {
  const { project, update, flush, savedCount } = usePostvEditor();
  const queryClient = useQueryClient();
  const voice = project.voice;
  const slug = project.slug;
  const [jobId, setJobId] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<Job | null>(null);
  const [version, setVersion] = useState(0);

  const info = useQuery({
    queryKey: ['postv-voice', slug, savedCount, version],
    queryFn: () => api.getProjectVoice(slug),
    refetchOnWindowFocus: false,
    placeholderData: (previous) => previous,
  });
  const available = info.data?.available ?? false;
  const voices = useQuery({
    queryKey: ['voices'],
    queryFn: api.listVoices,
    enabled: available,
    refetchOnWindowFocus: false,
    retry: false,
  });

  // Tải lại trang giữa lúc đang sinh: nối lại job giọng của dự án này (hỏi đúng một lần).
  useEffect(() => {
    let live = true;
    api
      .listActiveJobs()
      .then((rows) => {
        const mine = Array.isArray(rows)
          ? rows.find((r) => r.kind === 'voice' && r.slug === slug)
          : null;
        if (live && mine) setJobId(mine.id);
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [slug]);

  const running = jobId !== null && outcome === null;
  const { progress, cancel } = useJob(jobId, (job) => {
    setOutcome(job);
    setJobId(null);
    if (job.status === 'done') {
      update((p) => ({
        ...p,
        voice: { ...p.voice, engine: 'vieneu', file: 'voice.wav', trim_end: null },
      }));
      setVersion((v) => v + 1);
    }
  });

  const start = useMutation({
    mutationFn: async () => {
      await flush();
      return api.synthesizeVoice(slug);
    },
    onSuccess: (res) => {
      setOutcome(null);
      setJobId(res.job_id);
    },
  });

  const upload = useMutation({
    mutationFn: async (f: File) => {
      await flush();
      return api.uploadAsset(slug, 'voice', f);
    },
    onSuccess: (res) => {
      const server = res.project as unknown as PostvProject;
      update((p) => ({ ...p, voice: server.voice }));
      setVersion((v) => v + 1);
      void queryClient.invalidateQueries({ queryKey: ['postv-voice', slug] });
    },
  });

  const setEngine = (engine: 'vieneu' | 'file') =>
    update((p) => ({ ...p, voice: { ...p.voice, engine } }));
  const pick = (who: string, id: string | null) =>
    update((p) => {
      const cast = { ...p.voice.cast };
      if (id) cast[who] = id;
      else delete cast[who];
      return { ...p, voice: { ...p.voice, cast } };
    });
  const shuffle = () => update((p) => ({ ...p, voice: { ...p.voice, seed: p.voice.seed + 1 } }));

  const done = outcome?.output as unknown as VoiceJobOutput | undefined;
  const hasText = project.segments.some((s) => s.voice.trim() !== '');
  const data: ProjectVoice | undefined = info.data;
  const fileUrl = data?.url ? `${data.url}?v=${version}` : null;
  const player = fileUrl ? (
    <audio key={fileUrl} controls className="w-full" src={fileUrl} aria-label={T.listen} />
  ) : null;

  return (
    <Card as="section" aria-label={T.title} className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="mr-auto text-h2 font-bold">{T.title}</h2>
        <div role="group" aria-label={T.source} className="flex gap-2">
          <Chip small selected={voice.engine === 'vieneu'} onClick={() => setEngine('vieneu')}>
            {T.vieneu}
          </Chip>
          <Chip small selected={voice.engine === 'file'} onClick={() => setEngine('file')}>
            {T.file}
          </Chip>
        </div>
      </div>

      {voice.engine === 'vieneu' ? (
        <>
          {data && !available && (
            <div role="status" className="ui-inner space-y-1 p-3">
              <p className="text-small font-bold">{T.unavailableTitle}</p>
              <p className="text-small text-muted">{data.note}</p>
              <p className="text-small text-muted">{T.unavailableLead}</p>
            </div>
          )}

          {available && (
            <section aria-label={T.who} className="space-y-2">
              <div className="flex items-center justify-between gap-2">
                <h3 className="text-body font-bold">{T.who}</h3>
                <Chip small title={T.shuffleHint} disabled={running} onClick={shuffle}>
                  {T.shuffle}
                </Chip>
              </div>
              {voices.isPending && <p className="text-small text-muted">{T.loadingVoices}</p>}
              {voices.isError && (
                <p role="alert" className="ui-field-error">
                  {T.voicesFailed}
                </p>
              )}
              {voices.data && data && (
                <ul className="space-y-2">
                  {data.speakers.map((s) => (
                    <SpeakerRow
                      key={s.speaker}
                      name={speakerName(project, s.speaker)}
                      voiceId={s.voice_id}
                      manual={s.manual}
                      voices={voices.data.voices}
                      onPick={(id) => pick(s.speaker, id)}
                    />
                  ))}
                </ul>
              )}
            </section>
          )}

          {available && (
            <div className="space-y-2">
              <div className="flex flex-wrap items-center gap-3">
                <Button
                  tone="accent"
                  busy={start.isPending}
                  disabled={!hasText || running}
                  reason={!hasText ? T.needText : undefined}
                  onClick={() => start.mutate()}
                >
                  {data?.url ? T.resynthesize : T.synthesize}
                </Button>
                {running && (
                  <Button tone="soft" size="sm" onClick={() => void cancel()}>
                    {T.cancel}
                  </Button>
                )}
                {data && (
                  <span className="num text-small text-muted">
                    {T.estimate(data.estimated_seconds)}
                  </span>
                )}
              </div>
              {!hasText && <p className="text-small text-muted">{T.needText}</p>}
              <p className="text-small text-muted">{T.slowNote}</p>
              {running && (
                <div className="space-y-1">
                  <Progress value={progress.progress} label={T.progress} />
                  <p className="text-small font-semibold" aria-live="polite">
                    {progress.message || T.starting}
                  </p>
                </div>
              )}
              {outcome?.status === 'failed' && (
                <p role="alert" className="ui-field-error">
                  {T.failed(outcome.error ?? '')}
                </p>
              )}
              {outcome?.status === 'cancelled' && (
                <p role="status" className="text-small text-muted">
                  {T.cancelled}
                </p>
              )}
              {outcome?.status === 'done' && done && (
                <p role="status" className="text-small font-semibold text-ok">
                  {T.done(seconds(done.seconds), done.generated, done.cached)}
                </p>
              )}
              <ErrorNote error={start.error} />
            </div>
          )}

          {player}
          {data?.url && data.stale !== null && (
            <Badge tone={data.stale ? 'yel' : 'ok'}>{data.stale ? T.stale : T.fresh}</Badge>
          )}
          {data?.url && data.seconds !== null && (
            <p className="num text-small text-muted">{T.length(seconds(data.seconds))}</p>
          )}
        </>
      ) : (
        <>
          {player ?? <p className="text-small text-muted">{A.none}</p>}
          <AudioDrop
            label={voice.file ? A.replace : A.drop}
            busy={upload.isPending}
            onFile={(f) => upload.mutate(f)}
          />
          <ErrorNote error={upload.error} />
          {voice.file && (
            <Input
              label={A.trim}
              type="number"
              min={0}
              step={0.1}
              inputMode="decimal"
              hint={<p className="mt-1 text-small text-muted">{A.trimHelp}</p>}
              value={voice.trim_end ?? ''}
              onChange={(e) =>
                update((p) => ({
                  ...p,
                  voice: { ...p.voice, trim_end: trimValue(e.target.value) },
                }))
              }
            />
          )}
        </>
      )}
    </Card>
  );
}
