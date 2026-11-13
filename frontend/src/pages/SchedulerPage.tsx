import { useEffect, useState } from "react";
import type { KanbanRenderItem } from "../components/KanbanBoard";

const DAYS = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ Nhật"];

export function SchedulerPage() {
  const [items, setItems] = useState<KanbanRenderItem[]>([]);
  const [draggingId, setDraggingId] = useState<string | null>(null);
  const [selectedTime, setSelectedTime] = useState("19:00");

  const load = async () => {
    try {
      const res = await fetch("/api/kanban/renders");
      if (res.ok) {
        const d = await res.json();
        setItems(d.items ?? []);
      }
    } catch {
      // ignore
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const scheduleItem = async (id: string, dayLabel: string) => {
    const scheduledAt = `${dayLabel} ${selectedTime}`;
    setItems((prev) =>
      prev.map((i) =>
        i.id === id ? { ...i, pipeline_stage: "scheduled", scheduled_at: scheduledAt } : i
      )
    );
    try {
      await fetch(`/api/kanban/renders/${encodeURIComponent(id)}/stage`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pipeline_stage: "scheduled", scheduled_at: scheduledAt }),
      });
    } catch {
      // ignore
    }
  };

  const readyToSchedule = items.filter((i) => i.pipeline_stage === "edited");
  const scheduled = items.filter((i) => i.pipeline_stage === "scheduled");

  return (
    <main className="mx-auto max-w-6xl space-y-6 p-6">
      <header className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-white/10 bg-white/[0.03] p-5 backdrop-blur-md">
        <div>
          <h1 className="text-2xl font-bold text-white">Lịch Xuất Bản</h1>
          <p className="mt-1 text-sm text-slate-400">
            Kéo video từ cột &ldquo;Đã chỉnh sửa&rdquo; vào khung ngày trong tuần (lưu vào SQLite).
          </p>
        </div>
        <label className="flex items-center gap-2 text-sm text-slate-300">
          <span>Giờ đăng mặc định:</span>
          <input
            type="time"
            value={selectedTime}
            onChange={(e) => setSelectedTime(e.target.value)}
            className="rounded-lg border border-white/10 bg-[#090d16] px-2.5 py-1 text-white"
          />
        </label>
      </header>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[260px_1fr]">
        <aside className="space-y-3 rounded-2xl border border-white/10 bg-white/[0.03] p-4 backdrop-blur-md">
          <h2 className="text-sm font-semibold text-white">Đã chỉnh sửa ({readyToSchedule.length})</h2>
          <div className="space-y-2">
            {readyToSchedule.map((item) => (
              <div
                key={item.id}
                draggable
                onDragStart={() => setDraggingId(item.id)}
                className="cursor-grab rounded-xl border border-white/10 bg-[#0f1624] p-2.5 text-xs text-white hover:border-white/25"
              >
                <p className="truncate font-medium">{item.title}</p>
                <p className="mt-0.5 text-[11px] text-slate-400">
                  {item.engine} · {item.size_mb.toFixed(1)} MB
                </p>
              </div>
            ))}
            {readyToSchedule.length === 0 && (
              <p className="text-xs text-slate-500">Chưa có video nào ở trạng thái Đã chỉnh sửa.</p>
            )}
          </div>
        </aside>

        <section className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7">
          {DAYS.map((day) => {
            const dayItems = scheduled.filter((i) => i.scheduled_at.startsWith(day));
            return (
              <div
                key={day}
                onDragOver={(e) => e.preventDefault()}
                onDrop={() => {
                  if (draggingId) {
                    void scheduleItem(draggingId, day);
                    setDraggingId(null);
                  }
                }}
                className="flex min-h-[220px] flex-col gap-2 rounded-2xl border border-white/10 bg-white/[0.03] p-3 backdrop-blur-md"
              >
                <div className="border-b border-white/10 pb-1.5 text-xs font-semibold text-slate-200">
                  {day}
                </div>
                {dayItems.map((item) => (
                  <div
                    key={item.id}
                    className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-2 text-xs text-emerald-100"
                  >
                    <p className="truncate font-medium">{item.title}</p>
                    <p className="mt-0.5 text-[10px] text-emerald-300">{item.scheduled_at}</p>
                  </div>
                ))}
              </div>
            );
          })}
        </section>
      </div>
    </main>
  );
}
