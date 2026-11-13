import { useEffect, useState } from 'react';
import type { KanbanRenderItem } from '../components/KanbanBoard';

type SafeZonePlatform = 'none' | 'tiktok' | 'shorts' | 'reels';

export function EditorPage() {
  const [renders, setRenders] = useState<KanbanRenderItem[]>([]);
  const [selectedId, setSelectedId] = useState<string>('');
  const [safeZone, setSafeZone] = useState<SafeZonePlatform>('tiktok');
  const [trimStart, setTrimStart] = useState(0);
  const [trimEnd, setTrimEnd] = useState<string>('');
  const [removeSilence, setRemoveSilence] = useState(false);
  const [volume, setVolume] = useState(1.0);
  const [busy, setBusy] = useState(false);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);

  useEffect(() => {
    fetch('/api/kanban/renders')
      .then((r) => (r.ok ? r.json() : { items: [] }))
      .then((d) => {
        const list = d.items ?? [];
        setRenders(list);
        if (list.length > 0) setSelectedId(list[0].id);
      })
      .catch(() => {});
  }, []);

  const selected = renders.find((r) => r.id === selectedId);

  const handleProcess = async () => {
    if (!selectedId) return;
    setBusy(true);
    setStatusMsg(null);
    try {
      const res = await fetch('/api/editor/process', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          render_id: selectedId,
          trim_start: Number(trimStart),
          trim_end: trimEnd ? Number(trimEnd) : null,
          remove_silence: removeSilence,
          volume: Number(volume),
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setStatusMsg(`Lỗi: ${data.detail ?? 'Không xử lý được video'}`);
      } else {
        setStatusMsg(`Đã xuất bản chỉnh sửa: ${data.item?.title ?? 'final.mp4'}`);
      }
    } catch {
      setStatusMsg('Không thể kết nối FFmpeg Editor backend.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="mx-auto max-w-6xl space-y-6 p-6">
      <header className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-[#F59E0B]/40 bg-white/[0.03] p-5 backdrop-blur-md">
        <div>
          <span className="inline-block rounded-full border border-[#F59E0B]/50 bg-[#F59E0B]/15 px-3 py-0.5 text-xs font-medium text-amber-200">
            Video Editor (OpenCut Style)
          </span>
          <h1 className="mt-2 text-2xl font-bold text-white">Biên tập hậu kỳ 9:16</h1>
        </div>
        <div className="flex items-center gap-2">
          {(['none', 'tiktok', 'shorts', 'reels'] as SafeZonePlatform[]).map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => setSafeZone(p)}
              className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition ${
                safeZone === p
                  ? 'border-[#F59E0B] bg-[#F59E0B]/20 text-amber-200'
                  : 'border-white/10 bg-white/5 text-slate-300 hover:border-white/25'
              }`}
            >
              {p === 'none'
                ? 'Tắt Safe-Zone'
                : p === 'tiktok'
                  ? 'TikTok'
                  : p === 'shorts'
                    ? 'YouTube Shorts'
                    : 'Facebook Reels'}
            </button>
          ))}
        </div>
      </header>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[320px_1fr]">
        <div className="flex flex-col items-center rounded-2xl border border-white/10 bg-white/[0.03] p-4 backdrop-blur-md">
          <div className="relative aspect-[9/16] w-full max-w-[270px] overflow-hidden rounded-xl border border-white/15 bg-black">
            {selected ? (
              <video
                key={selected.file_path}
                src={`/api/files/raw?path=${encodeURIComponent(selected.file_path)}`}
                controls
                className="h-full w-full object-cover"
              />
            ) : (
              <div className="flex h-full items-center justify-center text-xs text-slate-500">
                Chọn video từ kho renders
              </div>
            )}

            {safeZone !== 'none' && (
              <div className="pointer-events-none absolute inset-0 border-2 border-dashed border-amber-400/70">
                <div className="absolute inset-x-0 top-0 h-[12%] bg-amber-500/15 text-center text-[10px] text-amber-200">
                  Vùng tránh UI trên ({safeZone.toUpperCase()})
                </div>
                <div className="absolute inset-x-0 bottom-0 h-[20%] bg-amber-500/15 text-center text-[10px] text-amber-200">
                  Vùng tránh mô tả / nút tương tác
                </div>
              </div>
            )}
          </div>
        </div>

        <div className="space-y-4 rounded-2xl border border-white/10 bg-white/[0.03] p-6 backdrop-blur-md">
          <label className="block space-y-1.5 text-sm">
            <span className="text-slate-300">Chọn video từ assets/renders/</span>
            <select
              value={selectedId}
              onChange={(e) => setSelectedId(e.target.value)}
              className="w-full rounded-xl border border-white/10 bg-[#090d16] px-3 py-2 text-white outline-none focus:border-[#F59E0B]"
            >
              {renders.map((r) => (
                <option key={r.id} value={r.id}>
                  [{r.engine}] {r.title} ({r.size_mb.toFixed(1)} MB)
                </option>
              ))}
            </select>
          </label>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <label className="block space-y-1.5 text-sm">
              <span className="text-slate-300">Cắt từ (giây)</span>
              <input
                type="number"
                min={0}
                step={0.1}
                value={trimStart}
                onChange={(e) => setTrimStart(Number(e.target.value))}
                className="w-full rounded-xl border border-white/10 bg-[#090d16] px-3 py-2 text-white"
              />
            </label>
            <label className="block space-y-1.5 text-sm">
              <span className="text-slate-300">Đến (giây, bỏ trống = hết)</span>
              <input
                type="number"
                min={0}
                step={0.1}
                value={trimEnd}
                onChange={(e) => setTrimEnd(e.target.value)}
                className="w-full rounded-xl border border-white/10 bg-[#090d16] px-3 py-2 text-white"
              />
            </label>
            <label className="block space-y-1.5 text-sm">
              <span className="text-slate-300">Âm lượng ({volume.toFixed(1)}x)</span>
              <input
                type="range"
                min={0}
                max={2}
                step={0.1}
                value={volume}
                onChange={(e) => setVolume(Number(e.target.value))}
                className="w-full accent-[#F59E0B]"
              />
            </label>
          </div>

          <label className="flex items-center gap-2 text-sm text-slate-200">
            <input
              type="checkbox"
              checked={removeSilence}
              onChange={(e) => setRemoveSilence(e.target.checked)}
              className="h-4 w-4 accent-[#F59E0B]"
            />
            Tự động xoá khoảng lặng (&gt; 0.35s)
          </label>

          <div className="flex items-center gap-4 pt-2">
            <button
              type="button"
              disabled={busy || !selectedId}
              onClick={handleProcess}
              className="rounded-xl bg-[#F59E0B] px-5 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-amber-400 disabled:opacity-50"
            >
              {busy ? 'Đang xử lý FFmpeg...' : 'Xuất bản đã chỉnh sửa'}
            </button>
            {statusMsg && <p className="text-sm text-slate-200">{statusMsg}</p>}
          </div>
        </div>
      </div>
    </main>
  );
}
