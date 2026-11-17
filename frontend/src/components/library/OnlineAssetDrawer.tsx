import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import { api } from '../../api/endpoints';
import type { OnlineGiphyItem, OnlineGreenMemeItem } from '../../api/types';
import { useToast } from '../../hooks/toast';
import { PlayIcon, PlusIcon, SearchIcon, StopIcon } from '../icons';
import { Button } from '../ui/Button';
import { Drawer } from '../ui/Drawer';

interface OnlineAssetDrawerProps {
  open: boolean;
  category: 'music' | 'memes' | 'stickers';
  onClose: () => void;
}

const QUICK_TAGS: Record<'music' | 'sfx' | 'memes' | 'stickers', readonly string[]> = {
  music: ['lofi chill', 'dramatic', 'quirky', 'upbeat'],
  sfx: ['meme', 'vine boom', 'bruh', 'bonk', 'whoosh', 'laugh'],
  memes: ['shocked', 'cat', 'laugh', 'angry'],
  stickers: ['happy', 'shock', 'cry', 'fire'],
};

export function OnlineAssetDrawer({ open, category, onClose }: OnlineAssetDrawerProps) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [query, setQuery] = useState('');
  const [audioKind, setAudioKind] = useState<'music' | 'sfx'>('sfx');
  const [sfxSource, setSfxSource] = useState<'tuna' | 'pixabay'>('tuna');
  const [stickerMode, setStickerMode] = useState<'giphy' | 'sigstick'>('giphy');
  const [sigstickUrl, setSigstickUrl] = useState('');

  const [audioResults, setAudioResults] = useState<
    Array<{
      id: string;
      title: string;
      subtitle: string;
      duration: number;
      preview_url: string;
      download_url: string;
      source: 'tuna' | 'pixabay';
      kind: 'music' | 'sfx';
      artist: string;
      tags: string[];
    }>
  >([]);
  const [greenMemeItems, setGreenMemeItems] = useState<OnlineGreenMemeItem[]>([]);
  const [giphyItems, setGiphyItems] = useState<OnlineGiphyItem[]>([]);
  const [savedIds, setSavedIds] = useState<Record<string, boolean>>({});
  const [missingKey, setMissingKey] = useState(false);
  const [searchErr, setSearchErr] = useState('');

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [playingUrl, setPlayingUrl] = useState<string | null>(null);

  const activeCategory = category === 'music' ? audioKind : category;
  const activeSource =
    activeCategory === 'sfx'
      ? sfxSource
      : activeCategory === 'music'
        ? 'pixabay'
        : activeCategory === 'memes'
          ? 'greenmeme'
          : stickerMode;

  const title =
    category === 'music'
      ? '🌐 Tìm & Tải Nhạc nền / Meme SFX Online'
      : category === 'memes'
        ? '🌐 Tìm & Tải Meme Phông Xanh (GreenScreenMemes)'
        : '🌐 Tìm & Nhập Sticker Động (Giphy & SigStick)';

  const searchMut = useMutation({
    mutationFn: async (overrideQ?: string) => {
      const qVal = (overrideQ ?? query).trim();
      setMissingKey(false);
      setSearchErr('');
      if (category === 'stickers' && stickerMode === 'sigstick') return;

      const res = await api.searchOnlineAssets(activeCategory, qVal, activeSource);
      if (res.missing_key) setMissingKey(true);
      if (res.error) setSearchErr(res.error);

      if (activeCategory === 'music' || activeCategory === 'sfx') {
        const mapped = (res.items ?? []).map((raw) => {
          const isTuna = res.source === 'tuna' || raw.source === 'tuna';
          return {
            id: String(raw.id ?? ''),
            title: String(raw.title ?? 'Âm thanh'),
            subtitle: isTuna ? 'Voicemod Tuna' : String(raw.artist ?? 'Pixabay'),
            duration: Number(raw.duration_sec ?? raw.duration ?? 0),
            preview_url: String(raw.preview_url ?? ''),
            download_url: String(raw.download_url ?? raw.preview_url ?? ''),
            source: (isTuna ? 'tuna' : 'pixabay') as 'tuna' | 'pixabay',
            kind: activeCategory,
            artist: String(raw.artist ?? 'Pixabay Creator'),
            tags: Array.isArray(raw.tags) ? raw.tags.map(String) : [],
          };
        });
        setAudioResults(mapped);
      } else if (activeCategory === 'memes') {
        setGreenMemeItems(res.items as unknown as OnlineGreenMemeItem[]);
      } else {
        setGiphyItems(res.items as unknown as OnlineGiphyItem[]);
      }
    },
    onError: (e) => toast.error(e),
  });

  // Đồng bộ & tự tải kết quả mặc định khi mở hoặc chuyển tab/nguồn
  useEffect(() => {
    if (!open) return;
    setAudioResults([]);
    setGreenMemeItems([]);
    setGiphyItems([]);
    setMissingKey(false);
    setSearchErr('');
    if (category === 'stickers' && stickerMode === 'sigstick') return;
    if (activeCategory === 'sfx' && sfxSource === 'tuna') {
      searchMut.mutate('meme');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, category, audioKind, sfxSource, stickerMode]);

  const importAudioMut = useMutation({
    mutationFn: async (it: (typeof audioResults)[number]) => {
      if (it.source === 'tuna') {
        return api.importTunaSfxOnline({
          item_id: it.id,
          title: it.title,
          preview_url: it.preview_url,
          tags: it.tags,
        });
      }
      return api.importPixabayOnline({
        item_id: it.id,
        title: it.title,
        artist: it.artist,
        download_url: it.download_url,
        kind: it.kind,
        tags: it.tags,
      });
    },
    onSuccess: (_r, it) => {
      setSavedIds((prev) => ({ ...prev, [it.id]: true }));
      void queryClient.invalidateQueries({ queryKey: ['asset-hub', 'music'] });
      toast.info(`Đã tải "${it.title}" vào thư viện!`);
    },
    onError: (e) => toast.error(e),
  });

  const importGreenMeme = useMutation({
    mutationFn: (it: OnlineGreenMemeItem) =>
      api.importGreenMemeOnline({
        meme_id: it.id,
        title: it.title,
        video_url: it.video_url,
        poster_url: it.poster_url,
      }),
    onSuccess: (_r, it) => {
      void queryClient.invalidateQueries({ queryKey: ['asset-hub', 'memes'] });
      toast.info(`Đã lưu meme "${it.title}" kèm tag tự động!`);
    },
    onError: (e) => toast.error(e),
  });

  const importGiphy = useMutation({
    mutationFn: (it: OnlineGiphyItem) =>
      api.importGiphyOnline({
        sticker_id: it.id,
        title: it.title,
        download_url: it.download_url,
      }),
    onSuccess: (_r, it) => {
      void queryClient.invalidateQueries({ queryKey: ['asset-hub', 'stickers'] });
      toast.info(`Đã lưu sticker "${it.title}"!`);
    },
    onError: (e) => toast.error(e),
  });

  const importSigStick = useMutation({
    mutationFn: () => api.importSigStickOnline(sigstickUrl.trim()),
    onSuccess: (res) => {
      void queryClient.invalidateQueries({ queryKey: ['asset-hub', 'stickers'] });
      toast.info(`Đã nhập ${res.count} sticker từ bộ "${res.pack_slug}"!`);
      setSigstickUrl('');
    },
    onError: (e) => toast.error(e),
  });

  const toggleAudio = (url: string) => {
    const el = audioRef.current;
    if (!el) return;
    if (playingUrl === url && !el.paused) {
      el.pause();
      setPlayingUrl(null);
    } else {
      el.src = url;
      void el.play().catch(() => {});
      setPlayingUrl(url);
    }
  };

  return (
    <Drawer open={open} onClose={onClose} title={title}>
      <audio ref={audioRef} onEnded={() => setPlayingUrl(null)} className="hidden" />
      <div className="space-y-4">
        {/* Bộ chọn danh mục & Nguồn API đồng bộ */}
        {category === 'music' && (
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex gap-1.5">
              {(
                [
                  { id: 'sfx', label: 'Hiệu ứng SFX' },
                  { id: 'music', label: 'Nhạc nền (BGM)' },
                ] as const
              ).map((k) => (
                <button
                  key={k.id}
                  type="button"
                  onClick={() => setAudioKind(k.id)}
                  aria-pressed={audioKind === k.id}
                  className={`ui-chip ui-chip-sm ${audioKind === k.id ? '!bg-primary !text-on-primary' : ''}`}
                >
                  {k.label}
                </button>
              ))}
            </div>
            {audioKind === 'sfx' && (
              <div className="flex gap-1.5">
                {(
                  [
                    { id: 'tuna', label: 'Voicemod Tuna' },
                    { id: 'pixabay', label: 'Pixabay' },
                  ] as const
                ).map((s) => (
                  <button
                    key={s.id}
                    type="button"
                    onClick={() => setSfxSource(s.id)}
                    aria-pressed={sfxSource === s.id}
                    className={`ui-chip ui-chip-sm ${sfxSource === s.id ? '!bg-engine-stickv !text-white' : ''}`}
                  >
                    {s.label}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {category === 'stickers' && (
          <div className="flex gap-2 rounded-inner bg-soft p-1">
            <button
              type="button"
              onClick={() => setStickerMode('giphy')}
              className={`flex-1 rounded-input px-3 py-2 text-tiny font-bold transition ${
                stickerMode === 'giphy' ? 'bg-card text-text shadow-sm' : 'text-muted'
              }`}
            >
              Tìm Giphy Stickers
            </button>
            <button
              type="button"
              onClick={() => setStickerMode('sigstick')}
              className={`flex-1 rounded-input px-3 py-2 text-tiny font-bold transition ${
                stickerMode === 'sigstick' ? 'bg-card text-text shadow-sm' : 'text-muted'
              }`}
            >
              Dán link bộ SigStick
            </button>
          </div>
        )}

        {/* Thanh Search Online thống nhất + Nút Tìm kiếm Vàng HBT */}
        {category === 'stickers' && stickerMode === 'sigstick' ? (
          <div className="space-y-3 rounded-inner border border-line bg-soft/60 p-4">
            <label className="block text-small font-bold text-text">
              Link gói Sticker từ SigStick.com
            </label>
            <input
              type="url"
              value={sigstickUrl}
              onChange={(e) => setSigstickUrl(e.target.value)}
              placeholder="https://www.sigstick.com/pack/..."
              className="ui-input text-small"
            />
            <Button
              tone="magic"
              busy={importSigStick.isPending}
              disabled={!sigstickUrl.trim()}
              onClick={() => importSigStick.mutate()}
              className="w-full"
            >
              Nhập cả bộ Sticker
            </Button>
          </div>
        ) : (
          <div className="space-y-2.5">
            <form
              className="flex gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                searchMut.mutate(undefined);
              }}
            >
              <div className="relative flex-1">
                <SearchIcon
                  size={16}
                  className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-muted"
                />
                <input
                  type="search"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder={
                    activeCategory === 'sfx'
                      ? 'Tìm meme SFX: vine boom, bruh, bonk, whoosh...'
                      : activeCategory === 'music'
                        ? 'Tìm nhạc nền: lofi chill, dramatic, pop...'
                        : activeCategory === 'memes'
                          ? 'Tìm meme: shocked, laugh, cat, trump...'
                          : 'Tìm sticker (để trống = Trending)...'
                  }
                  className="ui-input !pl-10 text-small"
                />
              </div>
              <Button type="submit" tone="export" busy={searchMut.isPending}>
                Tìm kiếm
              </Button>
            </form>

            {/* Hàng Chip từ khóa gợi ý nhanh */}
            <div className="flex flex-wrap gap-1.5">
              {QUICK_TAGS[activeCategory].map((tag) => (
                <button
                  key={tag}
                  type="button"
                  onClick={() => {
                    setQuery(tag);
                    searchMut.mutate(tag);
                  }}
                  className="rounded-pill bg-soft px-2.5 py-1 text-[11px] font-bold text-text-2 hover:bg-soft-2"
                >
                  #{tag}
                </button>
              ))}
            </div>
          </div>
        )}

        {missingKey && (
          <div className="rounded-inner border border-amber-400/40 bg-tint-yel p-3 text-small text-on-tint-yel">
            Chưa có API Key cho nguồn này. Hãy vào trang <b>Cài đặt</b> hoặc thêm vào file{' '}
            <code>.env</code>.
          </div>
        )}

        {searchErr && (
          <div className="rounded-inner border border-danger/30 bg-danger-soft p-3 text-small text-danger">
            {searchErr}
          </div>
        )}

        {/* Audio Result Row thống nhất cho Nhạc nền & SFX */}
        {(activeCategory === 'music' || activeCategory === 'sfx') && audioResults.length > 0 && (
          <ul className="space-y-2">
            {audioResults.map((it) => {
              const isSaved = Boolean(savedIds[it.id]);
              return (
                <li
                  key={`${it.source}-${it.id}`}
                  className="flex items-center justify-between gap-2 rounded-inner border border-line bg-card p-3"
                >
                  <button
                    type="button"
                    onClick={() => toggleAudio(it.preview_url)}
                    className="ui-icon-btn ui-icon-btn-sm bg-soft"
                    aria-label={`Nghe thử ${it.title}`}
                  >
                    {playingUrl === it.preview_url ? (
                      <StopIcon size={14} />
                    ) : (
                      <PlayIcon size={14} />
                    )}
                  </button>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5">
                      <p className="truncate text-small font-bold text-text">{it.title}</p>
                      <span className="rounded-pill bg-soft px-2 py-0.5 text-[10px] font-bold text-text-2">
                        {it.source === 'tuna' ? 'Tuna' : 'Pixabay'}
                      </span>
                    </div>
                    <p className="truncate text-tiny text-muted">
                      {it.subtitle} · {it.duration.toFixed(1)}s
                    </p>
                  </div>
                  <Button
                    size="sm"
                    tone={isSaved ? 'soft' : 'export'}
                    busy={importAudioMut.isPending}
                    disabled={isSaved}
                    icon={<PlusIcon size={14} />}
                    onClick={() => importAudioMut.mutate(it)}
                  >
                    {isSaved ? 'Đã lưu' : 'Tải về thư viện'}
                  </Button>
                </li>
              );
            })}
          </ul>
        )}

        {/* Kết quả GreenScreenMemes */}
        {category === 'memes' && greenMemeItems.length > 0 && (
          <ul className="grid grid-cols-2 gap-3">
            {greenMemeItems.map((it) => (
              <li
                key={it.id}
                className="flex flex-col overflow-hidden rounded-inner border border-line bg-card"
              >
                <div className="aspect-video bg-hero">
                  <video
                    src={it.video_url}
                    poster={it.poster_url || undefined}
                    muted
                    loop
                    playsInline
                    onMouseEnter={(e) => void e.currentTarget.play().catch(() => {})}
                    onMouseLeave={(e) => {
                      e.currentTarget.pause();
                      e.currentTarget.currentTime = 0;
                    }}
                    className="h-full w-full object-cover"
                  />
                </div>
                <div className="flex flex-1 flex-col justify-between gap-2 p-2.5">
                  <p className="line-clamp-2 text-tiny font-bold text-text">{it.title}</p>
                  <Button
                    size="sm"
                    tone="export"
                    busy={importGreenMeme.isPending}
                    icon={<PlusIcon size={14} />}
                    onClick={() => importGreenMeme.mutate(it)}
                    className="w-full"
                  >
                    Tải về thư viện
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}

        {/* Kết quả Giphy Stickers */}
        {category === 'stickers' && stickerMode === 'giphy' && giphyItems.length > 0 && (
          <ul className="grid grid-cols-3 gap-2.5">
            {giphyItems.map((it) => (
              <li
                key={it.id}
                className="flex flex-col justify-between gap-2 rounded-inner border border-line bg-card p-2"
              >
                <div className="flex aspect-square items-center justify-center overflow-hidden rounded-lg bg-soft">
                  <img
                    src={it.preview_url}
                    alt={it.title}
                    className="h-full w-full object-contain"
                  />
                </div>
                <Button
                  size="sm"
                  tone="export"
                  busy={importGiphy.isPending}
                  onClick={() => importGiphy.mutate(it)}
                  className="w-full"
                >
                  + Lưu
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Drawer>
  );
}
