import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useMemo, useRef, useState } from 'react';
import { api } from '../api/endpoints';
import type {
  AssetHubCategory,
  AssetHubItem,
  PuppetSlotKey,
  UnifiedRenderItem,
} from '../api/types';
import { ErrorNote } from '../components/ErrorNote';
import { RenderPlayerModal } from '../components/home/RenderPlayerModal';
import {
  CopyIcon,
  DownloadIcon,
  FolderIcon,
  PlayIcon,
  PlusIcon,
  SearchIcon,
  SparklesIcon,
  TrashIcon,
} from '../components/icons';
import { AudioTrackRow } from '../components/library/AudioTrackRow';
import { GameplayCard } from '../components/library/GameplayCard';
import { OnlineAssetDrawer } from '../components/library/OnlineAssetDrawer';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { Dialog } from '../components/ui/Dialog';
import { Skeleton } from '../components/ui/Skeleton';
import { StudioSelect } from '../components/ui/StudioSelect';
import { cx } from '../components/ui/cx';
import { releaseVideoElementLocks } from '../utils/media';
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
  {
    id: 'stickman',
    emoji: '🏃',
    label: 'Nhân vật Stickman',
    cta: 'Thêm nhân vật / Video Pose',
  },
  { id: 'watermarks', emoji: '🏷️', label: 'Logo Watermark', cta: 'Tải lên Watermark' },
];

const ENGINE_LABELS: Record<'all' | 'core' | 'postv' | 'chatting' | 'stickv', string> = {
  all: 'Tất cả',
  core: 'HBT Core',
  postv: 'PostV',
  chatting: 'Chatting',
  stickv: 'StickV',
};

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

const MEME_TAG_FILTERS = [
  { id: 'all', label: 'Tất cả' },
  { id: 'hai_huoc', label: 'Hài hước' },
  { id: 'bat_ngo', label: 'Bất ngờ / Sốc' },
  { id: 'ca_khia', label: 'Cà khịa' },
  { id: 'that_vong', label: 'Thất vọng' },
  { id: 'meo', label: 'Mèo' },
  { id: 'drama', label: 'Drama' },
] as const;

const PUPPET_SLOT_META: readonly { key: PuppetSlotKey; label: string; hint: string }[] = [
  { key: 'base_character', label: 'Thân gốc (A-Pose)', hint: 'Đầu tròn trắng không mặt' },
  { key: 'eyes_neutral', label: 'Mắt bình thường', hint: 'Mặc định / giải thích' },
  { key: 'eyes_happy', label: 'Mắt cười (^_^)', hint: 'Vui vẻ / ăn mừng' },
  { key: 'eyes_shock', label: 'Mắt sốc', hint: 'Bất ngờ / hoảng hốt' },
  { key: 'eyes_angry', label: 'Mắt giận / nhíu mày', hint: 'Nghiêm túc / cảnh báo' },
  { key: 'mouth_closed', label: 'Miệng khép / mỉm', hint: 'Khi ngắt hơi / im lặng' },
  { key: 'mouth_open', label: 'Miệng mở nói', hint: 'Co giãn theo giọng nói' },
];

export function AssetHubPage() {
  const [activeTab, setActiveTab] = useState<LibraryTab>('renders');
  const [previewItem, setPreviewItem] = useState<AssetHubItem | null>(null);
  const [previewRender, setPreviewRender] = useState<UnifiedRenderItem | null>(null);
  const [engineFilter, setEngineFilter] = useState<
    'all' | 'core' | 'postv' | 'chatting' | 'stickv'
  >('all');
  const [memeSearch, setMemeSearch] = useState('');
  const [memeTagFilter, setMemeTagFilter] = useState<string>('all');
  const [onlineOpen, setOnlineOpen] = useState(false);
  const [playingAudioUrl, setPlayingAudioUrl] = useState<string | null>(null);
  const [hoveredStickman, setHoveredStickman] = useState<string | null>(null);
  const [stickmanAnimGroup, setStickmanAnimGroup] = useState<'pose' | 'oneshot' | 'loop'>('pose');
  const [stickmanFilter, setStickmanFilter] = useState<'all' | 'pose' | 'oneshot' | 'loop'>('all');
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
  const stickmanQuery = useQuery({
    queryKey: ['asset-hub', 'stickman'],
    queryFn: () => api.listAssetHub('stickman'),
  });
  const puppetQuery = useQuery({
    queryKey: ['asset-hub', 'stickman-puppet'],
    queryFn: () => api.getStickmanPuppetStatus(),
    enabled: activeTab === 'stickman',
    retry: false,
  });
  const uploadPuppetMut = useMutation({
    mutationFn: ({ slot, file }: { slot: PuppetSlotKey; file: File }) =>
      api.uploadStickmanPuppetSlot(slot, file),
    onSuccess: (res) => {
      void queryClient.invalidateQueries({ queryKey: ['asset-hub', 'stickman-puppet'] });
      void queryClient.invalidateQueries({ queryKey: ['asset-hub', 'stickman'] });
      toast.info(
        res.segmented
          ? `Đã nạp "${res.slot}" & tự động tách khớp vai/cổ!`
          : `Đã nạp linh kiện "${res.slot}"!`,
      );
    },
    onError: (e) => toast.error(e),
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
    stickman: stickmanQuery,
    watermarks: watermarkQuery,
  } as const;

  const activeAssetQuery = !isRendersTab ? activeQueryMap[activeTab] : null;

  const tabCounts: Record<LibraryTab, number> = {
    renders: rendersQuery.data?.items.length ?? 0,
    music: musicQuery.data?.items.length ?? 0,
    backgrounds: bgQuery.data?.items.length ?? 0,
    memes: memeQuery.data?.items.length ?? 0,
    stickers: stickerQuery.data?.items.length ?? 0,
    stickman: stickmanQuery.data?.items.length ?? 0,
    watermarks: watermarkQuery.data?.items.length ?? 0,
  };

  const upload = useMutation({
    mutationFn: async (files: File[]) => {
      if (isRendersTab) return files;
      for (const f of files) {
        await api.uploadAssetHub(
          activeTab as AssetHubCategory,
          f,
          activeTab === 'stickman' ? stickmanAnimGroup : undefined,
        );
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
    mutationFn: (item: UnifiedRenderItem) => {
      if (previewRender?.id === item.id) setPreviewRender(null);
      releaseVideoElementLocks(item.video_url);
      return api.deleteUnifiedRender(item.id);
    },
    onSuccess: (_res, item) => {
      queryClient.setQueryData<{ items: UnifiedRenderItem[] }>(['unified-renders'], (old) =>
        old ? { items: old.items.filter((x) => x.id !== item.id) } : old,
      );
      void queryClient.invalidateQueries({ queryKey: ['unified-renders'] });
      toast.info(`Đã xóa video "${item.title}"`);
      if (previewRender?.id === item.id) setPreviewRender(null);
    },
    onError: (e) => toast.error(e),
  });

  const autoTagMut = useMutation({
    mutationFn: () => api.autoTagMemes(),
    onSuccess: (res) => {
      void queryClient.invalidateQueries({ queryKey: ['asset-hub', 'memes'] });
      toast.info(`Đã tự gắn tag cho ${res.updated}/${res.total} meme!`);
    },
    onError: (e) => toast.error(e),
  });

  const removeStickmanBgMut = useMutation({
    mutationFn: (item: AssetHubItem) => api.removeStickmanBg(item.name, item.source),
    onSuccess: (res) => {
      void queryClient.invalidateQueries({ queryKey: ['asset-hub', 'stickman'] });
      toast.info(
        res.removed
          ? `Đã tách nền trắng cho ${res.item.name}`
          : `${res.item.name} đã trong suốt sẵn`,
      );
    },
    onError: (e) => toast.error(e),
  });

  const setDefaultStickmanMut = useMutation({
    mutationFn: (item: AssetHubItem) => api.setDefaultStickman(item.name),
    onSuccess: (_res, item) => {
      void queryClient.invalidateQueries({ queryKey: ['asset-hub', 'stickman'] });
      toast.info(`Đã đặt "${item.name}" làm nhân vật mặc định cho StickV`);
    },
    onError: (e) => toast.error(e),
  });

  const items = useMemo(() => activeAssetQuery?.data?.items ?? [], [activeAssetQuery?.data?.items]);
  const filteredMemeItems = useMemo(() => {
    if (activeTab !== 'memes') return items;
    const q = memeSearch.trim().toLowerCase();
    return items.filter((it) => {
      if (memeTagFilter !== 'all') {
        const tags = (it.tags ?? []).map((t) => t.toLowerCase());
        if (!tags.includes(memeTagFilter)) return false;
      }
      if (!q) return true;
      const hay =
        `${it.title ?? ''} ${it.name} ${it.topic ?? ''} ${(it.tags ?? []).join(' ')}`.toLowerCase();
      return hay.includes(q);
    });
  }, [activeTab, items, memeSearch, memeTagFilter]);
  const supportsOnline = activeTab === 'music' || activeTab === 'memes' || activeTab === 'stickers';
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
    <main className="w-full max-w-full space-y-6 px-6 py-7 lg:px-8">
      <audio ref={audioRef} onEnded={() => setPlayingAudioUrl(null)} className="hidden" />

      {/* Header Visual Asset Hub — Light/Dark Adaptive */}
      <header className="flex flex-wrap items-center justify-between gap-4 rounded-card border border-border-subtle bg-surface-card p-6 shadow-card">
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
          <div className="flex flex-wrap items-center gap-2.5">
            {activeTab === 'stickman' && (
              <StudioSelect
                aria-label="Loại tài nguyên Stickman khi tải lên"
                autoWidth
                value={stickmanAnimGroup}
                onChange={(val) => setStickmanAnimGroup(val as 'pose' | 'oneshot' | 'loop')}
                options={[
                  { value: 'pose', label: 'Ảnh Pose tĩnh' },
                  { value: 'oneshot', label: 'Animation Phản ứng (One-shot)' },
                  { value: 'loop', label: 'Animation Lặp (Loop)' },
                ]}
                className="min-w-[210px]"
              />
            )}
            {supportsOnline && (
              <Button tone="postv" onClick={() => setOnlineOpen(true)}>
                🌐 Tìm &amp; Tải Online
              </Button>
            )}
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
              {(['all', 'core', 'postv', 'chatting', 'stickv'] as const).map((eng) => {
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
                        href={`${item.video_url}${item.video_url.includes('?') ? '&' : '?'}download=1`}
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
                <Card
                  key={`${item.source}-${item.name}`}
                  as="li"
                  padded={false}
                  className="overflow-hidden"
                >
                  <div className="flex aspect-square items-center justify-center bg-soft p-4">
                    <img
                      src={item.url}
                      alt={item.name}
                      className="max-h-full max-w-full object-contain"
                    />
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
      ) : activeTab === 'memes' ? (
        /* 5a. Tab Meme với tìm kiếm tức thì, chip Tag & Tự gắn tag AI */
        <section aria-label="Kho Meme theo tag và chủ đề" className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-card border border-line bg-card p-4 shadow-card">
            <div className="relative min-w-[240px] flex-1">
              <SearchIcon
                size={16}
                className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-muted"
              />
              <input
                type="search"
                value={memeSearch}
                onChange={(e) => setMemeSearch(e.target.value)}
                placeholder="Tìm meme theo tên, tag hoặc chủ đề..."
                aria-label="Tìm meme theo tên, tag hoặc chủ đề"
                className="ui-input !pl-10 text-small"
              />
            </div>
            <Button
              tone="magic"
              size="sm"
              busy={autoTagMut.isPending}
              icon={<SparklesIcon size={15} />}
              onClick={() => autoTagMut.mutate()}
            >
              ✨ Tự gắn tag AI
            </Button>
          </div>

          <div className="flex flex-wrap items-center gap-1.5">
            {MEME_TAG_FILTERS.map((tg) => {
              const active = memeTagFilter === tg.id;
              return (
                <button
                  key={tg.id}
                  type="button"
                  aria-pressed={active}
                  onClick={() => setMemeTagFilter(tg.id)}
                  className={`ui-chip ui-chip-sm ${active ? '!bg-primary !text-on-primary' : ''}`}
                >
                  {tg.label}
                </button>
              );
            })}
          </div>

          {filteredMemeItems.length === 0 ? (
            <Card className="py-12 text-center">
              <p className="text-body font-bold text-text">{T.empty}</p>
            </Card>
          ) : (
            <ul className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
              {filteredMemeItems.map((item) => (
                <Card
                  key={`${item.source}-${item.name}`}
                  as="li"
                  padded={false}
                  className="group flex flex-col overflow-hidden transition-all duration-180 hover:-translate-y-0.5 hover:shadow-card-hover"
                >
                  <button
                    type="button"
                    onClick={() => setPreviewItem(item)}
                    className="relative flex aspect-square w-full items-center justify-center overflow-hidden bg-soft"
                    aria-label={`Xem ${item.name}`}
                  >
                    {item.kind === 'video' ? (
                      <video
                        src={item.url}
                        muted
                        loop
                        playsInline
                        preload="metadata"
                        onMouseEnter={(e) => void e.currentTarget.play().catch(() => {})}
                        onMouseLeave={(e) => e.currentTarget.pause()}
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
                  <div className="flex flex-1 flex-col justify-between gap-2 p-3">
                    <div>
                      <p className="truncate text-tiny font-bold text-text">
                        {item.title || item.name}
                      </p>
                      {item.topic && (
                        <p className="mt-0.5 line-clamp-2 text-[11px] text-muted">{item.topic}</p>
                      )}
                      {item.tags && item.tags.length > 0 && (
                        <div className="mt-1.5 flex flex-wrap gap-1">
                          {item.tags.slice(0, 3).map((tg) => (
                            <span
                              key={tg}
                              className="rounded-pill bg-soft px-2 py-0.5 text-[10px] font-bold text-text-2"
                            >
                              #{tg}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                    <div className="flex items-center justify-between pt-1">
                      <span className="num text-[11px] text-muted">{formatBytes(item.size)}</span>
                      <button
                        type="button"
                        onClick={() => removeAsset.mutate(item)}
                        aria-label={`Xóa ${item.name}`}
                        className="ui-icon-btn ui-icon-btn-sm text-danger hover:bg-danger-soft"
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
      ) : items.length === 0 ? (
        <Card className="py-12 text-center">
          <p className="text-body font-bold text-text">{T.empty}</p>
        </Card>
      ) : (
        /* 5b. Tab Sticker / Stickman */
        <div className="space-y-4">
          {activeTab === 'stickman' && (
            <Card className="space-y-3 border-engine-stickv/25 bg-soft/60">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h2 className="text-body font-extrabold text-text">
                    Bộ Linh Kiện Puppet 2D (7 mảnh)
                  </h2>
                  <p className="text-tiny text-muted">
                    Tự động tách nền trắng, cắt khớp A-Pose &amp; nhép miệng 30fps theo giọng
                    VieNeu.
                  </p>
                </div>
                {puppetQuery.data && (
                  <Badge tone={puppetQuery.data.ready ? 'ok' : 'yel'}>
                    {puppetQuery.data.ready
                      ? `Sẵn sàng diễn hoạt tự động (${puppetQuery.data.present_count}/${puppetQuery.data.total} mảnh)`
                      : `Chưa đủ bộ tối thiểu (${puppetQuery.data.present_count}/${puppetQuery.data.total} mảnh)`}
                  </Badge>
                )}
              </div>
              <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4 lg:grid-cols-7">
                {PUPPET_SLOT_META.map((slotMeta) => {
                  const info = puppetQuery.data?.slots?.[slotMeta.key];
                  return (
                    <label
                      key={slotMeta.key}
                      className={cx(
                        'flex cursor-pointer flex-col items-center justify-between gap-1.5 rounded-inner border p-2 text-center transition-colors hover:border-primary',
                        info?.found
                          ? 'border-emerald-500/40 bg-card'
                          : 'border-dashed border-line bg-card/60',
                      )}
                      title={slotMeta.hint}
                    >
                      <input
                        type="file"
                        accept="image/*"
                        className="hidden"
                        onChange={(e) => {
                          const f = e.target.files?.[0];
                          if (f) {
                            uploadPuppetMut.mutate({ slot: slotMeta.key, file: f });
                          }
                          e.target.value = '';
                        }}
                      />
                      <div className="flex h-14 w-full items-center justify-center overflow-hidden rounded bg-[radial-gradient(#cbd5e1_1px,transparent_1px)] [background-size:10px_10px]">
                        {info?.found && info.url ? (
                          <img
                            src={info.url}
                            alt={slotMeta.label}
                            className="h-full w-full object-contain p-1"
                          />
                        ) : (
                          <span className="text-[11px] font-bold text-muted">+ Tải lên</span>
                        )}
                      </div>
                      <span className="line-clamp-1 text-[11px] font-bold text-text">
                        {slotMeta.label}
                      </span>
                    </label>
                  );
                })}
              </div>
            </Card>
          )}
          {activeTab === 'stickman' && (
            <div className="flex flex-wrap items-center gap-2">
              {(
                [
                  { id: 'all', label: 'Tất cả' },
                  { id: 'pose', label: 'Pose tĩnh' },
                  { id: 'oneshot', label: 'One-shot' },
                  { id: 'loop', label: 'Loop' },
                ] as const
              ).map((f) => (
                <button
                  key={f.id}
                  type="button"
                  onClick={() => setStickmanFilter(f.id)}
                  className={cx(
                    'rounded-pill px-3 py-1 text-tiny font-bold transition-colors',
                    stickmanFilter === f.id
                      ? 'bg-primary text-on-primary'
                      : 'bg-soft text-muted hover:text-text',
                  )}
                >
                  {f.label}
                </button>
              ))}
            </div>
          )}
          <ul className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
            {(activeTab === 'stickman' && stickmanFilter !== 'all'
              ? items.filter((it) => (it.anim_group || 'pose') === stickmanFilter)
              : items
            ).map((item) => {
              const cardKey = `${item.source}-${item.name}`;
              const isVideo = item.kind === 'video' || item.media_type === 'video';
              const isHovered = hoveredStickman === cardKey;
              const animGroup = item.anim_group;
              return (
                <Card
                  key={cardKey}
                  as="li"
                  padded={false}
                  className="group overflow-hidden transition-all duration-180 hover:-translate-y-0.5 hover:shadow-card-hover"
                  onMouseEnter={() => isVideo && setHoveredStickman(cardKey)}
                  onMouseLeave={() => isVideo && setHoveredStickman(null)}
                >
                  <button
                    type="button"
                    onClick={() => setPreviewItem(item)}
                    className={cx(
                      'relative flex aspect-square w-full items-center justify-center overflow-hidden',
                      activeTab === 'stickman'
                        ? 'bg-[radial-gradient(#cbd5e1_1px,transparent_1px)] [background-size:12px_12px] bg-soft'
                        : 'bg-soft',
                    )}
                    aria-label={`Xem ${item.name}`}
                  >
                    {activeTab === 'stickman' && animGroup === 'oneshot' && (
                      <span className="absolute left-2 top-2 z-10 rounded-pill bg-red-600 px-2 py-0.5 text-[10px] font-extrabold text-white">
                        ONE-SHOT{item.duration_sec ? ` · ${item.duration_sec.toFixed(1)}s` : ''}
                      </span>
                    )}
                    {activeTab === 'stickman' && animGroup === 'loop' && (
                      <span className="absolute left-2 top-2 z-10 rounded-pill bg-amber-400 px-2 py-0.5 text-[10px] font-extrabold text-black">
                        LOOP{item.duration_sec ? ` · ${item.duration_sec.toFixed(1)}s` : ''}
                      </span>
                    )}
                    {isVideo && animGroup !== 'oneshot' && animGroup !== 'loop' && (
                      <span className="absolute left-2 top-2 z-10 rounded-pill bg-black/75 px-2 py-0.5 text-[10px] font-extrabold text-white">
                        VIDEO{item.duration_sec ? ` · ${item.duration_sec.toFixed(1)}s` : ''}
                      </span>
                    )}
                    {isVideo ? (
                      isHovered || !item.thumb_url ? (
                        <video
                          src={item.file_url || item.url}
                          muted
                          loop
                          autoPlay={isHovered}
                          playsInline
                          preload="metadata"
                          className="h-full w-full object-cover"
                        />
                      ) : (
                        <img
                          src={item.thumb_url}
                          alt={item.name}
                          className="h-full w-full object-cover"
                          loading="lazy"
                        />
                      )
                    ) : (
                      <img
                        src={
                          activeTab === 'stickman'
                            ? `${item.url}?t=${encodeURIComponent(item.modified_at)}`
                            : item.url
                        }
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
                    <div className="flex items-center gap-1">
                      {activeTab === 'stickman' && !isVideo && (
                        <>
                          <Button
                            tone="soft"
                            size="sm"
                            busy={removeStickmanBgMut.isPending}
                            onClick={() => removeStickmanBgMut.mutate(item)}
                            aria-label={`Tách nền trắng ${item.name}`}
                            title="Tách nền trắng bên ngoài"
                          >
                            Tách nền trắng
                          </Button>
                          {item.source === 'assets' && item.name !== 'default.png' && (
                            <Button
                              tone="soft"
                              size="sm"
                              busy={setDefaultStickmanMut.isPending}
                              onClick={() => setDefaultStickmanMut.mutate(item)}
                              aria-label={`Đặt mặc định ${item.name}`}
                              title="Dùng làm nhân vật mặc định cho StickV"
                            >
                              Mặc định
                            </Button>
                          )}
                        </>
                      )}
                      <button
                        type="button"
                        onClick={() => removeAsset.mutate(item)}
                        aria-label={`Xóa ${item.name}`}
                        className="ui-icon-btn ui-icon-btn-sm text-danger hover:bg-danger-soft"
                      >
                        <TrashIcon size={14} />
                      </button>
                    </div>
                  </div>
                </Card>
              );
            })}
          </ul>
        </div>
      )}

      {/* Drawer Tìm & Tải Online */}
      {supportsOnline && (
        <OnlineAssetDrawer
          open={onlineOpen}
          category={activeTab as 'music' | 'memes' | 'stickers'}
          onClose={() => setOnlineOpen(false)}
        />
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
            {previewItem.kind === 'video' ? (
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
