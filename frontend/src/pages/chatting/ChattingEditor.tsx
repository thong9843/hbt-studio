import { useQuery } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { api } from '../../api/endpoints';
import { useSafeZone } from '../../components/SafeZoneOverlay';
import { PhonePreviewStage } from '../../components/studio/PhonePreviewStage';
import { SceneTimelineStrip } from '../../components/studio/SceneTimelineStrip';
import { StudioTopBar } from '../../components/studio/StudioTopBar';
import type { ChatDoc, ChatCharacter, ChatMessage } from '../../api/types';
import { useRenderJobStatus } from '../../hooks/renderJob';
import { useReleaseVideoOnUnmount } from '../../hooks/useReleaseVideoOnUnmount';
import { vi } from '../../i18n/vi';
import { Button } from '../../components/ui/Button';
import { Progress } from '../../components/ui/Progress';
import { StudioSelect } from '../../components/ui/StudioSelect';
import { ArrowLeftIcon, PlusIcon, TrashIcon } from '../../components/icons';

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

const STICKER_TAGS = [
  'soc',
  'cuoi',
  'khoc',
  'gian',
  'ngai',
  'yeu',
  'nghi',
  'can',
  'bat_luc',
  'ok',
] as const;

const VOICE_OPTIONS = ['Adam bựa', 'Trúc Ly', 'Thiện Minh', 'Mai Anh', 'Hải Đăng', 'Thùy Dung'];

export function ChattingEditor() {
  const { slug } = useParams<{ slug: string }>();
  const renderJob = useRenderJobStatus();
  const [selectedMsgIndex, setSelectedMsgIndex] = useState(0);
  const [isSaving, setIsSaving] = useState(false);
  const [isRerolling, setIsRerolling] = useState<'meme' | 'sfx' | null>(null);
  const [startingRender, setStartingRender] = useState(false);
  const [renderJobId, setRenderJobId] = useState<string | null>(null);
  const [avatarVersion, setAvatarVersion] = useState(0);
  const previewVideoRef = useRef<HTMLVideoElement | null>(null);
  const [renderProgress, setRenderProgress] = useState<number | null>(null);
  const [autoProgress, setAutoProgress] = useState<{
    percent: number;
    phase: string;
    text: string;
    llmSeconds?: number;
  } | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const { platform: safeZone, setPlatform: setSafeZone } = useSafeZone();

  const isRendering =
    startingRender ||
    (renderJob.running &&
      renderJob.kind === 'chatting_render' &&
      (!slug || renderJob.slug === slug));

  // 1. Lấy dữ liệu dự án
  const { data, refetch: refetchProject } = useQuery({
    queryKey: ['chattingProject', slug],
    queryFn: () => (slug ? api.getChattingProject(slug) : null),
    enabled: !!slug,
  });

  // 2. Lấy trạng thái job từ job.json
  const { data: jobInfo, refetch: refetchJob } = useQuery({
    queryKey: ['chattingJob', slug],
    queryFn: async () => {
      if (!slug) return null;
      try {
        return await api.getChattingJob(slug);
      } catch {
        return null;
      }
    },
    enabled: !!slug,
    refetchInterval: (query) => (query.state.data?.status === 'running' ? 2000 : false),
  });

  const doc = data?.doc;
  const activeRunningJob = jobInfo || data?.job;
  const latestRender = data?.renders?.[0];
  const videoUrl = latestRender
    ? `/api/chatting/${slug}/renders/${latestRender.video_file}`
    : data?.preview_url;
  useReleaseVideoOnUnmount(previewVideoRef, videoUrl);

  // Đồng bộ job chatting_auto vào RenderJobProvider toàn cục (0 EventSource trùng)
  useEffect(() => {
    const jId = activeRunningJob?.job_id;
    if (!jId || activeRunningJob?.status !== 'running' || !slug) return;
    renderJob.attachJob({
      jobId: jId,
      slug,
      kind: 'chatting_auto',
      engine: 'chatting',
      title: slug,
      route: `/chatting/${encodeURIComponent(slug)}`,
      progress: activeRunningJob.percent ?? 10,
      step: 'fetch',
      stage: activeRunningJob.text || 'Đang xử lý dự án...',
    });
  }, [
    activeRunningJob?.job_id,
    activeRunningJob?.status,
    activeRunningJob?.percent,
    activeRunningJob?.text,
    slug,
    renderJob,
  ]);

  // Lắng nghe tiến độ chatting_auto từ external store
  useEffect(() => {
    const jId = activeRunningJob?.job_id;
    if (!jId || renderJob.jobId !== jId) return;
    const apply = () => {
      const snap = renderJob.progressStore.getSnapshot();
      const timings = snap.timings as { llm_s?: number } | undefined;
      setAutoProgress({
        percent: snap.percent,
        phase: snap.phase || snap.step,
        text: snap.message || snap.stage,
        llmSeconds: timings?.llm_s,
      });
    };
    apply();
    return renderJob.progressStore.subscribe(apply);
  }, [activeRunningJob?.job_id, renderJob.jobId, renderJob.progressStore]);

  // Lắng nghe tiến độ chatting_render từ external store
  useEffect(() => {
    if (!renderJobId || renderJob.jobId !== renderJobId) return;
    const apply = () => {
      const snap = renderJob.progressStore.getSnapshot();
      setRenderProgress(Math.round(snap.percent));
    };
    apply();
    return renderJob.progressStore.subscribe(apply);
  }, [renderJobId, renderJob.jobId, renderJob.progressStore]);

  // Xử lý khi job Chatting (auto hoặc render) kết thúc
  useEffect(() => {
    const fin = renderJob.finished;
    if (!fin) return;
    if (activeRunningJob?.job_id && fin.id === activeRunningJob.job_id) {
      void refetchJob();
      void refetchProject();
      if (fin.status === 'failed') {
        setNotice(`Lỗi tạo video: ${fin.error || 'Thất bại'}`);
      }
    }
    if (renderJobId && fin.id === renderJobId) {
      setRenderJobId(null);
      setRenderProgress(null);
      if (fin.status === 'done') {
        void refetchProject();
        setNotice('Dựng video hoàn tất!');
      } else if (fin.status === 'failed') {
        setNotice(`Lỗi dựng video: ${fin.error || 'Thất bại'}`);
      }
    }
  }, [renderJob.finished, activeRunningJob?.job_id, renderJobId, refetchJob, refetchProject]);

  // Nếu đang trong quá trình tạo video tự động (chưa có doc hoặc job đang chạy)
  if (!doc && (activeRunningJob?.status === 'running' || autoProgress)) {
    const pct = autoProgress?.percent ?? activeRunningJob?.percent ?? 10;
    const msg = autoProgress?.text ?? activeRunningJob?.text ?? 'Đang xử lý dự án...';
    return (
      <main className="mx-auto max-w-3xl px-4 py-16">
        <div className="rounded-[28px] border border-line bg-card p-8 text-center shadow-sm">
          <h2 className="text-2xl font-extrabold text-text">Đang tạo video Chatting...</h2>
          <p className="mt-2 text-body text-muted">{msg}</p>

          <div className="mt-6">
            <div className="mb-2 flex items-center justify-between text-tiny font-bold">
              <span>{msg}</span>
              <span className="text-accent">{pct}%</span>
            </div>
            <Progress value={pct} label={msg} />
          </div>

          <div className="mt-6 grid grid-cols-4 gap-2 text-center text-tiny font-semibold">
            <div className={pct >= 20 ? 'font-bold text-text' : 'text-muted'}>
              1. {vi.chatting.phases.fetch}
            </div>
            <div
              className={
                pct >= 30 && pct <= 60
                  ? 'font-bold text-accent'
                  : pct > 60
                    ? 'font-bold text-text'
                    : 'text-muted'
              }
            >
              2. {vi.chatting.phases.llm}{' '}
              {autoProgress?.llmSeconds ? `(${autoProgress.llmSeconds}s)` : ''}
            </div>
            <div
              className={
                pct > 60 && pct < 85
                  ? 'font-bold text-accent'
                  : pct >= 85
                    ? 'font-bold text-text'
                    : 'text-muted'
              }
            >
              3. {vi.chatting.phases.voice}
            </div>
            <div className={pct >= 85 ? 'font-bold text-accent' : 'text-muted'}>
              4. {vi.chatting.phases.preview}
            </div>
          </div>

          <div className="mt-8 border-t border-line/60 pt-4 text-tiny text-muted">
            Tiến trình được lưu tự động. Bạn có thể thoải mái chuyển tab hoặc tải lại trang mà không
            lo mất.
          </div>
        </div>
      </main>
    );
  }

  // Nếu job thất bại
  if (!doc && activeRunningJob?.status === 'failed') {
    return (
      <main className="mx-auto max-w-xl px-4 py-16 text-center">
        <div className="rounded-2xl border border-danger/40 bg-card p-8 shadow-sm">
          <h2 className="text-xl font-bold text-danger">Tạo video thất bại</h2>
          <p className="mt-2 text-body text-muted">
            {activeRunningJob?.error || 'Đã xảy ra lỗi trong quá trình xử lý.'}
          </p>
          <div className="mt-6">
            <Link
              to="/chatting"
              className="inline-flex rounded-full bg-soft px-6 py-2 text-tiny font-bold text-text hover:bg-soft/80"
            >
              Quay về trang chủ Chatting
            </Link>
          </div>
        </div>
      </main>
    );
  }

  if (!doc) {
    return (
      <div className="flex h-64 items-center justify-center text-muted">{vi.common.loading}</div>
    );
  }

  const activeMsg = doc.messages[selectedMsgIndex] || doc.messages[0];

  const saveDoc = async (updatedDoc: ChatDoc) => {
    if (!slug) return;
    setIsSaving(true);
    try {
      await api.updateChattingProject(slug, updatedDoc);
      refetchProject();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      alert(`Lỗi lưu: ${msg}`);
    } finally {
      setIsSaving(false);
    }
  };

  const handleTextChange = (text: string) => {
    const newMsgs = [...doc.messages];
    newMsgs[selectedMsgIndex] = { ...activeMsg, text };
    saveDoc({ ...doc, messages: newMsgs });
  };

  const handleSenderChange = (from_: string) => {
    const newMsgs = [...doc.messages];
    newMsgs[selectedMsgIndex] = { ...activeMsg, from: from_ };
    saveDoc({ ...doc, messages: newMsgs });
  };

  const handleStickerChange = (sticker: string | null) => {
    const newMsgs = [...doc.messages];
    newMsgs[selectedMsgIndex] = {
      ...activeMsg,
      sticker,
      ...(sticker === null ? { meme_id: null, meme_query: null, asset_origin: null } : {}),
    };
    saveDoc({ ...doc, messages: newMsgs });
  };

  const handleRerollAsset = async (kind: 'meme' | 'sticker' | 'sfx') => {
    if (!slug) return;
    setIsRerolling(kind === 'sfx' ? 'sfx' : 'meme');
    setNotice(null);
    try {
      await api.rerollChattingAsset(slug, selectedMsgIndex, {
        kind,
        auto_fetch_online: doc.auto_fetch_online ?? true,
      });
      await refetchProject();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setNotice(msg || 'Không đổi được tài nguyên.');
    } finally {
      setIsRerolling(null);
    }
  };

  const handleClearSfx = () => {
    const newMsgs = [...doc.messages];
    newMsgs[selectedMsgIndex] = { ...activeMsg, sfx_id: null, sfx_query: null };
    saveDoc({ ...doc, messages: newMsgs });
  };

  const handleMediaUpload = async (file: File) => {
    if (!slug) return;
    const formData = new FormData();
    formData.append('file', file);
    try {
      const res = await fetch(`/api/chatting/${encodeURIComponent(slug)}/media`, {
        method: 'POST',
        body: formData,
      });
      if (res.ok) {
        const data = await res.json();
        const newMsgs = [...doc.messages];
        newMsgs[selectedMsgIndex] = {
          ...activeMsg,
          media_type: data.media_type,
          media_path: data.media_path,
        };
        saveDoc({ ...doc, messages: newMsgs });
      }
    } catch {
      setNotice('Không thể tải ảnh/video minh họa.');
    }
  };

  const handleMediaClear = () => {
    const newMsgs = [...doc.messages];
    newMsgs[selectedMsgIndex] = {
      ...activeMsg,
      media_type: 'none',
      media_path: null,
    };
    saveDoc({ ...doc, messages: newMsgs });
  };

  const handleAddMessage = () => {
    const newMsg: ChatMessage = {
      id: `m${doc.messages.length + 1}`,
      from: doc.characters[0].id,
      text: 'Tin nhắn mới',
      sticker: null,
    };
    const newMsgs = [...doc.messages, newMsg];
    saveDoc({ ...doc, messages: newMsgs });
    setSelectedMsgIndex(newMsgs.length - 1);
  };

  const handleDeleteMessage = (idx: number) => {
    if (doc.messages.length <= 8) {
      alert('Đoạn chat cần tối thiểu 8 tin nhắn.');
      return;
    }
    const newMsgs = doc.messages.filter((_: ChatMessage, i: number) => i !== idx);
    saveDoc({ ...doc, messages: newMsgs });
    setSelectedMsgIndex(Math.max(0, idx - 1));
  };

  const handleRegenAI = async () => {
    if (!slug) return;
    if (!window.confirm('Viết lại kịch bản bằng AI? Nội dung chỉnh sửa hiện tại sẽ được thay thế.'))
      return;
    setIsSaving(true);
    try {
      const res = await api.regenChattingProject(slug);
      refetchProject();
      if (res.doc?.warnings && res.doc.warnings.length > 0) {
        setNotice(`Đã viết lại kịch bản! (Có ${res.doc.warnings.length} lưu ý)`);
      } else {
        setNotice('Đã viết lại kịch bản!');
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      alert(`Lỗi AI: ${msg}`);
    } finally {
      setIsSaving(false);
    }
  };

  const handleRender = async (preview: boolean) => {
    if (!slug) return;
    setStartingRender(true);
    setNotice(null);
    try {
      const res = await api.renderChattingProject(slug, preview);
      setRenderJobId(res.job_id);
      renderJob.attachJob({
        jobId: res.job_id,
        slug,
        kind: 'chatting_render',
        engine: 'chatting',
        title: doc?.title || slug,
        route: `/chatting/${encodeURIComponent(slug)}`,
        preview,
        progress: 2,
        step: 'render',
        stage: 'Đang dựng video Chatting 60fps…',
      });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      alert(`Không thể bắt đầu dựng: ${msg}`);
    } finally {
      setStartingRender(false);
    }
  };

  const handleAvatarUpload = async (charId: string, file: File) => {
    if (!slug) return;
    const formData = new FormData();
    formData.append('file', file);
    try {
      const res = await fetch(`/api/chatting/${slug}/avatar/${charId}`, {
        method: 'POST',
        body: formData,
      });
      if (res.ok) {
        setAvatarVersion((v) => v + 1);
        refetchProject();
      } else {
        alert('Tải ảnh đại diện thất bại');
      }
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div className="flex h-screen max-h-screen flex-col overflow-hidden bg-bg text-text">
      <StudioTopBar
        engineBadge="Chatting"
        savedText={isSaving ? vi.chatting.saving : vi.studioShell.savedBadge}
        exportProps={{
          aspect: '9:16',
          showWatermarkControl: true,
          onExportPreview: () => void handleRender(true),
          onExportFinal: () => void handleRender(false),
          previewLabel: vi.chatting.exportFast,
          finalLabel: vi.chatting.exportFinal,
          disabled: isRendering,
          isRendering,
          subscribeGlobalProgress: isRendering,
          onCancelRender: isRendering ? () => void renderJob.cancel() : undefined,
          progressPct: renderProgress ?? 0,
          progressStage: isRendering ? 'Đang dựng video Chatting 60fps…' : '',
        }}
      />
      <div className="flex min-h-0 flex-1 overflow-hidden">
        {/* CỘT TRÁI (280px): Nhân vật + Danh sách tin nhắn */}
        <aside className="flex w-[280px] shrink-0 flex-col border-r border-line bg-card p-4 overflow-y-auto">
          <Link
            to="/chatting"
            className="mb-4 inline-flex items-center gap-1.5 text-tiny font-bold text-muted hover:text-text"
          >
            <ArrowLeftIcon size={16} /> Quay lại danh sách
          </Link>

          <h2 className="text-small font-extrabold text-text">{vi.chatting.characters}</h2>
          <div className="mt-3 space-y-3">
            {doc.characters.map((char: ChatCharacter) => (
              <div key={char.id} className="rounded-xl border border-line bg-soft-2 p-2.5">
                <div className="flex items-center gap-2.5">
                  <label className="relative flex h-10 w-10 shrink-0 cursor-pointer items-center justify-center overflow-hidden rounded-full border border-line bg-soft">
                    {char.avatar ? (
                      <img
                        src={
                          avatarVersion > 0
                            ? `/api/chatting/${slug}/${char.avatar}?v=${avatarVersion}`
                            : `/api/chatting/${slug}/${char.avatar}`
                        }
                        alt={char.name}
                        className="h-full w-full object-cover"
                      />
                    ) : (
                      <span className="font-bold text-text">{char.name ? char.name[0] : 'U'}</span>
                    )}
                    <input
                      type="file"
                      accept="image/*"
                      className="hidden"
                      onChange={(e) => {
                        if (e.target.files?.[0]) {
                          handleAvatarUpload(char.id, e.target.files[0]);
                        }
                      }}
                    />
                  </label>
                  <div className="flex-1 min-w-0">
                    <p className="truncate text-tiny font-bold text-text">
                      {char.name} ({char.side === 'right' ? 'Phải/Tôi' : 'Trái'})
                    </p>
                    <StudioSelect
                      aria-label={`Giọng của ${char.name}`}
                      variant="compact"
                      value={char.voice_id || 'Adam bựa'}
                      onChange={(val) => {
                        const newChars = doc.characters.map((c: ChatCharacter) =>
                          c.id === char.id ? { ...c, voice_id: val } : c,
                        );
                        saveDoc({ ...doc, characters: newChars });
                      }}
                      options={VOICE_OPTIONS.map((v) => ({ value: v, label: v }))}
                      className="mt-1"
                    />
                  </div>
                </div>
              </div>
            ))}
          </div>

          <div className="mt-6 flex items-center justify-between border-t border-line pt-4">
            <h2 className="text-small font-extrabold text-text">
              {vi.chatting.messages} ({doc.messages.length})
            </h2>
            <button
              type="button"
              onClick={handleAddMessage}
              className="rounded p-1 text-muted hover:bg-soft hover:text-text"
              title={vi.chatting.addMsg}
            >
              <PlusIcon size={16} />
            </button>
          </div>

          <div className="mt-2 flex-1 space-y-1.5 overflow-y-auto">
            {doc.messages.map((m: ChatMessage, idx: number) => {
              const isSelected = idx === selectedMsgIndex;
              const sender = doc.characters.find((c: ChatCharacter) => c.id === m.from);
              return (
                <div
                  key={idx}
                  onClick={() => setSelectedMsgIndex(idx)}
                  className={`flex cursor-pointer items-center justify-between rounded-xl px-2.5 py-2 text-tiny transition-colors ${
                    isSelected
                      ? 'bg-primary text-on-primary font-bold'
                      : 'bg-soft/40 hover:bg-soft text-text'
                  }`}
                >
                  <div className="flex-1 truncate mr-2">
                    <span className="opacity-70">{idx + 1}. </span>
                    <span className="font-semibold">{sender?.name}: </span>
                    <span>{m.text}</span>
                  </div>
                  {m.sticker && (
                    <span className="rounded bg-black/10 px-1.5 py-0.5 text-[10px] uppercase">
                      {m.sticker}
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        </aside>

        {/* CỘT GIỮA: Sửa tin đang chọn */}
        <main className="flex flex-1 flex-col p-6 overflow-y-auto">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line pb-4">
            <div>
              <h1 className="text-xl font-bold">{doc.title}</h1>
              <p className="text-tiny text-muted">
                {vi.chatting.platform}: {doc.platform} · {doc.messages.length} tin nhắn ·{' '}
                {doc.characters.length > 2 ? `Nhóm ${doc.characters.length} người` : '2 người'}
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              {isSaving && <span className="text-tiny text-muted">{vi.chatting.saving}</span>}
              <StudioSelect
                aria-label="Trần thời lượng video"
                variant="pill"
                autoWidth
                value={doc.target_duration_s ? String(doc.target_duration_s) : ''}
                onChange={(val) => {
                  const v = val ? Number(val) : null;
                  saveDoc({ ...doc, target_duration_s: v });
                }}
                options={DURATION_OPTIONS.map((d) => ({ value: d.id, label: d.label }))}
                className="min-w-[160px]"
              />
              <Button tone="soft" size="sm" onClick={handleRegenAI}>
                {vi.chatting.regenBtn}
              </Button>
            </div>
          </div>

          {notice && (
            <div className="mt-4 rounded-xl bg-tint-yel/60 p-3 text-tiny font-bold text-text">
              {notice}
            </div>
          )}

          {doc.warnings && doc.warnings.length > 0 && (
            <div className="mt-4 rounded-xl border border-tint-yel/60 bg-tint-yel/20 p-3.5 text-tiny text-text">
              <div className="flex items-center gap-1.5 font-bold text-accent">
                <span>⚠️ Lưu ý kịch bản:</span>
              </div>
              <ul className="mt-1 list-disc list-inside space-y-0.5 text-muted">
                {doc.warnings.map((w: string, i: number) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="mt-6 rounded-2xl border border-line bg-card p-6 shadow-sm">
            <div className="flex items-center justify-between">
              <h2 className="text-body font-extrabold">Sửa tin nhắn số {selectedMsgIndex + 1}</h2>
              <Button
                tone="soft"
                size="sm"
                onClick={() => handleDeleteMessage(selectedMsgIndex)}
                className="text-danger hover:bg-danger/10"
              >
                <TrashIcon size={14} /> {vi.chatting.delMsg}
              </Button>
            </div>

            {/* Chọn người gửi */}
            <div className="mt-4">
              <label className="text-tiny font-semibold text-muted">{vi.chatting.sender}:</label>
              <div className="mt-1.5 flex flex-wrap gap-2">
                {doc.characters.map((c: ChatCharacter) => (
                  <button
                    key={c.id}
                    type="button"
                    onClick={() => handleSenderChange(c.id)}
                    className={`rounded-full px-4 py-1.5 text-tiny font-bold transition-colors ${
                      activeMsg.from === c.id
                        ? 'bg-primary text-on-primary'
                        : 'bg-soft text-text hover:bg-soft/80'
                    }`}
                  >
                    {c.name} ({c.side === 'right' ? 'Tôi' : 'Bạn'})
                  </button>
                ))}
              </div>
            </div>

            {/* Nội dung tin nhắn */}
            <div className="mt-4">
              <div className="flex items-center justify-between">
                <label className="text-tiny font-semibold text-muted">Lời nhắn:</label>
                <span
                  className={`text-tiny font-bold tabular-nums ${
                    activeMsg.text.length > 300 ? 'text-danger' : 'text-muted'
                  }`}
                >
                  {activeMsg.text.length}/300
                </span>
              </div>
              <textarea
                value={activeMsg.text}
                onChange={(e) => handleTextChange(e.target.value)}
                rows={3}
                maxLength={300}
                className="mt-1.5 w-full resize-none rounded-xl border border-line bg-soft-2 p-3 text-body font-medium outline-none focus:border-text focus:ring-2 focus:ring-accent"
              />
            </div>

            {/* Ảnh / Video minh họa trong luồng chat */}
            <div className="mt-4 rounded-xl border border-line bg-soft-2 p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-tiny font-semibold text-muted">Ảnh / Video minh họa:</span>
                <div className="flex items-center gap-2">
                  <label className="cursor-pointer rounded-full bg-soft px-3 py-1 text-tiny font-bold text-text hover:bg-soft/80">
                    Đính kèm Ảnh / Video
                    <input
                      type="file"
                      accept="image/*,video/mp4,video/quicktime,.gif"
                      className="hidden"
                      onChange={(e) => {
                        const f = e.target.files?.[0];
                        if (f) void handleMediaUpload(f);
                        e.target.value = '';
                      }}
                    />
                  </label>
                  {activeMsg.media_path && (
                    <button
                      type="button"
                      onClick={handleMediaClear}
                      className="rounded-full bg-danger/15 px-3 py-1 text-tiny font-bold text-danger"
                    >
                      Xóa media
                    </button>
                  )}
                </div>
              </div>
              {activeMsg.media_hint && (
                <p className="mt-1.5 text-tiny text-muted">
                  💡 Gợi ý AI: <span className="text-text">{activeMsg.media_hint}</span>
                </p>
              )}
              {activeMsg.media_path && (
                <p className="mt-1 text-tiny font-mono text-emerald-400">
                  Đã đính kèm ({activeMsg.media_type}): {activeMsg.media_path}
                </p>
              )}
            </div>

            {/* Thẻ tài nguyên Smart Asset Director (chỉ hiện khi tin nhắn có meme/sticker hoặc SFX) */}
            {(activeMsg.meme_id || activeMsg.sticker || activeMsg.sfx_id) && (
              <div className="mt-4 space-y-2 rounded-xl border border-line bg-soft-2 p-3">
                {(activeMsg.meme_id || activeMsg.sticker) && (
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex min-w-0 items-center gap-2 text-tiny">
                      <span className="font-semibold text-muted">
                        {vi.chatting.assetMemeLabel}:
                      </span>
                      <span className="truncate font-mono font-bold text-text">
                        {activeMsg.meme_id || activeMsg.sticker}
                      </span>
                      {activeMsg.asset_origin === 'online_fetched' && (
                        <span className="rounded-full bg-tint-yel px-2 py-0.5 text-[10px] font-bold text-on-tint-yel">
                          {vi.chatting.badgeNewlyFetched}
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-1.5">
                      <button
                        type="button"
                        disabled={isRerolling !== null}
                        onClick={() =>
                          void handleRerollAsset(activeMsg.meme_id ? 'meme' : 'sticker')
                        }
                        className="rounded-full bg-soft px-3 py-1 text-tiny font-bold text-text hover:bg-soft/80 disabled:opacity-50"
                      >
                        {isRerolling === 'meme'
                          ? vi.chatting.rerollingAsset
                          : vi.chatting.rerollAsset}
                      </button>
                      <button
                        type="button"
                        onClick={() => handleStickerChange(null)}
                        title={vi.chatting.clearAsset}
                        className="rounded-full bg-danger/15 px-2.5 py-1 text-tiny font-bold text-danger hover:bg-danger/25"
                      >
                        × {vi.chatting.clearAsset}
                      </button>
                    </div>
                  </div>
                )}

                {activeMsg.sfx_id && (
                  <div className="flex flex-wrap items-center justify-between gap-2 border-t border-line/50 pt-2">
                    <div className="flex min-w-0 items-center gap-2 text-tiny">
                      <span className="font-semibold text-muted">{vi.chatting.assetSfxLabel}:</span>
                      <span className="truncate font-mono font-bold text-text">
                        {activeMsg.sfx_id}
                      </span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <button
                        type="button"
                        disabled={isRerolling !== null}
                        onClick={() => void handleRerollAsset('sfx')}
                        className="rounded-full bg-soft px-3 py-1 text-tiny font-bold text-text hover:bg-soft/80 disabled:opacity-50"
                      >
                        {isRerolling === 'sfx'
                          ? vi.chatting.rerollingAsset
                          : vi.chatting.rerollAsset}
                      </button>
                      <button
                        type="button"
                        onClick={handleClearSfx}
                        title={vi.chatting.clearAsset}
                        className="rounded-full bg-danger/15 px-2.5 py-1 text-tiny font-bold text-danger hover:bg-danger/25"
                      >
                        × {vi.chatting.clearAsset}
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Chọn Sticker */}
            <div className="mt-4">
              <label className="text-tiny font-semibold text-muted">{vi.chatting.sticker}:</label>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                <button
                  type="button"
                  onClick={() => handleStickerChange(null)}
                  className={`rounded-full px-3 py-1 text-tiny font-bold transition-colors ${
                    !activeMsg.sticker
                      ? 'bg-primary text-on-primary'
                      : 'bg-soft text-text hover:bg-soft/80'
                  }`}
                >
                  {vi.chatting.noSticker}
                </button>
                {STICKER_TAGS.map((tag) => (
                  <button
                    key={tag}
                    type="button"
                    onClick={() => handleStickerChange(tag)}
                    className={`rounded-full px-3 py-1 text-tiny font-bold uppercase transition-colors ${
                      activeMsg.sticker === tag
                        ? 'bg-accent text-primary'
                        : 'bg-soft text-text hover:bg-soft/80'
                    }`}
                  >
                    {tag}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </main>

        {/* CỘT PHẢI (376px): Xem trước 9:16 + Nút Xuất */}
        <aside className="w-[376px] shrink-0 overflow-y-auto border-l border-line bg-bg/50 p-4">
          <PhonePreviewStage
            title="Xem trước"
            badgeText={
              doc.platform === 'instagram'
                ? '9:16 · Instagram iOS · 60fps'
                : '9:16 · Messenger iOS · 60fps'
            }
            safeZone={safeZone}
            onSafeZoneChange={setSafeZone}
            previewBusy={isRendering}
            exportBusy={isRendering}
            previewDisabled={isRendering}
            exportDisabled={isRendering}
            previewLabel={vi.chatting.exportFast}
            exportLabel={vi.chatting.exportFinal}
            onPreview={() => handleRender(true)}
            onExport={() => handleRender(false)}
            footer={
              <div className="space-y-2 text-center">
                {isRendering && (
                  <p className="num text-tiny font-bold text-engine-chatting">
                    Đang dựng video... {renderProgress ? `${renderProgress}%` : ''}
                  </p>
                )}
                {videoUrl && (
                  <a
                    href={videoUrl}
                    download
                    className="inline-block text-tiny font-bold text-engine-postv hover:underline"
                  >
                    {vi.chatting.download}
                  </a>
                )}
              </div>
            }
          >
            {videoUrl ? (
              <video
                key={videoUrl}
                ref={previewVideoRef}
                src={videoUrl}
                controls
                autoPlay={false}
                preload="metadata"
                className="h-full w-full object-cover"
              />
            ) : (
              <div className="flex h-full w-full items-center justify-center p-4 text-center text-tiny text-muted-on-dark">
                Chưa có video xem nhanh. Bấm &quot;Xem nhanh&quot; để dựng.
              </div>
            )}
          </PhonePreviewStage>
        </aside>
      </div>
      <SceneTimelineStrip
        items={doc.messages.map((m: ChatMessage, idx: number) => {
          const sender = doc.characters.find((c: ChatCharacter) => c.id === m.from);
          return {
            id: String(idx),
            index: idx + 1,
            title: sender?.name,
            summary: `${sender?.name ? `${sender.name}: ` : ''}${m.text}`,
            badge: m.sticker ? `[${m.sticker}]` : sender?.name,
          };
        })}
        selectedId={String(selectedMsgIndex)}
        onSelect={(id) => setSelectedMsgIndex(Number(id))}
        onAdd={handleAddMessage}
        addLabel="+ Thêm tin nhắn"
        onDelete={(id) => handleDeleteMessage(Number(id))}
      />
    </div>
  );
}
