import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { api } from '../api/endpoints';
import { stickvApi } from '../api/stickv';
import type {
  StickvAnimationMode,
  StickvAspect,
  StickvBeat,
  StickvBoardType,
  StickvCameraShot,
  StickvDomain,
  StickvEmotion,
  StickvFaceMood,
  StickvInteraction,
  StickvMotion,
  StickvProject,
  StickvSfxTag,
  StickvTheme,
} from '../api/types';
import { ErrorNote } from '../components/ErrorNote';
import { CinemaInspectorPanel } from '../components/cinema/CinemaInspectorPanel';
import {
  ChevronDownIcon,
  CopyIcon,
  EyeIcon,
  FilmIcon,
  MusicIcon,
  PlusIcon,
  SparklesIcon,
  UploadIcon,
} from '../components/icons';
import { SafeZoneOverlay, type SafeZonePlatform } from '../components/SafeZoneOverlay';
import { StudioShell } from '../components/studio/StudioShell';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { Dialog } from '../components/ui/Dialog';
import { Input } from '../components/ui/Field';
import { SegmentedControl } from '../components/ui/SegmentedControl';
import { StudioSelect } from '../components/ui/StudioSelect';
import { Switch } from '../components/ui/Switch';
import { cx } from '../components/ui/cx';
import { useRenderJobStatus } from '../hooks/renderJob';
import { useReleaseVideoOnUnmount } from '../hooks/useReleaseVideoOnUnmount';
import { useToast } from '../hooks/toast';
import { vi } from '../i18n/vi';

/** Ghi nhớ các job StickV đã hoàn tất đã thông báo trong phiên để tránh toast trùng khi re-render. */
const seenCompletedStickvJobs = new Set<string>();

const DEFAULT_POSE_OPTIONS = [
  { id: 'point_up', label: 'Chỉ tay lên bảng' },
  { id: 'point_board_high', label: 'Chỉ cao lên bảng' },
  { id: 'think_chin', label: 'Vắt tay lên cằm' },
  { id: 'arms_crossed', label: 'Khoanh tay phân tích' },
  { id: 'hands_on_hips', label: 'Chống nạnh khẳng định' },
  { id: 'shrug_ask', label: 'Nhún vai đặt câu hỏi' },
  { id: 'present_board', label: 'Xòe tay giới thiệu' },
  { id: 'emphatic_chop', label: 'Đánh nhịp nhấn ý' },
  { id: 'shock_hands_up', label: 'Giơ tay sửng sốt' },
  { id: 'lean_secret', label: 'Thì thầm bật mí' },
  { id: 'count_points', label: 'Đếm ý trên tay' },
  { id: 'walk_explore', label: 'Sải bước khám phá' },
  { id: 'idle_breathe', label: 'Đứng thở tự nhiên' },
  { id: 'wave_hello', label: 'Vẫy tay chào mở đầu' },
  { id: 'scratch_head', label: 'Gãi đầu băn khoăn' },
  { id: 'facepalm_light', label: 'Vỗ trán ngán ngẩm' },
  { id: 'nod_yes', label: 'Gật đầu đồng tình' },
  { id: 'shake_no', label: 'Lắc đầu bác bỏ' },
  { id: 'guide_sweep_board', label: 'Quét tay giới thiệu bảng' },
  { id: 'guide_two_sides', label: 'Mở hai tay so sánh' },
  { id: 'guide_step_count', label: 'Đánh nhịp đếm từng ý' },
  { id: 'guide_zoom_focus', label: 'Tạo khung nhấn mạnh' },
  { id: 'welcome_open', label: 'Mở tay chào thân thiện' },
  { id: 'lean_curious', label: 'Nghiêng người tò mò' },
];

const EXTRA_POSE_LABELS: Record<string, string> = {
  explain: 'Giải thích (Cũ)',
  think: 'Suy nghĩ (Cũ)',
  shock: 'Bất ngờ / Sốc (Cũ)',
  happy: 'Vui vẻ (Cũ)',
  run: 'Chạy nhanh',
  rich: 'Giàu có',
  sad: 'Buồn bã',
  angry: 'Tức giận',
  idea: 'Ý tưởng / Sáng kiến',
  confused: 'Bối rối / Khó hiểu',
  detective: 'Thám tử / Điều tra',
  nerd: 'Mọt sách / Phân tích',
  secret: 'Bí mật / Suỵt',
  facepalm: 'Vỗ trán / Bó tay',
  laugh: 'Cười sảng khoái',
  evil_grin: 'Cười nham hiểm',
  cry: 'Khóc lóc',
  scared: 'Hoảng sợ',
  broke: 'Hết tiền / Cháy túi',
  tired: 'Mệt mỏi',
  sleepy: 'Buồn ngủ',
  cool: 'Ngầu / Tự tin',
  love: 'Yêu thích',
  stop: 'Dừng lại / Cảnh báo',
  present: 'Thuyết trình / Giới thiệu',
  winner: 'Chiến thắng / Cúp',
  pray: 'Cầu nguyện / Xin',
  salute: 'Chào nghiêm / Đồng ý',
};

const MOTIONS: { id: StickvMotion; label: string }[] = [
  { id: 'bounce', label: 'Nhún nhịp' },
  { id: 'slide_left', label: 'Trượt từ phải' },
  { id: 'slide_right', label: 'Trượt từ trái' },
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
  { id: 'timeline_era', label: 'Trục niên đại (Lịch sử)' },
  { id: 'location_map', label: 'Bản đồ địa danh' },
  { id: 'myth_vs_fact', label: 'Lầm tưởng vs Sự thật' },
  { id: 'bar_compare', label: 'Biểu đồ cột động' },
  { id: 'counter_grow', label: 'Bộ đếm số tăng' },
  { id: 'flow_steps', label: 'Sơ đồ bước' },
  { id: 'comparison', label: 'So sánh 2 cột' },
  { id: 'big_number', label: 'Con số lớn' },
  { id: 'card', label: 'Thẻ thông tin' },
  { id: 'quote', label: 'Trích dẫn' },
  { id: 'list', label: 'Danh sách' },
  { id: 'recap_card', label: 'Tóm tắt 3 ý (CTA)' },
  { id: 'pinned_photo', label: 'Ảnh tư liệu (Polaroid)' },
  { id: 'none', label: 'Thẻ tự động (Icon)' },
];

const DOMAINS: { id: StickvDomain; label: string; bgClass: string }[] = [
  { id: 'paper_classic', label: 'Giấy kem HBT', bgClass: 'bg-[#FAF7F0] text-slate-900' },
  { id: 'physics_science', label: 'Khoa học & Vật lý', bgClass: 'bg-[#0F172A] text-slate-50' },
  { id: 'history_geo', label: 'Cổ đại / Lịch sử', bgClass: 'bg-[#DFC69B] text-stone-900' },
  { id: 'psychology_story', label: 'Tâm lý & Kể chuyện', bgClass: 'bg-[#14121D] text-slate-50' },
  { id: 'cosmos_mystery', label: 'Vũ trụ & Bí ẩn', bgClass: 'bg-[#090D16] text-slate-50' },
];

const MUSIC_MOODS: { id: string; label: string }[] = [
  { id: 'curious_science', label: 'Tò mò / Khoa học' },
  { id: 'history_epic', label: 'Sử thi / Kịch tính' },
  { id: 'funny_quirky', label: 'Vui nhộn / Hài hước' },
  { id: 'mysterious_tense', label: 'Bí ẩn / Căng thẳng' },
  { id: 'calm_lofi', label: 'Nhẹ nhàng / Lofi' },
];

const CAMERA_SHOTS: { id: StickvCameraShot; label: string }[] = [
  { id: 'wide_stage', label: 'Toàn cảnh' },
  { id: 'focus_board', label: 'Zoom Bảng' },
  { id: 'closeup_react', label: 'Cận cảnh biểu cảm' },
];

const INTERACTIONS: { id: StickvInteraction; label: string }[] = [
  { id: 'none', label: 'Toàn cảnh' },
  { id: 'hold_prop', label: 'Cầm Icon' },
  { id: 'point_chart', label: 'Chỉ Biểu đồ' },
  { id: 'versus_split', label: 'So sánh 2 vế' },
];

const EMOTIONS: { id: StickvEmotion; label: string }[] = [
  { id: 'auto', label: 'Tự động theo thoại' },
  { id: 'neutral', label: 'Bình tĩnh / Trung tính' },
  { id: 'confident', label: 'Tự tin / Thuyết phục' },
  { id: 'curious', label: 'Tò mò / Dấu hỏi' },
  { id: 'idea', label: 'Bừng sáng ý tưởng' },
  { id: 'shock', label: 'Sửng sốt / Bất ngờ' },
  { id: 'skeptical', label: 'Hoài nghi / Nhướn mày' },
  { id: 'serious', label: 'Nghiêm túc / Nhấn mạnh' },
  { id: 'sad', label: 'Đồng cảm / Buồn nhẹ' },
  { id: 'happy', label: 'Vui vẻ / Cởi mở' },
  { id: 'excited', label: 'Hào hứng / Đỉnh điểm' },
];

function makeEmptyBeat(index: number): StickvBeat {
  return {
    id: `b${String(index).padStart(3, '0')}`,
    chapter: 1,
    narration: '',
    pose: 'present_board',
    emotion: 'auto',
    camera_shot: 'wide_stage',
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
  // Chỉ đăng ký trạng thái vòng đời job (KHÔNG lắng nghe % progress để trang re-render 0 lần khi đang dựng)
  const job = useRenderJobStatus();
  const [searchParams] = useSearchParams();
  const urlSlug = (searchParams.get('slug') ?? '').trim();

  const [selectedSlug, setSelectedSlug] = useState<string>(urlSlug);
  const [draft, setDraft] = useState<StickvProject | null>(null);
  const [selectedBeatId, setSelectedBeatId] = useState<string>('');
  const [activeTab, setActiveTab] = useState<'script' | 'visual' | 'audio' | 'inspect'>('script');
  const [safeZone, setSafeZone] = useState<SafeZonePlatform>('none');
  const [propPreviewMap, setPropPreviewMap] = useState<Record<string, string>>({});
  const [refPhotoResults, setRefPhotoResults] = useState<
    Array<{ id: string; title: string; url: string; thumb_url: string; source: string }>
  >([]);
  const [refPhotoSearching, setRefPhotoSearching] = useState(false);
  const [aiPhotoGenerating, setAiPhotoGenerating] = useState(false);

  // Trạng thái đóng/mở Accordion tạo kịch bản AI: tự động thu gọn khi dự án đã có >= 1 beat
  const [creatorManualOpen, setCreatorManualOpen] = useState<boolean | null>(null);
  const [renameOpen, setRenameOpen] = useState(false);
  const [renameTitle, setRenameTitle] = useState('');

  // 3 Chế độ kịch bản StickV
  const [inputMode, setInputMode] = useState<'ai' | 'json' | 'script'>('ai');
  const [idea, setIdea] = useState('');
  const [rawJson, setRawJson] = useState('');
  const [rawScript, setRawScript] = useState('');
  const [rawTitle, setRawTitle] = useState('');
  const [topic, setTopic] = useState('science');
  const [domain, setDomain] = useState<StickvDomain>('paper_classic');
  const [musicMood, setMusicMood] = useState('curious_science');
  const [animationMode, setAnimationMode] = useState<StickvAnimationMode>('auto');
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
    if (urlSlug && urlSlug !== selectedSlug) {
      setSelectedSlug(urlSlug);
    }
  }, [urlSlug, selectedSlug]);

  useEffect(() => {
    if (!selectedSlug && projects.length > 0) {
      setSelectedSlug(projects[0].slug);
    }
  }, [selectedSlug, projects]);

  const { attachJob } = job;

  // Đồng bộ job StickV bền vững khi mount / quay lại trang hoặc đổi dự án
  useEffect(() => {
    let cancelled = false;
    api
      .listJobs({ includeRecent: true })
      .then((rows) => {
        if (cancelled || !Array.isArray(rows)) return;
        const stickvJobs = rows.filter((r) => r.kind === 'stickv');
        const activeTarget =
          stickvJobs.find(
            (r) =>
              (r.status === 'running' || r.status === 'queued') &&
              (!selectedSlug || r.slug === selectedSlug),
          ) ??
          stickvJobs.find((r) => r.status === 'running' || r.status === 'queued') ??
          null;

        if (activeTarget) {
          if (!selectedSlug && activeTarget.slug) {
            setSelectedSlug(activeTarget.slug);
          }
          attachJob({
            jobId: activeTarget.id,
            slug: activeTarget.slug,
            kind: 'stickv',
            preview: activeTarget.mode === 'preview',
            progress: activeTarget.progress,
            step: activeTarget.step,
            stage: activeTarget.stage || activeTarget.step,
            currentBeat: activeTarget.current_beat ?? null,
            totalBeats: activeTarget.total_beats ?? null,
            startedAt: activeTarget.started_at ?? null,
          });
          return;
        }

        const recentDone = stickvJobs.find(
          (r) =>
            r.status === 'done' &&
            !seenCompletedStickvJobs.has(r.id) &&
            (!selectedSlug || r.slug === selectedSlug),
        );
        if (recentDone) {
          seenCompletedStickvJobs.add(recentDone.id);
          void qc.invalidateQueries({ queryKey: ['stickv-list'] });
          void qc.invalidateQueries({ queryKey: ['unified-renders'] });
          toast.info(vi.stickvJob.renderDoneAway);
        }
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [selectedSlug, attachJob, qc, toast]);

  const loadedSlugRef = useRef<string>('');
  useEffect(() => {
    const found = projects.find((p) => p.slug === selectedSlug) ?? null;
    if (found) {
      if (loadedSlugRef.current === found.slug) {
        setDraft((prev) => {
          if (!prev || prev.slug !== found.slug) return found;
          // Chỉ cập nhật `last_render` từ server refetch để không ghi đè lời thoại đang sửa dở
          if (JSON.stringify(prev.last_render) !== JSON.stringify(found.last_render)) {
            return { ...prev, last_render: found.last_render };
          }
          return prev;
        });
        return;
      }
      loadedSlugRef.current = found.slug;
      setDraft(found);
      if (found.domain) setDomain(found.domain);
      if (found.music_mood) setMusicMood(found.music_mood);
      if (found.animation_mode) setAnimationMode(found.animation_mode);
      setTheme(found.theme);
      setSelectedBeatId((prev) =>
        found.beats.some((b) => b.id === prev) ? prev : (found.beats[0]?.id ?? ''),
      );
    }
  }, [selectedSlug, projects]);

  const hasBeats = Boolean(draft && draft.beats.length > 0);
  const isCreatorOpen = creatorManualOpen ?? !hasBeats;

  const activeBeatIndex = useMemo(() => {
    if (!draft || draft.beats.length === 0) return 0;
    const idx = draft.beats.findIndex((b) => b.id === selectedBeatId);
    return idx >= 0 ? idx : 0;
  }, [draft, selectedBeatId]);

  const activeBeat = useMemo(() => draft?.beats[activeBeatIndex] ?? null, [draft, activeBeatIndex]);

  const poseOptions = useMemo(() => {
    const labelMap = new Map(DEFAULT_POSE_OPTIONS.map((d) => [d.id, d.label]));
    const byId = new Map<string, { id: string; label: string; url: string; isVideo: boolean }>();

    for (const d of DEFAULT_POSE_OPTIONS) {
      byId.set(d.id, {
        id: d.id,
        label: d.label,
        url: `/api/stickv/poses/${encodeURIComponent(d.id)}`,
        isVideo: false,
      });
    }

    for (const p of listQuery.data?.poses ?? []) {
      if (!byId.has(p)) {
        byId.set(p, {
          id: p,
          label: labelMap.get(p) ?? EXTRA_POSE_LABELS[p] ?? p,
          url: `/api/stickv/poses/${encodeURIComponent(p)}`,
          isVideo: false,
        });
      }
    }

    for (const it of stickmanQuery.data?.items ?? []) {
      const isVideo = it.kind === 'video' || it.media_type === 'video';
      if (isVideo) {
        byId.set(it.name, {
          id: it.name,
          label: `🎬 Video: ${it.title || it.name}`,
          url: it.file_url || it.url,
          isVideo: true,
        });
      } else {
        const stem = it.name.replace(/\.[^.]+$/, '');
        if (!DEFAULT_POSE_OPTIONS.some((d) => d.id === stem) && !byId.has(it.name)) {
          byId.set(it.name, {
            id: it.name,
            label: it.title || it.name,
            url: it.url,
            isVideo: false,
          });
        }
      }
    }

    return Array.from(byId.values());
  }, [listQuery.data?.poses, stickmanQuery.data?.items]);

  const lastRenderVideoRef = useRef<HTMLVideoElement | null>(null);
  const canvasPoseVideoRef = useRef<HTMLVideoElement | null>(null);
  const activePoseVideoUrl =
    activeBeat?.clip_path || poseOptions.find((p) => p.id === activeBeat?.pose)?.url;
  useReleaseVideoOnUnmount(lastRenderVideoRef, draft?.last_render?.video_url);
  useReleaseVideoOnUnmount(canvasPoseVideoRef, activePoseVideoUrl);

  const genMutation = useMutation({
    mutationFn: () =>
      stickvApi.generate({
        idea: idea.trim(),
        topic,
        domain,
        animation_mode: animationMode,
        music_mood: musicMood,
        aspect,
        theme,
        target_minutes: targetMinutes,
        model: geminiModel,
      }),
    onSuccess: ({ project }) => {
      void qc.invalidateQueries({ queryKey: ['stickv-list'] });
      setSelectedSlug(project.slug);
      setDraft(project);
      if (project.domain) setDomain(project.domain);
      if (project.music_mood) setMusicMood(project.music_mood);
      setSelectedBeatId(project.beats[0]?.id ?? '');
      setCreatorManualOpen(false);
      toast.info(`Đã sinh ${project.beats.length} beat kịch bản StickV`);
    },
    onError: (e: Error) => toast.error(e),
  });

  const importJsonMutation = useMutation({
    mutationFn: () =>
      stickvApi.importJson({
        raw_json: rawJson.trim(),
        topic,
        domain,
        animation_mode: animationMode,
        music_mood: musicMood,
        aspect,
        theme,
      }),
    onSuccess: ({ project }) => {
      void qc.invalidateQueries({ queryKey: ['stickv-list'] });
      setSelectedSlug(project.slug);
      setDraft(project);
      setSelectedBeatId(project.beats[0]?.id ?? '');
      setRawJson('');
      setCreatorManualOpen(false);
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
        domain,
        animation_mode: animationMode,
        music_mood: musicMood,
        aspect,
        theme,
      }),
    onSuccess: ({ project }) => {
      void qc.invalidateQueries({ queryKey: ['stickv-list'] });
      setSelectedSlug(project.slug);
      setDraft(project);
      setSelectedBeatId(project.beats[0]?.id ?? '');
      setRawScript('');
      setCreatorManualOpen(false);
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
      const res = await stickvApi.render(draft.slug, preview);
      return {
        job_id: res.job_id,
        slug: draft.slug,
        preview,
        totalBeats: preview ? Math.min(3, draft.beats.length) : draft.beats.length,
      };
    },
    onSuccess: ({ job_id, slug, preview, totalBeats }) => {
      seenCompletedStickvJobs.delete(job_id);
      job.attachJob({
        jobId: job_id,
        slug,
        kind: 'stickv',
        engine: 'stickv',
        title: draft?.title || slug,
        route: `/stickv?slug=${encodeURIComponent(slug)}`,
        preview,
        progress: 2,
        step: 'Sinh giọng VieNeu-TTS',
        stage: 'Sinh giọng VieNeu-TTS',
        message: vi.stickvJob.queued,
        currentBeat: 0,
        totalBeats,
        startedAt: Date.now() / 1000,
        estimateSeconds: Math.max(15, totalBeats * (preview ? 8 : 18)),
      });
      toast.info('Đã đưa StickV vào hàng đợi dựng');
    },
    onError: (e: Error) => toast.error(e),
  });

  useEffect(() => {
    if (job.finished && (job.kind === 'stickv' || job.finished.kind === 'stickv')) {
      seenCompletedStickvJobs.add(job.finished.id);
    }
  }, [job.finished, job.kind]);

  const isStickvJobRunning =
    job.running && job.kind === 'stickv' && (!draft?.slug || job.slug === draft.slug);

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

  const activePoseName = activeBeat?.pose || 'explain';
  const matchedStickman = (stickmanQuery.data?.items ?? []).find(
    (it) =>
      it.name === activePoseName ||
      it.name === `${activePoseName}.png` ||
      it.name === 'default.png',
  );
  const currentPoseUrl = `/api/stickv/poses/${encodeURIComponent(activePoseName)}${
    matchedStickman?.modified_at ? `?t=${encodeURIComponent(matchedStickman.modified_at)}` : ''
  }`;

  const currentAspect = draft?.aspect ?? aspect;
  const totalDurationSec = useMemo(
    () => (draft?.beats ?? []).reduce((acc, b) => acc + (b.duration_sec || 3.0), 0),
    [draft?.beats],
  );

  // Tab 1 (Kịch bản): CHỈ chứa lời đọc (narration), tiêu đề bảng, câu chốt + nút Thêm Beat & Lưu (0 dropdown hình ảnh!)
  const renderScriptBeatEditor = () => {
    if (!draft || !activeBeat) return null;
    return (
      <Card className="space-y-2.5">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line pb-2">
          <div className="flex min-w-0 items-center gap-2">
            <span className="shrink-0 rounded-md bg-brand px-2 py-0.5 text-tiny font-extrabold text-white tabular-nums">
              #{activeBeatIndex + 1} · Chương {activeBeat.chapter}
            </span>
            <span className="truncate text-tiny font-bold text-text">
              {activeBeat.chapter_title || activeBeat.id}
            </span>
          </div>

          <div className="flex items-center gap-1.5">
            <Button
              tone="soft"
              size="sm"
              icon={<PlusIcon size={13} />}
              onClick={() => {
                const next = makeEmptyBeat(draft.beats.length + 1);
                setDraft({ ...draft, beats: [...draft.beats, next] });
                setSelectedBeatId(next.id);
              }}
            >
              Thêm Beat
            </Button>
            <Button
              tone="ink"
              size="sm"
              busy={saveMutation.isPending}
              onClick={() => saveMutation.mutate(draft)}
            >
              Lưu
            </Button>
          </div>
        </div>

        <input
          type="text"
          aria-label="Tiêu đề bảng minh họa"
          value={activeBeat.board_title ?? ''}
          onChange={(e) => updateBeat(activeBeat.id, { board_title: e.target.value })}
          placeholder="Tiêu đề trên bảng minh họa..."
          className="ui-input !min-h-[36px] text-small font-semibold"
        />

        <textarea
          aria-label="Lời đọc beat"
          value={activeBeat.narration}
          onChange={(e) => updateBeat(activeBeat.id, { narration: e.target.value })}
          rows={3}
          placeholder="Lời đọc tiếng Việt cho beat đang chọn..."
          className="ui-input !min-h-[82px] text-small"
        />

        <input
          type="text"
          aria-label="Câu chốt ý (takeaway)"
          value={
            activeBeat.takeaway ??
            (typeof activeBeat.board_data?.takeaway === 'string'
              ? activeBeat.board_data.takeaway
              : '')
          }
          onChange={(e) => {
            const val = e.target.value;
            updateBeat(activeBeat.id, {
              takeaway: val,
              board_data: { ...(activeBeat.board_data ?? {}), takeaway: val },
            });
          }}
          placeholder="Chốt lại 1 dòng ngắn trên bảng (tuỳ chọn)..."
          className="ui-input !min-h-[36px] text-tiny"
        />
      </Card>
    );
  };

  // Tab 2 (Hình ảnh): Chứa cài đặt trực quan của beat đang chọn (Dáng, Biểu cảm, Góc máy, Loại bảng, Tương tác, Chèn clip/ảnh)
  const renderVisualBeatEditor = () => {
    if (!draft || !activeBeat) return null;
    return (
      <Card className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line pb-2">
          <span className="text-small font-bold text-text">
            Hình ảnh & Diễn hoạt Beat #{activeBeatIndex + 1}
          </span>
          <div className="flex items-center gap-1.5">
            <label className="inline-flex cursor-pointer items-center gap-1 rounded-lg border border-line bg-soft px-2.5 py-1 text-tiny font-semibold text-text hover:bg-soft-2">
              <UploadIcon size={12} />
              <span>{activeBeat.media_path ? 'Đổi clip/ảnh' : 'Chèn clip/ảnh'}</span>
              <input
                type="file"
                accept=".png,.jpg,.jpeg,.webp,.mp4,.mov,.webm"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) void handleUploadBeatMedia(activeBeat.id, f);
                }}
              />
            </label>
            <Button
              tone="ink"
              size="sm"
              busy={saveMutation.isPending}
              onClick={() => saveMutation.mutate(draft)}
            >
              Lưu
            </Button>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2">
          <StudioSelect
            aria-label="Dáng người que"
            variant="compact"
            value={activeBeat.pose}
            onChange={(val) => {
              const chosen = poseOptions.find((p) => p.id === val);
              updateBeat(activeBeat.id, {
                pose: val,
                clip_path: chosen?.isVideo ? chosen.url : '',
              });
            }}
            options={poseOptions.map((p) => ({
              value: p.id,
              label: `Dáng: ${p.label}`,
            }))}
          />

          <StudioSelect
            aria-label="Biểu cảm khuôn mặt"
            variant="compact"
            value={activeBeat.emotion ?? 'auto'}
            onChange={(val) => updateBeat(activeBeat.id, { emotion: val as StickvEmotion })}
            options={EMOTIONS.map((em) => ({
              value: em.id,
              label: `Cảm xúc: ${em.label}`,
            }))}
          />

          <StudioSelect
            aria-label="Góc máy ảo"
            variant="compact"
            value={activeBeat.camera_shot ?? 'wide_stage'}
            onChange={(val) => updateBeat(activeBeat.id, { camera_shot: val as StickvCameraShot })}
            options={CAMERA_SHOTS.map((cam) => ({
              value: cam.id,
              label: `Cam: ${cam.label}`,
            }))}
          />

          <StudioSelect
            aria-label="Loại bảng minh họa"
            variant="compact"
            value={activeBeat.board_type}
            onChange={(val) => updateBeat(activeBeat.id, { board_type: val as StickvBoardType })}
            options={BOARD_TYPES.map((bt) => ({
              value: bt.id,
              label: `Bảng: ${bt.label}`,
            }))}
          />

          <StudioSelect
            aria-label="Tương tác sân khấu"
            variant="compact"
            value={activeBeat.interaction ?? 'none'}
            onChange={(val) => updateBeat(activeBeat.id, { interaction: val as StickvInteraction })}
            options={INTERACTIONS.map((it) => ({
              value: it.id,
              label: `Tương tác: ${it.label}`,
            }))}
          />

          <StudioSelect
            aria-label={vi.stickvJob.faceMoodLabel}
            variant="compact"
            value={activeBeat.face_mood ?? ''}
            onChange={(val) =>
              updateBeat(activeBeat.id, {
                face_mood: (val || null) as StickvFaceMood | null,
              })
            }
            options={[
              { value: '', label: `Sắc thái: ${vi.stickvJob.faceMoods.auto}` },
              { value: 'explaining', label: `Sắc thái: ${vi.stickvJob.faceMoods.explaining}` },
              { value: 'curious', label: `Sắc thái: ${vi.stickvJob.faceMoods.curious}` },
              { value: 'excited', label: `Sắc thái: ${vi.stickvJob.faceMoods.excited}` },
              { value: 'skeptical', label: `Sắc thái: ${vi.stickvJob.faceMoods.skeptical}` },
              { value: 'shocked', label: `Sắc thái: ${vi.stickvJob.faceMoods.shocked}` },
              { value: 'warm_cta', label: `Sắc thái: ${vi.stickvJob.faceMoods.warm_cta}` },
            ]}
          />

          <StudioSelect
            aria-label="Chuyển động"
            variant="compact"
            value={activeBeat.motion}
            onChange={(val) => updateBeat(activeBeat.id, { motion: val as StickvMotion })}
            options={MOTIONS.map((m) => ({ value: m.id, label: m.label }))}
          />
        </div>

        <div className="flex flex-wrap items-center gap-2 pt-0.5">
          <StudioSelect
            aria-label="Hướng nhìn"
            variant="compact"
            autoWidth
            value={activeBeat.facing}
            onChange={(val) => updateBeat(activeBeat.id, { facing: val as 'left' | 'right' })}
            options={[
              { value: 'right', label: 'Quay phải →' },
              { value: 'left', label: '← Quay trái' },
            ]}
          />
          <input
            type="text"
            aria-label="Từ khóa Icon (prop_query)"
            placeholder="Từ khóa Icon (vd: brain, earth)..."
            value={activeBeat.prop_query ?? ''}
            onChange={(e) => updateBeat(activeBeat.id, { prop_query: e.target.value })}
            className="ui-input !min-h-[32px] min-w-[120px] flex-1 text-tiny"
          />
          <Button
            size="sm"
            tone="soft"
            onClick={async () => {
              const q = (activeBeat.prop_query ?? '').trim();
              if (!q) return;
              try {
                const res = await stickvApi.searchIconify(q);
                if (res.items[0]?.png_url) {
                  setPropPreviewMap((prev) => ({
                    ...prev,
                    [activeBeat.id]: res.items[0].png_url,
                  }));
                  toast.info(`Đã tìm thấy icon "${res.items[0].id}"`);
                } else {
                  toast.info('Không thấy icon khớp, sẽ dùng huy hiệu dự phòng');
                }
              } catch (err) {
                toast.error(err);
              }
            }}
          >
            Tìm Icon
          </Button>
          <Button
            size="sm"
            tone="soft"
            busy={refPhotoSearching}
            onClick={async () => {
              const q = (activeBeat.prop_query || activeBeat.board_title || '').trim();
              if (!q) return;
              setRefPhotoSearching(true);
              try {
                const res = await stickvApi.searchReferenceImages(q, 6);
                setRefPhotoResults(res.items);
                if (res.items.length === 0) {
                  toast.info(vi.stickvJob.photoNotFoundToast);
                }
              } catch (err) {
                toast.error(err);
              } finally {
                setRefPhotoSearching(false);
              }
            }}
          >
            {refPhotoSearching ? vi.stickvJob.swappingPhotoBtn : vi.stickvJob.swapPhotoBtn}
          </Button>
          <Button
            size="sm"
            tone="soft"
            busy={aiPhotoGenerating}
            onClick={async () => {
              if (!draft) return;
              const prompt = (
                activeBeat.image_prompt ||
                activeBeat.prop_query ||
                activeBeat.board_title ||
                activeBeat.narration ||
                ''
              ).trim();
              if (!prompt) return;
              setAiPhotoGenerating(true);
              try {
                const res = await stickvApi.generateBeatPhoto(draft.slug, activeBeat.id, {
                  prompt,
                  caption: activeBeat.board_title ?? '',
                });
                setDraft(res.project);
                setRefPhotoResults([]);
                toast.info(vi.stickvJob.photoGeneratedToast);
              } catch (err) {
                toast.error(err);
              } finally {
                setAiPhotoGenerating(false);
              }
            }}
          >
            {aiPhotoGenerating
              ? vi.stickvJob.generatingAiPhotoBtn
              : vi.stickvJob.generateAiPhotoBtn}
          </Button>
          {propPreviewMap[activeBeat.id] && (
            <img
              src={propPreviewMap[activeBeat.id]}
              alt={activeBeat.prop_query ?? 'icon'}
              className="h-7 w-7 rounded border border-line bg-white object-contain p-0.5"
            />
          )}
        </div>
        {refPhotoResults.length > 0 && (
          <div className="grid grid-cols-3 gap-2 pt-1">
            {refPhotoResults.map((item) => (
              <button
                key={item.id}
                type="button"
                title={item.title}
                onClick={async () => {
                  try {
                    const res = await stickvApi.applyReferenceImage(draft.slug, activeBeat.id, {
                      url: item.url,
                      query: activeBeat.prop_query ?? '',
                      caption: activeBeat.board_title ?? '',
                    });
                    setDraft(res.project);
                    setRefPhotoResults([]);
                    toast.info(vi.stickvJob.photoPickedToast);
                  } catch (err) {
                    toast.error(err);
                  }
                }}
                className="group overflow-hidden rounded-lg border border-line bg-soft text-left transition hover:border-brand"
              >
                <img src={item.thumb_url} alt={item.title} className="h-16 w-full object-cover" />
                <span className="block truncate px-1.5 py-0.5 text-[10px] text-muted">
                  {item.source === 'wikimedia' ? 'Wikimedia' : 'Pixabay'}
                </span>
              </button>
            ))}
          </div>
        )}
      </Card>
    );
  };

  return (
    <StudioShell
      topBar={{
        engineBadge: 'StickV',
        savedText: saveMutation.isPending ? 'Đang lưu…' : vi.studioShell.savedBadge,
        projectSelector:
          projects.length > 0 ? (
            <StudioSelect
              aria-label="Chọn dự án StickV"
              variant="compact"
              value={selectedSlug}
              onChange={(val) => setSelectedSlug(val)}
              options={projects.map((p) => ({
                value: p.slug,
                label: `${p.title} (${p.aspect})`,
              }))}
              className="w-full min-w-0 max-w-[260px] lg:max-w-[360px]"
            />
          ) : undefined,
        projectMenuItems: draft
          ? [
              {
                key: 'rename',
                label: vi.studioShell.renameProject,
                onSelect: () => {
                  setRenameTitle(draft.title);
                  setRenameOpen(true);
                },
              },
              {
                key: 'delete',
                label: vi.studioShell.deleteProject,
                danger: true,
                disabled: isStickvJobRunning,
                reason: vi.projects.renderingReason,
                onSelect: () => deleteMutation.mutate(draft.slug),
              },
            ]
          : undefined,
        aspect: currentAspect,
        onAspectChange: (nextAspect) => {
          setAspect(nextAspect);
          if (draft) setDraft({ ...draft, aspect: nextAspect });
        },
        exportProps: {
          aspect: currentAspect,
          outroEnabled: draft?.outro ?? true,
          onOutroChange: draft ? (checked) => setDraft({ ...draft, outro: checked }) : undefined,
          showWatermarkControl: true,
          onExportPreview: () => renderMutation.mutate(true),
          onExportFinal: () => renderMutation.mutate(false),
          previewLabel: vi.stickvJob.exportPreviewBtn,
          finalLabel: vi.stickvJob.exportFinalBtn,
          disabled: !draft || draft.beats.length === 0,
          isSubmitting: renderMutation.isPending,
          isRendering: isStickvJobRunning,
          subscribeGlobalProgress: true,
          onCancelRender: () => void job.cancel(),
        },
      }}
      liveBanner={listQuery.isError ? <ErrorNote error={listQuery.error} /> : undefined}
      activeTab={activeTab}
      onTabChange={(id) => setActiveTab(id as 'script' | 'visual' | 'audio' | 'inspect')}
      tabs={[
        {
          id: 'script',
          label: vi.studioShell.tabs.script,
          icon: <SparklesIcon size={13} />,
          content: (
            <div className="space-y-3.5">
              {/* Khung Khởi tạo Kịch bản AI: tự động gấp gọn khi dự án đã có >= 1 beat */}
              <div className="rounded-card border border-line bg-card shadow-card">
                <button
                  type="button"
                  aria-expanded={isCreatorOpen}
                  onClick={() => setCreatorManualOpen(!isCreatorOpen)}
                  className="flex w-full items-center justify-between gap-2 px-3.5 py-2.5 text-left text-tiny font-bold text-text transition-colors hover:bg-soft rounded-card"
                >
                  <span>{vi.studioShell.aiCreatorAccordionBtn}</span>
                  <ChevronDownIcon
                    size={15}
                    className={cx(
                      'shrink-0 text-muted transition-transform duration-150',
                      isCreatorOpen && 'rotate-180',
                    )}
                  />
                </button>

                <div
                  className="ui-accordion-grid"
                  data-open={isCreatorOpen ? 'true' : 'false'}
                  aria-hidden={!isCreatorOpen}
                >
                  <div className="ui-accordion-inner">
                    <div className="space-y-3 border-t border-line px-3.5 pb-3.5 pt-3">
                      <SegmentedControl
                        roleMode="tab"
                        aria-label="Chế độ đầu vào StickV"
                        value={inputMode}
                        onChange={(next) => setInputMode(next)}
                        options={[
                          { value: 'ai', label: 'Tạo tự động (API)' },
                          { value: 'json', label: 'Dán JSON (0 Token)' },
                          { value: 'script', label: 'Dán Lời thoại' },
                        ]}
                      />

                      {inputMode === 'ai' && (
                        <div className="space-y-2">
                          <textarea
                            value={idea}
                            onChange={(e) => setIdea(e.target.value)}
                            rows={2}
                            placeholder="Nhập ý tưởng video (vd: Tại sao 90% người mới đầu tư hay mất tiền?)"
                            className="ui-input !min-h-[60px] text-small"
                          />
                          <StudioSelect
                            aria-label="Chọn model Gemini"
                            variant="compact"
                            value={geminiModel}
                            onChange={(val) => setGeminiModel(val)}
                            options={models.map((m) => ({ value: m.id, label: m.name }))}
                          />
                        </div>
                      )}

                      {inputMode === 'json' && (
                        <div className="space-y-2">
                          <div className="flex flex-wrap items-center justify-between gap-2 rounded-inner border border-line bg-soft p-2">
                            <span className="text-tiny font-semibold text-text-2">
                              Copy Prompt Đạo diễn 5 chặng sang Gemini Web rồi dán JSON:
                            </span>
                            <Button
                              tone="soft"
                              size="sm"
                              icon={<CopyIcon size={13} />}
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
                            rows={3}
                            placeholder='Dán JSON từ Web Gemini Pro (vd: {"title":"...","beats":[...]})'
                            className="ui-input font-mono text-tiny"
                          />
                        </div>
                      )}

                      {inputMode === 'script' && (
                        <div className="space-y-2">
                          <input
                            type="text"
                            value={rawTitle}
                            onChange={(e) => setRawTitle(e.target.value)}
                            placeholder="Tiêu đề video (không bắt buộc)..."
                            className="ui-input !min-h-[36px] text-small"
                          />
                          <textarea
                            value={rawScript}
                            onChange={(e) => setRawScript(e.target.value)}
                            rows={3}
                            placeholder="Dán lời thoại có sẵn (mỗi câu/dòng tự tách thành 1 beat)..."
                            className="ui-input text-small"
                          />
                        </div>
                      )}

                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <SegmentedControl
                          aria-label="Thời lượng"
                          value={String(targetMinutes)}
                          onChange={(next) => setTargetMinutes(Number(next))}
                          options={[
                            { value: '1', label: '1p' },
                            { value: '3', label: '3p' },
                            { value: '5', label: '5p' },
                            { value: '8', label: '8p' },
                            { value: '10', label: '10p' },
                          ]}
                        />

                        {inputMode === 'ai' && (
                          <Button
                            tone="ink"
                            size="sm"
                            busy={genMutation.isPending}
                            disabled={!idea.trim()}
                            icon={<SparklesIcon size={14} />}
                            onClick={() => genMutation.mutate()}
                          >
                            Sinh kịch bản StickV
                          </Button>
                        )}
                        {inputMode === 'json' && (
                          <Button
                            tone="ink"
                            size="sm"
                            busy={importJsonMutation.isPending}
                            disabled={!rawJson.trim()}
                            icon={<SparklesIcon size={14} />}
                            onClick={() => importJsonMutation.mutate()}
                          >
                            Nạp JSON (0 Token)
                          </Button>
                        )}
                        {inputMode === 'script' && (
                          <Button
                            tone="ink"
                            size="sm"
                            busy={importScriptMutation.isPending}
                            disabled={!rawScript.trim()}
                            icon={<SparklesIcon size={14} />}
                            onClick={() => importScriptMutation.mutate()}
                          >
                            Tách lời thoại thành Beat
                          </Button>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {renderScriptBeatEditor()}
            </div>
          ),
        },
        {
          id: 'visual',
          label: vi.studioShell.tabs.visual,
          icon: <FilmIcon size={13} />,
          content: (
            <div className="space-y-3.5">
              {renderVisualBeatEditor()}

              <Card className="space-y-2.5">
                <h3 className="text-small font-bold text-text">Bối cảnh & Phong cách dự án</h3>
                <div className="grid grid-cols-2 gap-2">
                  <StudioSelect
                    aria-label="Bối cảnh sân khấu"
                    variant="compact"
                    value={draft?.domain ?? domain}
                    onChange={(val) => {
                      const nextDom = val as StickvDomain;
                      const syncedTheme: StickvTheme =
                        nextDom === 'paper_classic' || nextDom === 'history_geo' ? 'cream' : 'dark';
                      setDomain(nextDom);
                      setTheme(syncedTheme);
                      if (draft) setDraft({ ...draft, domain: nextDom, theme: syncedTheme });
                    }}
                    options={DOMAINS.map((d) => ({ value: d.id, label: d.label }))}
                  />
                  <StudioSelect
                    aria-label="Chủ đề màu"
                    variant="compact"
                    value={draft?.theme ?? theme}
                    onChange={(val) => {
                      const nextT = val as StickvTheme;
                      setTheme(nextT);
                      if (draft) setDraft({ ...draft, theme: nextT });
                    }}
                    options={[
                      { value: 'cream', label: 'Giấy kem (#FAF7F0)' },
                      { value: 'dark', label: 'Bảng tối (#111827)' },
                    ]}
                  />
                </div>
                <StudioSelect
                  aria-label="Chế độ diễn hoạt"
                  variant="compact"
                  value={draft?.animation_mode ?? animationMode}
                  onChange={(val) => {
                    const nextMode = val as StickvAnimationMode;
                    setAnimationMode(nextMode);
                    if (draft) setDraft({ ...draft, animation_mode: nextMode });
                  }}
                  options={[
                    { value: 'auto', label: 'Tự động (Puppet 2D → WebM → PNG)' },
                    { value: 'static', label: 'Chỉ dùng Ảnh Pose tĩnh' },
                  ]}
                />
              </Card>
            </div>
          ),
        },
        {
          id: 'audio',
          label: vi.studioShell.tabs.audio,
          icon: <MusicIcon size={13} />,
          content: (
            <div className="space-y-3.5">
              <Card className="space-y-3">
                <h3 className="text-small font-bold text-text">Giọng đọc VieNeu, Nhạc nền & SFX</h3>
                <StudioSelect
                  label="Giọng đọc chính"
                  aria-label="Chọn giọng đọc VieNeu"
                  value={
                    draft && voiceOptions.some((v) => v.id === draft.voice_id)
                      ? draft.voice_id
                      : defaultVoiceId
                  }
                  onChange={(val) => {
                    if (draft) setDraft({ ...draft, voice_id: val });
                  }}
                  options={voiceOptions.map((v) => ({
                    value: v.id,
                    label: `Giọng: ${v.label}`,
                  }))}
                />
                <StudioSelect
                  label="Tâm trạng nhạc nền"
                  aria-label="Tâm trạng nhạc"
                  value={draft?.music_mood ?? musicMood}
                  onChange={(val) => {
                    setMusicMood(val);
                    if (draft) setDraft({ ...draft, music_mood: val });
                  }}
                  options={MUSIC_MOODS.map((m) => ({ value: m.id, label: m.label }))}
                />
                <StudioSelect
                  label="Nhóm chủ đề âm thanh"
                  aria-label="Nhóm nhạc"
                  value={topic}
                  onChange={(val) => setTopic(val)}
                  options={[
                    { value: 'science', label: 'Khoa học / Chill' },
                    { value: 'fun', label: 'Vui nhộn' },
                    { value: 'history', label: 'Kịch tính' },
                    { value: 'mystery', label: 'Bí ẩn' },
                  ]}
                />
                {activeBeat && (
                  <StudioSelect
                    label={`SFX cho Beat #${activeBeatIndex + 1}`}
                    aria-label="Âm thanh SFX"
                    value={activeBeat.sfx_tag}
                    onChange={(val) => updateBeat(activeBeat.id, { sfx_tag: val as StickvSfxTag })}
                    options={SFX_TAGS.map((s) => ({ value: s.id, label: `SFX: ${s.label}` }))}
                  />
                )}
                {draft && (
                  <div className="flex items-center justify-between gap-2 rounded-inner border border-line bg-soft px-3 py-2 text-tiny font-bold text-text">
                    <span>Thêm Outro 4s (@HayBietTuot)</span>
                    <Switch
                      checked={draft.outro ?? true}
                      onChange={(checked) => setDraft({ ...draft, outro: checked })}
                      label="Thêm Outro 4s (@HayBietTuot)"
                    />
                  </div>
                )}
              </Card>
            </div>
          ),
        },
        {
          id: 'inspect',
          label: vi.studioShell.tabs.inspect,
          icon: <EyeIcon size={13} />,
          content: draft ? (
            <CinemaInspectorPanel
              stickvProject={draft}
              beatId={activeBeat?.id}
              disabled={job.running}
            />
          ) : (
            <Card className="p-4 text-small text-muted">Chưa có dự án StickV để kiểm định.</Card>
          ),
        },
      ]}
      canvas={{
        aspect: currentAspect,
        safeZoneActive: safeZone !== 'none',
        onToggleSafeZone: () => setSafeZone((prev) => (prev === 'none' ? 'tiktok' : 'none')),
        onOpenContactSheet: () => setActiveTab('inspect'),
        onPlayPreview: () => renderMutation.mutate(true),
        playPreviewLabel: vi.studioShell.canvasPlayBtn,
        children: (
          <div className="relative h-full w-full">
            {draft?.last_render?.video_url ? (
              <video
                key={draft.last_render.video_url}
                ref={lastRenderVideoRef}
                src={draft.last_render.video_url}
                controls
                preload="metadata"
                className="h-full w-full bg-black object-contain"
              />
            ) : (
              <div
                className={`flex h-full w-full flex-col justify-between p-4 ${
                  DOMAINS.find((d) => d.id === (draft?.domain ?? domain))?.bgClass ??
                  ((draft?.theme ?? theme) === 'cream'
                    ? 'bg-[#FAF7F0] text-slate-900'
                    : 'bg-[#111827] text-slate-50')
                }`}
              >
                {activeBeat?.board_type !== 'none' && (
                  <div className="rounded-xl border border-black/10 bg-white/90 p-3 text-slate-900 shadow-sm">
                    <p className="text-[11px] font-extrabold uppercase text-[#D9232E]">
                      {activeBeat?.board_type ?? 'bullets'}
                    </p>
                    <p className="mt-1 text-xs font-bold">
                      {activeBeat?.board_title || draft?.title || 'Bảng minh họa thông minh'}
                    </p>
                    <p className="mt-1 line-clamp-2 text-[11px] text-slate-600">
                      {activeBeat?.narration || 'Sinh kịch bản hoặc chọn beat để xem trước...'}
                    </p>
                  </div>
                )}

                <div className="flex flex-1 items-end justify-center pb-2">
                  {activeBeat?.clip_path ||
                  poseOptions.find((p) => p.id === activeBeat?.pose)?.isVideo ? (
                    <video
                      key={
                        activeBeat?.clip_path ||
                        poseOptions.find((p) => p.id === activeBeat?.pose)?.url
                      }
                      ref={canvasPoseVideoRef}
                      src={
                        activeBeat?.clip_path ||
                        poseOptions.find((p) => p.id === activeBeat?.pose)?.url
                      }
                      muted
                      playsInline
                      preload="metadata"
                      className="h-36 w-auto rounded-lg object-contain"
                    />
                  ) : (
                    <img
                      src={
                        listQuery.data?.puppet_ready && (draft?.animation_mode ?? 'auto') === 'auto'
                          ? `/api/stickv/puppet/preview?pose=${encodeURIComponent(
                              activeBeat?.pose ?? 'explain',
                            )}&interaction=${encodeURIComponent(
                              activeBeat?.interaction ?? 'none',
                            )}&facing=${encodeURIComponent(
                              activeBeat?.facing ?? 'right',
                            )}&emotion=${encodeURIComponent(activeBeat?.emotion ?? 'auto')}`
                          : currentPoseUrl
                      }
                      alt={activeBeat?.pose ?? 'explain'}
                      onError={(e) => {
                        if (!e.currentTarget.dataset.fb) {
                          e.currentTarget.dataset.fb = '1';
                          e.currentTarget.src = currentPoseUrl || '/api/stickv/poses/explain';
                        }
                      }}
                      className={`h-36 w-auto object-contain ${
                        !(
                          listQuery.data?.puppet_ready &&
                          (draft?.animation_mode ?? 'auto') === 'auto'
                        ) && activeBeat?.facing === 'left'
                          ? '-scale-x-100'
                          : ''
                      }`}
                    />
                  )}
                </div>
              </div>
            )}
            <SafeZoneOverlay platform={safeZone} />
          </div>
        ),
      }}
      timeline={
        draft
          ? {
              items: draft.beats.map((b, idx) => ({
                id: b.id,
                index: idx + 1,
                title: b.board_title,
                summary: b.narration,
                durationSec: b.duration_sec || 3.0,
              })),
              selectedId: activeBeat?.id ?? '',
              onSelect: (id) => setSelectedBeatId(id),
              onAdd: () => {
                const next = makeEmptyBeat(draft.beats.length + 1);
                setDraft({ ...draft, beats: [...draft.beats, next] });
                setSelectedBeatId(next.id);
              },
              addLabel: '+ Thêm Beat',
              onDelete: (id) => {
                if (draft.beats.length <= 1) return;
                setDraft({
                  ...draft,
                  beats: draft.beats.filter((x) => x.id !== id),
                });
              },
              totalDurationSec,
            }
          : undefined
      }
      modals={
        <Dialog
          open={renameOpen}
          onClose={() => setRenameOpen(false)}
          title={vi.studioShell.renameDialogTitle}
          footer={
            <div className="flex items-center justify-end gap-2">
              <Button tone="soft" size="sm" onClick={() => setRenameOpen(false)}>
                {vi.common.cancel}
              </Button>
              <Button
                tone="brand"
                size="sm"
                disabled={!renameTitle.trim() || !draft}
                onClick={() => {
                  if (!draft || !renameTitle.trim()) return;
                  const updated = { ...draft, title: renameTitle.trim() };
                  setDraft(updated);
                  saveMutation.mutate(updated);
                  setRenameOpen(false);
                }}
              >
                {vi.common.save}
              </Button>
            </div>
          }
        >
          <Input
            label={vi.studioShell.renameInputLabel}
            value={renameTitle}
            onChange={(e) => setRenameTitle(e.target.value)}
          />
        </Dialog>
      }
    />
  );
}
