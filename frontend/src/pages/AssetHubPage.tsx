import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useRef, useState } from 'react';
import { api } from '../api/endpoints';
import type { AssetHubCategory, AssetHubItem, UnifiedRenderItem } from '../api/types';
import { ErrorNote } from '../components/ErrorNote';
import { RenderPlayerModal } from '../components/home/RenderPlayerModal';
import { CopyIcon, DownloadIcon, FolderIcon, PlayIcon, PlusIcon, TrashIcon } from '../components/icons';
import { AudioTrackRow } from '../components/library/AudioTrackRow';
import { GameplayCard } from '../components/library/GameplayCard';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { Dialog } from '../components/ui/Dialog';
import { Skeleton } from '../components/ui/Skeleton';
import { cx } from '../components/ui/cx';
import { useToast } from '../hooks/toast';
import { vi } from '../i18n/vi';
import { Dropzone } from '../shared';
import { formatDate, formatDuration } from '../utils/format';

const T = vi.assetHub;

type LibraryTab = 'renders' | AssetHubCategory;

const TABS: {
  id: LibraryTab;
  emoji: string;
  label: string;
  cta?: string;
}[] = [
  { id: 'renders', emoji: '🎬', label: 'Video đã xuất' },
  { id: 'music', emoji: '🎵', label: 'Nhạc nền', cta: 'Import nhạc nền' },
  { id: 'backgrounds', emoji: '🎮', label: 'Video nền Gameplay', cta: 'Import video nền' },
  { id: 'memes', emoji: '😂', label: 'Meme', cta: 'Import Meme' },
  { id: 'stickers', emoji: '🎭', label: 'Sticker', cta: 'Import Sticker' },
  { id: 'watermarks', emoji: '🏷️', label: 'Logo Watermark', cta: 'Tải lên Watermark' },
];

const ENGINE_LABELS: Record<'all' | 'core' | 'postv' | 'chatting', string> = {
  all: 'Tất cả',
  core: 'HBT Core',
  postv: 'PostV',
  chatting: 'Chatting',
};

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function AssetHubPage() {
  const [activeTab, setActiveTab] = useState<LibraryTab>('renders');
  const [previewItem, setPreviewItem] = useState<AssetHubItem | null>(null);
  const [previewRender, setPreviewRender] = useState<UnifiedRenderItem | null>(null);
  const [engineFilter, setEngineFilter] = useState<'all' | 'core' | 'postv' | 'chatting'>('all');
  const [playingAudioUrl, setPlayingAudioUrl] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const queryClient = useQueryClient();
  const toast = useToast();

  const isRendersTab = activeTab === 'renders';

  const rendersQuery = useQuery({
    queryKey: ['unified-renders'],
    queryFn: () => api.listUnifiedRenders(),
  });

  const musicQuery = useQuery({
    queryKey: ['asset-hub', 'music'],
    queryFn: () => api.listAssetHub('music'),
  });
  const bgQuery = useQuery({
    queryKey: ['asset-hub', 'backgrounds'],
    queryFn: () => api.listAssetHub('backgrounds'),
  });
  const memeQuery = useQuery({
    queryKey: ['asset-hub', 'memes'],
    queryFn: () => api.listAssetHub('memes'),
  });
  const stickerQuery = useQuery({
    queryKey: ['asset-hub', 'stickers'],
    queryFn: () => api.listAssetHub('stickers'),
  });
  const watermarkQuery = useQuery({
    queryKey: ['asset-hub', 'watermarks'],
    queryFn: () => api.listAssetHub('watermarks'),
  });

  const activeQueryMap = {
    music: musicQuery,
    backgrounds: bgQuery,
    memes: memeQuery,
    stickers: stickerQuery,
    watermarks: watermarkQuery,
  } as const;

  const activeAssetQuery = !isRendersTab ? activeQueryMap[activeTab] : null;

  const tabCounts: Record<LibraryTab, number> = {
    renders: rendersQuery.data?.items.length ?? 0,
    music: musicQuery.data?.items.length ?? 0,
    backgrounds: bgQuery.data?.items.length ?? 0,
    memes: memeQuery.data?.items.length ?? 0,
    stickers: stickerQuery.data?.items.length ?? 0,
    watermarks: watermarkQuery.data?.items.length ?? 0,
  };

  const upload = useMutation({
    mutationFn: async (files: File[]) => {
      if (isRendersTab) return files;
      for (const f of files) {
        await api.uploadAssetHub(activeTab as AssetHubCategory, f);
      }
      return files;
    },
    onSuccess: (files) => {
      void queryClient.invalidateQueries({ queryKey: ['asset-hub', activeTab] });
      toast.info(T.uploaded(files.length === 1 ? files[0].name : `${files.length} tệp`));
    },
    onError: (e) => toast.error(e),
  });

  const removeAsset = useMutation({
    mutationFn: (item: AssetHubItem) =>
      api.deleteAssetHub(activeTab as AssetHubCategory, item.name, item.source),
    onSuccess: (_res, item) => {
      void queryClient.invalidateQueries({ queryKey: ['asset-hub', activeTab] });
      toast.info(T.deleted(item.name));
    },
    onError: (e) => toast.error(e),
  });

  const removeRender = useMutation({
    mutationFn: (item: UnifiedRenderItem) => api.deleteUnifiedRender(item.id),
    onSuccess: (_res, item) => {
      void queryClient.invalidateQueries({ queryKey: ['unified-renders'] });
      toast.info(`Đã xóa video "${item.title}"`);
      if (previewRender?.id === item.id) setPreviewRender(null);
    },
    onError: (e) => toast.error(e),
  });

  const items = activeAssetQuery?.data?.items ?? [];
  const allRenders = rendersQuery.data?.items ?? [];
  const filteredRenders =
    engineFilter === 'all' ? allRenders : allRenders.filter((r) => r.engine === engineFilter);
  const activeTabInfo = TABS.find((c) => c.id === activeTab) ?? TABS[0];

  const togglePlayAudio = (url: string) => {
    const el = audioRef.current;
    if (!el) return;
    if (playingAudioUrl === url && !el.paused) {
      el.pause();
      setPlayingAudioUrl(null);
    } else {
      el.src = url;
      void el.play().catch(() => {});
      setPlayingAudioUrl(url);
    }
  };

  const handleCopyPublish = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      toast.info('Đã sao chép nội dung đăng bài!');
    } catch (err) {
      toast.error(err);
    }
  };

  return (
    <main className="mx-auto max-w-[1320px] space-y-6 px-6 py-7">
      <audio ref={audioRef} onEnded={() => setPlayingAudioUrl(null)} className="hidden" />

      {/* Header Visual Asset Hub — Light/Dark Adaptive */}
      <header className="flex flex-wrap items-center justify-between gap-4 rounded-card border border-line bg-card/90 p-6 shadow-card backdrop-blur-sm">
        <div className="space-y-1.5">
          <div className="flex items-center gap-3">
            <span className="flex h-11 w-11 items-center justify-center rounded-inner bg-gradient-to-br from-[#F59E0B] to-[#EA580C] text-white shadow-sm">
              <FolderIcon size={22} />
            </span>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-h1 font-extrabold tracking-tight text-text">{T.title}</h1>
                <Badge tone="yel">{T.count(tabCounts[activeTab])}</Badge>
              </div>
              <p className="text-small text-muted">{T.lead}</p>
            </div>
          </div>
        </div>

        {!isRendersTab && (
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
            <Button
              tone="export"
              busy={upload.isPending}
              icon={<PlusIcon size={16} />}
              onClick={() => fileInputRef.current?.click()}
            >
              {activeTabInfo.cta || T.importCta}
            </Button>
          </div>
        )}
      </header>

      {/* Thanh Tab có bộ đếm số lượng từng loại */}
      <div
        role="tablist"
        aria-label={T.title}
        className="grid grid-cols-2 gap-2 rounded-card border border-line bg-card p-2 shadow-card sm:grid-cols-3 lg:grid-cols-6"
      >
        {TABS.map((cat) => {
          const selected = activeTab === cat.id;
          return (
            <button
              key={cat.id}
              type="button"
              role="tab"
              aria-selected={selected}
              onClick={() => setActiveTab(cat.id)}
              className={cx(
                'flex items-center justify-center gap-2 rounded-inner px-3 py-2.5 text-small font-bold transition-all duration-180',
                selected
                  ? 'bg-primary text-on-primary shadow-sm'
                  : 'text-muted hover:bg-soft hover:text-text',
              )}
            >
              <span aria-hidden="true">{cat.emoji}</span>
              <span className="truncate">{cat.label}</span>
              <span
                className={cx(
                  'num rounded-pill px-1.5 py-0.5 text-[11px] font-extrabold',
                  selected ? 'bg-white/20 text-on-primary' : 'bg-soft text-text-2',
                )}
              >
                {tabCounts[cat.id]}
              </span>
            </button>
          );
        })}
      </div>

      {/* Dropzone ở các tab nguyên liệu */}
      {!isRendersTab && (
        <Dropzone
          title={T.dropTitle}
          hint={T.dropHint}
          busy={upload.isPending}
          busyTitle={T.uploading}
          onFiles={(files) => upload.mutate(files)}
        />
      )}

      {(isRendersTab ? rendersQuery.error : activeAssetQuery?.error) && (
        <div className="space-y-2">
          <ErrorNote error={isRendersTab ? rendersQuery.error : activeAssetQuery?.error} />
          <Button
            tone="soft"
            size="sm"
            onClick={() =>
              void (isRendersTab ? rendersQuery.refetch() : activeAssetQuery?.refetch())
            }
          >
            {vi.common.retry}
          </Button>
        </div>
      )}

      {/* 1. Tab Video đã xuất */}
      {isRendersTab ? (
        <section aria-label="Video đã xuất trên hệ thống" className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-small text-muted">
              Toàn bộ video 9:16 đã dựng từ HBT Core, PostV và Chatting trong workspace.
            </p>
            <div className="flex flex-wrap items-center gap-1.5">
              {(['all', 'core', 'postv', 'chatting'] as const).map((eng) => {
                const active = engineFilter === eng;
                return (
                  <button
                    key={eng}
                    type="button"
                    aria-pressed={active}
                    onClick={() => setEngineFilter(eng)}
                    className={`ui-chip ui-chip-sm ${active ? '!bg-primary !text-on-primary' : ''}`}
                  >
                    {ENGINE_LABELS[eng]}
                  </button>
                );
              })}
            </div>
          </div>

          {rendersQuery.isPending ? (
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} height={320} className="!rounded-card" />
              ))}
            </div>
          ) : filteredRenders.length === 0 ? (
            <Card className="py-12 text-center">
              <p className="text-body font-bold text-text">Chưa có video nào được xuất ở mục này</p>
            </Card>
          ) : (
            <ul className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
              {filteredRenders.map((item) => (
                <Card
                  key={item.id}
                  as="li"
                  padded={false}
                  className="group flex flex-col overflow-hidden transition-all duration-180 hover:-translate-y-0.5 hover:shadow-card-hover"
                >
                  <button
                    type="button"
                    onClick={() => setPreviewRender(item)}
                    className="relative aspect-[9/16] w-full overflow-hidden bg-hero text-left"
                    aria-label={`Xem video ${item.title}`}
                  >
                    {item.cover_url ? (
                      <img
                        src={item.cover_url}
                        alt={item.title}
                        className="h-full w-full object-cover"
                        loading="lazy"
                      />
                    ) : (
                      <video
                        src={`${item.video_url}#t=0.5`}
                        muted
                        playsInline
                        preload="metadata"
                        poster="/brand/hay-biet-tuot_avatar.png"
                        className="h-full w-full object-cover"
                      />
                    )}
                    <div className="absolute inset-0 bg-gradient-to-t from-black/75 via-transparent to-black/25" />
                    <span className="absolute left-2.5 top-2.5">
                      <Badge tone={item.engine}>{ENGINE_LABELS[item.engine]}</Badge>
                    </span>
                    <span className="absolute inset-0 flex items-center justify-center opacity-0 transition-opacity group-hover:opacity-100">
                      <span className="flex h-12 w-12 items-center justify-center rounded-full bg-white/90 text-slate-900 shadow-lg">
                        <PlayIcon size={20} />
                      </span>
                    </span>
                    {item.duration_sec > 0 && (
                      <span className="num absolute bottom-2.5 right-2.5 rounded-md bg-black/75 px-2 py-0.5 text-tiny font-bold text-white">
                        {formatDuration(item.duration_sec)}
                      </span>
                    )}
                  </button>

                  <div className="flex flex-1 flex-col justify-between gap-2 p-3.5">
                    <div>
                      <p className="line-clamp-2 text-small font-bold text-text">{item.title}</p>
                      <p className="num mt-1 text-tiny text-muted">
                        {item.size_mb} MB
                        {item.created_at ? ` · ${formatDate(item.created_at)}` : ''}
                      </p>
                    </div>
                    <div className="flex items-center gap-1.5 pt-1">
                      <Button
                        size="sm"
                        tone="ink"
                        icon={<PlayIcon size={13} />}
                        onClick={() => setPreviewRender(item)}
                        className="flex-1"
                      >
                        Xem
                      </Button>
                      <a
                        href={item.video_url}
                        download={`${item.slug || 'video'}.mp4`}
                        className="ui-icon-btn ui-icon-btn-sm bg-soft"
                        title="Tải .mp4"
                        aria-label={`Tải ${item.title}`}
                      >
                        <DownloadIcon size={14} />
                      </a>
                      {item.publish_text && (
                        <button
                          type="button"
                          onClick={() => void handleCopyPublish(item.publish_text)}
                          className="ui-icon-btn ui-icon-btn-sm bg-soft"
                          title="Copy publish.txt"
                          aria-label={`Copy caption ${item.title}`}
                        >
                          <CopyIcon size={14} />
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={() => removeRender.mutate(item)}
                        className="ui-icon-btn ui-icon-btn-sm text-danger hover:bg-danger-soft"
                        aria-label={`Xóa video ${item.title}`}
                      >
                        <TrashIcon size={14} />
                      </button>
                    </div>
                  </div>
                </Card>
              ))}
            </ul>
          )}
        </section>
      ) : activeAssetQuery?.isPending ? (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} height={220} className="!rounded-card" />
          ))}
        </div>
      ) : activeTab === 'music' ? (
        /* 2. Tab Nhạc nền */
        items.length === 0 ? (
          <Card className="py-12 text-center">
            <p className="text-body font-bold text-text">{T.empty}</p>
          </Card>
        ) : (
          <ul className="space-y-2.5">
            {items.map((item) => (
              <AudioTrackRow
                key={`${item.source}-${item.name}`}
                item={item}
                isPlaying={playingAudioUrl === item.url}
                onTogglePlay={togglePlayAudio}
                onDelete={(it) => removeAsset.mutate(it)}
                audioElement={audioRef.current}
              />
            ))}
          </ul>
        )
      ) : activeTab === 'backgrounds' ? (
        /* 3. Tab Video nền Gameplay 9:16 Hover-to-Play */
        items.length === 0 ? (
          <Card className="py-12 text-center">
            <p className="text-body font-bold text-text">{T.empty}</p>
          </Card>
        ) : (
          <ul className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
            {items.map((item) => (
              <GameplayCard
                key={`${item.source}-${item.name}`}
                item={item}
                onPreview={setPreviewItem}
                onDelete={(it) => removeAsset.mutate(it)}
              />
            ))}
          </ul>
        )
      ) : activeTab === 'watermarks' ? (
        /* 4. Tab Logo Watermark */
        <div className="space-y-4">
          <Card className="flex flex-wrap items-center justify-between gap-4 border-engine-core/25 bg-engine-core-soft/40">
            <div className="flex items-center gap-4">
              <div className="flex h-16 w-16 items-center justify-center rounded-inner border border-line bg-card p-2 shadow-sm">
                <img
                  src="/brand/hbt-logo-mark.png"
                  alt="Logo HBT Studio mặc định"
                  className="max-h-full max-w-full object-contain"
                />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <p className="text-body font-extrabold text-text">Logo HBT Studio (Mặc định)</p>
                  <Badge tone="core">Đang dùng mặc định</Badge>
                </div>
                <p className="text-small text-muted">
                  Tự động chèn góc màn hình khi xuất bản video 9:16. Tải lên PNG trong suốt nếu muốn
                  thay thế.
                </p>
              </div>
            </div>
          </Card>

          {items.length > 0 && (
            <ul className="grid grid-cols-2 gap-4 sm:grid-cols-4 lg:grid-cols-6">
              {items.map((item) => (
                <Card key={`${item.source}-${item.name}`} as="li" padded={false} className="overflow-hidden">
                  <div className="flex aspect-square items-center justify-center bg-soft p-4">
                    <img src={item.url} alt={item.name} className="max-h-full max-w-full object-contain" />
                  </div>
                  <div className="flex items-center justify-between gap-2 p-3">
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-tiny font-bold text-text">{item.name}</p>
                      <p className="num text-[11px] text-muted">{formatBytes(item.size)}</p>
                    </div>
                    <button
                      type="button"
                      onClick={() => removeAsset.mutate(item)}
                      aria-label={`Xóa ${item.name}`}
                      className="ui-icon-btn ui-icon-btn-sm text-danger hover:bg-danger-soft"
                    >
                      <TrashIcon size={14} />
                    </button>
                  </div>
                </Card>
              ))}
            </ul>
          )}
        </div>
      ) : items.length === 0 ? (
        <Card className="py-12 text-center">
          <p className="text-body font-bold text-text">{T.empty}</p>
        </Card>
      ) : (
        /* 5. Tab Meme & Sticker */
        <ul className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
          {items.map((item) => (
            <Card
              key={`${item.source}-${item.name}`}
              as="li"
              padded={false}
              className="group overflow-hidden transition-all duration-180 hover:-translate-y-0.5 hover:shadow-card-hover"
            >
              <button
                type="button"
                onClick={() => setPreviewItem(item)}
                className="relative flex aspect-square w-full items-center justify-center overflow-hidden bg-soft"
                aria-label={`Xem ${item.name}`}
              >
                {item.type === 'video' ? (
                  <video
                    src={item.url}
                    muted
                    loop
                    playsInline
                    preload="metadata"
                    className="h-full w-full object-cover"
                  />
                ) : (
                  <img
                    src={item.url}
                    alt={item.name}
                    className="h-full w-full object-contain p-2"
                    loading="lazy"
                  />
                )}
              </button>
              <div className="flex items-center justify-between gap-2 p-3">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-tiny font-bold text-text">{item.name}</p>
                  <p className="num text-[11px] text-muted">{formatBytes(item.size)}</p>
                </div>
                <button
                  type="button"
                  onClick={() => removeAsset.mutate(item)}
                  aria-label={`Xóa ${item.name}`}
                  className="ui-icon-btn ui-icon-btn-sm text-danger hover:bg-danger-soft"
                >
                  <TrashIcon size={14} />
                </button>
              </div>
            </Card>
          ))}
        </ul>
      )}

      {/* Modal xem trước Video đã xuất */}
      <RenderPlayerModal
        item={previewRender}
        onClose={() => setPreviewRender(null)}
        onCopyPublish={(text) => void handleCopyPublish(text)}
        onRequestDelete={(item) => removeRender.mutate(item)}
      />

      {/* Modal xem trước tài nguyên lẻ */}
      <Dialog
        open={Boolean(previewItem)}
        onClose={() => setPreviewItem(null)}
        title={previewItem?.name ?? 'Xem trước tài nguyên'}
      >
        {previewItem && (
          <div className="flex flex-col items-center gap-4">
            {previewItem.type === 'video' ? (
              <video
                src={previewItem.url}
                controls
                autoPlay
                playsInline
                className="max-h-[70vh] w-full rounded-inner bg-hero"
              />
            ) : (
              <img
                src={previewItem.url}
                alt={previewItem.name}
                className="max-h-[70vh] w-auto rounded-inner object-contain"
              />
            )}
          </div>
        )}
      </Dialog>
    </main>
  );
}
