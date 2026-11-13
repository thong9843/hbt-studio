import { useEffect, useState } from 'react';

export type PipelineStage = 'draft' | 'rendered' | 'edited' | 'scheduled' | 'published';

export interface KanbanRenderItem {
  id: string;
  slug: string;
  title: string;
  engine: 'core' | 'postv' | 'chatting' | 'clipper' | 'editor';
  file_path: string;
  cover_path: string;
  duration_sec: number;
  size_mb: number;
  pipeline_stage: PipelineStage;
  source_credit: string;
  scheduled_at: string;
  created_at: string;
}

const COLUMNS: { key: PipelineStage; label: string }[] = [
  { key: 'draft', label: 'Bản nháp' },
  { key: 'rendered', label: 'Đã xuất' },
  { key: 'edited', label: 'Đã chỉnh sửa' },
  { key: 'scheduled', label: 'Lên lịch đăng' },
];

const ENGINE_BADGE: Record<string, { label: string; color: string }> = {
  core: { label: 'HBT Core', color: 'border-[#B22228]/60 bg-[#B22228]/15 text-red-200' },
  postv: { label: 'PostV', color: 'border-[#8B5CF6]/60 bg-[#8B5CF6]/15 text-purple-200' },
  chatting: { label: 'Chatting', color: 'border-[#10B981]/60 bg-[#10B981]/15 text-emerald-200' },
  clipper: { label: 'Clipper', color: 'border-[#F59E0B]/60 bg-[#F59E0B]/15 text-amber-200' },
  editor: { label: 'Editor', color: 'border-[#F59E0B]/60 bg-[#F59E0B]/15 text-amber-200' },
};

export function KanbanBoard() {
  const [items, setItems] = useState<KanbanRenderItem[]>([]);
  const [draggingId, setDraggingId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const loadRenders = async () => {
    try {
      const res = await fetch('/api/kanban/renders');
      if (res.ok) {
        const data = await res.json();
        setItems(data.items ?? []);
      }
    } catch {
      // ignore offline in unit tests
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadRenders();
  }, []);

  const moveCard = async (id: string, targetStage: PipelineStage) => {
    setItems((prev) =>
      prev.map((item) => (item.id === id ? { ...item, pipeline_stage: targetStage } : item)),
    );
    try {
      await fetch(`/api/kanban/renders/${encodeURIComponent(id)}/stage`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pipeline_stage: targetStage }),
      });
    } catch {
      // revert on error if needed
    }
  };

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-white">Kanban Pipeline</h2>
          <p className="text-xs text-slate-400">
            Kéo thả thẻ video giữa các giai đoạn để cập nhật vào SQLite
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs">
          {COLUMNS.map((col) => {
            const count = items.filter((i) => i.pipeline_stage === col.key).length;
            return (
              <span
                key={col.key}
                className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-slate-200"
              >
                {col.label}: <strong className="text-white">{count}</strong>
              </span>
            );
          })}
        </div>
      </div>

      {loading ? (
        <div className="rounded-2xl border border-white/10 bg-white/5 p-6 text-sm text-slate-400">
          Đang đồng bộ kho video...
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
          {COLUMNS.map((col) => {
            const colItems = items.filter((i) => i.pipeline_stage === col.key);
            return (
              <div
                key={col.key}
                onDragOver={(e) => e.preventDefault()}
                onDrop={() => {
                  if (draggingId) {
                    void moveCard(draggingId, col.key);
                    setDraggingId(null);
                  }
                }}
                className="flex min-h-[260px] flex-col gap-3 rounded-2xl border border-white/10 bg-white/[0.03] p-3 backdrop-blur-md"
              >
                <div className="flex items-center justify-between border-b border-white/10 pb-2">
                  <span className="text-sm font-medium text-slate-100">{col.label}</span>
                  <span className="rounded-md bg-white/10 px-2 py-0.5 text-xs text-slate-300">
                    {colItems.length}
                  </span>
                </div>

                <div className="flex flex-col gap-2.5">
                  {colItems.map((item) => {
                    const badge = ENGINE_BADGE[item.engine] ?? ENGINE_BADGE.core;
                    return (
                      <div
                        key={item.id}
                        draggable
                        onDragStart={() => setDraggingId(item.id)}
                        className="cursor-grab rounded-xl border border-white/10 bg-[#0f1624]/90 p-2.5 transition hover:border-white/25 active:cursor-grabbing"
                      >
                        <div className="flex gap-2.5">
                          <div className="h-16 w-9 shrink-0 overflow-hidden rounded-md bg-slate-800">
                            {item.cover_path ? (
                              <img
                                src={`/api/files/raw?path=${encodeURIComponent(item.cover_path)}`}
                                alt={item.title}
                                className="h-full w-full object-cover"
                              />
                            ) : (
                              <div className="flex h-full w-full items-center justify-center text-[10px] text-slate-500">
                                9:16
                              </div>
                            )}
                          </div>
                          <div className="min-w-0 flex-1">
                            <p className="truncate text-xs font-medium text-white">{item.title}</p>
                            <div className="mt-1 flex flex-wrap items-center gap-1.5">
                              <span
                                className={`rounded border px-1.5 py-0.5 text-[10px] ${badge.color}`}
                              >
                                {badge.label}
                              </span>
                              <span className="text-[10px] text-slate-400">
                                {item.size_mb.toFixed(1)} MB
                              </span>
                            </div>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                  {colItems.length === 0 && (
                    <div className="py-8 text-center text-xs text-slate-500">Kéo thẻ vào đây</div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
