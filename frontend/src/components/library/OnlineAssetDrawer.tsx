import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useRef, useState } from 'react';
import { api } from '../../api/endpoints';
import type { OnlineGiphyItem, OnlineGreenMemeItem, OnlinePixabayItem } from '../../api/types';
import { useToast } from '../../hooks/toast';
import { PlayIcon, PlusIcon, SearchIcon, StopIcon } from '../icons';
import { Button } from '../ui/Button';
import { Drawer } from '../ui/Drawer';

interface OnlineAssetDrawerProps {
  open: boolean;
  category: 'music' | 'memes' | 'stickers';
  onClose: () => void;
}

export function OnlineAssetDrawer({ open, category, onClose }: OnlineAssetDrawerProps) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [query, setQuery] = useState('');
  const [pixabayKind, setPixabayKind] = useState<'music' | 'sfx'>('music');
  const [stickerMode, setStickerMode] = useState<'giphy' | 'sigstick'>('giphy');
  const [sigstickUrl, setSigstickUrl] = useState('');

  const [pixabayItems, setPixabayItems] = useState<OnlinePixabayItem[]>([]);
  const [greenMemeItems, setGreenMemeItems] = useState<OnlineGreenMemeItem[]>([]);
  const [giphyItems, setGiphyItems] = useState<OnlineGiphyItem[]>([]);
  const [missingKey, setMissingKey] = useState(false);

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [playingUrl, setPlayingUrl] = useState<string | null>(null);

  const title =
    category === 'music'
      ? '🌐 Tìm & Tải Nhạc nền / SFX (Pixabay)'
      : category === 'memes'
        ? '🌐 Tìm & Tải Meme Phông Xanh (GreenScreenMemes)'
        : '🌐 Tìm & Nhập Sticker Động (Giphy & SigStick)';

  const searchMut = useMutation({
    mutationFn: async () => {
      setMissingKey(false);
      if (category === 'music') {
        const res = await api.searchPixabayOnline(query, pixabayKind);
        setMissingKey(Boolean(res.missing_key));
        setPixabayItems(res.items);
      } else if (category === 'memes') {
        const res = await api.searchGreenMemeOnline(query);
        setGreenMemeItems(res.items);
      } else {
        const res = await api.searchGiphyOnline(query);
        setMissingKey(Boolean(res.missing_key));
        setGiphyItems(res.items);
      }
    },
    onError: (e) => toast.error(e),
  });

  const importPixabay = useMutation({
    mutationFn: (it: OnlinePixabayItem) =>
      api.importPixabayOnline({
        item_id: it.id,
        title: it.title,
        artist: it.artist,
        download_url: it.download_url,
        kind: it.kind,
        tags: it.tags,
      }),
    onSuccess: (_r, it) => {
      void queryClient.invalidateQueries({ queryKey: ['asset-hub', 'music'] });
      toast.info(`Đã lưu "${it.title}" vào thư viện!`);
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

        {category === 'music' && (
          <div className="flex gap-2">
            {(['music', 'sfx'] as const).map((k) => (
              <button
                key={k}
                type="button"
                onClick={() => setPixabayKind(k)}
                aria-pressed={pixabayKind === k}
                className={`ui-chip ui-chip-sm ${pixabayKind === k ? '!bg-primary !text-on-primary' : ''}`}
              >
                {k === 'music' ? 'Nhạc nền (BGM)' : 'Tiếng động (SFX)'}
              </button>
            ))}
          </div>
        )}

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
          <form
            className="flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              searchMut.mutate();
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
                  category === 'music'
                    ? 'Ví dụ: lofi chill, dramatic, pop...'
                    : category === 'memes'
                      ? 'Ví dụ: shocked, laugh, cat, trump...'
                      : 'Tìm sticker (để trống = Trending)...'
                }
                className="ui-input !pl-10 text-small"
              />
            </div>
            <Button type="submit" tone="postv" busy={searchMut.isPending}>
              Tìm
            </Button>
          </form>
        )}

        {missingKey && (
          <div className="rounded-inner border border-amber-400/40 bg-tint-yel p-3 text-small text-on-tint-yel">
            Chưa có API Key cho nguồn này. Hãy vào trang <b>Cài đặt</b> hoặc thêm vào file{' '}
            <code>.env</code>.
          </div>
        )}

        {/* Kết quả Pixabay */}
        {category === 'music' && pixabayItems.length > 0 && (
          <ul className="space-y-2">
            {pixabayItems.map((it) => (
              <li
                key={it.id}
                className="flex items-center justify-between gap-2 rounded-inner border border-line bg-card p-3"
              >
                <button
                  type="button"
                  onClick={() => toggleAudio(it.preview_url)}
                  className="ui-icon-btn ui-icon-btn-sm bg-soft"
                  aria-label={`Nghe thử ${it.title}`}
                >
                  {playingUrl === it.preview_url ? <StopIcon size={14} /> : <PlayIcon size={14} />}
                </button>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-small font-bold text-text">{it.title}</p>
                  <p className="truncate text-tiny text-muted">
                    {it.artist} · {Math.round(it.duration)}s
                  </p>
                </div>
                <Button
                  size="sm"
                  tone="export"
                  busy={importPixabay.isPending}
                  icon={<PlusIcon size={14} />}
                  onClick={() => importPixabay.mutate(it)}
                >
                  Lưu
                </Button>
              </li>
            ))}
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
                <video
                  src={it.video_url}
                  poster={it.poster_url || undefined}
                  muted
                  loop
                  playsInline
                  preload="metadata"
                  onMouseEnter={(e) => void e.currentTarget.play().catch(() => {})}
                  onMouseLeave={(e) => e.currentTarget.pause()}
                  className="aspect-video w-full bg-hero object-cover"
                />
                <div className="flex flex-1 flex-col justify-between gap-2 p-2.5">
                  <p className="line-clamp-2 text-tiny font-bold text-text">{it.title}</p>
                  <Button
                    size="sm"
                    tone="export"
                    busy={importGreenMeme.isPending}
                    icon={<PlusIcon size={13} />}
                    onClick={() => importGreenMeme.mutate(it)}
                    className="w-full"
                  >
                    Lưu về kho
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
                className="flex flex-col items-center justify-between gap-2 rounded-inner border border-line bg-card p-2"
              >
                <img
                  src={it.preview_url}
                  alt={it.title}
                  className="h-20 w-20 object-contain"
                  loading="lazy"
                />
                <Button
                  size="sm"
                  tone="export"
                  busy={importGiphy.isPending}
                  icon={<PlusIcon size={12} />}
                  onClick={() => importGiphy.mutate(it)}
                  className="w-full"
                >
                  Lưu
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Drawer>
  );
}
