import { useState } from 'react';

export function ClipperPage() {
  const [sourceUrl, setSourceUrl] = useState('');
  const [sourceCredit, setSourceCredit] = useState('');
  const [title, setTitle] = useState('Clip Reaction');
  const [startSec, setStartSec] = useState(0);
  const [endSec, setEndSec] = useState(30);
  const [karaokeVi, setKaraokeVi] = useState(true);
  const [busy, setBusy] = useState(false);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);

  const handleExtract = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setStatusMsg(null);
    try {
      const res = await fetch('/api/clipper/extract', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          source_url: sourceUrl,
          source_credit: sourceCredit,
          title,
          start_sec: Number(startSec),
          end_sec: Number(endSec),
          karaoke_vi: karaokeVi,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setStatusMsg(`Lỗi: ${data.detail ?? 'Không trích xuất được clip'}`);
      } else {
        setStatusMsg(`Đã xuất clip: ${data.item?.title ?? title} (đã lưu vào SQLite)`);
      }
    } catch {
      setStatusMsg('Không thể kết nối backend Clipper.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="mx-auto max-w-4xl space-y-6 p-6">
      <header className="rounded-2xl border border-[#F59E0B]/40 bg-white/[0.03] p-5 backdrop-blur-md">
        <span className="inline-block rounded-full border border-[#F59E0B]/50 bg-[#F59E0B]/15 px-3 py-0.5 text-xs font-medium text-amber-200">
          Clipper & Reaction
        </span>
        <h1 className="mt-2 text-2xl font-bold text-white">Trích xuất Clip 9:16 & Ghi nguồn</h1>
        <p className="mt-1 text-sm text-slate-400">
          Dán link video highlight/reaction, tự động gắn nhãn{' '}
          <code className="text-amber-300">Nguồn: ...</code> cố định ở vùng an toàn và chạy phụ đề
          karaoke tiếng Việt.
        </p>
      </header>

      <form
        onSubmit={handleExtract}
        className="space-y-4 rounded-2xl border border-white/10 bg-white/[0.03] p-6 backdrop-blur-md"
      >
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <label className="block space-y-1.5 text-sm">
            <span className="text-slate-300">Link video nguồn</span>
            <input
              type="url"
              required
              value={sourceUrl}
              onChange={(e) => setSourceUrl(e.target.value)}
              placeholder="https://www.youtube.com/watch?v=..."
              className="w-full rounded-xl border border-white/10 bg-[#090d16] px-3 py-2 text-white outline-none focus:border-[#F59E0B]"
            />
          </label>

          <label className="block space-y-1.5 text-sm">
            <span className="text-slate-300">Nhãn ghi nguồn (bắt buộc)</span>
            <input
              type="text"
              required
              value={sourceCredit}
              onChange={(e) => setSourceCredit(e.target.value)}
              placeholder="Nguồn: @ten_kenh_goc"
              className="w-full rounded-xl border border-white/10 bg-[#090d16] px-3 py-2 text-white outline-none focus:border-[#F59E0B]"
            />
          </label>
        </div>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <label className="block space-y-1.5 text-sm">
            <span className="text-slate-300">Tiêu đề clip</span>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="w-full rounded-xl border border-white/10 bg-[#090d16] px-3 py-2 text-white outline-none focus:border-[#F59E0B]"
            />
          </label>
          <label className="block space-y-1.5 text-sm">
            <span className="text-slate-300">Bắt đầu (giây)</span>
            <input
              type="number"
              min={0}
              value={startSec}
              onChange={(e) => setStartSec(Number(e.target.value))}
              className="w-full rounded-xl border border-white/10 bg-[#090d16] px-3 py-2 text-white outline-none focus:border-[#F59E0B]"
            />
          </label>
          <label className="block space-y-1.5 text-sm">
            <span className="text-slate-300">Kết thúc (giây)</span>
            <input
              type="number"
              min={1}
              value={endSec}
              onChange={(e) => setEndSec(Number(e.target.value))}
              className="w-full rounded-xl border border-white/10 bg-[#090d16] px-3 py-2 text-white outline-none focus:border-[#F59E0B]"
            />
          </label>
        </div>

        <label className="flex items-center gap-2 text-sm text-slate-200">
          <input
            type="checkbox"
            checked={karaokeVi}
            onChange={(e) => setKaraokeVi(e.target.checked)}
            className="h-4 w-4 accent-[#F59E0B]"
          />
          Bật phụ đề karaoke tiếng Việt
        </label>

        <div className="flex items-center gap-4 pt-2">
          <button
            type="submit"
            disabled={busy}
            className="rounded-xl bg-[#F59E0B] px-5 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-amber-400 disabled:opacity-50"
          >
            {busy ? 'Đang trích xuất...' : 'Trích xuất Clip 9:16'}
          </button>
          {statusMsg && <p className="text-sm text-slate-200">{statusMsg}</p>}
        </div>
      </form>
    </main>
  );
}
