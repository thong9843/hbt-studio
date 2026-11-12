import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { ApiError } from '../../api/client';
import { api } from '../../api/endpoints';
import type {
  HbtCoreGeminiModel,
  HbtCoreScript,
  HbtCoreSegment,
  HbtCoreTopic,
} from '../../api/types';
import { useToast } from '../../hooks/toast';
import { vi } from '../../i18n/vi';
import { AlertIcon, PlayIcon } from '../icons';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { Dialog } from '../ui/Dialog';
import { Input, Textarea } from '../ui/Field';
import { Progress } from '../ui/Progress';

const T = vi.hbtCore;

const DEFAULT_GEMINI_MODELS: HbtCoreGeminiModel[] = [
  { id: 'gemini-3.8-flash', name: 'Gemini 3.8 Flash (Mặc định / Nhanh)' },
  { id: 'gemini-3.6-flash', name: 'Gemini 3.6 Flash' },
  { id: 'gemini-3.5-flash-lite', name: 'Gemini 3.5 Flash Lite (Nhẹ / Tiết kiệm)' },
  { id: 'gemini-3.1-flash-lite', name: 'Gemini 3.1 Flash Lite' },
];

const STICKER_PRESETS = ['question', 'shock', 'laugh', 'think', 'check', 'warning'] as const;

const SAMPLE_V1_SCRIPT: HbtCoreScript = {
  title: 'Vì sao Đấu trường La Mã vẫn đứng vững sau 2000 năm?',
  topic: 'history',
  total_segments: 3,
  segments: [
    {
      id: 1,
      order: 1,
      title: 'BÍ MẬT ĐẤU TRƯỜNG LA MÃ',
      text: 'Bạn có biết vì sao Đấu trường La Mã trải qua hàng chục trận động đất mà vẫn hiên ngang suốt hai thiên niên kỷ?',
      sticker: 'shock',
      image_prompt:
        'Cinematic shot of ancient Roman Colosseum under dramatic golden hour sunlight, ultra realistic, highly detailed historical atmosphere, 9:16 vertical framing',
      image: 'scene-01.png',
      sfx: 'impact',
    },
    {
      id: 2,
      order: 2,
      title: 'BÊ TÔNG TỰ LIỀN VẾT NỨT',
      text: 'Nhưng khoan đã, bí mật thực sự nằm ở loại bê tông tro núi lửa Pozzolana kết hợp với vôi sống tự liền vết nứt khi gặp nước mưa.',
      sticker: 'think',
      image_prompt:
        'Close-up cinematic shot of ancient Roman pozzolanic volcanic ash concrete texture with subtle golden light rays, photorealistic, 9:16 vertical framing',
      image: 'scene-02.png',
      sfx: 'pop',
    },
    {
      id: 3,
      order: 3,
      title: 'THEO DÕI HAY BIẾT TỐT',
      text: 'Theo bạn công trình cổ đại nào bền bỉ nhất? Hãy bình luận bên dưới và theo dõi Hay Biết Tốt trên TikTok và YouTube nhé!',
      sticker: 'question',
      image_prompt:
        'Wide aerial twilight shot of illuminated Roman Colosseum with starry sky, epic atmosphere, ultra detailed, 9:16 vertical framing',
      image: 'scene-03.png',
      sfx: 'whoosh',
    },
  ],
};

interface Props {
  open: boolean;
  onClose: () => void;
  /** Nếu mở từ trong một dự án đang có sẵn (`/p/:slug`). */
  slug?: string;
}

interface VoiceProgressDetail {
  current: number;
  total: number;
  percent: number;
}

export function HbtCoreStudioDialog({ open, onClose, slug: initialSlug }: Props) {
  const toast = useToast();
  const queryClient = useQueryClient();

  const [mode, setMode] = useState<'v1' | 'v2'>('v1');
  const [title, setTitle] = useState(SAMPLE_V1_SCRIPT.title);
  const [topic, setTopic] = useState<HbtCoreTopic>('history');
  const [segments, setSegments] = useState<HbtCoreSegment[]>(SAMPLE_V1_SCRIPT.segments);
  const [jsonText, setJsonText] = useState(() => JSON.stringify(SAMPLE_V1_SCRIPT, null, 2));
  const [jsonError, setJsonError] = useState<string | null>(null);

  // V2 state
  const [prompt, setPrompt] = useState('');
  const [v2Topic, setV2Topic] = useState<HbtCoreTopic>('history');
  const [selectedModel, setSelectedModel] = useState('gemini-3.8-flash');
  const [v2Loading, setV2Loading] = useState(false);
  const [fallbackNotice, setFallbackNotice] = useState<string | null>(null);

  // Render & SSE state
  const [rendering, setRendering] = useState(false);
  const [progressPct, setProgressPct] = useState(0);
  const [progressStep, setProgressStep] = useState('');
  const [progressMsg, setProgressMsg] = useState('');
  const [voiceDetail, setVoiceDetail] = useState<VoiceProgressDetail | null>(null);
  const [resultVideoUrl, setResultVideoUrl] = useState<string | null>(null);
  const [resultSlug, setResultSlug] = useState<string | null>(initialSlug ?? null);
  const [renderError, setRenderError] = useState<string | null>(null);

  const esRef = useRef<EventSource | null>(null);

  const { data: assets } = useQuery({
    queryKey: ['hbt-core-assets', resultSlug ?? initialSlug ?? ''],
    queryFn: () => api.getHbtCoreAssets(resultSlug ?? initialSlug),
    enabled: open,
  });

  const { data: modelsData } = useQuery({
    queryKey: ['hbt-core-models'],
    queryFn: () => api.getHbtCoreModels(),
    enabled: open,
    retry: false,
  });

  useEffect(() => {
    if (!open || !initialSlug) return;
    let active = true;
    api
      .getProjectCoreScript(initialSlug)
      .then((res) => {
        if (!active) return;
        const sc = res.script;
        setTitle(sc.title);
        setTopic((sc.topic as HbtCoreTopic) || 'science');
        setSegments(sc.segments);
        setJsonText(JSON.stringify(sc, null, 2));
        setResultSlug(initialSlug);
      })
      .catch(() => {
        // Nếu dự án chưa có core_script thì giữ mẫu mặc định
      });
    return () => {
      active = false;
    };
  }, [open, initialSlug]);

  useEffect(() => {
    return () => {
      if (esRef.current) {
        esRef.current.close();
        esRef.current = null;
      }
    };
  }, []);

  const syncEditorToJsonText = (
    nextTitle: string,
    nextTopic: string,
    nextSegments: HbtCoreSegment[],
  ) => {
    const normalized: HbtCoreSegment[] = nextSegments.map((s, idx) => ({
      id: idx + 1,
      order: idx + 1,
      title: s.title ?? '',
      text: s.text,
      sticker: s.sticker || 'question',
      image_prompt: s.image_prompt ?? '',
      image: s.image,
      sfx: s.sfx || 'whoosh',
    }));
    const doc: HbtCoreScript = {
      title: nextTitle,
      topic: nextTopic,
      total_segments: normalized.length,
      segments: normalized,
    };
    setJsonText(JSON.stringify(doc, null, 2));
    setJsonError(null);
  };

  const applyJsonTextareaToSegments = (): HbtCoreScript | null => {
    try {
      const parsed = JSON.parse(jsonText) as Partial<HbtCoreScript>;
      if (!parsed || typeof parsed !== 'object') {
        throw new Error('JSON phải là đối tượng { topic, total_segments, segments }');
      }
      const rawTopicStr = String(parsed.topic ?? '').trim();
      const nextTitle = String(parsed.title ?? rawTopicStr).trim();
      if (!nextTitle) {
        throw new Error('Thiếu trường "topic" hoặc "title" trong JSON');
      }
      const rawTopic = (rawTopicStr || 'science').toLowerCase();
      const validTopic: HbtCoreTopic = (
        ['history', 'fun', 'science', 'mystery'].includes(rawTopic) ? rawTopic : 'science'
      ) as HbtCoreTopic;
      if (!Array.isArray(parsed.segments) || parsed.segments.length === 0) {
        throw new Error('Trường "segments" phải là mảng có ít nhất 1 phân đoạn');
      }
      const nextSegs: HbtCoreSegment[] = parsed.segments.map((item, idx) => {
        const orderNum = Number(item?.id ?? item?.order ?? idx + 1) || idx + 1;
        return {
          id: orderNum,
          order: idx + 1,
          title: String(item?.title ?? item?.card_text ?? '').trim(),
          text: String(item?.text ?? '').trim(),
          sticker: String(item?.sticker ?? 'question').trim() || 'question',
          image_prompt: String(item?.image_prompt ?? '').trim(),
          image: String(item?.image ?? `scene-${String(idx + 1).padStart(2, '0')}.png`).trim(),
          sfx: String(item?.sfx ?? 'whoosh').trim() || 'whoosh',
        };
      });
      if (!nextSegs.some((s) => s.text.length > 0)) {
        throw new Error('Cần ít nhất 1 phân đoạn có lời thoại "text"');
      }
      setTitle(nextTitle);
      setTopic(validTopic);
      setSegments(nextSegs);
      setJsonError(null);
      return {
        title: nextTitle,
        topic: rawTopicStr || validTopic,
        total_segments: nextSegs.length,
        segments: nextSegs,
      };
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Khối JSON không hợp lệ';
      setJsonError(msg);
      return null;
    }
  };

  const updateSegment = (index: number, patch: Partial<HbtCoreSegment>) => {
    const next = segments.map((s, i) => (i === index ? { ...s, ...patch } : s));
    setSegments(next);
    syncEditorToJsonText(title, topic, next);
  };

  const addSegment = () => {
    const nextOrder = segments.length + 1;
    const next: HbtCoreSegment[] = [
      ...segments,
      {
        id: nextOrder,
        order: nextOrder,
        title: '',
        text: '',
        sticker: 'question',
        image_prompt: '',
        image: `scene-${String(nextOrder).padStart(2, '0')}.png`,
        sfx: 'whoosh',
      },
    ];
    setSegments(next);
    syncEditorToJsonText(title, topic, next);
  };

  const removeSegment = (index: number) => {
    if (segments.length <= 1) return;
    const next = segments.filter((_, i) => i !== index).map((s, idx) => ({ ...s, order: idx + 1 }));
    setSegments(next);
    syncEditorToJsonText(title, topic, next);
  };

  const connectJobSse = (jobId: string, targetSlug: string) => {
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }
    setRendering(true);
    setRenderError(null);
    setResultVideoUrl(null);
    setProgressPct(2);
    setProgressStep('init');
    setProgressMsg('Đang khởi động chuỗi tự động HBT Core…');
    setVoiceDetail(null);

    if (typeof EventSource === 'undefined') {
      return;
    }

    const es = new EventSource(`/api/jobs/${encodeURIComponent(jobId)}/events`);
    esRef.current = es;

    es.addEventListener('progress', (ev: MessageEvent) => {
      try {
        const data = JSON.parse(String(ev.data)) as {
          progress?: number;
          step?: string;
          message?: string;
          current?: number;
          total?: number;
          percent?: number;
        };
        if (typeof data.progress === 'number') setProgressPct(data.progress);
        if (data.step) setProgressStep(data.step);
        if (data.message) setProgressMsg(data.message);
        if (
          data.step === 'voice' &&
          typeof data.current === 'number' &&
          typeof data.total === 'number'
        ) {
          setVoiceDetail({
            current: data.current,
            total: data.total,
            percent:
              typeof data.percent === 'number' ? data.percent : Math.round(data.progress ?? 0),
          });
        }
      } catch {
        // Bỏ qua gói tin lỗi cú pháp
      }
    });

    es.addEventListener('end', (ev: MessageEvent) => {
      es.close();
      esRef.current = null;
      setRendering(false);
      try {
        const data = JSON.parse(String(ev.data)) as {
          status?: string;
          error?: string | null;
          output?: { video?: string } | null;
        };
        if (data.status === 'done') {
          setProgressPct(100);
          setResultVideoUrl(data.output?.video ?? null);
          setResultSlug(targetSlug);
          void queryClient.invalidateQueries({ queryKey: ['projects'] });
          void queryClient.invalidateQueries({ queryKey: ['project', targetSlug] });
        } else if (data.status === 'failed') {
          setRenderError(data.error ?? vi.export.failed);
        }
      } catch {
        setRenderError(vi.export.failed);
      }
    });

    es.onerror = () => {
      es.close();
      esRef.current = null;
      setRendering(false);
    };
  };

  const handleStartV1Render = async () => {
    const validScript = applyJsonTextareaToSegments();
    if (!validScript) return;

    setRendering(true);
    setRenderError(null);
    setResultVideoUrl(null);
    try {
      const res = await api.renderHbtCoreV1({
        script: validScript,
        slug: resultSlug ?? initialSlug ?? null,
      });
      if (res.success === false || res.ok === false || !res.slug) {
        const msg = res.message || res.detail || res.error || vi.export.failed;
        setRendering(false);
        setRenderError(msg);
        toast.error(new Error(msg));
        return;
      }
      setResultSlug(res.slug);
      if (res.job_id) {
        connectJobSse(res.job_id, res.slug);
      } else {
        setRendering(false);
      }
    } catch (err) {
      setRendering(false);
      const msg = err instanceof Error ? err.message : String(err);
      setRenderError(msg);
      toast.error(err);
    }
  };

  const handleRunV2Prompt = async () => {
    const cleanPrompt = prompt.trim();
    if (!cleanPrompt) return;

    setV2Loading(true);
    setFallbackNotice(null);
    setRenderError(null);
    try {
      const res = await api.promptHbtCoreV2({
        prompt: cleanPrompt,
        topic: v2Topic,
        selectedModel,
        slug: resultSlug ?? initialSlug ?? null,
        auto_render: true,
      });
      // Nếu backend trả về cấu trúc fallback_v1 (ví dụ: {success: false, fallback_v1: true, message, error})
      if (res.fallback_v1 || res.success === false || res.ok === false || !res.script) {
        const fallbackMsg =
          res.message ||
          res.detail ||
          res.error ||
          'Lỗi gọi Gemini Flash API. Đã tự động chuyển sang Chế độ V1.';
        setFallbackNotice(fallbackMsg);
        setMode('v1');
        toast.error(new Error(fallbackMsg));
        return;
      }

      // Nạp kịch bản Gemini vừa sinh vào V1 state và kích hoạt tiến trình
      const sc = res.script;
      setTitle(sc.title);
      setTopic((sc.topic as HbtCoreTopic) || v2Topic);
      setSegments(sc.segments);
      setJsonText(JSON.stringify(sc, null, 2));
      if (res.slug) {
        setResultSlug(res.slug);
      }
      toast.info(T.v2.successToast);
      if (res.job_id && res.slug) {
        connectJobSse(res.job_id, res.slug);
      }
    } catch (err) {
      let msg = 'Lỗi gọi Gemini Flash API. Đã tự động chuyển sang Chế độ V1.';
      if (err instanceof ApiError) {
        const errBody = err.body as {
          message?: unknown;
          detail?: unknown;
          error?: unknown;
        } | null;
        if (errBody && typeof errBody.message === 'string' && errBody.message.trim()) {
          msg = errBody.message;
        } else if (errBody && typeof errBody.detail === 'string' && errBody.detail.trim()) {
          msg = errBody.detail;
        } else if (errBody && typeof errBody.error === 'string' && errBody.error.trim()) {
          msg = errBody.error;
        } else if (err.message) {
          msg = err.message;
        }
      } else if (err instanceof Error && err.message) {
        msg = err.message;
      }
      setFallbackNotice(msg);
      // Tự động chuyển hướng người dùng sang Chế độ V1 để không bị gián đoạn công việc
      setMode('v1');
      toast.error(new Error(msg));
    } finally {
      setV2Loading(false);
    }
  };

  const sfxOptions = assets?.sfx_presets ?? ['whoosh', 'pop', 'impact', 'none'];
  const existingImages = assets?.images ?? [];
  const geminiModels =
    modelsData?.models && modelsData.models.length > 0
      ? modelsData.models
      : assets?.gemini_models && assets.gemini_models.length > 0
        ? assets.gemini_models
        : DEFAULT_GEMINI_MODELS;

  return (
    <Dialog
      open={open}
      onClose={() => {
        if (!rendering && !v2Loading) onClose();
      }}
      title={T.title}
      className="!max-w-[920px]"
      footer={
        mode === 'v1' ? (
          <>
            <Button tone="soft" disabled={rendering} onClick={onClose}>
              {vi.common.close}
            </Button>
            <Button disabled={rendering} onClick={() => void handleStartV1Render()}>
              {rendering ? T.v1.renderingBtn : T.v1.renderBtn}
            </Button>
          </>
        ) : (
          <>
            <Button tone="soft" disabled={v2Loading || rendering} onClick={onClose}>
              {vi.common.close}
            </Button>
            <Button
              disabled={v2Loading || rendering || !prompt.trim()}
              onClick={() => void handleRunV2Prompt()}
            >
              {v2Loading ? T.v2.submittingBtn : T.v2.submitBtn}
            </Button>
          </>
        )
      }
    >
      <div className="max-h-[75vh] space-y-5 overflow-y-auto pr-1">
        <p className="text-small text-muted">{T.lead}</p>

        {/* Thanh 2 Tab Chế độ V1 / V2 */}
        <div role="tablist" aria-label={T.title} className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          <button
            type="button"
            role="tab"
            aria-selected={mode === 'v1'}
            onClick={() => setMode('v1')}
            className={`flex items-center justify-between gap-2 rounded-inner border px-4 py-3 text-left text-small font-bold transition ${
              mode === 'v1'
                ? 'border-ink bg-hero text-on-hero'
                : 'border-line bg-soft text-ink hover:bg-soft-2'
            }`}
          >
            <span>{T.tabV1}</span>
            <Badge tone="ok">{T.offlineBadge}</Badge>
          </button>

          <button
            type="button"
            role="tab"
            aria-selected={mode === 'v2'}
            onClick={() => setMode('v2')}
            className={`flex items-center justify-between gap-2 rounded-inner border px-4 py-3 text-left text-small font-bold transition ${
              mode === 'v2'
                ? 'border-ink bg-hero text-on-hero'
                : 'border-line bg-soft text-ink hover:bg-soft-2'
            }`}
          >
            <span>{T.tabV2}</span>
            <Badge tone="yel">{T.geminiBadge}</Badge>
          </button>
        </div>

        {/* Thông báo khi tự động chuyển hướng từ V2 sang V1 do lỗi API / hết quota */}
        {fallbackNotice && (
          <div
            role="alert"
            className="flex items-start gap-2.5 rounded-inner bg-danger-soft p-3.5 text-small text-danger"
          >
            <AlertIcon size={18} />
            <div className="space-y-1">
              <p className="font-bold">{T.v2.fallbackNoticeTitle}</p>
              <p>{fallbackNotice}</p>
            </div>
          </div>
        )}

        {mode === 'v1' ? (
          <div className="space-y-5" role="tabpanel" aria-label={T.tabV1}>
            {/* Khung Textarea lớn dán trực tiếp khối JSON kịch bản */}
            <div className="space-y-2">
              <Textarea
                label={T.v1.jsonLabel}
                value={jsonText}
                rows={8}
                spellCheck={false}
                error={jsonError ?? undefined}
                className="!bg-hero !font-mono !text-small !text-on-hero"
                onChange={(e) => {
                  setJsonText(e.target.value);
                  setJsonError(null);
                }}
              />
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  tone="soft"
                  size="sm"
                  onClick={() => {
                    const parsed = applyJsonTextareaToSegments();
                    if (parsed) toast.info(T.v1.validJsonToast);
                  }}
                >
                  {T.v1.parseBtn}
                </Button>
                <span className="text-tiny text-muted">
                  Chế độ V1 hoàn toàn không gọi API ngoài (0 token, offline 100%).
                </span>
              </div>
            </div>

            {/* Chỉnh sửa tiêu đề & chủ đề nhạc nền */}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Input
                label={T.v1.videoTitleLabel}
                value={title}
                onChange={(e) => {
                  const v = e.target.value;
                  setTitle(v);
                  syncEditorToJsonText(v, topic, segments);
                }}
              />
              <div className="ui-field">
                <label htmlFor="hbt-core-v1-topic" className="ui-label">
                  {T.topics.label}
                </label>
                <select
                  id="hbt-core-v1-topic"
                  className="ui-input"
                  value={topic}
                  onChange={(e) => {
                    const nextTopic = e.target.value as HbtCoreTopic;
                    setTopic(nextTopic);
                    syncEditorToJsonText(title, nextTopic, segments);
                  }}
                >
                  <option value="history">{T.topics.history}</option>
                  <option value="fun">{T.topics.fun}</option>
                  <option value="science">{T.topics.science}</option>
                  <option value="mystery">{T.topics.mystery}</option>
                </select>
              </div>
            </div>

            {/* Danh sách từng phân đoạn cho phép chỉnh sửa trực tiếp lời thoại, ảnh, SFX */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-small font-bold">{T.v1.segmentsTitle}</h3>
                <Button tone="soft" size="sm" onClick={addSegment}>
                  {T.v1.addSegment}
                </Button>
              </div>

              <ul className="space-y-3">
                {segments.map((seg, idx) => (
                  <li
                    key={idx}
                    className="space-y-3 rounded-inner border border-line bg-soft p-3.5"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-small font-extrabold">
                        {T.v1.segmentOrder(idx + 1)}
                      </span>
                      {segments.length > 1 && (
                        <Button tone="soft" size="sm" onClick={() => removeSegment(idx)}>
                          {T.v1.removeSegment(idx + 1)}
                        </Button>
                      )}
                    </div>

                    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                      <Input
                        label={T.v1.segmentCardTitleLabel(idx + 1)}
                        value={seg.title ?? ''}
                        placeholder="TIÊU ĐỀ THẺ KEM NGẮN"
                        onChange={(e) =>
                          updateSegment(idx, { title: e.target.value, card_text: e.target.value })
                        }
                      />
                      <div className="ui-field">
                        <label htmlFor={`hbt-core-sticker-${idx}`} className="ui-label">
                          {T.v1.segmentStickerLabel(idx + 1)}
                        </label>
                        <select
                          id={`hbt-core-sticker-${idx}`}
                          className="ui-input"
                          value={seg.sticker || 'question'}
                          onChange={(e) => updateSegment(idx, { sticker: e.target.value })}
                        >
                          {STICKER_PRESETS.map((st) => (
                            <option key={st} value={st}>
                              {st}
                            </option>
                          ))}
                        </select>
                      </div>
                    </div>

                    <Textarea
                      label={T.v1.segmentTextLabel(idx + 1)}
                      rows={2}
                      value={seg.text}
                      onChange={(e) => updateSegment(idx, { text: e.target.value })}
                    />

                    <Textarea
                      label={T.v1.segmentImagePromptLabel(idx + 1)}
                      rows={2}
                      value={seg.image_prompt ?? ''}
                      placeholder="Cinematic shot..., 9:16 vertical framing"
                      onChange={(e) => updateSegment(idx, { image_prompt: e.target.value })}
                    />

                    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                      <div>
                        <Input
                          label={T.v1.segmentImageLabel(idx + 1)}
                          value={seg.image}
                          placeholder={T.v1.imagePlaceholder}
                          list={`hbt-core-imgs-${idx}`}
                          onChange={(e) => updateSegment(idx, { image: e.target.value })}
                        />
                        {existingImages.length > 0 && (
                          <datalist id={`hbt-core-imgs-${idx}`}>
                            {existingImages.map((imgPath) => (
                              <option key={imgPath} value={imgPath} />
                            ))}
                          </datalist>
                        )}
                      </div>

                      <div className="ui-field">
                        <label htmlFor={`hbt-core-sfx-${idx}`} className="ui-label">
                          {T.v1.segmentSfxLabel(idx + 1)}
                        </label>
                        <select
                          id={`hbt-core-sfx-${idx}`}
                          className="ui-input"
                          value={seg.sfx}
                          onChange={(e) => updateSegment(idx, { sfx: e.target.value })}
                        >
                          {sfxOptions.map((sfxName) => (
                            <option key={sfxName} value={sfxName}>
                              {sfxName}
                            </option>
                          ))}
                          {assets?.sfx.map((item) => (
                            <option key={item.id} value={item.name}>
                              {item.name} ({item.category})
                            </option>
                          ))}
                        </select>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        ) : (
          <div className="space-y-4" role="tabpanel" aria-label={T.tabV2}>
            <Textarea
              data-autofocus
              label={T.v2.promptLabel}
              rows={4}
              value={prompt}
              placeholder={T.v2.promptPlaceholder}
              onChange={(e) => setPrompt(e.target.value)}
            />

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="ui-field">
                <label htmlFor="hbt-core-v2-topic" className="ui-label">
                  {T.topics.label}
                </label>
                <select
                  id="hbt-core-v2-topic"
                  className="ui-input"
                  value={v2Topic}
                  onChange={(e) => setV2Topic(e.target.value as HbtCoreTopic)}
                >
                  <option value="history">{T.topics.history}</option>
                  <option value="fun">{T.topics.fun}</option>
                  <option value="science">{T.topics.science}</option>
                  <option value="mystery">{T.topics.mystery}</option>
                </select>
              </div>

              <div className="ui-field">
                <label htmlFor="hbt-core-v2-model" className="ui-label">
                  {T.v2.modelLabel}
                </label>
                <select
                  id="hbt-core-v2-model"
                  className="ui-input"
                  value={selectedModel}
                  onChange={(e) => setSelectedModel(e.target.value)}
                >
                  {geminiModels.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.name}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>
        )}

        {/* Khối hiển thị tiến trình SSE VieNeu-TTS & Render */}
        {(rendering || resultVideoUrl || renderError) && (
          <section
            aria-label={T.progress.title}
            className="space-y-3 rounded-inner border border-line bg-soft-2 p-4"
          >
            <div className="flex items-center justify-between gap-2">
              <p className="text-small font-bold">{T.progress.title}</p>
              <span className="num text-small font-extrabold">{Math.round(progressPct)}%</span>
            </div>
            <Progress value={progressPct} label={T.progress.title} />
            {voiceDetail && progressStep === 'voice' && (
              <p className="text-small font-semibold">
                {T.progress.voiceStep(voiceDetail.current, voiceDetail.total, voiceDetail.percent)}
              </p>
            )}
            {progressMsg && <p className="text-tiny text-muted">{progressMsg}</p>}

            {renderError && (
              <p role="alert" className="text-small font-bold text-danger">
                {renderError}
              </p>
            )}

            {resultVideoUrl && (
              <div className="space-y-3 pt-2">
                <p className="text-small font-bold text-ok">{T.progress.doneTitle}</p>
                <div className="flex flex-wrap items-center gap-2">
                  <a
                    href={resultVideoUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="ui-btn ui-btn-ink"
                  >
                    <PlayIcon size={18} />
                    {T.progress.watchVideo}
                  </a>
                  {resultSlug && (
                    <Link
                      to={`/p/${encodeURIComponent(resultSlug)}`}
                      className="ui-btn ui-btn-soft"
                      onClick={onClose}
                    >
                      {T.progress.openProject}
                    </Link>
                  )}
                </div>
              </div>
            )}
          </section>
        )}
      </div>
    </Dialog>
  );
}
