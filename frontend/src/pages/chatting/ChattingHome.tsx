import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../../api/endpoints';
import { vi } from '../../i18n/vi';
import { Button } from '../../components/ui/Button';
import { FilmIcon, MessagesSquareIcon, TrashIcon } from '../../components/icons';

const BACKGROUND_OPTIONS = [
  { id: 'minecraft4-1080p60', label: 'Minecraft Parkour 1' },
  { id: 'minecraft10-1080p60', label: 'Minecraft Parkour 2' },
  { id: 'minecraft11-1080p60', label: 'Minecraft Parkour 3' },
  { id: 'minecraft12-1080p60', label: 'Minecraft Parkour 4' },
];

export function ChattingHome() {
  const navigate = useNavigate();
  const [inputText, setInputText] = useState('');
  const [platform, setPlatform] = useState<'messenger' | 'zalo'>('messenger');
  const [background, setBackground] = useState('minecraft4-1080p60');
  const [isDirectScript, setIsDirectScript] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // 1. Kiểm tra trạng thái Ollama
  const { data: status, isLoading: isStatusLoading } = useQuery({
    queryKey: ['chattingStatus'],
    queryFn: api.getChattingStatus,
    refetchInterval: 10_000,
  });

  // 2. Danh sách dự án gần đây
  const { data: projects, refetch: refetchProjects } = useQuery({
    queryKey: ['chattingProjects'],
    queryFn: api.listChattingProjects,
    staleTime: 3000,
  });

  const handleCreate = async () => {
    if (!inputText.trim()) return;
    setErrorMsg(null);
    setIsSubmitting(true);
    try {
      const res = await api.createChattingProject({
        input: inputText.trim(),
        platform,
        background,
        direct_script: isDirectScript,
      });
      // Điều hướng ngay sang trang chi tiết để theo dõi tiến trình
      navigate(`/chatting/${res.slug}`);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setErrorMsg(msg || 'Không thể tạo video Chatting');
      setIsSubmitting(false);
    }
  };

  const handleDelete = async (slug: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!window.confirm('Xoá dự án này?')) return;
    try {
      await api.deleteChattingProject(slug);
      refetchProjects();
    } catch (err) {
      console.error(err);
    }
  };

  const isOllamaMissing = !isDirectScript && !isStatusLoading && status && !status.ollama_running;

  return (
    <main className="mx-auto max-w-5xl px-4 py-8">
      <div className="mb-8 text-center">
        <h1 className="flex items-center justify-center gap-3 text-3xl font-extrabold tracking-tight">
          <MessagesSquareIcon size={32} />
          {vi.chatting.title}
        </h1>
        <p className="mt-2 text-muted">Tạo video dạng tin nhắn Messenger / Zalo nhanh chóng</p>
      </div>

      {/* Màn trống cảnh báo nếu Ollama chưa chạy và đang ở chế độ AI */}
      {isOllamaMissing && (
        <div className="mb-6 rounded-2xl border border-line bg-tint-yel p-6 text-center text-text">
          <p className="text-body font-bold">{vi.chatting.noOllama}</p>
          <p className="mt-1 text-tiny text-muted">
            Khởi động ứng dụng Ollama trên máy của bạn và đảm bảo model{' '}
            <code className="font-mono font-bold">
              {status?.model_name || 'qwen2.5:3b-instruct'}
            </code>{' '}
            đã được tải. Hoặc bạn có thể chọn tab <b>Dán kịch bản trực tiếp (Bypass LLM)</b> để tạo
            video ngay mà không cần Ollama.
          </p>
        </div>
      )}

      {/* Ô nhập lớn ở giữa bo 28 */}
      <div className="rounded-[28px] border border-line bg-card p-6 shadow-sm">
        {/* Tab chọn chế độ: Viết AI vs Kịch bản trực tiếp */}
        <div className="mb-4 flex items-center gap-2 border-b border-line pb-3">
          <button
            type="button"
            onClick={() => setIsDirectScript(false)}
            className={`rounded-full px-4 py-1.5 text-tiny font-bold transition-colors ${
              !isDirectScript ? 'bg-text text-bg shadow-sm' : 'bg-soft text-muted hover:text-text'
            }`}
          >
            Từ bài viết / Link (AI viết)
          </button>
          <button
            type="button"
            onClick={() => setIsDirectScript(true)}
            className={`rounded-full px-4 py-1.5 text-tiny font-bold transition-colors ${
              isDirectScript
                ? 'bg-accent text-white shadow-sm'
                : 'bg-soft text-muted hover:text-text'
            }`}
          >
            Dán kịch bản trực tiếp (Bypass LLM)
          </button>
        </div>

        <textarea
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          placeholder={
            isDirectScript
              ? 'Dán kịch bản đối thoại trực tiếp không qua AI, ví dụ:\nMinh: Ê tối nay đi ăn lẩu không?\nLinh: Mấy giờ thế? Tao đang bận tí việc (ngại)\nMinh: Tầm 7 rưỡi nhé!\nLinh: Ok chốt luôn [sticker: ok]'
              : vi.chatting.inputPlaceholder
          }
          rows={6}
          disabled={isSubmitting}
          className="w-full resize-none rounded-2xl border border-line bg-soft-2 p-4 text-body font-medium outline-none focus:border-text focus:ring-2 focus:ring-accent"
        />

        {errorMsg && (
          <div className="mt-3 rounded-xl bg-danger/10 p-3 text-tiny font-bold text-danger">
            {errorMsg}
          </div>
        )}

        {/* Hàng chip điều khiển */}
        <div className="mt-4 flex flex-wrap items-center justify-between gap-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-tiny font-semibold text-muted">{vi.chatting.platform}:</span>
            <button
              type="button"
              onClick={() => setPlatform('messenger')}
              className={`rounded-full px-4 py-1.5 text-tiny font-bold transition-colors ${
                platform === 'messenger'
                  ? 'bg-primary text-on-primary'
                  : 'bg-soft text-text hover:bg-soft/80'
              }`}
            >
              {vi.chatting.messenger}
            </button>
            <button
              type="button"
              onClick={() => setPlatform('zalo')}
              className={`rounded-full px-4 py-1.5 text-tiny font-bold transition-colors ${
                platform === 'zalo'
                  ? 'bg-primary text-on-primary'
                  : 'bg-soft text-text hover:bg-soft/80'
              }`}
            >
              {vi.chatting.zalo}
            </button>

            <span className="ml-4 text-tiny font-semibold text-muted">
              {vi.chatting.background}:
            </span>
            <select
              value={background}
              onChange={(e) => setBackground(e.target.value)}
              className="rounded-full border border-line bg-soft px-3 py-1.5 text-tiny font-bold text-text outline-none"
            >
              {BACKGROUND_OPTIONS.map((bg) => (
                <option key={bg.id} value={bg.id}>
                  {bg.label}
                </option>
              ))}
            </select>
          </div>

          <Button
            tone="brand"
            size="lg"
            onClick={handleCreate}
            disabled={!inputText.trim() || isSubmitting}
            className="rounded-full px-8 font-extrabold shadow-md"
          >
            {isSubmitting ? 'Đang khởi tạo…' : vi.chatting.createBtn}
          </Button>
        </div>
      </div>

      {/* Lưới dự án Chatting gần đây */}
      <div className="mt-12">
        <h2 className="mb-4 text-xl font-bold">{vi.chatting.recentProjects}</h2>
        {projects && projects.length > 0 ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-3">
            {projects.map((p) => {
              const isJobRunning = p.job && p.job.status === 'running';
              return (
                <div
                  key={p.slug}
                  onClick={() => navigate(`/chatting/${p.slug}`)}
                  className="group relative flex cursor-pointer flex-col justify-between rounded-2xl border border-line bg-card p-4 transition-all hover:-translate-y-1 hover:shadow-md"
                >
                  <div>
                    <div className="mb-2 flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="rounded-full bg-soft px-2.5 py-0.5 text-tiny font-bold uppercase text-muted">
                          {p.platform}
                        </span>
                        {isJobRunning && (
                          <span className="animate-pulse rounded-full bg-accent/20 px-2 py-0.5 text-tiny font-bold text-accent">
                            Đang tạo {p.job?.percent}%
                          </span>
                        )}
                      </div>
                      <button
                        type="button"
                        onClick={(e) => handleDelete(p.slug, e)}
                        title="Xoá dự án"
                        className="rounded-full p-1 text-muted opacity-0 hover:bg-soft hover:text-danger group-hover:opacity-100"
                      >
                        <TrashIcon size={16} />
                      </button>
                    </div>
                    <h3 className="line-clamp-2 text-body font-bold text-text">{p.title}</h3>
                    <p className="mt-1 text-tiny text-muted">
                      {p.messages_count} tin nhắn · {p.characters_count} nhân vật
                    </p>
                  </div>

                  <div className="mt-4 flex items-center justify-between border-t border-line/60 pt-3 text-tiny">
                    {p.has_render ? (
                      <span className="flex items-center gap-1 font-semibold text-ok">
                        <FilmIcon size={14} /> Có video
                      </span>
                    ) : (
                      <span className="text-muted">{isJobRunning ? 'Đang xử lý' : 'Bản nháp'}</span>
                    )}
                    {p.timings?.llm_s !== undefined && (
                      <span className="text-muted">LLM: {p.timings.llm_s}s</span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <p className="text-body text-muted">{vi.chatting.noRecent}</p>
        )}
      </div>
    </main>
  );
}
