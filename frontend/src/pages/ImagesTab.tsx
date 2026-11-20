import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useRef, useState } from 'react';
import { api, projectFileUrl } from '../api/endpoints';
import type { DraftDoc, DraftScene, Scene } from '../api/types';
import { ErrorNote } from '../components/ErrorNote';
import { AlertIcon, CheckIcon, CopyIcon, ImageIcon } from '../components/icons';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { Textarea } from '../components/ui/Field';
import { Navigate } from 'react-router-dom';
import { useDraft, useDraftState } from '../hooks/useDraft';
import { useProjectEditor } from '../hooks/projectEditor';
import { useToast } from '../hooks/toast';
import { vi } from '../i18n/vi';
import { sceneNumber } from '../utils/scene';

const T = vi.gd2.images;

interface RowProps {
  index: number;
  slug: string;
  scene: Scene;
  draft: DraftScene;
  imageVersion: number;
  busy: boolean;
  onUpload: (index: number, file: File) => Promise<void>;
  onSavePrompt: (index: number, prompt: string) => Promise<void>;
}

function SceneImageRow({
  index,
  slug,
  scene,
  draft,
  imageVersion,
  busy,
  onUpload,
  onSavePrompt,
}: RowProps) {
  const toast = useToast();
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [text, setText] = useState(draft.image_prompt);
  const [saving, setSaving] = useState(false);
  const hasImage = Boolean(scene.image);
  const n = sceneNumber(index);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(draft.full_prompt);
      toast.info(T.copied);
    } catch {
      toast.error(new Error(T.copyFailed));
    }
  };

  const pick = (file: File | undefined) => {
    if (file) void onUpload(index, file);
  };

  const status = !hasImage
    ? { tone: 'neutral' as const, label: T.noImage }
    : draft.image_approved
      ? { tone: 'ok' as const, label: T.approved }
      : { tone: 'yel' as const, label: T.notApproved };

  return (
    <li>
      <Card className="grid grid-cols-[90px_minmax(0,1fr)] gap-4 p-4 min-[1024px]:grid-cols-[90px_minmax(0,1fr)_220px]">
        <div className="relative h-[160px] w-[90px] overflow-hidden rounded-inner bg-soft">
          {hasImage ? (
            <img
              src={`${projectFileUrl(slug, scene.image)}?v=${imageVersion}`}
              alt={T.scene(n)}
              loading="lazy"
              decoding="async"
              className="h-full w-full object-cover"
            />
          ) : (
            <span className="flex h-full items-center justify-center text-muted">
              <ImageIcon size={28} />
            </span>
          )}
        </div>

        <div className="min-w-0 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-h2 font-bold">{T.scene(n)}</h2>
            <Badge tone={status.tone}>{status.label}</Badge>
          </div>
          {scene.voice && <p className="line-clamp-2 text-small text-muted">{scene.voice}</p>}

          {draft.image_prompt_ok ? (
            <div className="space-y-2">
              <p className="ui-label">{T.promptLabel}</p>
              <p
                className="rounded-input bg-soft-2 px-3 py-2 font-mono text-small break-words"
                data-testid={`prompt-${index}`}
              >
                {draft.image_prompt}
              </p>
              {draft.forbidden.length > 0 && (
                <p
                  role="status"
                  className="flex items-center gap-2 text-small font-semibold text-on-tint-yel"
                >
                  <AlertIcon size={16} />
                  {T.forbidden(draft.forbidden)}
                </p>
              )}
              <Button
                tone="soft"
                size="sm"
                icon={<CopyIcon size={16} />}
                onClick={() => void copy()}
              >
                {T.copy}
              </Button>
            </div>
          ) : (
            <div className="space-y-2">
              <p
                role="status"
                className="flex items-center gap-2 text-small font-semibold text-on-tint-yel"
              >
                <AlertIcon size={16} />
                {T.noPrompt}
              </p>
              <Textarea
                label={`${T.writeLabel} · ${T.scene(n)}`}
                value={text}
                rows={3}
                spellCheck={false}
                placeholder={T.writePlaceholder}
                onChange={(e) => setText(e.target.value)}
              />
              <Button
                tone="soft"
                size="sm"
                busy={saving}
                disabled={!text.trim()}
                onClick={() => {
                  setSaving(true);
                  void onSavePrompt(index, text).finally(() => setSaving(false));
                }}
              >
                {T.savePrompt}
              </Button>
            </div>
          )}
        </div>

        <div
          className="ui-drop col-span-2 !flex-col !gap-2 !p-3 min-[1024px]:col-span-1"
          data-active={dragging}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            pick(e.dataTransfer.files[0]);
          }}
        >
          <span className="text-small text-muted">{T.dropHere}</span>
          <Button tone="soft" size="sm" disabled={busy} onClick={() => input.current?.click()}>
            {hasImage ? T.replaceImage : T.pickImage}
          </Button>
          <input
            ref={input}
            type="file"
            accept="image/*"
            hidden
            aria-label={`${T.pickImage} · ${T.scene(n)}`}
            data-testid={`image-file-${index}`}
            onChange={(e) => {
              pick(e.target.files?.[0]);
              e.target.value = '';
            }}
          />
        </div>
      </Card>
    </li>
  );
}

/** Bước Ảnh (GĐ2, G2): prompt từng cảnh, Sao chép, thả ảnh đúng cảnh, "Đã duyệt ảnh". */
export function ImagesTab() {
  const editor = useProjectEditor();
  const { project, imageVersion } = editor;
  const slug = project.slug;
  const toast = useToast();
  const queryClient = useQueryClient();
  const { exists, loaded } = useDraftState(slug);
  const { data: draft, error } = useDraft(slug, exists);
  const [uploading, setUploading] = useState(false);

  const store = (next: DraftDoc) => queryClient.setQueryData(['draft', slug], next);

  const upload = async (index: number, file: File) => {
    setUploading(true);
    try {
      await editor.uploadImage(index, file);
      toast.info(T.uploaded);
      await queryClient.invalidateQueries({ queryKey: ['draft', slug] });
    } catch (e) {
      toast.error(e);
    } finally {
      setUploading(false);
    }
  };

  const savePrompt = async (index: number, prompt: string) => {
    try {
      store(await api.setScenePrompt(slug, index, prompt));
    } catch (e) {
      toast.error(e);
    }
  };

  const approve = useMutation({
    mutationFn: (approved: boolean) => api.setImagesApproved(slug, approved),
    onSuccess: (next) => {
      store(next);
      if (next.images_approved) toast.info(T.approvedAll);
    },
    onError: (e) => toast.error(e),
  });

  // Dự án không có nháp: về trình soạn, không để trang trắng.
  if (loaded && !exists) return <Navigate to={`/p/${slug}`} replace />;
  if (!exists) return null;
  if (error) {
    return (
      <div className="p-6">
        <ErrorNote error={error} />
      </div>
    );
  }
  if (!draft) return null;

  const have = project.scenes.filter((s) => s.image).length;
  const total = project.scenes.length;
  const ok = draft.scenes.filter((s) => s.image_approved).length;
  const firstMissing = project.scenes.findIndex((s) => !s.image);
  const canApprove = firstMissing === -1;
  const approved = draft.images_approved;

  return (
    <div className="mx-auto max-w-[1000px] space-y-5 p-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-h1 font-extrabold uppercase">{T.title}</h1>
          <p className="mt-1 text-small text-muted">{T.lead}</p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <span role="status" className="text-small font-semibold tabular-nums">
            {T.stats(have, total, ok)}
          </span>
          {approved ? (
            <Button
              tone="soft"
              busy={approve.isPending}
              icon={<CheckIcon size={16} />}
              onClick={() => approve.mutate(false)}
            >
              {T.unapprove}
            </Button>
          ) : (
            <Button
              tone="accent"
              busy={approve.isPending}
              disabled={!canApprove}
              reason={canApprove ? undefined : T.missing(sceneNumber(firstMissing))}
              onClick={() => approve.mutate(true)}
            >
              {T.approve}
            </Button>
          )}
        </div>
      </div>

      <ul className="space-y-4">
        {project.scenes.map((scene, i) => {
          const d = draft.scenes[i];
          if (!d) return null;
          return (
            <SceneImageRow
              key={i}
              index={i}
              slug={slug}
              scene={scene}
              draft={d}
              imageVersion={imageVersion}
              busy={uploading}
              onUpload={upload}
              onSavePrompt={savePrompt}
            />
          );
        })}
      </ul>
    </div>
  );
}
