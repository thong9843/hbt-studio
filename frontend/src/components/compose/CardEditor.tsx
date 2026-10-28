import { useMutation } from '@tanstack/react-query';
import { useCallback, type ReactNode } from 'react';
import { useDropzone } from 'react-dropzone';
import { projectFileUrl } from '../../api/endpoints';
import type { CardLine, LineSize, Scene, Theme } from '../../api/types';
import { vi } from '../../i18n/vi';
import {
  CARD_PRESETS,
  CARD_Y_MAX,
  LINE_SIZES,
  MAX_CARD_LINES,
  cardPositionKey,
  cardYFromSelection,
  clampCardY,
  newCardLine,
} from '../../utils/card';
import { LINE_CHAR_LIMIT } from '../../utils/charCount';
import { sceneNumber } from '../../utils/scene';
import { ErrorNote } from '../ErrorNote';
import { ImageIcon, PlusIcon, TrashIcon } from '../icons';
import { Button } from '../ui/Button';
import { Chip } from '../ui/Chip';
import { Input } from '../ui/Field';
import { IconButton } from '../ui/IconButton';
import { ColorDots } from './ColorDots';

const T = vi.compose.card;
const IMAGE_ACCEPT = { 'image/png': [], 'image/jpeg': [], 'image/webp': [] };

interface Props {
  slug: string;
  sceneIndex: number;
  scene: Scene;
  theme: Theme;
  imageVersion: number;
  onChange: (fn: (scene: Scene) => Scene) => void;
  onUploadImage: (file: File) => Promise<void>;
  /** Nút ở góc phải tiêu đề (vd xoá cảnh). */
  actions?: ReactNode;
}

function SceneImage({
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
  const { getRootProps, getInputProps, open, fileRejections } = useDropzone({
    onDrop,
    accept: IMAGE_ACCEPT,
    multiple: false,
    maxFiles: 1,
    noClick: true,
    noKeyboard: true,
  });
  return (
    <div>
      <div {...getRootProps({ className: 'flex items-center gap-4' })}>
        <input {...getInputProps({ 'aria-label': T.image })} />
        <span className="ui-scene-img !h-24 !w-[54px] shrink-0">
          {scene.image ? (
            <img
              src={`${projectFileUrl(slug, scene.image)}?v=${imageVersion}`}
              alt=""
              className="h-full w-full object-cover"
              decoding="async"
            />
          ) : (
            <ImageIcon size={20} />
          )}
        </span>
        <Button
          tone="soft"
          size="sm"
          busy={upload.isPending}
          icon={<ImageIcon size={18} />}
          onClick={open}
        >
          {upload.isPending ? T.uploading : scene.image ? T.changeImage : T.addImage}
        </Button>
      </div>
      {fileRejections.length > 0 && (
        <p role="alert" className="mt-2 text-small font-bold text-danger">
          {T.imageRejected}
        </p>
      )}
      <ErrorNote error={upload.error} className="mt-2" />
    </div>
  );
}

/** Cột 1: ảnh + thẻ chữ của cảnh đang chọn (vị trí, các dòng, cỡ, màu, bộ đếm ký tự). */
export function CardEditor({
  slug,
  sceneIndex,
  scene,
  theme,
  imageVersion,
  onChange,
  onUploadImage,
  actions,
}: Props) {
  const setCard = (patch: Partial<Scene['card']>) =>
    onChange((s) => ({ ...s, card: { ...s.card, ...patch } }));
  const setLine = (i: number, patch: Partial<CardLine>) =>
    onChange((s) => ({
      ...s,
      card: { ...s.card, lines: s.card.lines.map((l, k) => (k === i ? { ...l, ...patch } : l)) },
    }));

  const position = cardPositionKey(scene.card.y);
  const lines = scene.card.lines;
  const title = T.title(sceneNumber(sceneIndex));
  return (
    <section aria-label={title} className="space-y-5">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-h2 font-bold">{title}</h2>
        {actions}
      </div>
      <SceneImage slug={slug} scene={scene} imageVersion={imageVersion} onUpload={onUploadImage} />

      <div className="space-y-2">
        <p className="ui-label !mb-0" id={`pos-${sceneIndex}`}>
          {T.position}
        </p>
        <div role="group" aria-labelledby={`pos-${sceneIndex}`} className="flex flex-wrap gap-2">
          {[...CARD_PRESETS, 'custom' as const].map((key) => (
            <Chip
              key={key}
              small
              selected={position === key}
              onClick={() => setCard({ y: cardYFromSelection(key, scene.card.y) })}
            >
              {T.positions[key]}
            </Chip>
          ))}
        </div>
        {typeof scene.card.y === 'number' && (
          <Input
            type="number"
            min={0}
            max={CARD_Y_MAX}
            aria-label={T.customPx}
            className="!w-32"
            value={scene.card.y}
            onChange={(e) => setCard({ y: clampCardY(e.target.value) })}
          />
        )}
      </div>

      <ul className="space-y-3">
        {lines.map((line, i) => (
          <li key={i} className="ui-inner space-y-3 p-3">
            <Input
              aria-label={T.lineText(i + 1)}
              placeholder={T.line(i + 1)}
              value={line.text}
              limit={LINE_CHAR_LIMIT[line.size]}
              onChange={(e) => setLine(i, { text: e.target.value })}
            />
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
              <div role="group" aria-label={T.lineSize(i + 1)} className="flex gap-1">
                {LINE_SIZES.map((size) => (
                  <Chip
                    key={size}
                    small
                    selected={line.size === size}
                    aria-label={T.sizeNames[size]}
                    title={T.sizeNames[size]}
                    onClick={() => setLine(i, { size: size as LineSize })}
                  >
                    {T.sizes[size]}
                  </Chip>
                ))}
              </div>
              <ColorDots
                value={line.color}
                theme={theme}
                label={T.lineColor(i + 1)}
                onChange={(color) => setLine(i, { color })}
              />
              <IconButton
                label={T.removeLine(i + 1)}
                small
                className="ml-auto"
                onClick={() => setCard({ lines: lines.filter((_, k) => k !== i) })}
              >
                <TrashIcon size={18} />
              </IconButton>
            </div>
          </li>
        ))}
      </ul>
      <Button
        tone="soft"
        size="sm"
        icon={<PlusIcon size={18} />}
        disabled={lines.length >= MAX_CARD_LINES}
        reason={T.maxLines}
        title={T.addLineTitle}
        onClick={() => setCard({ lines: [...lines, newCardLine()] })}
      >
        {T.addLine}
      </Button>
    </section>
  );
}
