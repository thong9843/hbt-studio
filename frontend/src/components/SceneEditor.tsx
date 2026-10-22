import { useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import { useMutation } from '@tanstack/react-query';
import { projectFileUrl } from '../api/endpoints';
import type { CardLine, CardPreset, Label, LineSize, Scene } from '../api/types';
import { vi } from '../i18n/vi';
import { VOICE_CHAR_LIMIT, countVoiceChars } from '../utils/voice';
import { ColorField } from './ColorField';
import { ErrorNote } from './ErrorNote';

const T = vi.compose.editor;
const PRESETS: CardPreset[] = ['top', 'upper', 'middle', 'lower'];
const SIZES: LineSize[] = ['s', 'm', 'l', 'xl'];
const MAX_LINES = 5;
const IMAGE_ACCEPT = { 'image/png': [], 'image/jpeg': [], 'image/webp': [] };

interface Props {
  slug: string;
  sceneIndex: number;
  scene: Scene;
  imageVersion: number;
  totalVoiceChars: number;
  onChange: (fn: (scene: Scene) => Scene) => void;
  onUploadImage: (file: File) => Promise<void>;
}

function ImageDrop({
  slug,
  scene,
  imageVersion,
  onUpload,
}: {
  slug: string;
  scene: Scene;
  imageVersion: number;
  onUpload: (file: File) => Promise<void>;
}) {
  const upload = useMutation({ mutationFn: onUpload });
  const onDrop = useCallback(
    (files: File[]) => {
      if (files[0]) upload.mutate(files[0]);
    },
    [upload],
  );
  const { getRootProps, getInputProps, isDragActive, fileRejections } = useDropzone({
    onDrop,
    accept: IMAGE_ACCEPT,
    maxFiles: 1,
    multiple: false,
  });
  return (
    <div>
      <div
        {...getRootProps()}
        className={`flex cursor-pointer items-center gap-4 rounded-2xl border-2 border-dashed p-3 transition ${
          isDragActive ? 'border-fg bg-surface-2' : 'border-border bg-surface'
        }`}
      >
        <input {...getInputProps({ 'aria-label': T.image })} />
        <span className="h-24 w-14 shrink-0 overflow-hidden rounded-lg bg-surface-2">
          {scene.image && (
            <img
              src={`${projectFileUrl(slug, scene.image)}?v=${imageVersion}`}
              alt=""
              className="h-full w-full object-cover"
            />
          )}
        </span>
        <span className="text-sm font-bold">
          {upload.isPending
            ? T.imageUploading
            : isDragActive
              ? T.imageDropActive
              : scene.image
                ? T.imageReplace
                : T.imageDrop}
        </span>
      </div>
      {fileRejections.length > 0 && (
        <p role="alert" className="mt-2 text-sm font-bold text-danger">
          {T.imageRejected}
        </p>
      )}
      <ErrorNote error={upload.error} className="mt-2" />
    </div>
  );
}

function numberOrNull(raw: string): number | null {
  if (raw.trim() === '') return null;
  const n = Number(raw);
  return Number.isFinite(n) ? n : null;
}

export function SceneEditor({
  slug,
  sceneIndex,
  scene,
  imageVersion,
  totalVoiceChars,
  onChange,
  onUploadImage,
}: Props) {
  const idp = `s${sceneIndex}`;
  const setCard = (patch: Partial<Scene['card']>) =>
    onChange((s) => ({ ...s, card: { ...s.card, ...patch } }));
  const setLine = (i: number, patch: Partial<CardLine>) =>
    onChange((s) => ({
      ...s,
      card: {
        ...s.card,
        lines: s.card.lines.map((l, k) => (k === i ? { ...l, ...patch } : l)),
      },
    }));
  const setLabel = (i: number, patch: Partial<Label>) =>
    onChange((s) => ({ ...s, labels: s.labels.map((l, k) => (k === i ? { ...l, ...patch } : l)) }));

  const preset = typeof scene.card.y === 'number' ? 'custom' : scene.card.y;
  const voiceChars = countVoiceChars(scene.voice);

  return (
    <div className="space-y-8">
      <section>
        <h2 className="label">{T.image}</h2>
        <ImageDrop slug={slug} scene={scene} imageVersion={imageVersion} onUpload={onUploadImage} />
      </section>

      <section className="space-y-3">
        <h2 className="label">{T.card}</h2>
        <div className="flex flex-wrap items-end gap-3">
          <div className="w-48">
            <label className="label" htmlFor={`${idp}-cardy`}>
              {T.cardPosition}
            </label>
            <select
              id={`${idp}-cardy`}
              className="input"
              value={preset}
              onChange={(e) =>
                setCard({ y: e.target.value === 'custom' ? 300 : (e.target.value as CardPreset) })
              }
            >
              {PRESETS.map((p) => (
                <option key={p} value={p}>
                  {T.positions[p]}
                </option>
              ))}
              <option value="custom">{T.positions.custom}</option>
            </select>
          </div>
          {typeof scene.card.y === 'number' && (
            <input
              type="number"
              min={0}
              max={1920}
              aria-label={T.positions.custom}
              className="input w-28"
              value={scene.card.y}
              onChange={(e) =>
                setCard({ y: Math.min(1920, Math.max(0, Math.round(Number(e.target.value) || 0))) })
              }
            />
          )}
        </div>

        <ul className="space-y-2">
          {scene.card.lines.map((line, i) => (
            <li key={i} className="grid grid-cols-[1fr_auto] gap-2 rounded-2xl bg-surface p-3">
              <input
                aria-label={`${T.line(i + 1)}: ${T.lineText}`}
                className="input col-span-2"
                placeholder={T.line(i + 1)}
                value={line.text}
                onChange={(e) => setLine(i, { text: e.target.value })}
              />
              <div className="flex flex-wrap items-center gap-2">
                <select
                  aria-label={`${T.line(i + 1)}: ${T.lineSize}`}
                  className="input w-32"
                  value={line.size}
                  onChange={(e) => setLine(i, { size: e.target.value as LineSize })}
                >
                  {SIZES.map((s) => (
                    <option key={s} value={s}>
                      {T.sizes[s]}
                    </option>
                  ))}
                </select>
                <div className="w-48">
                  <ColorField
                    label={`${T.line(i + 1)}: ${T.lineColor}`}
                    value={line.color}
                    onChange={(color) => setLine(i, { color })}
                  />
                </div>
              </div>
              <button
                type="button"
                className="btn btn-ghost btn-sm justify-self-end"
                onClick={() => setCard({ lines: scene.card.lines.filter((_, k) => k !== i) })}
              >
                {T.removeLine}
              </button>
            </li>
          ))}
        </ul>
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          disabled={scene.card.lines.length >= MAX_LINES}
          onClick={() =>
            setCard({ lines: [...scene.card.lines, { text: '', size: 'm', color: 'ink' }] })
          }
        >
          + {T.addLine}
        </button>
      </section>

      <section className="space-y-3">
        <h2 className="label">{T.labels}</h2>
        <ul className="space-y-2">
          {scene.labels.map((label, i) => (
            <li
              key={i}
              className="grid grid-cols-2 gap-2 rounded-2xl bg-surface p-3 sm:grid-cols-6"
            >
              <input
                aria-label={`${T.labelText} ${i + 1}`}
                className="input col-span-2 sm:col-span-6"
                placeholder={T.labelText}
                value={label.text}
                onChange={(e) => setLabel(i, { text: e.target.value })}
              />
              {(
                [
                  ['x', T.labelX],
                  ['y', T.labelY],
                  ['size', T.labelSize],
                  ['rot', T.labelRot],
                ] as const
              ).map(([field, text]) => (
                <input
                  key={field}
                  type="number"
                  aria-label={`${text} ${i + 1}`}
                  placeholder={text}
                  className="input"
                  value={label[field]}
                  onChange={(e) => setLabel(i, { [field]: Number(e.target.value) || 0 })}
                />
              ))}
              <div className="col-span-2 sm:col-span-1">
                <ColorField
                  label={`${vi.compose.editor.lineColor} ${i + 1}`}
                  value={label.color}
                  onChange={(color) => setLabel(i, { color })}
                />
              </div>
              <button
                type="button"
                className="btn btn-ghost btn-sm col-span-2 justify-self-end sm:col-span-6"
                onClick={() =>
                  onChange((s) => ({ ...s, labels: s.labels.filter((_, k) => k !== i) }))
                }
              >
                {T.removeLabel}
              </button>
            </li>
          ))}
        </ul>
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          onClick={() =>
            onChange((s) => ({
              ...s,
              labels: [...s.labels, { text: '', x: 540, y: 960, size: 80, color: 'ink', rot: 0 }],
            }))
          }
        >
          + {T.addLabel}
        </button>
      </section>

      <section>
        <label className="label" htmlFor={`${idp}-voice`}>
          {T.voice}
        </label>
        <textarea
          id={`${idp}-voice`}
          rows={5}
          className="input"
          value={scene.voice}
          aria-describedby={`${idp}-voice-hint`}
          onChange={(e) => onChange((s) => ({ ...s, voice: e.target.value }))}
        />
        <p
          id={`${idp}-voice-hint`}
          className="mt-1 flex flex-wrap justify-between gap-2 text-xs text-muted"
        >
          <span>{T.voiceHintSyntax}</span>
          <span>
            {T.voiceCount(voiceChars)} ·{' '}
            <span className={totalVoiceChars > VOICE_CHAR_LIMIT ? 'font-bold text-danger' : ''}>
              {T.voiceTotal(totalVoiceChars, VOICE_CHAR_LIMIT)}
            </span>
          </span>
        </p>
      </section>

      <section className="grid gap-4 sm:grid-cols-2">
        <label className="flex items-start gap-3 rounded-2xl bg-surface p-4">
          <input
            type="checkbox"
            className="mt-1 h-5 w-5 accent-[var(--color-accent)]"
            checked={scene.punch}
            onChange={(e) => onChange((s) => ({ ...s, punch: e.target.checked }))}
          />
          <span>
            <span className="block font-extrabold">{T.punch}</span>
            <span className="block text-xs text-muted">{T.punchHelp}</span>
          </span>
        </label>
        <div>
          <label className="label" htmlFor={`${idp}-capy`}>
            {T.captionY}
          </label>
          <input
            id={`${idp}-capy`}
            type="number"
            min={0}
            max={1920}
            className="input"
            value={scene.caption_y ?? ''}
            onChange={(e) => onChange((s) => ({ ...s, caption_y: numberOrNull(e.target.value) }))}
          />
        </div>
      </section>
    </div>
  );
}
