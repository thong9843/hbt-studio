import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useRef, useState } from 'react';
import { api } from '../api/endpoints';
import type { AssetHubCategory, AssetHubItem, UnifiedRenderItem } from '../api/types';
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
import { formatDate, formatDuration } from '../utils/format';

const T = vi.assetHub;

type LibraryTab = AssetHubCategory | 'renders';

const TABS: {
  id: LibraryTab;
  emoji: string;
  label: string;
  cta?: string;
}[] = [
  { id: 'music', emoji: '🎵', label: 'Nhạc nền', cta: '+ Thêm nhạc nền' },
  { id: 'backgrounds', emoji: '🎮', label: 'Video nền', cta: '+ Thêm video nền' },
  { id: 'memes', emoji: '😂', label: 'Meme', cta: '+ Thêm Meme' },
  { id: 'stickers', emoji: '🎭', label: 'Sticker', cta: '+ Thêm Sticker' },
  { id: 'watermarks', emoji: '🏷️', label: 'Logo Watermark', cta: '+ Tải lên Watermark' },
  { id: 'renders', emoji: '🎬', label: 'Video đã xuất' },
];

const ENGINE_LABELS: Record<'all' | 'core' | 'postv' | 'chatting', string> = {
  all: 'Tất cả',
  core: 'HBT Core',
  postv: 'PostV',
  chatting: 'Chatting',
};

const ENGINE_BADGE_STYLE: Record<'core' | 'postv' | 'chatting', string> = {
  core: 'bg-[#D9232E] text-white border-[#F87171]/40',
  postv: 'bg-white text-[#0B0D12] border-white/80',
  chatting: 'bg-[#FACC15] text-[#0B0D12] border-[#FACC15]',
};

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function AssetHubPage() {
  const [activeTab, setActiveTab] = useState<LibraryTab>('music');
  const [previewItem, setPreviewItem] = useState<AssetHubItem | null>(null);
  const [previewRender, setPreviewRender] = useState<UnifiedRenderItem | null>(null);
  const [engineFilter, setEngineFilter] = useState<'all' | 'core' | 'postv' | 'chatting'>('all');
  const [playingAudioUrl, setPlayingAudioUrl] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const queryClient = useQueryClient();
  const toast = useToast();

  const isRendersTab = activeTab === 'renders';

  const assetQuery = useQuery({
    queryKey: ['asset-hub', activeTab],
    queryFn: () => api.listAssetHub(activeTab as AssetHubCategory),
    enabled: !isRendersTab,
  });

  const rendersQuery = useQuery({
    queryKey: ['unified-renders'],
    queryFn: () => api.listUnifiedRenders(),
    enabled: isRendersTab,
  });

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

  const items = assetQuery.data?.items ?? [];
  const allRenders = rendersQuery.data?.items ?? [];
  const filteredRenders =
    engineFilter === 'all' ? allRenders : allRenders.filter((r) => r.engine === engineFilter);
  const activeTabInfo = TABS.find((c) => c.id === activeTab) ?? TABS[0];
  const currentCount = isRendersTab ? filteredRenders.length : items.length;

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
    <main className="mx-auto max-w-[1360px] space-y-6 px-6 py-8">
      <audio ref={audioRef} onEnded={() => setPlayingAudioUrl(null)} className="hidden" />

      {/* Header với nút + Import tài nguyên Vàng Nghệ nổi bật */}
      <header className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-white/10 bg-surface-dark p-6 text-on-dark shadow-lg">
        <div className="space-y-1.5">
          <div className="flex items-center gap-3">
            <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br from-[#D9232E] to-[#B91C1C] text-white shadow-md">
              <FolderIcon size={22} />
            </span>
            <h1 className="text-h1 font-extrabold uppercase tracking-tight text-on-dark">
              {T.title}
            </h1>
            <Badge tone="yel">{T.count(currentCount)}</Badge>
          </div>
          <p className="text-small text-muted-on-dark">{T.lead}</p>
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
            <button
              type="button"
              disabled={upload.isPending}
              onClick={() => fileInputRef.current?.click()}
              className="ui-btn-gold inline-flex items-center gap-2 rounded-full bg-gradient-to-r from-[#FACC15] to-[#F59E0B] px-5 py-3 text-small font-extrabold text-[#0B0D12] shadow-[0_6px_20px_rgba(245,158,11,0.35)] transition hover:-translate-y-0.5 active:scale-95"
            >
              <PlusIcon size={18} />
              <span>{activeTabInfo.cta || T.importCta}</span>
            </button>
          </div>
        )}
      </header>

      {/* Tabs Thư viện: 5 nhóm nguyên liệu + Video đã xuất */}
      <div
        role="tablist"
        aria-label={T.title}
        className="grid grid-cols-2 gap-2 rounded-2xl border border-white/10 bg-surface-dark p-2 sm:grid-cols-3 lg:grid-cols-6"
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
                'flex items-center justify-center gap-2 rounded-xl px-3 py-2.5 text-small font-extrabold transition duration-150',
                selected
                  ? 'bg-gradient-to-r from-[#D9232E] to-[#B91C1C] text-white shadow-[0_6px_18px_rgba(217,35,46,0.35)]'
                  : 'text-muted-on-dark hover:bg-white/5 hover:text-on-dark',
              )}
            >
              <span aria-hidden="true">{cat.emoji}</span>
              <span className="truncate">{cat.label}</span>
            </button>
          );
        })}
      </div>

      {/* Dropzone chỉ hiện ở các tab nguyên liệu */}
      {!isRendersTab && (
        <Dropzone
          title={T.dropTitle}
          hint={T.dropHint}
          busy={upload.isPending}
          busyTitle={T.uploading}
          onFiles={(files) => upload.mutate(files)}
        />
      )}

      {(isRendersTab ? rendersQuery.error : assetQuery.error) && (
        <div className="space-y-2">
          <ErrorNote error={isRendersTab ? rendersQuery.error : assetQuery.error} />
          <Button
            tone="soft"
            size="sm"
            onClick={() => void (isRendersTab ? rendersQuery.refetch() : assetQuery.refetch())}
          >
            {vi.common.retry}
          </Button>
        </div>
      )}

      {/* Nội dung Tab Video đã xuất */}
      {isRendersTab ? (
        <section aria-label="Video đã xuất trên hệ thống" className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-small text-muted">
              Toàn bộ video 9:16 đã dựng từ HBT Core, PostV và Chatting trong workspace.
            </p>
            <div
              role="tablist"
              aria-label="Lọc video theo động cơ"
              className="flex flex-wrap items-center gap-1.5 rounded-inner border border-line bg-card p-1"
            >
              {(['all', 'core', 'postv', 'chatting'] as const).map((eng) => {
                const active = engineFilter === eng;
                return (
                  <button
                    key={eng}
                    type="button"
                    role="tab"
                    aria-selected={active}
                    onClick={() => setEngineFilter(eng)}
                    className={`rounded-inner px-3 py-1.5 text-tiny font-bold transition-colors ${
                      active
                        ? 'bg-[#D9232E] text-white'
                        : 'text-muted hover:bg-soft hover:text-text'
                    }`}
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
                <Skeleton key={i} height={280} className="!rounded-card" />
              ))}
            </div>
          ) : filteredRenders.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-line bg-card p-12 text-center text-small text-muted">
              Chưa có video nào được xuất trong mục này.
            </div>
          ) : (
            <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
              {filteredRenders.map((item) => (
                <li
                  key={item.id}
                  className="flex flex-col overflow-hidden rounded-2xl border border-white/10 bg-surface-dark text-on-dark transition duration-150 hover:-translate-y-0.5 hover:border-[#FACC15]/60"
                >
                  <button
                    type="button"
                    onClick={() => setPreviewRender(item)}
                    className="group relative aspect-[9/16] w-full overflow-hidden bg-[#0B0D12] text-left"
                    aria-label={`Xem video: ${item.title}`}
                  >
                    <video
                      src={item.video_url}
                      poster={item.cover_url ?? undefined}
                      preload="metadata"
                      muted
                      playsInline
                      className="h-full w-full object-cover opacity-90 transition-opacity group-hover:opacity-100"
                    />
                    <span
                      className={`absolute top-2.5 left-2.5 rounded-pill border px-2.5 py-0.5 text-tiny font-extrabold uppercase ${ENGINE_BADGE_STYLE[item.engine]}`}
                    >
                      {ENGINE_LABELS[item.engine]}
                    </span>
                    {item.duration_sec > 0 && (
                      <span className="num absolute right-2.5 bottom-2.5 rounded bg-black/80 px-2 py-0.5 text-tiny font-bold text-white">
                        {formatDuration(item.duration_sec)}
                      </span>
                    )}
                  </button>
                  <div className="flex flex-1 flex-col justify-between gap-3 p-3.5">
                    <div>
                      <p className="line-clamp-2 text-small font-bold text-on-dark">{item.title}</p>
                      <p className="num mt-1 text-tiny text-muted-on-dark">
                        {item.size_mb} MB · {item.created_at ? formatDate(item.created_at) : ''}
                      </p>
                    </div>
                    <div className="flex flex-wrap items-center gap-1.5">
                      <Button
                        size="sm"
                        tone="brand"
                        onClick={() => setPreviewRender(item)}
                        className="flex-1"
                      >
                        Xem video
                      </Button>
                      <a
                        href={item.video_url}
                        download={`${item.slug || 'video'}.mp4`}
                        className="flex h-9 w-9 items-center justify-center rounded-lg bg-white/10 text-white transition hover:bg-[#FACC15] hover:text-[#0B0D12]"
                        title="Tải .mp4"
                        aria-label={`Tải .mp4: ${item.title}`}
                      >
                        <DownloadIcon size={15} />
                      </a>
                      {item.publish_text && (
                        <button
                          type="button"
                          onClick={() => void handleCopyPublish(item.publish_text)}
                          className="rounded-lg bg-white/10 px-2.5 py-1.5 text-tiny font-bold text-[#FACC15] transition hover:bg-[#FACC15] hover:text-[#0B0D12]"
                        >
                          Copy
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={() => removeRender.mutate(item)}
                        disabled={removeRender.isPending}
                        aria-label={`Xóa: ${item.title}`}
                        title="Xóa"
                        className="flex h-9 w-9 items-center justify-center rounded-lg bg-white/10 text-[#EF4444] transition hover:bg-[#D9232E] hover:text-white"
                      >
                        <TrashIcon size={15} />
                      </button>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      ) : assetQuery.isPending ? (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} height={220} className="!rounded-card" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-line bg-card p-12 text-center text-small text-muted">
          {T.empty}
        </div>
      ) : activeTab === 'music' ? (
        /* Tab Nhạc nền: Dạng danh sách gọn đẹp */
        <ul className="divide-y divide-white/10 overflow-hidden rounded-2xl border border-white/10 bg-surface-dark text-on-dark">
          {items.map((item) => {
            const isPlaying = playingAudioUrl === item.url;
            return (
              <li
                key={`${item.source ?? 'assets'}:${item.name}`}
                className="flex flex-wrap items-center justify-between gap-4 px-5 py-3.5 transition hover:bg-white/[0.03]"
              >
                <div className="flex min-w-0 flex-1 items-center gap-3.5">
                  <button
                    type="button"
                    onClick={() => togglePlayAudio(item.url)}
                    aria-label={`${isPlaying ? 'Dừng' : 'Nghe thử'}: ${item.title || item.name}`}
                    className={cx(
                      'flex h-10 w-10 shrink-0 items-center justify-center rounded-full transition',
                      isPlaying
                        ? 'bg-[#FACC15] text-[#0B0D12]'
                        : 'bg-[#D9232E] text-white hover:bg-[#B91C1C]',
                    )}
                  >
                    <PlayIcon size={16} />
                  </button>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-small font-bold text-on-dark">
                      {item.title && item.title !== item.name ? item.title : item.name}
                    </p>
                    <div className="mt-0.5 flex flex-wrap items-center gap-2 text-tiny text-muted-on-dark">
                      {item.artist && <span>{item.artist}</span>}
                      <span>{formatBytes(item.size)}</span>
                      {item.duration && item.duration > 0 ? (
                        <span className="num">{formatDuration(item.duration)}</span>
                      ) : null}
                      {item.moods?.slice(0, 3).map((m) => (
                        <span
                          key={m}
                          className="rounded-pill bg-white/10 px-2 py-0.5 text-[11px] font-semibold text-[#FACC15]"
                        >
                          {m}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <audio
                    src={item.url}
                    controls
                    preload="none"
                    className="hidden h-8 w-48 sm:block"
                  />
                  <a
                    href={item.url}
                    download={item.name}
                    aria-label={`${T.download}: ${item.name}`}
                    title={T.download}
                    className="flex h-9 w-9 items-center justify-center rounded-lg bg-white/10 text-white transition hover:bg-[#FACC15] hover:text-[#0B0D12]"
                  >
                    <DownloadIcon size={15} />
                  </a>
                  {!item.readonly && (
                    <button
                      type="button"
                      aria-label={`${T.delete}: ${item.name}`}
                      title={T.delete}
                      disabled={removeAsset.isPending}
                      onClick={() => removeAsset.mutate(item)}
                      className="flex h-9 w-9 items-center justify-center rounded-lg bg-white/10 text-[#EF4444] transition hover:bg-[#D9232E] hover:text-white"
                    >
                      <TrashIcon size={15} />
                    </button>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      ) : (
        /* Grid View trực quan cho Video nền, Meme, Sticker, Logo Watermark */
        <ul className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
          {items.map((item) => (
            <li
              key={`${item.source ?? 'assets'}:${item.name}`}
              className="group flex flex-col overflow-hidden rounded-2xl border border-white/10 bg-surface-dark text-on-dark transition duration-150 hover:-translate-y-0.5 hover:border-[#FACC15]/60"
            >
              <div className="relative aspect-square w-full overflow-hidden bg-[#0B0D12]">
                {item.kind === 'image' ? (
                  <img
                    src={item.url}
                    alt={item.name}
                    loading="lazy"
                    className="h-full w-full object-contain p-3 transition duration-200 group-hover:scale-105"
                  />
                ) : item.kind === 'video' ? (
                  <video
                    src={item.url}
                    poster={item.thumb_url ?? undefined}
                    muted
                    loop
                    playsInline
                    preload="metadata"
                    onMouseEnter={(e) => {
                      void e.currentTarget.play().catch(() => {});
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.pause();
                      e.currentTarget.currentTime = 0;
                    }}
                    className="h-full w-full object-cover"
                  />
                ) : (
                  <div className="flex h-full items-center justify-center p-3 text-tiny text-muted-on-dark">
                    {item.name}
                  </div>
                )}
              </div>

              <div className="flex flex-1 flex-col gap-2 p-3.5">
                <p
                  className="truncate text-small font-bold text-on-dark"
                  title={item.title || item.name}
                >
                  {item.title && item.title !== item.name ? item.title : item.name}
                </p>
                <p className="text-tiny text-muted-on-dark">
                  {formatBytes(item.size)}
                  {item.duration && item.duration > 0 ? ` · ${formatDuration(item.duration)}` : ''}
                </p>

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

                  {!item.readonly && (
                    <button
                      type="button"
                      aria-label={`${T.delete}: ${item.name}`}
                      title={T.delete}
                      disabled={removeAsset.isPending}
                      onClick={() => removeAsset.mutate(item)}
                      className="flex h-8 w-8 items-center justify-center rounded-lg bg-white/10 text-[#EF4444] transition hover:bg-[#D9232E] hover:text-white"
                    >
                      <TrashIcon size={14} />
                    </button>
                  )}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}

      {/* Dialog xem trước tệp nguyên liệu */}
      <Dialog
        open={previewItem !== null}
        onClose={() => setPreviewItem(null)}
        title={previewItem?.title || previewItem?.name || ''}
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

      {/* Dialog xem trước Video đã xuất (9:16 + publish.txt) */}
      <Dialog
        open={previewRender !== null}
        onClose={() => setPreviewRender(null)}
        title={previewRender?.title ?? 'Video đã xuất'}
        className="!max-w-[760px]"
      >
        {previewRender && (
          <div className="grid grid-cols-1 gap-6 md:grid-cols-[240px_1fr]">
            <div className="mx-auto aspect-[9/16] w-full max-w-[240px] overflow-hidden rounded-inner border border-line bg-black">
              <video
                src={previewRender.video_url}
                controls
                autoPlay
                playsInline
                className="h-full w-full object-contain"
              />
            </div>
            <div className="flex flex-col justify-between gap-4">
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-small font-bold">Nội dung đăng bài (publish.txt)</span>
                  {previewRender.publish_text && (
                    <Button
                      size="sm"
                      tone="accent"
                      onClick={() => void handleCopyPublish(previewRender.publish_text)}
                    >
                      Sao chép publish.txt
                    </Button>
                  )}
                </div>
                <pre className="max-h-56 overflow-y-auto rounded-inner border border-line bg-soft p-3 font-sans text-small whitespace-pre-wrap">
                  {previewRender.publish_text || 'Chưa có nội dung publish.txt đính kèm.'}
                </pre>
              </div>
              <div className="flex flex-wrap items-center justify-between gap-2 border-t border-line pt-4">
                <a
                  href={previewRender.video_url}
                  download={`${previewRender.slug || 'video'}.mp4`}
                  className="ui-btn ui-btn-brand ui-btn-sm"
                >
                  Tải .mp4
                </a>
                <Button size="sm" tone="danger" onClick={() => removeRender.mutate(previewRender)}>
                  Xóa video
                </Button>
              </div>
            </div>
          </div>
        )}
      </Dialog>
    </main>
  );
}
