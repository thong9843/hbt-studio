import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { api } from '../../api/endpoints';
import type { HbtVoiceJobOutput, Job } from '../../api/types';
import { useProjectEditor } from '../../hooks/projectEditor';
import { useJob } from '../../hooks/useJob';
import { vi } from '../../i18n/vi';
import { ErrorNote } from '../ErrorNote';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { Card } from '../ui/Card';
import { Progress } from '../ui/Progress';
import { Select } from '../ui/Select';

const T = vi.gd2.voice;

const seconds = (n: number) => (Math.round(n * 10) / 10).toString().replace('.', ',');

/**
 * Thẻ Giọng VieNeu (GĐ2, G3) ở tab Âm thanh của dự án HBT: chọn giọng (nhớ lần trước), tạo giọng như
 * một job có tiến độ theo cảnh và nút Huỷ. Chưa cài VieNeu thì vẫn hiện ghi chú; thả file Vbee ở
 * thẻ Giọng đọc bên dưới dùng như cũ.
 */
export function VieNeuCard() {
  const editor = useProjectEditor();
  const queryClient = useQueryClient();
  const slug = editor.project.slug;
  const [version, setVersion] = useState(0);
  const [jobId, setJobId] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<Job | null>(null);
  const [picked, setPicked] = useState<string | null>(null);

  const info = useQuery({
    queryKey: ['hbt-voice', slug, editor.savedCount, version],
    queryFn: () => api.getHbtVoice(slug),
    refetchOnWindowFocus: false,
    placeholderData: (previous) => previous,
  });
  const data = info.data;
  const available = data?.available ?? false;
  const voices = useQuery({
    queryKey: ['voices'],
    queryFn: api.listVoices,
    enabled: available,
    refetchOnWindowFocus: false,
    retry: false,
  });

  // Giọng đã nhớ làm mặc định cho ô chọn (chỉ lần đầu có dữ liệu).
  const remembered = data?.voice_id ?? null;
  useEffect(() => {
    if (picked === null && remembered) setPicked(remembered);
  }, [picked, remembered]);

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
      // Máy chủ đã đặt `voice` của dự án: nạp lại để các thẻ khác thấy file mới.
      void api.getProject(slug).then((server) => {
        editor.applyServer((p) => ({ ...p, voice: server.voice }));
        setVersion((v) => v + 1);
        void queryClient.invalidateQueries({ queryKey: ['renders', slug] });
      });
    }
  });

  const remember = useMutation({ mutationFn: (id: string | null) => api.setVoicePreference(id) });
  const choose = (id: string) => {
    setPicked(id || null);
    remember.mutate(id || null);
  };

  const start = useMutation({
    mutationFn: async () => {
      await editor.flush();
      return api.synthesizeHbtVoice(slug, picked ?? undefined);
    },
    onSuccess: (res) => {
      setOutcome(null);
      setJobId(res.job_id);
    },
  });

  const done = outcome?.output as unknown as HbtVoiceJobOutput | undefined;
  const hasText = (data?.scenes ?? 0) > 0;
  const needVoice = picked === null;
  const fileUrl = data?.url && data.from_vieneu ? `${data.url}?v=${version}` : null;
  const blocked = !hasText ? T.needText : needVoice ? T.pickFirst : undefined;

  return (
    <Card as="section" aria-label={T.title} className="space-y-4">
      <h2 className="text-h2 font-bold">{T.title}</h2>

      {data && !available && (
        <div role="status" className="ui-inner space-y-1 p-3">
          <p className="text-small font-bold">{T.unavailableTitle}</p>
          {data.note && <p className="text-small text-muted">{data.note}</p>}
          <p className="text-small text-muted">{T.unavailableLead}</p>
        </div>
      )}

      {available && (
        <>
          <p className="text-small text-muted">{T.lead}</p>
          {voices.isPending && <p className="text-small text-muted">{T.loadingVoices}</p>}
          {voices.isError && (
            <p role="alert" className="ui-field-error">
              {T.voicesFailed}
            </p>
          )}
          {voices.data && (
            <Select
              id="hbt-voice-pick"
              label={T.pick}
              value={picked ?? ''}
              disabled={running}
              onChange={(e) => choose(e.target.value)}
            >
              <option value="">{T.pickPlaceholder}</option>
              {voices.data.voices.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.label}
                </option>
              ))}
            </Select>
          )}

          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-3">
              <Button
                tone="accent"
                busy={start.isPending}
                disabled={Boolean(blocked) || running}
                reason={blocked}
                onClick={() => start.mutate()}
              >
                {data?.has_file ? T.resynthesize : T.synthesize}
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
            {data?.has_file && !running && (
              <p className="text-small font-semibold text-on-tint-yel">{T.replaces}</p>
            )}
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

          {fileUrl && (
            <audio key={fileUrl} controls className="w-full" src={fileUrl} aria-label={T.listen} />
          )}
          {data?.from_vieneu && data.stale !== null && (
            <Badge tone={data.stale ? 'yel' : 'ok'}>{data.stale ? T.stale : T.fresh}</Badge>
          )}
          {data?.from_vieneu && data.seconds !== null && (
            <p className="num text-small text-muted">{T.length(seconds(data.seconds))}</p>
          )}
        </>
      )}
    </Card>
  );
}
