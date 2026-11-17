import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../api/endpoints';
import { stickvApi } from '../api/stickv';
import type {
  StickvAspect,
  StickvBeat,
  StickvBoardType,
  StickvMotion,
  StickvProject,
  StickvSfxTag,
  StickvTheme,
} from '../api/types';
import { ErrorNote } from '../components/ErrorNote';
import { CopyIcon, PlusIcon, SparklesIcon, TrashIcon, UploadIcon } from '../components/icons';
import type { SafeZonePlatform } from '../components/SafeZoneOverlay';
import { PhonePreviewStage } from '../components/studio/PhonePreviewStage';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { useRenderJob } from '../hooks/renderJob';
import { useToast } from '../hooks/toast';

const DEFAULT_POSE_OPTIONS = [
  { id: 'explain', label: 'Giải thích' },
  { id: 'think', label: 'Suy nghĩ' },
  { id: 'shock', label: 'Bất ngờ / Sốc' },
  { id: 'happy', label: 'Vui vẻ' },
  { id: 'run', label: 'Chạy nhanh' },
  { id: 'rich', label: 'Giàu có' },
  { id: 'sad', label: 'Buồn bã' },
  { id: 'angry', label: 'Tức giận' },
];

const MOTIONS: { id: StickvMotion; label: string }[] = [
  { id: 'bounce', label: 'Nhún nhịp' },
  { id: 'slide_left', label: 'Trượt từ phải' },
  { id: 'slide_right', label: 'Trượt từ trái' },
  { id: 'shake', label: 'Rung mạnh' },
  { id: 'float', label: 'Lơ lửng' },
  { id: 'static', label: 'Đứng yên' },
];

const SFX_TAGS: { id: StickvSfxTag; label: string }[] = [
  { id: 'whoosh', label: 'Whoosh' },
  { id: 'pop', label: 'Pop' },
  { id: 'vine_boom', label: 'Vine Boom' },
  { id: 'ding', label: 'Ding' },
  { id: 'none', label: 'Không SFX' },
];

const BOARD_TYPES: { id: StickvBoardType; label: string }[] = [
  { id: 'bullets', label: 'Gạch đầu dòng' },
  { id: 'big_number', label: 'Con số lớn' },
  { id: 'comparison', label: 'So sánh 2 cột' },
  { id: 'flow_steps', label: 'Sơ đồ bước' },
  { id: 'none', label: 'Ẩn bảng' },
];

function makeEmptyBeat(index: number): StickvBeat {
  return {
    id: `b${String(index).padStart(3, '0')}`,
    chapter: 1,
    narration: '',
    pose: 'explain',
    facing: 'right',
    motion: 'bounce',
    sfx_tag: 'whoosh',
    board_type: 'bullets',
    board_title: '',
    board_data: { items: ['Ý chính 1'] },
    media_path: '',
    duration_sec: 0,
  };
}

export function StickvPage() {
  const qc = useQueryClient();
  const toast = useToast();
  const job = useRenderJob();

  const [selectedSlug, setSelectedSlug] = useState<string>('');
  const [draft, setDraft] = useState<StickvProject | null>(null);
  const [selectedBeatId, setSelectedBeatId] = useState<string>('');
  const [safeZone, setSafeZone] = useState<SafeZonePlatform>('none');
  const [rendering, setRendering] = useState(false);
  const [renderProgress, setRenderProgress] = useState<{ pct: number; step: string } | null>(null);
  const esRef = useRef<EventSource | null>(null);

  // 3 Chế độ kịch bản StickV
  const [inputMode, setInputMode] = useState<'ai' | 'json' | 'script'>('ai');
  const [idea, setIdea] = useState('');
  const [rawJson, setRawJson] = useState('');
  const [rawScript, setRawScript] = useState('');
  const [rawTitle, setRawTitle] = useState('');
  const [topic, setTopic] = useState('science');
  const [aspect, setAspect] = useState<StickvAspect>('9:16');
  const [theme, setTheme] = useState<StickvTheme>('cream');
  const [targetMinutes, setTargetMinutes] = useState<number>(1);
  const [geminiModel, setGeminiModel] = useState('');

  const listQuery = useQuery({
    queryKey: ['stickv-list'],
    queryFn: () => stickvApi.list(),
  });

  const stickmanQuery = useQuery({
    queryKey: ['asset-hub', 'stickman'],
    queryFn: () => api.listAssetHub('stickman'),
  });

  const voicesQuery = useQuery({
    queryKey: ['voices'],
    queryFn: () => api.listVoices(),
    retry: false,
  });

  const voiceOptions = useMemo(() => {
    const raw = voicesQuery.data?.voices ?? [];
    if (raw.length === 0) {
      return [{ id: 'Thanh Bình', label: 'Thanh Bình (Mặc định)' }];
    }
    return raw.map((v) => ({
      id: String(v.id),
      label: String(v.label || v.id),
    }));
  }, [voicesQuery.data?.voices]);

  const defaultVoiceId = useMemo(() => {
    if (voiceOptions.some((v) => v.id === 'Thanh Bình')) return 'Thanh Bình';
    return voiceOptions[0]?.id ?? 'Thanh Bình';
  }, [voiceOptions]);

  const models = useMemo(
    () =>
      (listQuery.data?.gemini_models ?? []).map((m) =>
        typeof m === 'string'
          ? { id: m, name: m }
          : { id: String(m.id ?? ''), name: String(m.name || m.id || '') },
      ),
    [listQuery.data?.gemini_models],
  );
  const projects = useMemo(() => listQuery.data?.items ?? [], [listQuery.data?.items]);

  useEffect(() => {
    if (!geminiModel && listQuery.data?.default_model) {
      setGeminiModel(listQuery.data.default_model);
    }
  }, [geminiModel, listQuery.data?.default_model]);

  useEffect(() => {
    if (!selectedSlug && projects.length > 0) {
      setSelectedSlug(projects[0].slug);
    }
  }, [selectedSlug, projects]);

  useEffect(() => {
    const found = projects.find((p) => p.slug === selectedSlug) ?? null;
    if (found) {
      setDraft(found);
      if (found.beats.length > 0 && !found.beats.some((b) => b.id === selectedBeatId)) {
        setSelectedBeatId(found.beats[0].id);
      }
    }
  }, [selectedSlug, projects, selectedBeatId]);

  const activeBeat = useMemo(
    () => draft?.beats.find((b) => b.id === selectedBeatId) ?? draft?.beats[0] ?? null,
    [draft, selectedBeatId],
  );

  const poseOptions = useMemo(() => {
    const custom = (stickmanQuery.data?.items ?? [])
      .filter((it) => !DEFAULT_POSE_OPTIONS.some((d) => `${d.id}.png` === it.name))
      .map((it) => ({ id: it.name, label: it.title || it.name, url: it.url }));
    return [
      ...DEFAULT_POSE_OPTIONS.map((d) => ({
        ...d,
        url:
          stickmanQuery.data?.items.find((it) => it.name === `${d.id}.png`)?.url ??
          `/api/asset-hub/file/library/stickman/poses/${d.id}.png`,
      })),
      ...custom,
    ];
  }, [stickmanQuery.data?.items]);

  const genMutation = useMutation({
    mutationFn: () =>
      stickvApi.generate({
        idea: idea.trim(),
        topic,
        aspect,
        theme,
        target_minutes: targetMinutes,
        model: geminiModel,
      }),
    onSuccess: ({ project }) => {
      void qc.invalidateQueries({ queryKey: ['stickv-list'] });
      setSelectedSlug(project.slug);
      setDraft(project);
      setSelectedBeatId(project.beats[0]?.id ?? '');
      toast.info(`Đã sinh ${project.beats.length} beat kịch bản StickV`);
    },
    onError: (e: Error) => toast.error(e),
  });

  const importJsonMutation = useMutation({
    mutationFn: () =>
      stickvApi.importJson({
        raw_json: rawJson.trim(),
        topic,
        aspect,
        theme,
      }),
    onSuccess: ({ project }) => {
      void qc.invalidateQueries({ queryKey: ['stickv-list'] });
      setSelectedSlug(project.slug);
      setDraft(project);
      setSelectedBeatId(project.beats[0]?.id ?? '');
      setRawJson('');
      toast.info(`Đã nạp ${project.beats.length} beat từ JSON (0 Token API)`);
    },
    onError: (e: Error) => toast.error(e),
  });

  const importScriptMutation = useMutation({
    mutationFn: () =>
      stickvApi.importScript({
        raw_text: rawScript.trim(),
        title: rawTitle.trim(),
        topic,
        aspect,
        theme,
      }),
    onSuccess: ({ project }) => {
      void qc.invalidateQueries({ queryKey: ['stickv-list'] });
      setSelectedSlug(project.slug);
      setDraft(project);
      setSelectedBeatId(project.beats[0]?.id ?? '');
      setRawScript('');
      toast.info(`Đã tách ${project.beats.length} beat từ lời thoại có sẵn`);
    },
    onError: (e: Error) => toast.error(e),
  });

  const saveMutation = useMutation({
    mutationFn: (proj: StickvProject) => stickvApi.save(proj.slug, proj),
    onSuccess: ({ project }) => {
      setDraft(project);
      void qc.invalidateQueries({ queryKey: ['stickv-list'] });
      toast.info('Đã lưu dự án StickV');
    },
    onError: (e: Error) => toast.error(e),
  });

  const deleteMutation = useMutation({
    mutationFn: (slug: string) => stickvApi.remove(slug),
    onSuccess: () => {
      setSelectedSlug('');
      setDraft(null);
      void qc.invalidateQueries({ queryKey: ['stickv-list'] });
      toast.info('Đã xóa dự án StickV');
    },
  });

  const renderMutation = useMutation({
    mutationFn: async (preview: boolean) => {
      if (!draft) throw new Error('Chưa có dự án để dựng');
      await stickvApi.save(draft.slug, draft);
      return stickvApi.render(draft.slug, preview);
    },
    onSuccess: ({ job_id }) => {
      setRendering(true);
      setRenderProgress({ pct: 2, step: 'Đang khởi động...' });
      toast.info('Đã đưa StickV vào hàng đợi dựng');
      if (typeof EventSource !== 'undefined') {
        esRef.current?.close();
        const es = new EventSource(`/api/jobs/${encodeURIComponent(job_id)}/events`);
        esRef.current = es;
        es.addEventListener('progress', (ev) => {
          try {
            const d = JSON.parse((ev as MessageEvent).data) as {
              progress?: number;
              step?: string;
              text?: string;
            };
            setRenderProgress({
              pct: Math.round(d.progress ?? 0),
              step: d.text || d.step || 'Đang dựng...',
            });
          } catch {
            // ignore
          }
        });
        es.addEventListener('end', (ev) => {
          es.close();
          esRef.current = null;
          setRendering(false);
          setRenderProgress(null);
          try {
            const d = JSON.parse((ev as MessageEvent).data) as { status?: string; error?: string };
            if (d.status === 'done') {
              void qc.invalidateQueries({ queryKey: ['stickv-list'] });
              void qc.invalidateQueries({ queryKey: ['unified-renders'] });
              toast.info('Đã dựng xong video StickV!');
            } else if (d.status === 'failed') {
              toast.error(d.error || 'Dựng video StickV thất bại');
            }
          } catch {
            void qc.invalidateQueries({ queryKey: ['stickv-list'] });
          }
        });
        es.onerror = () => {
          es.close();
          esRef.current = null;
          setRendering(false);
        };
      }
    },
    onError: (e: Error) => toast.error(e),
  });

  useEffect(() => () => esRef.current?.close(), []);

  const updateBeat = (beatId: string, patch: Partial<StickvBeat>) => {
    if (!draft) return;
    setDraft({
      ...draft,
      beats: draft.beats.map((b) => (b.id === beatId ? { ...b, ...patch } : b)),
    });
  };

  const handleUploadBeatMedia = async (beatId: string, file: File) => {
    if (!draft) return;
    try {
      const res = await stickvApi.uploadBeatMedia(draft.slug, beatId, file);
      setDraft(res.project);
      toast.info(`Đã đính kèm media cho ${beatId}`);
    } catch (e) {
      toast.error(e);
    }
  };

  const currentPoseUrl =
    poseOptions.find((p) => p.id === activeBeat?.pose)?.url ??
    `/api/asset-hub/file/library/stickman/poses/explain.png`;

  return (
    <div className="mx-auto max-w-[1440px] space-y-6 pb-10">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <span className="inline-flex items-center gap-1.5 rounded-pill bg-engine-stickv-soft px-3 py-1 text-tiny font-extrabold text-on-engine-stickv-soft">
            <SparklesIcon size={14} />
            StickV · Động cơ Người que 2D/2.5D
          </span>
          <h1 className="mt-2 text-h1 font-extrabold tracking-tight text-text">
            Xưởng Video Người Que (Shorts 9:16 & Longform 16:9)
          </h1>
        </div>

        {projects.length > 0 && (
          <div className="flex items-center gap-2">
            <select
              aria-label="Chọn dự án StickV"
              value={selectedSlug}
              onChange={(e) => setSelectedSlug(e.target.value)}
              className="rounded-input border border-line-input bg-card px-3 py-2 text-small font-semibold text-text"
            >
              {projects.map((p) => (
                <option key={p.slug} value={p.slug}>
                  {p.title} ({p.aspect})
                </option>
              ))}
            </select>
            {draft && (
              <Button
                tone="soft"
                size="sm"
                icon={<TrashIcon size={14} />}
                onClick={() => deleteMutation.mutate(draft.slug)}
                aria-label="Xóa dự án StickV"
              >
                Xóa
              </Button>
            )}
          </div>
        )}
      </header>

      {listQuery.isError && <ErrorNote error={listQuery.error} />}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1.35fr_380px]">
        {/* Cột trái: Sinh kịch bản AI + Danh sách Beat */}
        <div className="space-y-5">
          <Card className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-title font-bold text-text">1. Kịch bản StickV (3 Chế độ)</h2>
              <div
                role="tablist"
                aria-label="Chế độ đầu vào StickV"
                className="inline-flex rounded-pill border border-line bg-soft p-0.5 text-tiny font-bold"
              >
                {(
                  [
                    { id: 'ai', label: 'Tạo tự động (API)' },
                    { id: 'json', label: 'Dán JSON (0 Token)' },
                    { id: 'script', label: 'Dán Lời thoại' },
                  ] as const
                ).map((t) => (
                  <button
                    key={t.id}
                    type="button"
                    role="tab"
                    aria-selected={inputMode === t.id}
                    onClick={() => setInputMode(t.id)}
                    className={`rounded-pill px-3 py-1 transition-colors ${
                      inputMode === t.id
                        ? 'bg-card text-text shadow-sm'
                        : 'text-muted hover:text-text'
                    }`}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
            </div>

            {inputMode === 'ai' && (
              <textarea
                value={idea}
                onChange={(e) => setIdea(e.target.value)}
                rows={2}
                placeholder="Nhập ý tưởng video (vd: Tại sao 90% người mới đầu tư hay mất tiền?)"
                className="w-full rounded-input border border-line-input bg-soft-2 p-3 text-small text-text focus:border-engine-stickv focus:outline-none"
              />
            )}

            {inputMode === 'json' && (
              <div className="space-y-2.5">
                <div className="flex flex-wrap items-center justify-between gap-2 rounded-inner border border-engine-stickv/30 bg-engine-stickv-soft/40 p-3">
                  <span className="text-tiny font-semibold text-text-2">
                    Copy Prompt Đạo diễn 5 chặng sang Web Gemini Pro rồi dán JSON vào đây (0 Token
                    API):
                  </span>
                  <Button
                    tone="soft"
                    size="sm"
                    icon={<CopyIcon size={14} />}
                    onClick={() => {
                      const prompt =
                        listQuery.data?.director_prompt ||
                        'Biên kịch StickV 5 chặng -> trả về JSON {title, beats}';
                      void navigator.clipboard
                        .writeText(prompt)
                        .then(() => toast.info('Đã copy Prompt Đạo diễn!'))
                        .catch((err) => toast.error(err));
                    }}
                  >
                    Copy Prompt Đạo diễn
                  </Button>
                </div>
                <textarea
                  value={rawJson}
                  onChange={(e) => setRawJson(e.target.value)}
                  rows={4}
                  placeholder='Dán JSON từ Web Gemini Pro (vd: {"title":"...","beats":[...]})'
                  className="w-full rounded-input border border-line-input bg-soft-2 p-3 font-mono text-tiny text-text focus:border-engine-stickv focus:outline-none"
                />
              </div>
            )}

            {inputMode === 'script' && (
              <div className="space-y-2.5">
                <input
                  type="text"
                  value={rawTitle}
                  onChange={(e) => setRawTitle(e.target.value)}
                  placeholder="Tiêu đề video (không bắt buộc)..."
                  className="w-full rounded-input border border-line-input bg-soft-2 px-3 py-2 text-small text-text focus:border-engine-stickv focus:outline-none"
                />
                <textarea
                  value={rawScript}
                  onChange={(e) => setRawScript(e.target.value)}
                  rows={4}
                  placeholder="Dán lời thoại có sẵn (mỗi câu hoặc mỗi dòng sẽ tự tách thành 1 beat + gắn dáng người que & bảng)..."
                  className="w-full rounded-input border border-line-input bg-soft-2 p-3 text-small text-text focus:border-engine-stickv focus:outline-none"
                />
              </div>
            )}

            <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
              <label className="space-y-1 text-tiny font-bold text-muted">
                <span>Khung hình</span>
                <select
                  value={aspect}
                  onChange={(e) => setAspect(e.target.value as StickvAspect)}
                  className="w-full rounded-input border border-line-input bg-card px-2.5 py-2 text-small text-text"
                >
                  <option value="9:16">9:16 Shorts</option>
                  <option value="16:9">16:9 YouTube</option>
                </select>
              </label>

              <label className="space-y-1 text-tiny font-bold text-muted">
                <span>Chủ đề màu</span>
                <select
                  value={theme}
                  onChange={(e) => setTheme(e.target.value as StickvTheme)}
                  className="w-full rounded-input border border-line-input bg-card px-2.5 py-2 text-small text-text"
                >
                  <option value="cream">Giấy kem (#FAF7F0)</option>
                  <option value="dark">Bảng tối (#111827)</option>
                </select>
              </label>

              <label className="space-y-1 text-tiny font-bold text-muted">
                <span>Thời lượng</span>
                <select
                  value={targetMinutes}
                  onChange={(e) => setTargetMinutes(Number(e.target.value))}
                  className="w-full rounded-input border border-line-input bg-card px-2.5 py-2 text-small text-text"
                >
                  <option value={1}>~1 phút (Shorts)</option>
                  <option value={3}>~3 phút</option>
                  <option value={5}>~5 phút (Long)</option>
                  <option value={10}>~10 phút (Long)</option>
                  <option value={15}>~15 phút (Long)</option>
                </select>
              </label>

              <label className="space-y-1 text-tiny font-bold text-muted">
                <span>Nhóm nhạc</span>
                <select
                  value={topic}
                  onChange={(e) => setTopic(e.target.value)}
                  className="w-full rounded-input border border-line-input bg-card px-2.5 py-2 text-small text-text"
                >
                  <option value="science">Khoa học / Chill</option>
                  <option value="fun">Vui nhộn</option>
                  <option value="history">Kịch tính</option>
                  <option value="mystery">Bí ẩn</option>
                </select>
              </label>

              <label className="space-y-1 text-tiny font-bold text-muted">
                <span>Model Gemini</span>
                <select
                  aria-label="Chọn model Gemini"
                  value={geminiModel}
                  onChange={(e) => setGeminiModel(e.target.value)}
                  className="w-full rounded-input border border-line-input bg-card px-2.5 py-2 text-small text-text"
                >
                  {models.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.name}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <div className="flex justify-end">
              {inputMode === 'ai' && (
                <Button
                  tone="export"
                  busy={genMutation.isPending}
                  disabled={!idea.trim()}
                  icon={<SparklesIcon size={16} />}
                  onClick={() => genMutation.mutate()}
                >
                  Sinh kịch bản StickV
                </Button>
              )}
              {inputMode === 'json' && (
                <Button
                  tone="export"
                  busy={importJsonMutation.isPending}
                  disabled={!rawJson.trim()}
                  icon={<SparklesIcon size={16} />}
                  onClick={() => importJsonMutation.mutate()}
                >
                  Nạp JSON (0 Token)
                </Button>
              )}
              {inputMode === 'script' && (
                <Button
                  tone="export"
                  busy={importScriptMutation.isPending}
                  disabled={!rawScript.trim()}
                  icon={<SparklesIcon size={16} />}
                  onClick={() => importScriptMutation.mutate()}
                >
                  Tách lời thoại thành Beat
                </Button>
              )}
            </div>
          </Card>

          {draft && (
            <Card className="space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h2 className="text-title font-bold text-text">
                    2. Kịch bản từng Beat ({draft.beats.length} beat)
                  </h2>
                  <p className="text-tiny text-muted">
                    Mỗi beat tự neo thời gian theo giọng VieNeu-TTS + SFX + Bảng minh họa
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <select
                    aria-label="Chọn giọng đọc VieNeu"
                    value={
                      voiceOptions.some((v) => v.id === draft.voice_id)
                        ? draft.voice_id
                        : defaultVoiceId
                    }
                    onChange={(e) => setDraft({ ...draft, voice_id: e.target.value })}
                    className="rounded-input border border-line-input bg-card px-2.5 py-1.5 text-tiny font-semibold text-text"
                  >
                    {voiceOptions.map((v) => (
                      <option key={v.id} value={v.id}>
                        Giọng: {v.label}
                      </option>
                    ))}
                  </select>
                  <Button
                    tone="soft"
                    size="sm"
                    icon={<PlusIcon size={14} />}
                    onClick={() => {
                      const next = makeEmptyBeat(draft.beats.length + 1);
                      setDraft({ ...draft, beats: [...draft.beats, next] });
                      setSelectedBeatId(next.id);
                    }}
                  >
                    Thêm Beat
                  </Button>
                  <Button
                    tone="primary"
                    size="sm"
                    busy={saveMutation.isPending}
                    onClick={() => saveMutation.mutate(draft)}
                  >
                    Lưu thay đổi
                  </Button>
                </div>
              </div>

              <div className="space-y-3">
                {draft.beats.map((beat, idx) => {
                  const isSel = activeBeat?.id === beat.id;
                  return (
                    <div
                      key={beat.id}
                      onClick={() => setSelectedBeatId(beat.id)}
                      className={`cursor-pointer rounded-inner border p-3.5 transition-colors ${
                        isSel
                          ? 'border-engine-stickv bg-engine-stickv-soft/40'
                          : 'border-line bg-soft-2/50 hover:border-line-input'
                      }`}
                    >
                      <div className="mb-2 flex items-center justify-between gap-2">
                        <span className="rounded-pill bg-card px-2.5 py-0.5 text-tiny font-extrabold text-text shadow-sm">
                          #{idx + 1} · Chương {beat.chapter} ({beat.id})
                        </span>
                        <div className="flex items-center gap-2">
                          <label className="inline-flex cursor-pointer items-center gap-1 rounded-pill bg-card px-2.5 py-1 text-tiny font-semibold text-text-2 hover:bg-soft">
                            <UploadIcon size={12} />
                            <span>{beat.media_path ? 'Đổi clip/ảnh' : 'Chèn clip .mp4/ảnh'}</span>
                            <input
                              type="file"
                              accept=".png,.jpg,.jpeg,.webp,.mp4,.mov,.webm"
                              className="hidden"
                              onChange={(e) => {
                                const f = e.target.files?.[0];
                                if (f) void handleUploadBeatMedia(beat.id, f);
                              }}
                            />
                          </label>
                          {draft.beats.length > 1 && (
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                setDraft({
                                  ...draft,
                                  beats: draft.beats.filter((x) => x.id !== beat.id),
                                });
                              }}
                              className="rounded-pill p-1 text-muted hover:text-danger"
                              aria-label={`Xóa beat ${beat.id}`}
                            >
                              <TrashIcon size={14} />
                            </button>
                          )}
                        </div>
                      </div>

                      <textarea
                        value={beat.narration}
                        onChange={(e) => updateBeat(beat.id, { narration: e.target.value })}
                        rows={2}
                        placeholder="Lời đọc tiếng Việt cho beat này..."
                        className="w-full rounded-input border border-line-input bg-card p-2 text-small text-text"
                      />

                      <div className="mt-2.5 grid grid-cols-2 gap-2 sm:grid-cols-5">
                        <select
                          aria-label="Dáng người que"
                          value={beat.pose}
                          onChange={(e) => updateBeat(beat.id, { pose: e.target.value })}
                          className="rounded-input border border-line-input bg-card px-2 py-1.5 text-tiny font-semibold text-text"
                        >
                          {poseOptions.map((p) => (
                            <option key={p.id} value={p.id}>
                              Dáng: {p.label}
                            </option>
                          ))}
                        </select>

                        <select
                          aria-label="Hướng nhìn"
                          value={beat.facing}
                          onChange={(e) =>
                            updateBeat(beat.id, { facing: e.target.value as 'left' | 'right' })
                          }
                          className="rounded-input border border-line-input bg-card px-2 py-1.5 text-tiny font-semibold text-text"
                        >
                          <option value="right">Quay phải →</option>
                          <option value="left">← Quay trái</option>
                        </select>

                        <select
                          aria-label="Chuyển động"
                          value={beat.motion}
                          onChange={(e) =>
                            updateBeat(beat.id, { motion: e.target.value as StickvMotion })
                          }
                          className="rounded-input border border-line-input bg-card px-2 py-1.5 text-tiny font-semibold text-text"
                        >
                          {MOTIONS.map((m) => (
                            <option key={m.id} value={m.id}>
                              {m.label}
                            </option>
                          ))}
                        </select>

                        <select
                          aria-label="Âm thanh SFX"
                          value={beat.sfx_tag}
                          onChange={(e) =>
                            updateBeat(beat.id, { sfx_tag: e.target.value as StickvSfxTag })
                          }
                          className="rounded-input border border-line-input bg-card px-2 py-1.5 text-tiny font-semibold text-text"
                        >
                          {SFX_TAGS.map((s) => (
                            <option key={s.id} value={s.id}>
                              SFX: {s.label}
                            </option>
                          ))}
                        </select>

                        <select
                          aria-label="Loại bảng minh họa"
                          value={beat.board_type}
                          onChange={(e) =>
                            updateBeat(beat.id, { board_type: e.target.value as StickvBoardType })
                          }
                          className="rounded-input border border-line-input bg-card px-2 py-1.5 text-tiny font-semibold text-text"
                        >
                          {BOARD_TYPES.map((bt) => (
                            <option key={bt.id} value={bt.id}>
                              Bảng: {bt.label}
                            </option>
                          ))}
                        </select>
                      </div>
                    </div>
                  );
                })}
              </div>
            </Card>
          )}
        </div>

        {/* Cột phải: PhonePreviewStage 9:16 / 16:9 */}
        <div className="space-y-4">
          <PhonePreviewStage
            title="Sân khấu StickV"
            badgeText={draft ? `${draft.theme === 'cream' ? 'Kem ấm' : 'Bảng tối'}` : 'Sẵn sàng'}
            safeZone={safeZone}
            onSafeZoneChange={setSafeZone}
            aspect={draft?.aspect ?? aspect}
            onAspectChange={(nextAspect) => {
              setAspect(nextAspect);
              if (draft) setDraft({ ...draft, aspect: nextAspect });
            }}
            estimateText={
              renderProgress
                ? `${renderProgress.pct}% · ${renderProgress.step}`
                : draft
                  ? `${draft.beats.length} beat · ${draft.aspect} · ${draft.fps}fps`
                  : 'Chưa chọn dự án'
            }
            previewBusy={renderMutation.isPending || rendering || job.running}
            exportBusy={renderMutation.isPending || rendering || job.running}
            previewDisabled={!draft || draft.beats.length === 0 || rendering || job.running}
            exportDisabled={!draft || draft.beats.length === 0 || rendering || job.running}
            onPreview={() => renderMutation.mutate(true)}
            onExport={() => renderMutation.mutate(false)}
            exportLabel={`Xuất bản đẹp (${(draft?.aspect ?? aspect) === '16:9' ? '1920×1080' : '1080×1920'})`}
          >
            {draft?.last_render?.video_url ? (
              <video
                key={draft.last_render.video_url}
                src={draft.last_render.video_url}
                controls
                className="h-full w-full object-contain bg-black"
              />
            ) : (
              <div
                className={`flex h-full w-full flex-col justify-between p-4 ${
                  (draft?.theme ?? theme) === 'cream'
                    ? 'bg-[#FAF7F0] text-slate-900'
                    : 'bg-[#111827] text-slate-50'
                }`}
              >
                <div className="rounded-xl border border-black/10 bg-white/80 p-3 text-slate-900 shadow-sm">
                  <p className="text-[11px] font-extrabold text-amber-600 uppercase">
                    {activeBeat?.board_type ?? 'bullets'}
                  </p>
                  <p className="mt-1 text-xs font-bold">
                    {activeBeat?.board_title || draft?.title || 'Bảng minh họa thông minh'}
                  </p>
                  <p className="mt-1 line-clamp-2 text-[11px] text-slate-600">
                    {activeBeat?.narration || 'Sinh kịch bản hoặc chọn beat để xem trước...'}
                  </p>
                </div>

                <div className="flex flex-1 items-end justify-center pb-2">
                  <img
                    src={currentPoseUrl}
                    alt={activeBeat?.pose ?? 'explain'}
                    className={`h-32 w-auto object-contain ${
                      activeBeat?.facing === 'left' ? '-scale-x-100' : ''
                    }`}
                  />
                </div>
              </div>
            )}
          </PhonePreviewStage>
        </div>
      </div>
    </div>
  );
}
