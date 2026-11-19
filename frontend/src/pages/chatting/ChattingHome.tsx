import { useQuery } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../../api/endpoints';
import { StudioTopBar } from '../../components/studio/StudioTopBar';
import { Button } from '../../components/ui/Button';
import { StudioSelect } from '../../components/ui/StudioSelect';
import { FilmIcon, MessagesSquareIcon, TrashIcon } from '../../components/icons';
import { useStudioWorkspace } from '../../hooks/studioWorkspace';
import { vi } from '../../i18n/vi';

const BACKGROUND_OPTIONS = [
  { id: 'minecraft4-1080p60', label: 'Minecraft Parkour 1' },
  { id: 'minecraft10-1080p60', label: 'Minecraft Parkour 2' },
  { id: 'minecraft11-1080p60', label: 'Minecraft Parkour 3' },
  { id: 'minecraft12-1080p60', label: 'Minecraft Parkour 4' },
];

const DURATION_OPTIONS = [
  { id: '', label: 'Tự động (tối đa 5p)' },
  { id: '60', label: '1 phút (60s)' },
  { id: '90', label: '1 phút 30s (90s)' },
  { id: '120', label: '2 phút (120s)' },
  { id: '150', label: '2 phút 30s (150s)' },
  { id: '180', label: '3 phút (180s)' },
  { id: '240', label: '4 phút (240s)' },
  { id: '300', label: '5 phút (300s)' },
];

export function ChattingHome() {
  const navigate = useNavigate();
  const ws = useStudioWorkspace();
  const setStudioMode = ws?.setStudioMode;
  const [inputText, setInputText] = useState('');

  useEffect(() => {
    setStudioMode?.(true);
    return () => {
      setStudioMode?.(false);
    };
  }, [setStudioMode]);
  const [platform, setPlatform] = useState<'messenger' | 'instagram'>('messenger');
  const [background, setBackground] = useState('minecraft4-1080p60');
  const [targetDuration, setTargetDuration] = useState('');
  const [selectedModel, setSelectedModel] = useState('gemini-3.8-flash');
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
        target_duration_s: targetDuration ? Number(targetDuration) : null,
        model: selectedModel,
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

  const isGeminiMissing =
    !isDirectScript && !isStatusLoading && status && !status.gemini_configured;

  return (
    <div className="flex min-h-screen w-full flex-col bg-bg">
      <StudioTopBar
        engineBadge="Chatting · 60fps"
        title="Hội thoại Tin nhắn Messenger / Instagram"
        exportProps={{
          aspect: '9:16',
          showWatermarkControl: true,
          onExportFinal: () => void handleCreate(),
          finalLabel: isSubmitting ? 'Đang khởi tạo…' : vi.chatting.createBtn,
          disabled: !inputText.trim() || isSubmitting,
          isSubmitting,
        }}
      />
      <main className="mx-auto w-full max-w-5xl flex-1 px-6 py-7 lg:px-8">
        <div className="mb-6 text-center">
          <div className="mx-auto mb-2.5 flex h-11 w-11 items-center justify-center rounded-xl border border-line bg-card text-text shadow-card">
            <MessagesSquareIcon size={22} />
          </div>
          <h1 className="text-h1 font-bold tracking-tight text-text">{vi.chatting.title}</h1>
          <p className="mt-1 text-small text-muted">
            Tạo video dạng tin nhắn Messenger / Zalo 60fps nhanh chóng
          </p>
        </div>

        {/* Màn trống cảnh báo nếu chưa cấu hình GEMINI_API_KEY và đang ở chế độ AI */}
        {isGeminiMissing && (
          <div className="mb-5 rounded-card border border-line bg-tint-yel p-4 text-center text-text">
            <p className="text-body font-bold">{vi.chatting.noGemini}</p>
            <p className="mt-1 text-tiny text-muted">
              Hệ thống dùng chung <code className="font-mono font-bold">GEMINI_API_KEY</code> với
              HBT Core (model{' '}
              <code className="font-mono font-bold">
                {status?.model_name || 'gemini-3.8-flash'}
              </code>
              ). Hoặc bạn có thể chọn tab <b>Dán kịch bản trực tiếp (Bypass LLM)</b> để tạo video
              ngay không cần API Key.
            </p>
          </div>
        )}

        {/* Khung nhập chuẩn VEED Bright Minimalist */}
        <div className="rounded-card border border-line bg-card p-5 shadow-card">
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
                  ? 'bg-accent text-on-accent shadow-sm'
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
                onClick={() => setPlatform('instagram')}
                className={`rounded-full px-4 py-1.5 text-tiny font-bold transition-colors ${
                  platform === 'instagram'
                    ? 'bg-primary text-on-primary'
                    : 'bg-soft text-text hover:bg-soft/80'
                }`}
              >
                {vi.chatting.instagram}
              </button>

              <span className="ml-4 text-tiny font-semibold text-muted">
                {vi.chatting.background}:
              </span>
              <StudioSelect
                aria-label={vi.chatting.background}
                variant="pill"
                autoWidth
                value={background}
                onChange={(val) => setBackground(val)}
                options={BACKGROUND_OPTIONS.map((bg) => ({ value: bg.id, label: bg.label }))}
                className="min-w-[165px]"
              />

              {!isDirectScript && (
                <>
                  <span className="ml-3 text-tiny font-semibold text-muted">Model Gemini:</span>
                  <StudioSelect
                    aria-label="Model Gemini"
                    variant="pill"
                    autoWidth
                    value={selectedModel}
                    onChange={(val) => setSelectedModel(val)}
                    options={(
                      status?.models ?? [
                        { id: 'gemini-3.8-flash', name: 'Gemini 3.8 Flash' },
                        { id: 'gemini-3.6-flash', name: 'Gemini 3.6 Flash' },
                        { id: 'gemini-3.5-flash-lite', name: 'Gemini 3.5 Flash Lite' },
                        { id: 'gemini-3.1-flash-lite', name: 'Gemini 3.1 Flash Lite' },
                      ]
                    ).map((m) => ({ value: m.id, label: m.name }))}
                    className="min-w-[170px]"
                  />
                </>
              )}

              <span className="ml-3 text-tiny font-semibold text-muted">Thời lượng:</span>
              <StudioSelect
                aria-label="Thời lượng video"
                variant="pill"
                autoWidth
                value={targetDuration}
                onChange={(val) => setTargetDuration(val)}
                options={DURATION_OPTIONS.map((d) => ({ value: d.id, label: d.label }))}
                className="min-w-[160px]"
              />
            </div>

            <Button
              tone="chatting"
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
                            <span className="rounded-full bg-tint-yel px-2 py-0.5 text-tiny font-bold text-on-tint-yel">
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
                        <span className="text-muted">
                          {isJobRunning ? 'Đang xử lý' : 'Bản nháp'}
                        </span>
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
    </div>
  );
}
