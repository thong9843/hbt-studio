import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { ApiError } from '../../api/client';
import { api, projectFileUrl } from '../../api/endpoints';
import { useSafeZone } from '../SafeZoneOverlay';
import { CinemaInspectorPanel } from '../cinema/CinemaInspectorPanel';
import { ExportPopover } from '../studio/ExportPopover';
import { PhonePreviewStage } from '../studio/PhonePreviewStage';
import { SceneTimelineStrip } from '../studio/SceneTimelineStrip';
import type {
  HbtCoreGeminiModel,
  HbtCoreScript,
  HbtCoreSegment,
  HbtCoreTopic,
} from '../../api/types';
import { SAMPLE_V1_SCRIPT, useStudioWorkspace } from '../../hooks/studioWorkspace';
import { useRenderJobProgress, useRenderJobStatus } from '../../hooks/renderJob';
import { useToast } from '../../hooks/toast';
import { vi } from '../../i18n/vi';
import { WaterfallProgress, type WaterfallStep, type WaterfallStepState } from '../../shared';
import {
  AlertIcon,
  CheckIcon,
  CopyIcon,
  PlayIcon,
  SettingsIcon,
  SparklesIcon,
  TrashIcon,
} from '../icons';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { Dialog } from '../ui/Dialog';
import { Input, Textarea } from '../ui/Field';
import { StudioSelect } from '../ui/StudioSelect';
import { cx } from '../ui/cx';

const T = vi.hbtCore;

const DEFAULT_GEMINI_MODELS: HbtCoreGeminiModel[] = [
  { id: 'gemini-3.8-flash', name: 'Gemini 3.8 Flash' },
  { id: 'gemini-3.6-flash', name: 'Gemini 3.6 Flash' },
  { id: 'gemini-3.5-flash-lite', name: 'Gemini 3.5 Flash Lite' },
  { id: 'gemini-3.1-flash-lite', name: 'Gemini 3.1 Flash Lite' },
];

const STICKER_PRESETS = ['question', 'shock', 'laugh', 'think', 'check', 'warning'] as const;

const STICKER_EMOJI: Record<string, string> = {
  question: '🤔',
  shock: '😲',
  laugh: '😂',
  think: '🧐',
  check: '✅',
  warning: '⚠️',
};

export interface HbtCoreWorkspaceProps {
  /** Nếu truyền slug từ dự án đang mở (`/p/:slug`) hoặc `/core?slug=...`. */
  slug?: string;
  /** Nếu dùng bên trong Dialog cũ, truyền onClose để hiện nút Đóng. */
  onClose?: () => void;
  /** Cờ bật/tắt query khi nằm trong Dialog ẩn; mặc định `true` cho Workspace View. */
  active?: boolean;
}

interface VoiceProgressDetail {
  current: number;
  total: number;
  percent: number;
}

function AutoImageProgressBar({
  totalFallback,
  onCancel,
}: {
  totalFallback: number;
  onCancel: () => void;
}) {
  const progress = useRenderJobProgress();
  const cur = progress.currentBeat ?? 0;
  const total = progress.totalBeats ?? totalFallback;
  const pct = Math.max(0, Math.min(100, Math.round(progress.percent)));
  return (
    <div
      role="status"
      aria-live="polite"
      className="mt-3 flex flex-wrap items-center justify-between gap-2 rounded-inner border border-line bg-soft px-3 py-2 text-tiny"
    >
      <div className="flex min-w-0 flex-1 items-center gap-2">
        <span className="font-bold text-text whitespace-nowrap">
          {T.autoImage.progressLabel(cur, total)}
        </span>
        <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-line">
          <div
            className="h-full rounded-full bg-brand transition-all duration-200"
            style={{ width: `${pct}%` }}
          />
        </div>
        <span className="font-mono text-muted tabular-nums">{pct}%</span>
      </div>
      <button
        type="button"
        onClick={onCancel}
        className="rounded-inner border border-line bg-card px-2 py-0.5 text-tiny font-bold text-muted hover:text-text"
      >
        {vi.common.cancel}
      </button>
    </div>
  );
}

export function HbtCoreWorkspace({
  slug: initialSlug,
  onClose,
  active = true,
}: HbtCoreWorkspaceProps) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const shared = useStudioWorkspace();
  const renderJob = useRenderJobStatus();
  const { platform: safeZone, setPlatform: setSafeZone } = useSafeZone();

  const [localTitle, setLocalTitle] = useState(SAMPLE_V1_SCRIPT.title);
  const [localTopic, setLocalTopic] = useState<HbtCoreTopic>('history');
  const [localSegments, setLocalSegments] = useState<HbtCoreSegment[]>(SAMPLE_V1_SCRIPT.segments);
  const [localJsonText, setLocalJsonText] = useState(() =>
    JSON.stringify(SAMPLE_V1_SCRIPT, null, 2),
  );
  const [localPrompt, setLocalPrompt] = useState('');
  const [localV2Topic, setLocalV2Topic] = useState<HbtCoreTopic>('history');
  const [localSelectedModel, setLocalSelectedModel] = useState('gemini-3.8-flash');
  const [localFallbackNotice, setLocalFallbackNotice] = useState<string | null>(null);
  const [localResultVideoUrl, setLocalResultVideoUrl] = useState<string | null>(null);
  const [localResultSlug, setLocalResultSlug] = useState<string | null>(initialSlug ?? null);

  const useShared = Boolean(shared && !initialSlug);

  const title = useShared ? shared!.title : localTitle;
  const setTitle = useShared ? shared!.setTitle : setLocalTitle;
  const topic = useShared ? shared!.topic : localTopic;
  const setTopic = useShared ? shared!.setTopic : setLocalTopic;
  const segments = useShared ? shared!.segments : localSegments;
  const setSegments = useShared ? shared!.setSegments : setLocalSegments;
  const jsonText = useShared ? shared!.jsonText : localJsonText;
  const setJsonText = useShared ? shared!.setJsonText : setLocalJsonText;
  const prompt = useShared ? shared!.prompt : localPrompt;
  const setPrompt = useShared ? shared!.setPrompt : setLocalPrompt;
  const v2Topic = useShared ? shared!.v2Topic : localV2Topic;
  const setV2Topic = useShared ? shared!.setV2Topic : setLocalV2Topic;
  const selectedModel = useShared ? shared!.selectedModel : localSelectedModel;
  const setSelectedModel = useShared ? shared!.setSelectedModel : setLocalSelectedModel;
  const fallbackNotice = useShared ? shared!.fallbackNotice : localFallbackNotice;
  const setFallbackNotice = useShared ? shared!.setFallbackNotice : setLocalFallbackNotice;
  const resultVideoUrl = useShared ? shared!.resultVideoUrl : localResultVideoUrl;
  const setResultVideoUrl = useShared ? shared!.setResultVideoUrl : setLocalResultVideoUrl;
  const resultSlug = useShared ? shared!.resultSlug : localResultSlug;
  const setResultSlug = useShared ? shared!.setResultSlug : setLocalResultSlug;

  const [selectedSegIndex, setSelectedSegIndex] = useState(0);
  const [showAdvancedJson, setShowAdvancedJson] = useState(false);
  const [copiedIdx, setCopiedIdx] = useState<number | null>(null);
  const [jsonError, setJsonError] = useState<string | null>(null);
  const [v2Loading, setV2Loading] = useState(false);
  const [imageBusyStarting, setImageBusyStarting] = useState(false);
  const [regenSceneIdx, setRegenSceneIdx] = useState<number | null>(null);
  const [imageError, setImageError] = useState<string | null>(null);
  const [imageMissingKey, setImageMissingKey] = useState(false);
  const [imgVersion, setImgVersion] = useState(0);

  const isGeneratingImages =
    imageBusyStarting || (renderJob.running && renderJob.kind === 'hbt_core_images');

  // Render & SSE state
  const [rendering, setRendering] = useState(false);
  const [progressPct, setProgressPct] = useState(0);
  const [progressStep, setProgressStep] = useState('');
  const [voiceDetail, setVoiceDetail] = useState<VoiceProgressDetail | null>(null);
  const [renderError, setRenderError] = useState<string | null>(null);
  const [stepLogs, setStepLogs] = useState<
    Record<'script' | 'voice' | 'assets' | 'render', string[]>
  >({
    script: [],
    voice: [],
    assets: [],
    render: [],
  });

  const esRef = useRef<EventSource | null>(null);

  const { data: assets } = useQuery({
    queryKey: ['hbt-core-assets', resultSlug ?? initialSlug ?? ''],
    queryFn: () => api.getHbtCoreAssets(resultSlug ?? initialSlug),
    enabled: active,
  });

  const { data: modelsData } = useQuery({
    queryKey: ['hbt-core-models'],
    queryFn: () => api.getHbtCoreModels(),
    enabled: active,
    retry: false,
  });

  useEffect(() => {
    if (!active || !initialSlug) return;
    let mounted = true;
    api
      .getProjectCoreScript(initialSlug)
      .then((res) => {
        if (!mounted) return;
        const sc = res.script;
        setTitle(sc.title);
        setTopic((sc.topic as HbtCoreTopic) || 'science');
        setSegments(sc.segments);
        setJsonText(JSON.stringify(sc, null, 2));
        setResultSlug(initialSlug);
      })
      .catch(() => {
        // Giữ mẫu mặc định nếu dự án chưa có core_script
      });
    return () => {
      mounted = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, initialSlug]);

  useEffect(() => {
    return () => {
      if (esRef.current) {
        esRef.current.close();
        esRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    if (renderJob.kind !== 'hbt_core_images' || !renderJob.finished) return;
    if (renderJob.finished.status === 'done') {
      setImgVersion((v) => v + 1);
      setImageError(null);
      setImageMissingKey(false);
      void queryClient.invalidateQueries({ queryKey: ['hbt-core-assets'] });
    } else if (renderJob.finished.status === 'failed' && renderJob.finished.error) {
      setImageError(renderJob.finished.error);
      setImageMissingKey(/cloudflare|cài đặt/i.test(renderJob.finished.error));
    }
  }, [renderJob.finished, renderJob.kind, queryClient]);

  const safeIndex = Math.min(selectedSegIndex, Math.max(0, segments.length - 1));
  const activeSegment = segments[safeIndex];

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
      setV2Topic(validTopic);
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
    setSelectedSegIndex(next.length - 1);
    syncEditorToJsonText(title, topic, next);
  };

  const removeSegment = (index: number) => {
    if (segments.length <= 1) return;
    const next = segments.filter((_, i) => i !== index).map((s, idx) => ({ ...s, order: idx + 1 }));
    setSegments(next);
    setSelectedSegIndex((prev) => Math.max(0, Math.min(prev, next.length - 1)));
    syncEditorToJsonText(title, topic, next);
  };

  const handleCopyImagePrompt = async (idx: number, text: string) => {
    if (!text.trim()) return;
    try {
      await navigator.clipboard.writeText(text);
      setCopiedIdx(idx);
      toast.info(T.studio.copiedPrompt);
      setTimeout(() => setCopiedIdx((curr) => (curr === idx ? null : curr)), 1600);
    } catch {
      toast.error(new Error(vi.export.publish.copyFailed));
    }
  };

  const buildCurrentScript = (): HbtCoreScript => ({
    title,
    topic,
    total_segments: segments.length,
    segments: segments.map((s, idx) => ({
      id: idx + 1,
      order: idx + 1,
      title: s.title ?? '',
      text: s.text,
      sticker: s.sticker || 'question',
      image_prompt: s.image_prompt ?? '',
      image: s.image || `images/scene-${String(idx + 1).padStart(2, '0')}.png`,
      sfx: s.sfx || 'whoosh',
    })),
  });

  const handleImageApiError = (err: unknown) => {
    let msg: string = T.autoImage.missingKeyError;
    let missingKey = false;
    if (err instanceof ApiError) {
      const body = err.body as { code?: unknown; detail?: unknown; message?: unknown } | null;
      if (body?.code === 'missing_cloudflare_key') missingKey = true;
      if (typeof body?.detail === 'string' && body.detail.trim()) msg = body.detail;
      else if (typeof body?.message === 'string' && body.message.trim()) msg = body.message;
      else if (err.message) msg = err.message;
    } else if (err instanceof Error && err.message) {
      msg = err.message;
    }
    if (/cloudflare|cài đặt/i.test(msg)) missingKey = true;
    setImageError(msg);
    setImageMissingKey(missingKey);
    toast.error(new Error(msg));
  };

  const handleGenerateAllImages = async () => {
    setImageError(null);
    setImageMissingKey(false);
    if (assets?.cloudflare_configured === false) {
      setImageError(T.autoImage.missingKeyError);
      setImageMissingKey(true);
      return;
    }
    setImageBusyStarting(true);
    try {
      const targetSlug = resultSlug ?? initialSlug ?? '_new';
      const res = await api.generateHbtCoreImages(targetSlug, {
        script: buildCurrentScript(),
      });
      if (res.slug) setResultSlug(res.slug);
      renderJob.attachJob({
        jobId: res.job_id,
        slug: res.slug,
        kind: 'hbt_core_images',
        stage: 'Tự vẽ ảnh 2D',
        currentBeat: 0,
        totalBeats: res.total ?? segments.length,
      });
    } catch (err) {
      handleImageApiError(err);
    } finally {
      setImageBusyStarting(false);
    }
  };

  const handleGenerateSingleImage = async (idx: number) => {
    const seg = segments[idx];
    if (!seg) return;
    setImageError(null);
    setImageMissingKey(false);
    if (assets?.cloudflare_configured === false) {
      setImageError(T.autoImage.missingKeyError);
      setImageMissingKey(true);
      return;
    }
    setRegenSceneIdx(idx);
    try {
      const targetSlug = resultSlug ?? initialSlug ?? '_new';
      const res = await api.generateHbtCoreSceneImage(targetSlug, idx, {
        image_prompt: seg.image_prompt ?? '',
        script: buildCurrentScript(),
      });
      if (res.slug) setResultSlug(res.slug);
      updateSegment(idx, { image: res.image });
      setImgVersion((v) => v + 1);
      void queryClient.invalidateQueries({ queryKey: ['hbt-core-assets'] });
      toast.info(T.autoImage.sceneDoneToast(idx + 1));
    } catch (err) {
      handleImageApiError(err);
    } finally {
      setRegenSceneIdx(null);
    }
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
    setVoiceDetail(null);
    setStepLogs((prev) => ({
      ...prev,
      voice: [],
      assets: [],
      render: ['Khởi tạo phiên dựng video HBT Core…'],
    }));

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
        if (data.message) {
          const msg = String(data.message);
          const bucket: 'script' | 'voice' | 'assets' | 'render' =
            data.step === 'init'
              ? 'script'
              : data.step === 'voice'
                ? 'voice'
                : data.step === 'bgm' || data.step === 'sfx'
                  ? 'assets'
                  : 'render';
          setStepLogs((prev) => ({
            ...prev,
            [bucket]: [...prev[bucket].slice(-25), msg],
          }));
        }
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
    setStepLogs({
      script: [`Gửi yêu cầu Gemini (${selectedModel}) cho chủ đề: "${cleanPrompt}"`],
      voice: [],
      assets: [],
      render: [],
    });
    try {
      const res = await api.promptHbtCoreV2({
        prompt: cleanPrompt,
        topic: v2Topic,
        selectedModel,
        slug: resultSlug ?? initialSlug ?? null,
        auto_render: true,
      });
      if (res.fallback_v1 || res.success === false || res.ok === false || !res.script) {
        const fallbackMsg =
          res.message ||
          res.detail ||
          res.error ||
          'Lỗi gọi Gemini Flash API. Đã tự động chuyển sang chế độ chỉnh tay.';
        setFallbackNotice(fallbackMsg);
        setShowAdvancedJson(true);
        toast.error(new Error(fallbackMsg));
        return;
      }

      const sc = res.script;
      setTitle(sc.title);
      setTopic((sc.topic as HbtCoreTopic) || v2Topic);
      setSegments(sc.segments);
      setSelectedSegIndex(0);
      setJsonText(JSON.stringify(sc, null, 2));
      if (res.slug) {
        setResultSlug(res.slug);
      }
      toast.info(T.v2.successToast);
      if (res.job_id && res.slug) {
        connectJobSse(res.job_id, res.slug);
      }
    } catch (err) {
      let msg = 'Lỗi gọi Gemini Flash API. Đã tự động chuyển sang chế độ chỉnh tay.';
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
      setShowAdvancedJson(true);
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

  const activeImageSrc = (() => {
    if (!activeSegment?.image) return null;
    if (activeSegment.image.startsWith('http') || activeSegment.image.startsWith('/')) {
      return activeSegment.image;
    }
    const normalizedRel = activeSegment.image.startsWith('images/')
      ? activeSegment.image
      : `images/${activeSegment.image}`;
    if (
      resultSlug &&
      (existingImages.includes(activeSegment.image) ||
        existingImages.includes(normalizedRel) ||
        imgVersion > 0)
    ) {
      const base = projectFileUrl(resultSlug, normalizedRel);
      return imgVersion > 0 ? `${base}?v=${imgVersion}` : base;
    }
    return null;
  })();

  return (
    <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
      {/* KHU VỰC TRÁI: WORKSPACE & PROMPT-FIRST INPUT */}
      <div className="min-w-0 space-y-5">
        {/* Thanh Prompt thông minh trung tâm */}
        <section
          aria-label="Thanh Prompt trung tâm"
          className="rounded-card border border-line bg-card p-4 transition duration-150 focus-within:border-indigo-500/70"
        >
          <label htmlFor="hbt-core-prompt-input" className="sr-only">
            {T.v2.promptLabel}
          </label>
          <textarea
            id="hbt-core-prompt-input"
            rows={3}
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder={T.studio.promptPlaceholder}
            className="w-full resize-none bg-transparent text-body text-ink placeholder:text-muted focus:outline-none"
          />

          {/* Thanh công cụ tích hợp ngay trong ô input */}
          <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-line pt-3">
            <div className="flex flex-wrap items-center gap-2">
              <StudioSelect
                aria-label={T.v2.modelLabel}
                variant="compact"
                autoWidth
                value={selectedModel}
                onChange={(val) => setSelectedModel(val)}
                options={geminiModels.map((m) => ({
                  value: m.id,
                  label: m.name.replace(/\s*\([^)]*\)/g, '').trim(),
                }))}
                className="min-w-[180px]"
              />

              <StudioSelect
                aria-label={T.topics.label}
                variant="compact"
                autoWidth
                value={v2Topic}
                onChange={(val) => {
                  const next = val as HbtCoreTopic;
                  setV2Topic(next);
                  setTopic(next);
                  syncEditorToJsonText(title, next, segments);
                }}
                options={[
                  { value: 'history', label: T.topics.history },
                  { value: 'fun', label: T.topics.fun },
                  { value: 'science', label: T.topics.science },
                  { value: 'mystery', label: T.topics.mystery },
                ]}
                className="min-w-[130px]"
              />

              <button
                type="button"
                aria-expanded={showAdvancedJson}
                aria-label={T.studio.advancedToggle}
                title={T.studio.advancedToggle}
                onClick={() => setShowAdvancedJson((v) => !v)}
                className={cx(
                  'flex items-center gap-1.5 rounded-inner border px-2.5 py-1.5 text-tiny font-bold transition',
                  showAdvancedJson
                    ? 'border-indigo-500 bg-indigo-500/15 text-indigo-300'
                    : 'border-line bg-soft text-muted hover:text-ink',
                )}
              >
                <SettingsIcon size={14} />
                <span>JSON</span>
              </button>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              {onClose && (
                <Button tone="soft" size="sm" disabled={rendering || v2Loading} onClick={onClose}>
                  {vi.common.close}
                </Button>
              )}
              <button
                type="button"
                disabled={isGeneratingImages || v2Loading || rendering}
                onClick={() => void handleGenerateAllImages()}
                className="ui-btn ui-btn-soft ui-btn-sm"
              >
                <SparklesIcon size={15} />
                <span>
                  {isGeneratingImages ? T.autoImage.generatingBtn : T.autoImage.generateAllBtn}
                </span>
              </button>
              <button
                type="button"
                disabled={v2Loading || rendering || !prompt.trim()}
                onClick={() => void handleRunV2Prompt()}
                className="ui-btn ui-btn-ink ui-btn-sm"
              >
                <SparklesIcon size={16} />
                <span>{v2Loading ? T.studio.generatingBtn : T.studio.generateBtn}</span>
              </button>
              <ExportPopover
                aspect="9:16"
                showWatermarkControl
                onExportFinal={() => void handleStartV1Render()}
                finalLabel={rendering ? T.v1.renderingBtn : T.studio.renderBtn}
                disabled={rendering || v2Loading}
                isRendering={rendering}
                progressPct={progressPct}
                progressStage={progressStep}
              />
            </div>
          </div>
          {isGeneratingImages && (
            <AutoImageProgressBar
              totalFallback={segments.length}
              onCancel={() => void renderJob.cancel()}
            />
          )}
        </section>

        {imageError && (
          <div
            role="alert"
            className="flex flex-wrap items-center justify-between gap-2 rounded-card border border-danger/30 bg-danger-soft p-3.5 text-small text-danger"
          >
            <div className="flex items-start gap-2">
              <AlertIcon size={18} />
              <span>{imageError}</span>
            </div>
            {imageMissingKey && (
              <Link to="/settings" className="ui-btn ui-btn-soft ui-btn-sm">
                {T.autoImage.openSettingsLink}
              </Link>
            )}
          </div>
        )}

        {/* Thông báo fallback V2 -> V1 nếu Gemini lỗi / hết quota */}
        {fallbackNotice && (
          <div
            role="alert"
            className="flex items-start gap-2.5 rounded-card border border-danger/30 bg-danger-soft p-3.5 text-small text-danger"
          >
            <AlertIcon size={18} />
            <div className="space-y-0.5">
              <p className="font-bold">{T.v2.fallbackNoticeTitle}</p>
              <p>{fallbackNotice}</p>
            </div>
          </div>
        )}

        {/* Dialog phụ nhẹ nhàng cho Vi chỉnh nâng cao / Dán JSON */}
        <Dialog
          open={showAdvancedJson}
          onClose={() => setShowAdvancedJson(false)}
          title={T.studio.advancedTitle}
          className="!max-w-[760px]"
          footer={
            <div className="flex flex-wrap items-center justify-between gap-2 w-full">
              <Badge tone="ok">{T.offlineBadge}</Badge>
              <div className="flex items-center gap-2">
                <Button tone="soft" size="sm" onClick={() => setShowAdvancedJson(false)}>
                  {vi.common.close}
                </Button>
                <Button
                  size="sm"
                  onClick={() => {
                    const parsed = applyJsonTextareaToSegments();
                    if (parsed) {
                      toast.info(T.v1.validJsonToast);
                      setShowAdvancedJson(false);
                    }
                  }}
                >
                  {T.v1.parseBtn}
                </Button>
              </div>
            </div>
          }
        >
          <div className="space-y-4">
            <Input
              label={T.v1.videoTitleLabel}
              value={title}
              onChange={(e) => {
                const v = e.target.value;
                setTitle(v);
                syncEditorToJsonText(v, topic, segments);
              }}
            />
            <Textarea
              label={T.v1.jsonLabel}
              value={jsonText}
              rows={10}
              spellCheck={false}
              error={jsonError ?? undefined}
              className="!font-mono !text-tiny"
              onChange={(e) => {
                setJsonText(e.target.value);
                setJsonError(null);
              }}
            />
          </div>
        </Dialog>

        {/* Dải phân cảnh ngang chuẩn VEED + Trình sửa DUY NHẤT phân cảnh đang chọn (giảm 80% DOM) */}
        <section aria-label={T.v1.segmentsTitle} className="space-y-3">
          <div className="overflow-hidden rounded-card border border-line bg-card">
            <SceneTimelineStrip
              items={segments.map((seg, idx) => ({
                id: String(idx),
                index: idx + 1,
                title: seg.title,
                summary: seg.text,
              }))}
              selectedId={String(safeIndex)}
              onSelect={(id) => setSelectedSegIndex(Number(id))}
              onAdd={addSegment}
              addLabel={T.v1.addSegment}
              onDelete={(id) => removeSegment(Number(id))}
            />
          </div>

          {activeSegment &&
            (() => {
              const seg = activeSegment;
              const idx = safeIndex;
              return (
                <div className="space-y-3 rounded-card border border-line bg-card p-4 shadow-card">
                  <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line pb-2.5">
                    <div className="flex items-center gap-2">
                      <span className="flex h-6 w-6 items-center justify-center rounded-md bg-brand text-tiny font-extrabold text-white tabular-nums">
                        {idx + 1}
                      </span>
                      <span className="text-small font-bold text-text">
                        {seg.title || T.v1.segmentOrder(idx + 1)}
                      </span>
                      <Badge tone="neutral">
                        {STICKER_EMOJI[seg.sticker || 'question'] ?? '✨'}{' '}
                        {seg.sticker || 'question'}
                      </Badge>
                    </div>
                    {segments.length > 1 && (
                      <button
                        type="button"
                        aria-label={T.v1.removeSegment(idx + 1)}
                        onClick={() => removeSegment(idx)}
                        className="rounded-inner p-1.5 text-muted transition hover:bg-danger-soft hover:text-danger"
                      >
                        <TrashIcon size={15} />
                      </button>
                    )}
                  </div>

                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    <Input
                      label={T.v1.segmentCardTitleLabel}
                      value={seg.title ?? ''}
                      placeholder="TIÊU ĐỀ THẺ KEM NGẮN"
                      onChange={(e) =>
                        updateSegment(idx, { title: e.target.value, card_text: e.target.value })
                      }
                    />
                    <div className="ui-field">
                      <StudioSelect
                        id={`hbt-core-sticker-${idx}`}
                        label={T.v1.segmentStickerLabel}
                        value={seg.sticker || 'question'}
                        onChange={(val) => updateSegment(idx, { sticker: val })}
                        options={STICKER_PRESETS.map((st) => ({
                          value: st,
                          label: `${STICKER_EMOJI[st]} ${st}`,
                        }))}
                      />
                    </div>
                  </div>

                  <Textarea
                    label={T.v1.segmentTextLabel}
                    rows={2}
                    value={seg.text}
                    onChange={(e) => updateSegment(idx, { text: e.target.value })}
                  />

                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between gap-2">
                      <label htmlFor={`hbt-core-img-prompt-${idx}`} className="ui-label !mb-0">
                        {T.v1.segmentImagePromptLabel}
                      </label>
                      <div className="flex items-center gap-1.5">
                        <button
                          type="button"
                          disabled={regenSceneIdx === idx || isGeneratingImages || rendering}
                          onClick={() => void handleGenerateSingleImage(idx)}
                          className="inline-flex items-center gap-1 rounded-inner border border-line bg-soft px-2.5 py-1 text-tiny font-bold text-text transition hover:bg-soft-2 disabled:opacity-50"
                        >
                          <SparklesIcon size={13} />
                          <span>
                            {regenSceneIdx === idx
                              ? T.autoImage.regeningSceneBtn
                              : T.autoImage.regenSceneBtn}
                          </span>
                        </button>
                        <button
                          type="button"
                          onClick={() => void handleCopyImagePrompt(idx, seg.image_prompt ?? '')}
                          className="inline-flex items-center gap-1 rounded-inner border border-line bg-soft px-2.5 py-1 text-tiny font-bold text-text transition hover:bg-soft-2"
                        >
                          {copiedIdx === idx ? <CheckIcon size={13} /> : <CopyIcon size={13} />}
                          <span>{T.studio.copyPrompt}</span>
                        </button>
                      </div>
                    </div>
                    <textarea
                      id={`hbt-core-img-prompt-${idx}`}
                      rows={2}
                      value={seg.image_prompt ?? ''}
                      placeholder="Cinematic shot..., 9:16 vertical framing"
                      onChange={(e) => updateSegment(idx, { image_prompt: e.target.value })}
                      className="ui-input !min-h-0 font-mono text-tiny"
                    />
                  </div>

                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    <div>
                      <Input
                        label={T.v1.segmentImageLabel}
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
                      <StudioSelect
                        id={`hbt-core-sfx-${idx}`}
                        label={T.v1.segmentSfxLabel}
                        value={seg.sfx}
                        onChange={(val) => updateSegment(idx, { sfx: val })}
                        options={[
                          ...sfxOptions.map((sfxName) => ({ value: sfxName, label: sfxName })),
                          ...(assets?.sfx ?? []).map((item) => ({
                            value: item.name,
                            label: `${item.name} (${item.category})`,
                          })),
                        ]}
                      />
                    </div>
                  </div>
                </div>
              );
            })()}
        </section>
      </div>

      {/* KHU VỰC PHẢI: SÂN KHẤU DOT-GRID XEM TRƯỚC 9:16 & TIẾN TRÌNH */}
      <aside className="space-y-4 lg:sticky lg:top-4 lg:self-start">
        <div className="ui-stage-dots rounded-card border border-line p-3">
          <PhonePreviewStage
            title={T.studio.previewTitle}
            badgeText={T.studio.segmentLabel(safeIndex + 1, segments.length)}
            safeZone={safeZone}
            onSafeZoneChange={setSafeZone}
            exportBusy={rendering}
            exportDisabled={rendering || v2Loading}
            exportLabel={rendering ? T.v1.renderingBtn : T.studio.renderBtn}
            onExport={() => void handleStartV1Render()}
            showWatermarkControl={false}
            footer={
              <div className="flex items-center justify-between gap-2 pt-1">
                <Button
                  tone="soft"
                  size="sm"
                  disabled={safeIndex <= 0}
                  onClick={() => setSelectedSegIndex((i) => Math.max(0, i - 1))}
                >
                  ← Trước
                </Button>
                <Button
                  tone="soft"
                  size="sm"
                  disabled={safeIndex >= segments.length - 1}
                  onClick={() => setSelectedSegIndex((i) => Math.min(segments.length - 1, i + 1))}
                >
                  Sau →
                </Button>
              </div>
            }
          >
            {activeImageSrc ? (
              <img
                src={activeImageSrc}
                alt={activeSegment?.title || `Cảnh ${safeIndex + 1}`}
                className="h-full w-full object-cover"
              />
            ) : (
              <div className="flex h-full w-full flex-col items-center justify-center px-5 text-center">
                <span className="text-3xl opacity-60">🖼️</span>
                <p className="mt-2 line-clamp-3 text-tiny text-muted-on-dark">
                  {activeSegment?.image_prompt || activeSegment?.image || T.studio.previewHint}
                </p>
              </div>
            )}

            {/* Thẻ kem (Cream Card) ở vùng trên khung 9:16 */}
            <div className="absolute inset-x-4 top-6 rounded-2xl bg-[#F7EEDA] px-3.5 py-2.5 text-center shadow-md">
              <p className="text-small font-extrabold uppercase leading-tight text-[#1E1816]">
                {activeSegment?.title || title}
              </p>
            </div>

            {/* Sticker biểu cảm */}
            <div className="absolute right-4 top-24 flex h-11 w-11 items-center justify-center rounded-full border border-white/20 bg-black/45 text-2xl shadow">
              <span aria-hidden="true">
                {STICKER_EMOJI[activeSegment?.sticker || 'question'] ?? '🤔'}
              </span>
            </div>

            {/* Phụ đề karaoke mô phỏng ở vùng dưới */}
            <div className="absolute inset-x-4 bottom-8 text-center">
              <p className="inline-block rounded-lg bg-black/55 px-2.5 py-1 text-tiny font-bold leading-snug text-[#FFD43B]">
                {activeSegment?.text || '…'}
              </p>
            </div>
          </PhonePreviewStage>
        </div>

        <CinemaInspectorPanel
          coreScript={{
            title,
            topic,
            total_segments: segments.length,
            segments,
          }}
          beatIndex={safeIndex}
          disabled={rendering || v2Loading}
        />

        {/* Khối hiển thị tiến trình Waterfall Dropdown */}
        {(v2Loading || rendering || resultVideoUrl || renderError) &&
          (() => {
            const done = Boolean(resultVideoUrl) && !rendering;
            const scriptState: WaterfallStepState = v2Loading
              ? 'running'
              : renderError && !rendering && progressPct <= 5
                ? 'error'
                : 'done';
            const voiceState: WaterfallStepState = done
              ? 'done'
              : progressStep === 'voice' && rendering
                ? 'running'
                : ['bgm', 'sfx', 'render', 'mix', 'compose'].includes(progressStep)
                  ? 'done'
                  : 'waiting';
            const assetsState: WaterfallStepState = done
              ? 'done'
              : ['bgm', 'sfx'].includes(progressStep) && rendering
                ? 'running'
                : ['render', 'mix', 'compose'].includes(progressStep)
                  ? 'done'
                  : 'waiting';
            const renderState: WaterfallStepState = done
              ? 'done'
              : renderError && !rendering
                ? 'error'
                : ['render', 'mix', 'compose'].includes(progressStep) && rendering
                  ? 'running'
                  : 'waiting';

            const wfSteps: WaterfallStep[] = [
              {
                id: 'script',
                icon: '📝',
                title: 'Khởi tạo kịch bản (Gemini API)',
                state: scriptState,
                logs: stepLogs.script,
              },
              {
                id: 'voice',
                icon: '🎙️',
                title: 'Sinh giọng thuyết minh (VieNeu-TTS từng câu)',
                state: voiceState,
                badgeText: voiceDetail
                  ? `${voiceDetail.current}/${voiceDetail.total} câu`
                  : undefined,
                logs: stepLogs.voice,
              },
              {
                id: 'assets',
                icon: '🎨',
                title: 'Chuẩn bị hình ảnh & Sticker',
                state: assetsState,
                logs: stepLogs.assets,
              },
              {
                id: 'render',
                icon: '🎬',
                title: 'Render video hoàn chỉnh (FFmpeg timeline 9:16)',
                state: renderState,
                logs: stepLogs.render,
              },
            ];

            return (
              <div className="space-y-3">
                <WaterfallProgress
                  title={T.progress.title}
                  overallPercent={v2Loading ? 10 : progressPct}
                  steps={wfSteps}
                  error={renderError}
                />
                {resultVideoUrl && (
                  <div className="space-y-3 rounded-card border border-ok/40 bg-card p-4">
                    <p className="text-small font-bold text-ok">{T.progress.doneTitle}</p>
                    <div className="flex flex-wrap items-center gap-2">
                      <a
                        href={resultVideoUrl}
                        target="_blank"
                        rel="noreferrer"
                        className="ui-btn ui-btn-ink ui-btn-sm"
                      >
                        <PlayIcon size={16} />
                        {T.progress.watchVideo}
                      </a>
                      {resultSlug && (
                        <Link
                          to={`/p/${encodeURIComponent(resultSlug)}`}
                          className="ui-btn ui-btn-soft ui-btn-sm"
                          onClick={onClose}
                        >
                          {T.progress.openProject}
                        </Link>
                      )}
                    </div>
                  </div>
                )}
              </div>
            );
          })()}
      </aside>
    </div>
  );
}
