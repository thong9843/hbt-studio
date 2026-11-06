import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../../api/endpoints';
import type { MemeEntry } from '../../api/types';
import { vi } from '../../i18n/vi';
import { Button } from '../ui/Button';
import { Dialog } from '../ui/Dialog';
import { Input } from '../ui/Field';

interface Props {
  open: boolean;
  onClose: () => void;
  onSelect: (memeId: string, pos: 'bottom_right' | 'bottom_center' | 'center') => void;
  currentMemeId?: string | null;
  currentPos?: 'bottom_right' | 'bottom_center' | 'center';
}

export function MemePickerModal({
  open,
  onClose,
  onSelect,
  currentMemeId,
  currentPos = 'bottom_right',
}: Props) {
  const t = vi.postv.memes;
  const qc = useQueryClient();
  const [tab, setTab] = useState<'online' | 'library'>('online');
  const [searchQuery, setSearchQuery] = useState('cat');
  const [submittedQuery, setSubmittedQuery] = useState('cat');
  const [pos, setPos] = useState<'bottom_right' | 'bottom_center' | 'center'>(currentPos);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);

  // 1. Danh sách đã tải về
  const libraryQuery = useQuery({
    queryKey: ['memes-library'],
    queryFn: () => api.listMemeLibrary(),
    enabled: open,
  });

  // 2. Tìm kiếm trực tuyến
  const searchQueryHook = useQuery({
    queryKey: ['memes-search', submittedQuery],
    queryFn: () => api.searchMemes(submittedQuery),
    enabled: open && tab === 'online',
    staleTime: 60_000,
  });

  // 3. Tải về và gắn meme
  const downloadMutation = useMutation({
    mutationFn: (meme: MemeEntry) =>
      api.downloadMeme({
        meme_id: meme.id,
        video_url: meme.video_url,
        title: meme.title,
        poster_url: meme.poster_url,
        source: meme.source || meme.video_url,
        license: meme.license || 'chưa rõ',
      }),
    onSuccess: (saved) => {
      qc.invalidateQueries({ queryKey: ['memes-library'] });
      setDownloadingId(null);
      onSelect(saved.id, pos);
      onClose();
    },
    onError: () => {
      setDownloadingId(null);
    },
  });

  const handleSelect = (meme: MemeEntry) => {
    if (meme.downloaded) {
      onSelect(meme.id, pos);
      onClose();
    } else {
      setDownloadingId(meme.id);
      downloadMutation.mutate(meme);
    }
  };

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchQuery.trim()) {
      setSubmittedQuery(searchQuery.trim());
    }
  };

  const items = tab === 'online' ? (searchQueryHook.data ?? []) : (libraryQuery.data ?? []);

  return (
    <Dialog open={open} onClose={onClose} title={t.title} className="max-w-2xl">
      <p className="text-small text-muted mb-4">{t.lead}</p>

      {/* Tabs */}
      <div className="flex items-center gap-2 mb-4 border-b border-line pb-2">
        <button
          type="button"
          onClick={() => setTab('online')}
          className={`px-3 py-1.5 rounded-full text-small font-bold transition-colors ${
            tab === 'online' ? 'bg-brand text-ink' : 'text-muted hover:text-ink'
          }`}
        >
          {t.onlineTab}
        </button>
        <button
          type="button"
          onClick={() => setTab('library')}
          className={`px-3 py-1.5 rounded-full text-small font-bold transition-colors ${
            tab === 'library' ? 'bg-brand text-ink' : 'text-muted hover:text-ink'
          }`}
        >
          {t.libraryTab} ({libraryQuery.data?.length ?? 0})
        </button>
      </div>

      {/* Cấu hình vị trí */}
      <div className="mb-4 flex flex-wrap items-center gap-2 p-2.5 rounded-card bg-soft border border-line">
        <span className="text-small font-semibold text-muted">{t.posLabel}:</span>
        <button
          type="button"
          onClick={() => setPos('bottom_right')}
          className={`px-2.5 py-1 rounded text-small font-semibold ${
            pos === 'bottom_right' ? 'bg-card text-ink shadow-sm' : 'text-muted hover:text-ink'
          }`}
        >
          {t.pos.bottom_right}
        </button>
        <button
          type="button"
          onClick={() => setPos('bottom_center')}
          className={`px-2.5 py-1 rounded text-small font-semibold ${
            pos === 'bottom_center' ? 'bg-card text-ink shadow-sm' : 'text-muted hover:text-ink'
          }`}
        >
          {t.pos.bottom_center}
        </button>
        <button
          type="button"
          onClick={() => setPos('center')}
          className={`px-2.5 py-1 rounded text-small font-semibold ${
            pos === 'center' ? 'bg-card text-ink shadow-sm' : 'text-muted hover:text-ink'
          }`}
        >
          {t.pos.center}
        </button>
      </div>

      {/* Tìm kiếm (Online tab) */}
      {tab === 'online' && (
        <form onSubmit={handleSearch} className="flex gap-2 mb-4">
          <div className="flex-1">
            <Input
              label=""
              placeholder={t.searchPlaceholder}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
          <Button tone="soft" type="submit" busy={searchQueryHook.isFetching}>
            {searchQueryHook.isFetching ? t.searching : t.search}
          </Button>
        </form>
      )}

      {/* Lưới meme */}
      <div className="max-h-96 overflow-y-auto pr-1">
        {items.length === 0 ? (
          <div className="py-8 text-center text-muted text-small">{t.noResults}</div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            {items.map((m) => {
              const isSelected = currentMemeId === m.id;
              const isDownloading = downloadingId === m.id;
              return (
                <div
                  key={m.id}
                  className={`group relative flex flex-col rounded-card overflow-hidden border transition-all ${
                    isSelected ? 'border-brand ring-2 ring-brand' : 'border-line hover:border-muted'
                  }`}
                >
                  <div className="aspect-square bg-black relative flex items-center justify-center overflow-hidden">
                    {m.poster_url ? (
                      <img
                        src={m.poster_url}
                        alt={m.title}
                        className="w-full h-full object-cover group-hover:scale-105 transition-transform"
                        loading="lazy"
                      />
                    ) : (
                      <div className="w-full h-full bg-emerald-950 flex items-center justify-center text-emerald-400 font-bold text-xs p-2 text-center">
                        Green Screen Meme
                      </div>
                    )}
                    {m.duration > 0 && (
                      <span className="absolute bottom-1 right-1 px-1.5 py-0.5 rounded text-[10px] bg-black/75 text-white font-mono">
                        {t.duration(m.duration)}
                      </span>
                    )}
                  </div>

                  <div className="p-2 flex flex-col justify-between flex-1 bg-card">
                    <span className="text-small font-bold line-clamp-1 mb-2" title={m.title}>
                      {m.title}
                    </span>
                    <Button
                      tone={isSelected ? 'brand' : 'ghost'}
                      size="sm"
                      busy={isDownloading}
                      onClick={() => handleSelect(m)}
                    >
                      {isDownloading
                        ? t.downloading
                        : isSelected
                          ? t.useMeme
                          : m.downloaded
                            ? t.useMeme
                            : t.download}
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </Dialog>
  );
}
