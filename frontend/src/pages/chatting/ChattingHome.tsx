import { useQuery } from '@tanstack/react-query';
import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../../api/endpoints';
import { vi } from '../../i18n/vi';
import { Button } from '../../components/ui/Button';
import { Progress } from '../../components/ui/Progress';
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
  const [activeJob, setActiveJob] = useState<{ id: string; slug: string } | null>(null);
  const [jobProgress, setJobProgress] = useState<{
    percent: number;
    phase: string;
    text: string;
    llmSeconds?: number;
  } | null>(null);
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
    staleTime: 5000,
  });

  // Lắng nghe tiến độ SSE khi có activeJob
  useEffect(() => {
    if (!activeJob) return;
    const es = new EventSource(`/api/render/events/${activeJob.id}`);

    es.addEventListener('progress', (e) => {
      try {
        const data = JSON.parse(e.data);
        const timings = data.timings;
        setJobProgress({
          percent: data.percent ?? data.progress ?? 0,
          phase: data.phase ?? data.step ?? '',
          text: data.text ?? data.message ?? '',
          llmSeconds: timings?.llm_s,
        });
      } catch (err) {
        console.error('SSE parse error:', err);
      }
    });

    es.addEventListener('end', (e) => {
      try {
        const data = JSON.parse(e.data);
        es.close();
        if (data.status === 'done') {
          refetchProjects();
          navigate(`/chatting/${activeJob.slug}`);
        } else if (data.status === 'failed') {
          setErrorMsg(data.error || 'Dựng video thất bại');
          setActiveJob(null);
        }
      } catch {
        es.close();
      }
    });

    es.onerror = () => {
      es.close();
    };

    return () => {
      es.close();
    };
  }, [activeJob, navigate, refetchProjects]);

  const handleCreate = async () => {
    if (!inputText.trim()) return;
    setErrorMsg(null);
    try {
      const res = await api.createChattingProject({
        input: inputText.trim(),
        platform,
        background,
      });
      setActiveJob({ id: res.job_id, slug: res.slug });
      setJobProgress({ percent: 5, phase: 'fetch', text: 'Bắt đầu xử lý...' });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setErrorMsg(msg || 'Không thể tạo video Chatting');
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

  const isOllamaMissing = !isStatusLoading && status && !status.ollama_running;

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <div className="mb-8 text-center">
        <h1 className="flex items-center justify-center gap-3 text-3xl font-extrabold tracking-tight">
          <MessagesSquareIcon size={32} />
          {vi.chatting.title}
        </h1>
        <p className="mt-2 text-muted">Tạo video dạng tin nhắn Messenger / Zalo nhanh chóng</p>
      </div>

      {/* Màn trống cảnh báo nếu Ollama chưa chạy */}
      {isOllamaMissing && (
        <div className="mb-6 rounded-2xl border border-line bg-tint-yel p-6 text-center text-text">
          <p className="text-body font-bold">{vi.chatting.noOllama}</p>
          <p className="mt-1 text-tiny text-muted">
            Khởi động ứng dụng Ollama trên máy của bạn và đảm bảo model{' '}
            <code className="font-mono font-bold">
              {status?.model_name || 'qwen2.5:3b-instruct'}
            </code>{' '}
            đã được tải.
          </p>
        </div>
      )}

      {/* Ô nhập lớn ở giữa bo 28 */}
      <div className="rounded-[28px] border border-line bg-card p-6 shadow-sm">
        <textarea
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          placeholder={vi.chatting.inputPlaceholder}
          rows={5}
          disabled={!!activeJob}
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
            disabled={!inputText.trim() || !!activeJob}
            className="rounded-full px-8 font-extrabold shadow-md"
          >
            {activeJob ? 'Đang tạo…' : vi.chatting.createBtn}
          </Button>
        </div>

        {/* Thanh tiến độ 4 pha */}
        {activeJob && jobProgress && (
          <div className="mt-6 rounded-2xl border border-line bg-soft-2 p-4">
            <div className="mb-2 flex items-center justify-between text-tiny">
              <span className="font-bold text-text">{jobProgress.text}</span>
              <span className="font-extrabold tabular-nums text-accent">
                {jobProgress.percent}%
              </span>
            </div>
            <Progress value={jobProgress.percent} label={jobProgress.text || 'Tiến độ'} />

            <div className="mt-3 grid grid-cols-4 gap-2 text-center text-tiny font-semibold">
              <div className={jobProgress.percent >= 20 ? 'font-bold text-text' : 'text-muted'}>
                1. {vi.chatting.phases.fetch}
              </div>
              <div
                className={
                  jobProgress.percent >= 30 && jobProgress.percent <= 60
                    ? 'font-bold text-accent'
                    : jobProgress.percent > 60
                      ? 'font-bold text-text'
                      : 'text-muted'
                }
              >
                2. {vi.chatting.phases.llm}{' '}
                {jobProgress.llmSeconds ? `(${jobProgress.llmSeconds}s)` : ''}
              </div>
              <div
                className={
                  jobProgress.percent > 60 && jobProgress.percent < 85
                    ? 'font-bold text-accent'
                    : jobProgress.percent >= 85
                      ? 'font-bold text-text'
                      : 'text-muted'
                }
              >
                3. {vi.chatting.phases.voice}
              </div>
              <div className={jobProgress.percent >= 85 ? 'font-bold text-accent' : 'text-muted'}>
                4. {vi.chatting.phases.preview}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Lưới dự án Chatting gần đây */}
      <div className="mt-12">
        <h2 className="mb-4 text-xl font-bold">{vi.chatting.recentProjects}</h2>
        {projects && projects.length > 0 ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-3">
            {projects.map((p) => (
              <div
                key={p.slug}
                onClick={() => navigate(`/chatting/${p.slug}`)}
                className="group relative flex cursor-pointer flex-col justify-between rounded-2xl border border-line bg-card p-4 transition-all hover:-translate-y-1 hover:shadow-md"
              >
                <div>
                  <div className="mb-2 flex items-center justify-between">
                    <span className="rounded-full bg-soft px-2.5 py-0.5 text-tiny font-bold uppercase text-muted">
                      {p.platform}
                    </span>
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
                    <span className="text-muted">Bản nháp</span>
                  )}
                  {p.timings?.llm_s && <span className="text-muted">LLM: {p.timings.llm_s}s</span>}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-body text-muted">{vi.chatting.noRecent}</p>
        )}
      </div>
    </div>
  );
}
