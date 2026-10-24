import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { fetchHealth, fetchText } from '../api/client';
import { api } from '../api/endpoints';
import type { Fps, Job, LintIssue, LintResult, RenderOptions, RenderRecord } from '../api/types';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { ErrorNote } from '../components/ErrorNote';
import { ThumbnailEditor } from '../components/ThumbnailEditor';
import { AlertIcon, CopyIcon, DownloadIcon, PlayIcon, StopIcon } from '../components/icons';
import { ProgressBar } from '../components/ProgressBar';
import { useProjectEditor } from '../hooks/projectEditor';
import { useToast } from '../hooks/toast';
import { useJob } from '../hooks/useJob';
import { vi } from '../i18n/vi';
import { alignerLabel, alignerNotes } from '../utils/aligner';
import { formatBytes, formatDateTime, formatDuration } from '../utils/format';
import { splitPublishBlocks } from '../utils/publish';
import { sceneNumber } from '../utils/scene';

const X = vi.export;
const LEVEL_CHIP = { block: 'chip-danger', warn: 'chip-warn', info: 'chip-muted' } as const;
const FPS: Fps[] = [30, 50, 60];
export const HEAD_PREVIEW_SECONDS = 10;

function issueScope(issue: LintIssue): string {
  return issue.scene_index === null
    ? X.checks.wholeVideo
    : X.checks.scene(sceneNumber(issue.scene_index));
}

function Checks({ lint }: { lint: { data?: LintResult; isPending: boolean; error: unknown } }) {
  const data = lint.data;
  return (
    <section className="space-y-3">
      <h2>{X.checks.title}</h2>
      {lint.isPending && (
        <p className="flex items-center gap-3 text-text-muted">
          <span className="spinner" aria-hidden="true" />
          {X.checks.running}
        </p>
      )}
      <ErrorNote error={lint.error} />
      {data && data.problems.length === 0 && data.issues.length === 0 && (
        <p className="chip chip-ok">{X.checks.ok}</p>
      )}
      {data && data.problems.length > 0 && (
        <ul className="space-y-2">
          {data.problems.map((p) => (
            <li key={p} className="flex items-center gap-2 text-small">
              <span className="chip chip-danger">
                <AlertIcon size={14} />
                {X.checks.missing}
              </span>
              {p}
            </li>
          ))}
        </ul>
      )}
      {data && data.issues.length > 0 && (
        <ul className="space-y-2">
          {data.issues.map((issue, i) => (
            <li key={i} className="flex flex-wrap items-center gap-2 text-small">
              <span className={`chip ${LEVEL_CHIP[issue.level]}`}>
                {issue.level !== 'info' && <AlertIcon size={14} />}
                {X.checks[issue.level]}
              </span>
              <b>{issueScope(issue)}</b>
              <span>{issue.message}</span>
              {issue.hint && <span className="text-text-muted">{issue.hint}</span>}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function CopyButton({ text, label }: { text: string; label: string }) {
  const [state, setState] = useState<'idle' | 'copied' | 'failed'>('idle');
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setState('copied');
      setTimeout(() => setState('idle'), 2000);
    } catch {
      setState('failed');
    }
  };
  return (
    <span className="inline-flex items-center gap-2">
      <button
        type="button"
        className="btn btn-secondary btn-sm"
        aria-label={label}
        onClick={() => void copy()}
      >
        <CopyIcon size={18} />
        {state === 'copied' ? X.publish.copied : X.publish.copy}
      </button>
      {state === 'failed' && (
        <span role="alert" className="text-small text-danger">
          {X.publish.copyFailed}
        </span>
      )}
    </span>
  );
}

function PublishBox({ url }: { url: string }) {
  const text = useQuery({
    queryKey: ['publish', url],
    queryFn: () => fetchText(url),
    retry: false,
  });
  const blocks = splitPublishBlocks(text.data ?? '');
  return (
    <section className="space-y-3">
      <h2>{X.publish.title}</h2>
      <ErrorNote error={text.error} />
      {blocks.length === 0 && text.data !== undefined && (
        <textarea
          readOnly
          rows={8}
          aria-label={X.publish.title}
          className="input font-mono"
          value={text.data}
        />
      )}
      <ul className="space-y-4">
        {blocks.map((b) => (
          <li key={b.name} className="card space-y-3 p-6">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-tiny font-semibold uppercase text-text-muted">{b.name}</h3>
              <CopyButton text={b.body} label={X.publish.copyBlock(b.name)} />
            </div>
            <pre className="whitespace-pre-wrap break-words font-mono text-small">{b.body}</pre>
          </li>
        ))}
      </ul>
      {text.data && blocks.length > 1 && <CopyButton text={text.data} label={X.publish.copyAll} />}
    </section>
  );
}

function ResultView({ job }: { job: Job }) {
  const out = job.output;
  if (!out) return null;
  const R = X.result;
  return (
    <section className="space-y-6">
      <h2>{R.title}</h2>
      <div className="mx-auto w-full max-w-[360px] overflow-hidden rounded-frame bg-surface">
        <video
          controls
          aria-label={X.player}
          className="aspect-[9/16] w-full bg-black"
          src={out.video}
        />
      </div>
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        {[
          [R.duration, formatDuration(out.duration)],
          [R.fps, String(out.fps)],
          [R.lufs, out.lufs === null ? '—' : `${out.lufs.toFixed(1)} LUFS`],
          [R.aligner, alignerLabel(out.aligner, out.aligner_info)],
          [R.seconds, `${out.seconds} ${vi.common.seconds}`],
        ].map(([k, v]) => (
          <div key={k} className="card p-4">
            <dt className="label mb-0">{k}</dt>
            <dd className="num">{v}</dd>
          </div>
        ))}
      </dl>
      {alignerNotes(out.aligner, out.aligner_info).map((note) => (
        <p key={note} className="text-small text-text-muted">
          {note}
        </p>
      ))}
      {out.warnings.length > 0 && (
        <div className="rounded-card bg-accent p-4 text-small text-on-accent">
          <b className="flex items-center gap-2">
            <AlertIcon size={18} />
            {R.warnings}
          </b>
          <ul className="mt-1 list-disc pl-5">
            {out.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </div>
      )}
      <div className="flex flex-wrap gap-3">
        <a className="btn btn-primary" href={out.video} download="video.mp4">
          <DownloadIcon size={20} />
          {R.video}
        </a>
        {out.srt && (
          <a className="btn btn-secondary" href={out.srt} download="captions.srt">
            <DownloadIcon size={20} />
            {R.srt}
          </a>
        )}
        {out.cover && (
          <a className="btn btn-secondary" href={out.cover} download="cover_9x16.jpg">
            <DownloadIcon size={20} />
            {R.cover}
          </a>
        )}
        {out.youtube_cover && (
          <a className="btn btn-secondary" href={out.youtube_cover} download="youtube_3x2.jpg">
            <DownloadIcon size={20} />
            {R.youtubeCover}
          </a>
        )}
      </div>
      <PublishBox url={out.publish} />
    </section>
  );
}

function CleanBuild({ slug, disabled }: { slug: string; disabled: boolean }) {
  const C = X.clean;
  const toast = useToast();
  const [confirming, setConfirming] = useState(false);
  const clean = useMutation({
    mutationFn: () => api.cleanBuild(slug),
    onSuccess: (r) => {
      setConfirming(false);
      toast.info(C.done(formatBytes(r.freed_bytes)));
    },
    onError: (e) => {
      setConfirming(false);
      toast.error(e);
    },
  });
  return (
    <section className="space-y-3">
      <h2>{C.title}</h2>
      <p className="text-small text-text-muted">{C.help}</p>
      <button
        type="button"
        className="btn btn-outline"
        disabled={disabled || clean.isPending}
        onClick={() => setConfirming(true)}
      >
        {C.button}
      </button>
      {confirming && (
        <ConfirmDialog
          title={C.confirmTitle}
          message={C.confirmMessage}
          confirmLabel={clean.isPending ? C.busy : C.confirm}
          busy={clean.isPending}
          onConfirm={() => clean.mutate()}
          onCancel={() => setConfirming(false)}
        />
      )}
    </section>
  );
}

function History({
  renders,
  onPlay,
}: {
  renders: RenderRecord[];
  onPlay: (r: RenderRecord) => void;
}) {
  const H = X.history;
  return (
    <section className="space-y-3">
      <h2>{H.title}</h2>
      <p className="text-small text-text-muted">{H.note}</p>
      {renders.length === 0 && <p className="text-text-muted">{H.empty}</p>}
      <ul className="border-t border-border">
        {renders.map((r) => (
          <li
            key={r.job_id}
            className="flex flex-wrap items-center gap-3 border-b border-border py-3 text-small"
          >
            <span className={`chip ${r.preview ? 'chip-muted' : 'chip-warn'}`}>
              {r.preview ? (r.preview_seconds ? H.fastHead(r.preview_seconds) : H.fast) : H.final}
            </span>
            <span className="num">{formatDateTime(r.created_at)}</span>
            <span className="num text-text-muted">
              {r.duration ? formatDuration(r.duration) : ''}
              {r.fps ? ` · ${r.fps} fps` : ''}
              {` · ${formatBytes(r.size)}`}
              {r.aligner ? ` · ${alignerLabel(r.aligner, r.aligner_info)}` : ''}
            </span>
            <span className="ml-auto flex flex-wrap gap-2">
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => onPlay(r)}>
                <PlayIcon size={18} />
                {H.play}
              </button>
              {r.video && (
                <a className="btn btn-outline btn-sm" href={r.video} download="video.mp4">
                  <DownloadIcon size={18} />
                  {H.video}
                </a>
              )}
              {r.srt && (
                <a className="btn btn-outline btn-sm" href={r.srt} download="captions.srt">
                  <DownloadIcon size={18} />
                  {H.srt}
                </a>
              )}
              {r.cover && (
                <a className="btn btn-outline btn-sm" href={r.cover} download="cover_9x16.jpg">
                  <DownloadIcon size={18} />
                  {H.cover}
                </a>
              )}
              {r.youtube_cover && (
                <a
                  className="btn btn-outline btn-sm"
                  href={r.youtube_cover}
                  download="youtube_3x2.jpg"
                >
                  <DownloadIcon size={18} />
                  {H.youtubeCover}
                </a>
              )}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function ExportTab() {
  const editor = useProjectEditor();
  const toast = useToast();
  const { project } = editor;
  const slug = project.slug;
  const queryClient = useQueryClient();
  const outro = project.settings.outro;
  const [finalFps, setFinalFps] = useState<Fps>(
    (FPS as number[]).includes(project.settings.fps) ? (project.settings.fps as Fps) : 50,
  );
  const [jobId, setJobId] = useState<string | null>(null);
  const [lastOptions, setLastOptions] = useState<RenderOptions>({});
  const [finished, setFinished] = useState<Job | null>(null);
  const [played, setPlayed] = useState<RenderRecord | null>(null);
  const health = useQuery({ queryKey: ['health'], queryFn: () => fetchHealth(), retry: false });
  const renders = useQuery({ queryKey: ['renders', slug], queryFn: () => api.listRenders(slug) });

  const { progress, job, connectionError, cancel } = useJob(jobId, (j) => {
    setFinished(j);
    void queryClient.invalidateQueries({ queryKey: ['renders', slug] });
    if (j.status === 'done') toast.info(X.done);
  });

  const lint = useQuery({
    queryKey: ['lint', slug, editor.savedCount],
    queryFn: () => api.lint(slug),
    retry: false,
  });
  const blocked = !!lint.data && (lint.data.blocked || lint.data.problems.length > 0);
  const noFfmpeg = health.data?.ffmpeg === false;

  const start = useMutation({
    mutationFn: async (options: RenderOptions) => {
      await editor.flush();
      return api.startRender(slug, options);
    },
    onSuccess: (res, options) => {
      setLastOptions(options);
      setFinished(null);
      setPlayed(null);
      setJobId(res.job_id);
    },
    onError: (e, options) => toast.error(e, () => start.mutate(options)),
  });

  const running = jobId !== null && finished === null && !connectionError;
  const cannotStart = running || start.isPending || blocked || noFfmpeg;
  const reason = blocked ? X.blocked : noFfmpeg ? X.missingFfmpeg : undefined;
  const launch = (options: RenderOptions) => start.mutate({ ...options, outro });
  const failure = finished?.status === 'failed' ? finished : null;
  const withCovers = renders.data?.find((r) => r.cover && r.youtube_cover);
  const latestCovers =
    withCovers?.cover && withCovers.youtube_cover
      ? { cover: withCovers.cover, youtube: withCovers.youtube_cover }
      : null;
  const pct = job?.progress ?? progress.progress;

  return (
    <div className="max-w-4xl space-y-12">
      <Checks lint={lint} />

      <section className="space-y-4">
        <h2>{X.title}</h2>
        <label className="flex min-h-[44px] w-fit cursor-pointer items-center gap-3 font-bold">
          <input
            type="checkbox"
            className="h-5 w-5 accent-[var(--accent)]"
            checked={outro}
            onChange={(e) =>
              editor.update((p) => ({
                ...p,
                settings: { ...p.settings, outro: e.target.checked },
              }))
            }
          />
          {X.options.outro}
        </label>
        <div className="flex flex-wrap items-end gap-4">
          <button
            type="button"
            className="btn btn-primary"
            disabled={cannotStart}
            title={reason}
            onClick={() => launch({ preview: true, preview_seconds: HEAD_PREVIEW_SECONDS })}
          >
            {start.isPending ? (
              <span className="spinner" aria-hidden="true" />
            ) : (
              <PlayIcon size={20} />
            )}
            {X.fast}
          </button>
          <button
            type="button"
            className="btn btn-outline"
            disabled={cannotStart}
            title={reason}
            onClick={() => launch({ preview: true })}
          >
            {X.fastFull}
          </button>
          <div className="flex items-end gap-2">
            <div>
              <label className="label" htmlFor="final-fps">
                {X.finalFps}
              </label>
              <select
                id="final-fps"
                className="input w-24"
                value={finalFps}
                onChange={(e) => setFinalFps(Number(e.target.value) as Fps)}
              >
                {FPS.map((f) => (
                  <option key={f} value={f}>
                    {f}
                  </option>
                ))}
              </select>
            </div>
            <button
              type="button"
              className="btn btn-accent"
              disabled={cannotStart}
              title={reason}
              onClick={() => launch({ preview: false, fps: finalFps })}
            >
              {X.finalLabel(finalFps)}
            </button>
          </div>
        </div>
        <p className="text-small text-text-muted">
          {X.fastHelp} · {X.finalHelp}
        </p>
        {reason && (
          <p className="flex items-center gap-2 text-small font-bold text-danger">
            <AlertIcon size={18} />
            {reason}
          </p>
        )}
      </section>

      {jobId && (
        <section className="space-y-4" aria-live="polite">
          <h2>{X.progress}</h2>
          <ProgressBar
            label={X.progress}
            value={pct}
            step={job?.step ?? progress.step}
            message={running ? progress.message : undefined}
          />
          {running && (
            <button type="button" className="btn btn-outline btn-sm" onClick={() => void cancel()}>
              <StopIcon size={18} />
              {X.cancel}
            </button>
          )}
          <ErrorNote error={connectionError} />
          {finished?.status === 'cancelled' && <p className="chip chip-muted">{X.cancelled}</p>}
          {failure && (
            <div className="space-y-3 rounded-card border-[1.5px] border-danger p-4">
              <p role="alert" className="flex items-center gap-2 font-bold text-danger">
                <AlertIcon size={18} />
                {X.failed}: {failure.error}
              </p>
              {failure.needs_confirmation && (
                <>
                  <p className="text-small">{X.confirmTrim}</p>
                  <button
                    type="button"
                    className="btn btn-primary btn-sm"
                    onClick={() => start.mutate({ ...lastOptions, allow_long_trim: true })}
                  >
                    {X.confirmTrimButton}
                  </button>
                </>
              )}
            </div>
          )}
        </section>
      )}

      {finished?.status === 'done' && !played && <ResultView job={finished} />}
      {played && played.video && (
        <section className="space-y-4">
          <div className="mx-auto w-full max-w-[360px] overflow-hidden rounded-frame bg-surface">
            <video
              controls
              aria-label={X.player}
              className="aspect-[9/16] w-full bg-black"
              src={played.video}
            />
          </div>
          {played.publish && <PublishBox url={played.publish} />}
        </section>
      )}

      <ThumbnailEditor covers={latestCovers} />

      <History renders={renders.data ?? []} onPlay={setPlayed} />

      <CleanBuild slug={slug} disabled={running} />
    </div>
  );
}
