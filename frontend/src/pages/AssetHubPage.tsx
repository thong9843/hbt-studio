import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { api } from '../api/endpoints';
import type { AssetHubCategory, AssetHubItem } from '../api/types';
import { ErrorNote } from '../components/ErrorNote';
import { DownloadIcon, FolderIcon, PlayIcon, TrashIcon } from '../components/icons';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Dialog } from '../components/ui/Dialog';
import { Skeleton } from '../components/ui/Skeleton';
import { cx } from '../components/ui/cx';
import { useToast } from '../hooks/toast';
import { vi } from '../i18n/vi';
import { Dropzone } from '../shared';

const T = vi.assetHub;

const CATEGORIES: { id: AssetHubCategory; emoji: string; label: string }[] = [
  { id: 'stickers', emoji: '🎭', label: T.tabs.stickers },
  { id: 'memes', emoji: '🐸', label: T.tabs.memes },
  { id: 'backgrounds', emoji: '🎮', label: T.tabs.backgrounds },
  { id: 'renders', emoji: '🎬', label: T.tabs.renders },
];

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function AssetHubPage() {
  const [activeTab, setActiveTab] = useState<AssetHubCategory>('stickers');
  const [previewItem, setPreviewItem] = useState<AssetHubItem | null>(null);
  const queryClient = useQueryClient();
  const toast = useToast();

  const { data, isPending, error, refetch } = useQuery({
    queryKey: ['asset-hub', activeTab],
    queryFn: () => api.listAssetHub(activeTab),
  });

  const upload = useMutation({
    mutationFn: async (files: File[]) => {
      for (const f of files) {
        await api.uploadAssetHub(activeTab, f);
      }
      return files;
    },
    onSuccess: (files) => {
      void queryClient.invalidateQueries({ queryKey: ['asset-hub', activeTab] });
      toast.info(T.uploaded(files.length === 1 ? files[0].name : `${files.length} tệp`));
    },
    onError: (e) => toast.error(e),
  });

  const remove = useMutation({
    mutationFn: (filename: string) => api.deleteAssetHub(activeTab, filename),
    onSuccess: (_res, filename) => {
      void queryClient.invalidateQueries({ queryKey: ['asset-hub', activeTab] });
      toast.info(T.deleted(filename));
    },
    onError: (e) => toast.error(e),
  });

  const items = data?.items ?? [];

  return (
    <main className="mx-auto max-w-[1360px] space-y-6 px-6 py-8">
      {/* Header */}
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div className="space-y-1">
          <div className="flex items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-inner bg-gradient-to-br from-indigo-500 via-violet-500 to-amber-500 text-white shadow-sm">
              <FolderIcon size={20} />
            </span>
            <h1 className="text-h1 font-extrabold uppercase tracking-tight">{T.title}</h1>
            <Badge tone="neutral">{T.count(items.length)}</Badge>
          </div>
          <p className="text-small text-muted">{T.lead}</p>
        </div>
      </header>

      {/* Tabs chuyển danh mục */}
      <div
        role="tablist"
        aria-label={T.title}
        className="flex flex-wrap gap-2 rounded-card border border-line bg-card p-2"
      >
        {CATEGORIES.map((cat) => {
          const selected = activeTab === cat.id;
          return (
            <button
              key={cat.id}
              type="button"
              role="tab"
              aria-selected={selected}
              onClick={() => setActiveTab(cat.id)}
              className={cx(
                'flex items-center gap-2 rounded-inner px-4 py-2.5 text-small font-bold transition duration-150',
                selected
                  ? 'bg-gradient-to-r from-indigo-600 via-violet-600 to-amber-500 text-white shadow-sm'
                  : 'text-muted hover:bg-soft hover:text-ink',
              )}
            >
              <span aria-hidden="true">{cat.emoji}</span>
              <span>{cat.label}</span>
            </button>
          );
        })}
      </div>

      {/* Khu vực kéo thả (Dropzone) */}
      <Dropzone
        title={T.dropTitle}
        hint={T.dropHint}
        busy={upload.isPending}
        busyTitle={T.uploading}
        onFiles={(files) => upload.mutate(files)}
      />

      {error && (
        <div className="space-y-2">
          <ErrorNote error={error} />
          <Button tone="soft" size="sm" onClick={() => void refetch()}>
            {vi.common.retry}
          </Button>
        </div>
      )}

      {/* Grid View */}
      {isPending ? (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} height={220} className="!rounded-card" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <div className="rounded-card border border-line bg-card p-10 text-center text-small text-muted">
          {T.empty}
        </div>
      ) : (
        <ul className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
          {items.map((item) => (
            <li
              key={item.name}
              className="group flex flex-col overflow-hidden rounded-card border border-line bg-card transition duration-150 hover:border-indigo-500/50"
            >
              <div className="relative aspect-square w-full overflow-hidden bg-soft-2">
                {item.kind === 'image' ? (
                  <img
                    src={item.url}
                    alt={item.name}
                    className="h-full w-full object-contain p-2 transition duration-200 group-hover:scale-105"
                  />
                ) : item.kind === 'video' ? (
                  <video
                    src={item.url}
                    muted
                    playsInline
                    preload="metadata"
                    className="h-full w-full object-cover"
                  />
                ) : (
                  <div className="flex h-full items-center justify-center text-tiny text-muted">
                    {item.name}
                  </div>
                )}
              </div>

              <div className="flex flex-1 flex-col gap-2 p-3">
                <p className="truncate text-small font-bold" title={item.name}>
                  {item.name}
                </p>
                <p className="text-tiny text-muted">{formatBytes(item.size)}</p>

                <div className="mt-auto flex items-center justify-between gap-1.5 pt-1">
                  <div className="flex items-center gap-1">
                    {(item.kind === 'video' || item.kind === 'image') && (
                      <button
                        type="button"
                        aria-label={`${T.preview}: ${item.name}`}
                        title={T.preview}
                        onClick={() => setPreviewItem(item)}
                        className="flex h-8 w-8 items-center justify-center rounded-inner bg-soft text-ink transition hover:bg-indigo-600 hover:text-white"
                      >
                        <PlayIcon size={14} />
                      </button>
                    )}
                    <a
                      href={item.url}
                      download={item.name}
                      aria-label={`${T.download}: ${item.name}`}
                      title={T.download}
                      className="flex h-8 w-8 items-center justify-center rounded-inner bg-soft text-ink transition hover:bg-indigo-600 hover:text-white"
                    >
                      <DownloadIcon size={14} />
                    </a>
                  </div>

                  <button
                    type="button"
                    aria-label={`${T.delete}: ${item.name}`}
                    title={T.delete}
                    disabled={remove.isPending}
                    onClick={() => remove.mutate(item.name)}
                    className="flex h-8 w-8 items-center justify-center rounded-inner bg-soft text-danger transition hover:bg-danger hover:text-white"
                  >
                    <TrashIcon size={14} />
                  </button>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}

      {/* Dialog xem trước tệp */}
      <Dialog
        open={previewItem !== null}
        onClose={() => setPreviewItem(null)}
        title={previewItem?.name ?? ''}
        className="!max-w-[680px]"
      >
        {previewItem && (
          <div className="flex flex-col items-center gap-4">
            {previewItem.kind === 'video' ? (
              <video
                src={previewItem.url}
                controls
                autoPlay
                className="max-h-[70vh] w-full rounded-inner bg-black"
              />
            ) : (
              <img
                src={previewItem.url}
                alt={previewItem.name}
                className="max-h-[70vh] w-full rounded-inner object-contain"
              />
            )}
            <a href={previewItem.url} download={previewItem.name} className="ui-btn ui-btn-ink">
              <DownloadIcon size={16} />
              {T.download}
            </a>
          </div>
        )}
      </Dialog>
    </main>
  );
}
