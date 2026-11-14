import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useRef, useState } from 'react';
import { api } from '../api/endpoints';
import type { AssetHubCategory, AssetHubItem } from '../api/types';
import { ErrorNote } from '../components/ErrorNote';
import { DownloadIcon, FolderIcon, PlayIcon, PlusIcon, TrashIcon } from '../components/icons';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Dialog } from '../components/ui/Dialog';
import { Skeleton } from '../components/ui/Skeleton';
import { cx } from '../components/ui/cx';
import { useToast } from '../hooks/toast';
import { vi } from '../i18n/vi';
import { Dropzone } from '../shared';

const T = vi.assetHub;

const CATEGORIES: {
  id: AssetHubCategory;
  emoji: string;
  label: string;
  cta: string;
}[] = [
  { id: 'music', emoji: '🎵', label: T.tabs.music, cta: '+ Thêm nhạc nền' },
  { id: 'backgrounds', emoji: '🎮', label: T.tabs.backgrounds, cta: '+ Thêm video nền' },
  { id: 'stickers', emoji: '🎭', label: T.tabs.stickers, cta: '+ Thêm Sticker / Meme' },
  { id: 'watermarks', emoji: '🏷️', label: T.tabs.watermarks, cta: '+ Tải lên Watermark' },
];

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function AssetHubPage() {
  const [activeTab, setActiveTab] = useState<AssetHubCategory>('stickers');
  const [previewItem, setPreviewItem] = useState<AssetHubItem | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
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
  const activeCat = CATEGORIES.find((c) => c.id === activeTab) ?? CATEGORIES[0];

  return (
    <main className="mx-auto max-w-[1360px] space-y-6 px-6 py-8">
      {/* Header với nút + Import tài nguyên Vàng Nghệ nổi bật */}
      <header className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-white/10 bg-[#131720] p-6 shadow-lg">
        <div className="space-y-1.5">
          <div className="flex items-center gap-3">
            <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br from-[#D9232E] to-[#B91C1C] text-white shadow-md">
              <FolderIcon size={22} />
            </span>
            <h1 className="text-h1 font-extrabold uppercase tracking-tight text-white">
              {T.title}
            </h1>
            <Badge tone="yel">{T.count(items.length)}</Badge>
          </div>
          <p className="text-small text-[#94A3B8]">{T.lead}</p>
        </div>

        <div className="flex items-center gap-3">
          <input
            ref={fileInputRef}
            type="file"
            multiple
            className="hidden"
            onChange={(e) => {
              const selected = Array.from(e.target.files ?? []);
              if (selected.length > 0) {
                upload.mutate(selected);
              }
              e.target.value = '';
            }}
          />
          <button
            type="button"
            disabled={upload.isPending}
            onClick={() => fileInputRef.current?.click()}
            className="ui-btn-gold inline-flex items-center gap-2 rounded-full bg-gradient-to-r from-[#FACC15] to-[#F59E0B] px-5 py-3 text-small font-extrabold text-[#0B0D12] shadow-[0_6px_20px_rgba(245,158,11,0.35)] transition hover:-translate-y-0.5 active:scale-95"
          >
            <PlusIcon size={18} />
            <span>{activeCat.cta || T.importCta}</span>
          </button>
        </div>
      </header>

      {/* 4 Tabs nguyên liệu đầu vào */}
      <div
        role="tablist"
        aria-label={T.title}
        className="grid grid-cols-2 gap-2.5 rounded-2xl border border-white/10 bg-[#131720] p-2 sm:grid-cols-4"
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
                'flex items-center justify-center gap-2 rounded-xl px-4 py-3 text-small font-extrabold transition duration-150',
                selected
                  ? 'bg-gradient-to-r from-[#D9232E] to-[#B91C1C] text-white shadow-[0_6px_18px_rgba(217,35,46,0.35)]'
                  : 'text-[#94A3B8] hover:bg-white/5 hover:text-white',
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
        <div className="rounded-2xl border border-dashed border-white/15 bg-[#131720] p-12 text-center text-small text-[#94A3B8]">
          {T.empty}
        </div>
      ) : (
        <ul className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
          {items.map((item) => (
            <li
              key={item.name}
              className="group flex flex-col overflow-hidden rounded-2xl border border-white/10 bg-[#131720] transition duration-150 hover:-translate-y-0.5 hover:border-[#FACC15]/60"
            >
              <div className="relative aspect-square w-full overflow-hidden bg-[#0B0D12]">
                {item.kind === 'image' ? (
                  <img
                    src={item.url}
                    alt={item.name}
                    className="h-full w-full object-contain p-3 transition duration-200 group-hover:scale-105"
                  />
                ) : item.kind === 'video' ? (
                  <video
                    src={item.url}
                    muted
                    playsInline
                    preload="metadata"
                    className="h-full w-full object-cover"
                  />
                ) : item.kind === 'audio' ? (
                  <div className="flex h-full flex-col items-center justify-center gap-3 p-4 text-center">
                    <span className="text-4xl">🎵</span>
                    <audio src={item.url} controls preload="none" className="w-full max-w-[200px]" />
                  </div>
                ) : (
                  <div className="flex h-full items-center justify-center text-tiny text-muted">
                    {item.name}
                  </div>
                )}
              </div>

              <div className="flex flex-1 flex-col gap-2 p-3.5">
                <p className="truncate text-small font-bold text-white" title={item.name}>
                  {item.name}
                </p>
                <p className="text-tiny text-[#94A3B8]">{formatBytes(item.size)}</p>

                <div className="mt-auto flex items-center justify-between gap-1.5 pt-1">
                  <div className="flex items-center gap-1">
                    {(item.kind === 'video' || item.kind === 'image' || item.kind === 'audio') && (
                      <button
                        type="button"
                        aria-label={`${T.preview}: ${item.name}`}
                        title={T.preview}
                        onClick={() => setPreviewItem(item)}
                        className="flex h-8 w-8 items-center justify-center rounded-lg bg-white/10 text-white transition hover:bg-[#FACC15] hover:text-[#0B0D12]"
                      >
                        <PlayIcon size={14} />
                      </button>
                    )}
                    <a
                      href={item.url}
                      download={item.name}
                      aria-label={`${T.download}: ${item.name}`}
                      title={T.download}
                      className="flex h-8 w-8 items-center justify-center rounded-lg bg-white/10 text-white transition hover:bg-[#FACC15] hover:text-[#0B0D12]"
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
                    className="flex h-8 w-8 items-center justify-center rounded-lg bg-white/10 text-[#EF4444] transition hover:bg-[#D9232E] hover:text-white"
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
            ) : previewItem.kind === 'audio' ? (
              <audio src={previewItem.url} controls autoPlay className="w-full" />
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
