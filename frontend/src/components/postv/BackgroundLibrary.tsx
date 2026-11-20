import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useRef, useState, type FormEvent } from 'react';
import { api } from '../../api/endpoints';
import type { BackgroundEntry } from '../../api/types';
import { useBackgrounds } from '../../hooks/useBackgrounds';
import { vi } from '../../i18n/vi';
import { isLowRes } from '../../utils/background';
import { ConfirmDialog } from '../ConfirmDialog';
import { ErrorNote } from '../ErrorNote';
import { PlusIcon, TrashIcon, UploadIcon } from '../icons';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { Card } from '../ui/Card';
import { Dialog } from '../ui/Dialog';
import { Input } from '../ui/Field';

const T = vi.postv.library;
type Key = keyof typeof T.fields;
const KEYS = Object.keys(T.fields) as Key[];
const REQUIRED: readonly Key[] = ['title'];
const EMPTY: Record<Key, string> = { title: '', tags: '' };
/** Ô một clip: ảnh xem nhanh 9:16, tên, thời lượng; tuỳ chọn có ô chọn hoặc nút xoá. */
export function ClipTile({
  clip,
  selected,
  onToggle,
  onDelete,
}: {
  clip: BackgroundEntry;
  selected?: boolean;
  onToggle?: () => void;
  onDelete?: () => void;
}) {
  return (
    <li className="ui-inner flex w-[132px] flex-none flex-col gap-2 p-2">
      <div className="relative aspect-[9/16] overflow-hidden rounded-inner bg-soft">
        <img
          src={api.backgroundThumbUrl(clip.id)}
          alt=""
          loading="lazy"
          className="h-full w-full object-cover"
        />
        {onToggle && (
          <input
            type="checkbox"
            checked={!!selected}
            onChange={onToggle}
            aria-label={vi.postv.preview.pickClip(clip.title)}
            className="absolute left-2 top-2 h-5 w-5"
          />
        )}
        {onDelete && (
          <Button
            tone="soft"
            size="sm"
            icon={<TrashIcon size={14} />}
            aria-label={`${T.delete} ${clip.title}`}
            onClick={(e) => {
              e.stopPropagation();
              onDelete();
            }}
            className="absolute right-2 top-2 !h-7 !w-7 !p-0 bg-base/80 text-danger hover:bg-base"
          />
        )}
      </div>
      <p className="line-clamp-2 text-small font-bold" title={clip.title}>
        {clip.title}
      </p>
      <p className="num text-tiny text-muted">
        {T.seconds(clip.duration)} · {T.size(clip.width, clip.height, clip.fps)}
      </p>
      <div className="flex flex-wrap gap-1">
        {clip.license && <Badge tone="ok">{T.licensed(clip.license)}</Badge>}
        {isLowRes(clip) && <Badge tone="yel">{T.lowRes}</Badge>}
      </div>
    </li>
  );
}

/** Hộp "Thêm clip nền": video dọc + tên, nguồn, giấy phép bắt buộc (như thư viện nhạc). */
export function AddBackgroundDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [fields, setFields] = useState(EMPTY);
  const fileRef = useRef<HTMLInputElement>(null);
  const add = useMutation({
    mutationFn: () => api.addBackground({ file: file!, ...fields }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['backgrounds'] });
      setFile(null);
      setFields(EMPTY);
      onClose();
    },
  });
  const ready = file !== null && Boolean(fields.title.trim());

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (ready && !add.isPending) add.mutate();
  };

  return (
    <Dialog
      open={open}
      onClose={() => !add.isPending && onClose()}
      title={T.dialogTitle}
      footer={
        <>
          <Button tone="soft" onClick={onClose} disabled={add.isPending}>
            {T.cancel}
          </Button>
          <Button
            type="submit"
            form="add-background"
            tone="ink"
            disabled={!ready}
            busy={add.isPending}
          >
            {add.isPending ? T.submitting : T.submit}
          </Button>
        </>
      }
    >
      <form id="add-background" onSubmit={submit} className="space-y-4">
        <div className="flex flex-wrap items-center gap-3">
          <Button tone="soft" icon={<UploadIcon />} onClick={() => fileRef.current?.click()}>
            {T.pick}
          </Button>
          <input
            ref={fileRef}
            type="file"
            accept="video/*,.mp4,.mov,.mkv,.webm"
            className="sr-only"
            tabIndex={-1}
            aria-label={T.pick}
            onChange={(e) => {
              const f = e.target.files?.[0] ?? null;
              setFile(f);
              if (f && !fields.title) {
                setFields((s) => ({ ...s, title: f.name.replace(/\.[^.]+$/, '') }));
              }
              e.target.value = '';
            }}
          />
          {file && (
            <p className="text-small">
              {T.fileChosen}: <b>{file.name}</b>
            </p>
          )}
        </div>
        <div className="grid gap-3 min-[560px]:grid-cols-2">
          {KEYS.map((key) => (
            <Input
              key={key}
              label={T.fields[key]}
              required={REQUIRED.includes(key)}
              value={fields[key]}
              onChange={(e) => setFields((s) => ({ ...s, [key]: e.target.value }))}
            />
          ))}
        </div>
        <ErrorNote error={add.error} />
      </form>
    </Dialog>
  );
}

/** Khối "Thư viện nền" của trang /postv. */
export function BackgroundLibraryCard() {
  const [adding, setAdding] = useState(false);
  const [deletingClip, setDeletingClip] = useState<BackgroundEntry | null>(null);
  const { data, isPending, error } = useBackgrounds();
  const queryClient = useQueryClient();

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.deleteBackground(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['backgrounds'] });
      setDeletingClip(null);
    },
  });

  return (
    <Card as="section" aria-label={T.title} className="mt-8 space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="mr-auto">
          <h2 className="text-h2 font-bold">{T.title}</h2>
          <p className="text-small text-muted">
            {T.lead}
            {data && data.length > 0 ? ` · ${T.count(data.length)}` : ''}
          </p>
        </div>
        <Button tone="soft" icon={<PlusIcon />} onClick={() => setAdding(true)}>
          {T.add}
        </Button>
      </div>
      <ErrorNote error={error ?? deleteMutation.error} />
      {!isPending && data && data.length === 0 && (
        <p className="text-small text-muted">{T.empty}</p>
      )}
      {data && data.length > 0 && (
        <ul className="flex gap-3 overflow-x-auto pb-1" aria-label={T.title}>
          {data.map((c) => (
            <ClipTile key={c.id} clip={c} onDelete={() => setDeletingClip(c)} />
          ))}
        </ul>
      )}
      <AddBackgroundDialog open={adding} onClose={() => setAdding(false)} />
      {deletingClip && (
        <ConfirmDialog
          title={T.deleteConfirmTitle}
          message={T.deleteConfirmMessage(deletingClip.title)}
          confirmLabel={T.delete}
          danger
          busy={deleteMutation.isPending}
          onConfirm={() => deleteMutation.mutate(deletingClip.id)}
          onCancel={() => !deleteMutation.isPending && setDeletingClip(null)}
        />
      )}
    </Card>
  );
}
