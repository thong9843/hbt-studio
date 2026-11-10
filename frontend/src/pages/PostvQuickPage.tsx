import { useQuery } from '@tanstack/react-query';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api, fileUrl } from '../api/endpoints';
import type {
  PostvPickComment,
  PostvPickData,
  PostvQuickOptions,
  PostvStage,
  PostvStageEvent,
} from '../api/types';
import {
  AlertIcon,
  CheckIcon,
  CopyIcon,
  DownloadIcon,
  FolderIcon,
  GripIcon,
  PlayIcon,
  PlusIcon,
  StopIcon,
  UploadIcon,
} from '../components/icons';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { Chip } from '../components/ui/Chip';
import { Dialog } from '../components/ui/Dialog';
import { Menu } from '../components/ui/Menu';
import { Progress } from '../components/ui/Progress';
import { Select } from '../components/ui/Select';
import { cx } from '../components/ui/cx';
import { vi } from '../i18n/vi';

const T = vi.postvQuick;

const STAGE_ORDER: PostvStage[] = ['fetch', 'pick', 'script', 'voice', 'render', 'done'];

const DURATION_CHOICES = [
  { value: 60, label: T.options.duration60 },
  { value: 90, label: T.options.duration90 },
  { value: 120, label: T.options.duration120 },
  { value: 150, label: T.options.duration150 },
  { value: 180, label: T.options.duration180 },
] as const;

interface PickSnippetData {
  handle?: string;
  snippet?: string;
  picked_count?: number;
  total_comments?: number;
  estimated_seconds?: number;
}

interface CompletedOutput {
  video?: string;
  cover?: string | null;
  youtube_cover?: string | null;
  publish?: string;
  srt?: string | null;
  duration?: number;
  fps?: number;
  project_slug?: string;
  picked_comments?: number;
  total_comments?: number;
  target_seconds?: number;
  warning?: string | null;
}

export function PostvQuickPage() {
  const navigate = useNavigate();

  // Danh sách các dự án để hiện ở cột trái
  const { data: projectsData, refetch: refetchProjects } = useQuery({
    queryKey: ['projects'],
    queryFn: api.listProjects,
    staleTime: 10_000,
  });
  const postvProjects = (projectsData || []).filter((p) => p.kind === 'postv');

  // Lấy danh sách giọng VieNeu & tuỳ chọn đã nhớ
  const { data: voiceList } = useQuery({
    queryKey: ['voices'],
    queryFn: api.listVoices,
    staleTime: 60_000,
  });
  const { data: postvSettings } = useQuery({
    queryKey: ['postv-settings'],
    queryFn: api.getPostvSettings,
    staleTime: 60_000,
  });
  const { data: voicePref } = useQuery({
    queryKey: ['voice-preference'],
    queryFn: api.getVoicePreference,
    staleTime: 60_000,
  });
  const { data: musicList } = useQuery({
    queryKey: ['music'],
    queryFn: api.listMusic,
    staleTime: 60_000,
  });

  // Trạng thái nhập liệu & tuỳ chọn
  const [input, setInput] = useState('');
  const [selectedVoice, setSelectedVoice] = useState<string | null>(null);
  const [duration, setDuration] = useState<number>(90);
  const [music, setMusic] = useState<'auto' | 'none'>('auto');
  const [selectedMusicId, setSelectedMusicId] = useState<string>('');
  const [fps, setFps] = useState<30 | 60>(60);
  const [outro, setOutro] = useState<boolean>(true);
  const [pickMode, setPickMode] = useState<'auto' | 'manual'>(() => {
    return (localStorage.getItem('hbt_postv_pick_mode') as 'auto' | 'manual') || 'auto';
  });

  // Tự động chọn ngẫu nhiên 1 bài BGM mặc định khi mở trang nếu người dùng chưa chọn thủ công
  useEffect(() => {
    if (music !== 'none' && !selectedMusicId && musicList && musicList.length > 0) {
      const idx = Math.floor(Math.random() * musicList.length);
      setSelectedMusicId(musicList[idx].id);
    }
  }, [music, selectedMusicId, musicList]);

  // Trạng thái nghe thử giọng
  const [isPlayingSample, setIsPlayingSample] = useState(false);
  const audioSampleRef = useRef<HTMLAudioElement | null>(null);

  // Khởi tạo giọng đọc từ settings postv.json hoặc preferences
  useEffect(() => {
    if (!selectedVoice) {
      if (postvSettings?.voice_id) {
        setSelectedVoice(postvSettings.voice_id);
      } else if (voicePref?.voice_id) {
        setSelectedVoice(voicePref.voice_id);
      } else if (voiceList?.voices && voiceList.voices.length > 0) {
        setSelectedVoice(voiceList.voices[0].id);
      }
    }
  }, [postvSettings, voicePref, voiceList, selectedVoice]);

  // Đổi giọng đọc và lưu vào postv.json
  const handleVoiceChange = (vId: string) => {
    setSelectedVoice(vId);
    if (audioSampleRef.current) {
      audioSampleRef.current.pause();
      setIsPlayingSample(false);
    }
    void api.savePostvSettings({ voice_id: vId });
  };

  // Nghe thử giọng đọc
  const handleToggleSample = (e?: React.MouseEvent) => {
    e?.stopPropagation();
    if (!selectedVoice) return;
    if (isPlayingSample && audioSampleRef.current) {
      audioSampleRef.current.pause();
      audioSampleRef.current.currentTime = 0;
      setIsPlayingSample(false);
      return;
    }

    if (audioSampleRef.current) {
      audioSampleRef.current.pause();
    }
    const audio = new Audio(api.voiceSampleUrl(selectedVoice));
    audioSampleRef.current = audio;
    setIsPlayingSample(true);
    audio.play().catch(() => setIsPlayingSample(false));
    audio.onended = () => setIsPlayingSample(false);
  };

  // Trạng thái chuỗi tự động
  const [jobId, setJobId] = useState<string | null>(null);
  const [projectSlug, setProjectSlug] = useState<string | null>(null);
  const [submittedInput, setSubmittedInput] = useState<string>('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [duplicateSlug, setDuplicateSlug] = useState<string | null>(null);

  // Trạng thái chọn bình luận thủ công (waiting_pick)
  const [isWaitingPick, setIsWaitingPick] = useState(false);
  const [manualPickData, setManualPickData] = useState<PostvPickData | null>(null);
  const [orderedComments, setOrderedComments] = useState<PostvPickComment[]>([]);
  const [checkedCommentIds, setCheckedCommentIds] = useState<string[]>([]);
  const [expandedCommentIds, setExpandedCommentIds] = useState<Set<string>>(new Set());
  const [draggedIdx, setDraggedIdx] = useState<number | null>(null);

  // Trạng thái xoá video gần đây
  const [deletingSlug, setDeletingSlug] = useState<string | null>(null);

  // Tiến trình SSE
  const [currentStage, setCurrentStage] = useState<PostvStage>('fetch');
  const [stageStatuses, setStageStatuses] = useState<
    Record<PostvStage, 'waiting' | 'running' | 'done' | 'failed'>
  >({
    fetch: 'waiting',
    pick: 'waiting',
    script: 'waiting',
    voice: 'waiting',
    render: 'waiting',
    done: 'waiting',
  });
  const [progressPct, setProgressPct] = useState<number>(0);
  const [stageMessage, setStageMessage] = useState<string>('');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [pickData, setPickData] = useState<PickSnippetData | null>(null);
  const [output, setOutput] = useState<CompletedOutput | null>(null);
  const [isFinished, setIsFinished] = useState(false);
  const [copiedPublish, setCopiedPublish] = useState(false);

  // Drawer ngăn kéo cột trái trên màn hình nhỏ (< 1024 px)
  const [drawerOpen, setDrawerOpen] = useState(false);

  const eventSourceRef = useRef<EventSource | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  // Tự co giãn chiều cao ô textarea
  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 200)}px`;
    }
  };

  // Nối SSE cho một Job đang chạy
  const connectSSE = useCallback(
    (jId: string) => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }

      const es = new EventSource(`/api/jobs/${encodeURIComponent(jId)}/events`);
      eventSourceRef.current = es;

      es.addEventListener('progress', (e) => {
        try {
          const payload: PostvStageEvent = JSON.parse(e.data);
          if (payload.stage) {
            setCurrentStage(payload.stage);
            setStageStatuses((prev) => {
              const next = { ...prev };
              const currIdx = STAGE_ORDER.indexOf(payload.stage);
              STAGE_ORDER.forEach((stg, i) => {
                if (i < currIdx) next[stg] = 'done';
                else if (i === currIdx) {
                  next[stg] = payload.status === 'waiting_pick' ? 'running' : payload.status;
                } else next[stg] = 'waiting';
              });
              return next;
            });
          }
          if (typeof payload.progress === 'number') {
            setProgressPct(payload.progress);
          }
          if (payload.message) {
            setStageMessage(payload.message);
          }
          if (payload.data) {
            if (payload.stage === 'pick') {
              setPickData(payload.data);
              if (payload.status === 'waiting_pick') {
                setIsWaitingPick(true);
                setManualPickData(payload.data as unknown as PostvPickData);
                if (payload.data.comments) {
                  setOrderedComments(payload.data.comments);
                  setCheckedCommentIds(
                    payload.data.comments
                      .filter((c: PostvPickComment) => c.picked)
                      .map((c: PostvPickComment) => c.id),
                  );
                }
              }
            } else if (payload.stage === 'done') {
              setOutput(payload.data as CompletedOutput);
              setIsFinished(true);
            }
          }
        } catch {
          // bỏ qua frame lỗi parse
        }
      });

      es.addEventListener('end', (e) => {
        try {
          const payload = JSON.parse(e.data);
          if (payload.status === 'done') {
            setStageStatuses({
              fetch: 'done',
              pick: 'done',
              script: 'done',
              voice: 'done',
              render: 'done',
              done: 'done',
            });
            setProgressPct(100);
            setIsFinished(true);
            setIsWaitingPick(false);
            if (payload.output) {
              setOutput(payload.output);
            }
            refetchProjects();
          } else if (payload.status === 'failed') {
            setErrorMessage(payload.error || 'Có lỗi xảy ra trong quá trình tạo video');
          }
        } catch {
          // bỏ qua
        }
        es.close();
      });

      es.onerror = () => {
        if (es.readyState === EventSource.CLOSED) {
          void api
            .getJob(jId)
            .then((final) => {
              if (final.status === 'done') {
                setStageStatuses({
                  fetch: 'done',
                  pick: 'done',
                  script: 'done',
                  voice: 'done',
                  render: 'done',
                  done: 'done',
                });
                setProgressPct(100);
                setIsFinished(true);
                setIsWaitingPick(false);
                if (final.output) {
                  setOutput(final.output);
                }
                refetchProjects();
              } else if (final.status === 'failed') {
                setErrorMessage(final.error || 'Mất kết nối máy chủ');
              } else if (final.status === 'waiting_pick') {
                setIsWaitingPick(true);
                void api.getPostvPickData(jId).then((data) => {
                  setManualPickData(data);
                  if (data.comments) {
                    setOrderedComments(data.comments);
                    setCheckedCommentIds(data.comments.filter((c) => c.picked).map((c) => c.id));
                  }
                });
              }
            })
            .catch(() => undefined);
        }
      };
    },
    [refetchProjects],
  );

  // Phục hồi job đang chạy khi tải lại trang
  const hasRestoredJobRef = useRef(false);
  const { data: activeJobs } = useQuery({
    queryKey: ['active-jobs'],
    queryFn: api.listActiveJobs,
    refetchInterval: isFinished || !!errorMessage || !!jobId ? false : 3000,
  });

  useEffect(() => {
    if (!hasRestoredJobRef.current && !jobId && activeJobs && activeJobs.length > 0) {
      const runningJob = activeJobs.find(
        (j) =>
          (j.kind === 'postv_quick' || j.kind === 'postv_auto') &&
          (j.status === 'running' || j.status === 'waiting_pick'),
      );
      if (runningJob) {
        hasRestoredJobRef.current = true;
        setJobId(runningJob.id);
        setProjectSlug(runningJob.slug);
        setSubmittedInput(`Dự án: ${runningJob.slug}`);
        if (runningJob.status === 'waiting_pick') {
          setIsWaitingPick(true);
          void api.getPostvPickData(runningJob.id).then((data) => {
            setManualPickData(data);
            if (data.comments) {
              setOrderedComments(data.comments);
              setCheckedCommentIds(data.comments.filter((c) => c.picked).map((c) => c.id));
            }
          });
        }
        connectSSE(runningJob.id);
      }
    }
  }, [activeJobs, jobId, connectSSE]);

  // Dọn dẹp SSE và audio khi unmount
  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
      if (audioSampleRef.current) {
        audioSampleRef.current.pause();
      }
    };
  }, []);

  // Khởi tạo chạy tự động
  const handleStartAuto = async (forceNew = false) => {
    const textToSubmit = input.trim();
    if (!textToSubmit) return;

    setIsSubmitting(true);
    setDuplicateSlug(null);
    setErrorMessage(null);

    const opts: PostvQuickOptions = {
      voice_id: selectedVoice,
      target_seconds: duration,
      music,
      music_id:
        music !== 'none' && selectedMusicId && selectedMusicId !== 'auto'
          ? selectedMusicId
          : undefined,
      fps,
      outro,
      pick_mode: pickMode,
    };

    try {
      const res = await api.startPostvQuick({
        url: textToSubmit,
        options: opts,
        force_new: forceNew,
      });

      if (res.existing_slug && !forceNew) {
        setDuplicateSlug(res.existing_slug);
        setIsSubmitting(false);
        return;
      }

      if (res.job_id) {
        hasRestoredJobRef.current = true;
        setJobId(res.job_id);
        setProjectSlug(res.project_slug);
        setSubmittedInput(textToSubmit);
        setIsFinished(false);
        setIsWaitingPick(false);
        setOutput(null);
        setPickData(null);
        setStageStatuses({
          fetch: 'running',
          pick: 'waiting',
          script: 'waiting',
          voice: 'waiting',
          render: 'waiting',
          done: 'waiting',
        });
        setProgressPct(5);
        connectSSE(res.job_id);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setErrorMessage(msg);
    } finally {
      setIsSubmitting(false);
    }
  };

  // Huỷ job đang chạy
  const handleCancel = async () => {
    if (!jobId) return;
    try {
      await api.cancelJob(jobId);
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
      setIsWaitingPick(false);
      setErrorMessage('Đã huỷ tác vụ');
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setErrorMessage(msg);
    }
  };

  // Thử lại từ bước lỗi
  const handleRetry = async () => {
    if (!jobId) return;
    setIsSubmitting(true);
    setErrorMessage(null);
    try {
      const res = await api.retryPostvQuick(jobId);
      if (res.job_id) {
        hasRestoredJobRef.current = true;
        setJobId(res.job_id);
        connectSSE(res.job_id);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setErrorMessage(msg);
    } finally {
      setIsSubmitting(false);
    }
  };

  // Người dùng xác nhận danh sách bình luận đã tự chọn
  const handleConfirmPick = async () => {
    if (!jobId) return;
    setIsSubmitting(true);
    try {
      const res = await api.submitPostvPick(jobId, checkedCommentIds);
      setIsWaitingPick(false);
      if (res.job_id && res.job_id !== jobId) {
        setJobId(res.job_id);
        connectSSE(res.job_id);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setErrorMessage(msg);
    } finally {
      setIsSubmitting(false);
    }
  };

  // Đổi thứ tự bình luận (kéo thả hoặc mũi tên)
  const moveComment = (fromIndex: number, direction: -1 | 1) => {
    const toIndex = fromIndex + direction;
    if (toIndex < 0 || toIndex >= orderedComments.length) return;
    const next = [...orderedComments];
    const [moved] = next.splice(fromIndex, 1);
    next.splice(toIndex, 0, moved);
    setOrderedComments(next);
  };

  const handleDragStart = (e: React.DragEvent, index: number) => {
    setDraggedIdx(index);
    e.dataTransfer.effectAllowed = 'move';
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
  };

  const handleDrop = (e: React.DragEvent, targetIndex: number) => {
    e.preventDefault();
    if (draggedIdx === null || draggedIdx === targetIndex) return;
    const next = [...orderedComments];
    const [moved] = next.splice(draggedIdx, 1);
    next.splice(targetIndex, 0, moved);
    setOrderedComments(next);
    setDraggedIdx(null);
  };

  // Tích / bỏ chọn bình luận
  const toggleComment = (cid: string) => {
    setCheckedCommentIds((prev) =>
      prev.includes(cid) ? prev.filter((id) => id !== cid) : [...prev, cid],
    );
  };

  // Bật / tắt mở rộng nội dung bình luận
  const toggleExpand = (cid: string) => {
    setExpandedCommentIds((prev) => {
      const next = new Set(prev);
      if (next.has(cid)) next.delete(cid);
      else next.add(cid);
      return next;
    });
  };

  // Tính thời lượng ước tính hiện tại khi chọn bình luận
  const currentChars =
    (manualPickData?.post_text || '').replace(/\s+/g, ' ').trim().length +
    orderedComments
      .filter((c) => checkedCommentIds.includes(c.id))
      .reduce((sum, c) => sum + c.text.replace(/\s+/g, ' ').trim().length, 0);
  const estimatedSec = Math.round(currentChars / 16.5);

  // Reset về trạng thái khung chat ban đầu
  const handleReset = () => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }
    setJobId(null);
    setProjectSlug(null);
    setSubmittedInput('');
    setIsFinished(false);
    setIsWaitingPick(false);
    setOutput(null);
    setPickData(null);
    setErrorMessage(null);
    setDuplicateSlug(null);
    setProgressPct(0);
  };

  // Mở video cũ khi gặp link trùng
  const handleOpenExisting = (slug: string) => {
    navigate(`/postv/${slug}`);
  };

  // Sao chép nội dung publish.txt
  const handleCopyPublish = async () => {
    if (!output?.publish) return;
    try {
      const res = await fetch(fileUrl(output.publish));
      const text = await res.text();
      await navigator.clipboard.writeText(text);
      setCopiedPublish(true);
      setTimeout(() => setCopiedPublish(false), 2500);
    } catch {
      // bỏ qua lỗi clipboard
    }
  };

  // Thời gian ước tính còn lại (ETA)
  const remainingEta = Math.max(5, Math.round(((100 - progressPct) / 100) * duration * 0.8));

  // Cột trái: Danh sách Video gần đây
  const RecentVideosList = (
    <div className="flex h-full flex-col p-4">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-body font-bold text-ink">{T.recentVideos}</h2>
        <Button size="sm" tone="brand" onClick={handleReset}>
          {T.newVideo}
        </Button>
      </div>

      <div className="flex-1 space-y-2 overflow-y-auto pr-1">
        {postvProjects.length === 0 ? (
          <p className="py-6 text-center text-small text-muted">{T.noRecent}</p>
        ) : (
          postvProjects.map((p) => {
            const hasVideo = Boolean(p.last_final || p.last_render);
            const isBusy = Boolean(
              activeJobs?.some((j) => j.slug === p.slug && j.status === 'running'),
            );
            return (
              <div
                key={p.slug}
                className={cx(
                  'group relative flex items-center justify-between rounded-xl border border-line bg-card p-2.5 transition-all hover:border-brand/60 hover:shadow-sm',
                  projectSlug === p.slug && 'border-brand bg-brand/5',
                )}
              >
                <div
                  onClick={() => {
                    setDrawerOpen(false);
                    navigate(`/postv/${p.slug}`);
                  }}
                  className="flex flex-1 cursor-pointer items-center gap-3 min-w-0"
                >
                  <div className="relative h-14 w-9 shrink-0 overflow-hidden rounded-md bg-subtle">
                    <img
                      src={`/api/projects/${p.slug}/postv/preview.png?w=90`}
                      alt=""
                      onError={(e) => {
                        (e.target as HTMLElement).style.display = 'none';
                      }}
                      className="h-full w-full object-cover"
                    />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-small font-semibold text-ink group-hover:text-brand">
                      {p.title || p.slug}
                    </p>
                    <p className="text-tiny text-muted">{hasVideo ? 'Đã hoàn tất' : 'Bản nháp'}</p>
                  </div>
                </div>

                {/* Nút ⋮ mở menu: Mở · Tải video · Xoá */}
                <div className="shrink-0 pl-1" onClick={(e) => e.stopPropagation()}>
                  <Menu
                    label="Tuỳ chọn"
                    icon={
                      <svg width={16} height={16} viewBox="0 0 24 24" fill="currentColor">
                        <circle cx="12" cy="5" r="1.5" />
                        <circle cx="12" cy="12" r="1.5" />
                        <circle cx="12" cy="19" r="1.5" />
                      </svg>
                    }
                    items={[
                      {
                        key: 'open',
                        label: T.recentMenu.open,
                        onSelect: () => {
                          setDrawerOpen(false);
                          navigate(`/postv/${p.slug}`);
                        },
                      },
                      {
                        key: 'download',
                        label: T.recentMenu.download,
                        disabled: !hasVideo,
                        onSelect: () => {
                          window.open(`/api/projects/${p.slug}/postv/video.mp4`, '_blank');
                        },
                      },
                      {
                        key: 'delete',
                        label: T.recentMenu.delete,
                        danger: true,
                        disabled: isBusy,
                        reason: isBusy ? T.recentMenu.busy : undefined,
                        onSelect: () => setDeletingSlug(p.slug),
                      },
                    ]}
                  />
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );

  return (
    <div className="flex min-h-[calc(100vh-64px)] w-full overflow-hidden bg-bg">
      {/* Cột trái: Hiện thẳng trên desktop (>= 1024px) */}
      <aside className="hidden w-72 shrink-0 border-r border-line bg-nav lg:block">
        {RecentVideosList}
      </aside>

      {/* Nút mở ngăn kéo cột trái trên thiết bị nhỏ (< 1024px) */}
      <div className="fixed bottom-4 left-4 z-40 lg:hidden">
        <Button tone="soft" size="sm" onClick={() => setDrawerOpen(true)}>
          <FolderIcon size={16} />
          {T.recentVideos}
        </Button>
      </div>

      {/* Drawer ngăn kéo di động */}
      {drawerOpen && (
        <div className="fixed inset-0 z-50 flex lg:hidden">
          <div
            className="fixed inset-0 bg-black/50 backdrop-blur-sm"
            onClick={() => setDrawerOpen(false)}
          />
          <div className="relative w-80 max-w-[85vw] bg-nav shadow-2xl">{RecentVideosList}</div>
        </div>
      )}

      {/* Hộp xác nhận xoá video gần đây */}
      {deletingSlug && (
        <Dialog
          open={true}
          onClose={() => setDeletingSlug(null)}
          title={T.recentMenu.deleteConfirmTitle}
          role="alertdialog"
          footer={
            <div className="flex justify-end gap-2">
              <Button size="sm" tone="soft" onClick={() => setDeletingSlug(null)}>
                {T.recentMenu.cancel}
              </Button>
              <Button
                size="sm"
                tone="danger"
                onClick={async () => {
                  const slug = deletingSlug;
                  setDeletingSlug(null);
                  try {
                    await api.deletePostvProject(slug);
                    void refetchProjects();
                  } catch (e) {
                    setErrorMessage(String(e));
                  }
                }}
              >
                {T.recentMenu.confirm}
              </Button>
            </div>
          }
        >
          <p className="text-small text-muted">{T.recentMenu.deleteConfirmDesc}</p>
        </Dialog>
      )}

      {/* Khu vực giữa chính */}
      <main className="flex flex-1 flex-col items-center justify-center p-4 md:p-8">
        <div className="w-full max-w-2xl">
          {/* TRƯỜNG HỢP 1: TRẠNG THÁI TRỐNG HOẶC ĐANG NHẬP */}
          {!jobId && (
            <div className="space-y-6 animate-in fade-in slide-in-from-bottom-2 duration-200">
              <div className="text-center">
                <div className="mx-auto mb-3 flex h-14 w-14 items-center justify-center rounded-2xl bg-brand/10 text-brand">
                  <PlusIcon size={28} />
                </div>
                <h1 className="text-h1 font-extrabold text-ink">{T.greeting}</h1>
                <p className="mx-auto mt-2 max-w-md text-small text-muted">{T.greetingSub}</p>
              </div>

              {/* Thông báo trùng link đã tạo */}
              {duplicateSlug && (
                <Card className="border-brand bg-brand/5 p-4">
                  <div className="flex items-start gap-3">
                    <span className="text-brand">
                      <AlertIcon size={20} />
                    </span>
                    <div className="flex-1">
                      <h3 className="text-small font-bold text-ink">{T.duplicateNotice.title}</h3>
                      <p className="mt-1 text-tiny text-muted">
                        {T.duplicateNotice.desc(duplicateSlug)}
                      </p>
                      <div className="mt-3 flex gap-2">
                        <Button
                          size="sm"
                          tone="brand"
                          onClick={() => handleOpenExisting(duplicateSlug)}
                        >
                          {T.duplicateNotice.openExisting}
                        </Button>
                        <Button size="sm" tone="soft" onClick={() => handleStartAuto(true)}>
                          {T.duplicateNotice.forceNew}
                        </Button>
                      </div>
                    </div>
                  </div>
                </Card>
              )}

              {/* Lỗi nếu có */}
              {errorMessage && (
                <Card className="border-danger/40 bg-danger/5 p-4 text-small text-danger">
                  <div className="flex items-center gap-2 font-medium">
                    <AlertIcon size={18} />
                    <span>{errorMessage}</span>
                  </div>
                </Card>
              )}

              {/* Khung nhập liệu kiểu Chat */}
              <div className="rounded-2xl border-2 border-line bg-card p-3 shadow-md transition-all focus-within:border-brand focus-within:ring-2 focus-within:ring-brand/20">
                <textarea
                  ref={textareaRef}
                  value={input}
                  onChange={handleInputChange}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault();
                      if (input.trim() && !isSubmitting) {
                        handleStartAuto(false);
                      }
                    }
                  }}
                  rows={3}
                  placeholder={T.inputPlaceholder}
                  className="w-full resize-none bg-transparent px-2 py-1 text-body text-ink outline-none placeholder:text-muted"
                />

                {/* Hàng chip tuỳ chọn */}
                <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-line/60 pt-3">
                  {/* Chip Bình luận: Tự động | Tự chọn */}
                  <Chip
                    selected={pickMode === 'manual'}
                    onClick={() => {
                      const next = pickMode === 'auto' ? 'manual' : 'auto';
                      setPickMode(next);
                      localStorage.setItem('hbt_postv_pick_mode', next);
                    }}
                    className="cursor-pointer"
                  >
                    💬 {T.pickMode.label}:{' '}
                    {pickMode === 'auto' ? T.pickMode.auto : T.pickMode.manual}
                  </Chip>

                  {/* Dropdown Giọng (VieNeu) & Nút ▶ nghe thử */}
                  <div className="flex items-center gap-1.5 rounded-full border border-line bg-card pl-3 pr-1.5 py-0.5 text-tiny text-ink shadow-sm">
                    <span className="shrink-0">🎙️ {T.voice.label}:</span>
                    <Select
                      aria-label={T.voice.label}
                      variant="compact"
                      autoWidth
                      value={selectedVoice || ''}
                      onChange={(e) => handleVoiceChange(e.target.value)}
                      className="border-0 bg-transparent min-h-[28px] max-w-[140px] truncate"
                    >
                      {voiceList?.voices && voiceList.voices.length > 0 ? (
                        voiceList.voices.map((v) => (
                          <option key={v.id} value={v.id}>
                            {v.label || v.id}
                          </option>
                        ))
                      ) : (
                        <option value="">{T.voice.defaultOption}</option>
                      )}
                    </Select>
                    {selectedVoice && (
                      <button
                        type="button"
                        title={isPlayingSample ? T.voice.previewing : T.voice.preview}
                        onClick={handleToggleSample}
                        className={cx(
                          'ml-0.5 rounded-full p-1 text-muted hover:text-brand transition-colors',
                          isPlayingSample && 'text-brand animate-pulse',
                        )}
                      >
                        {isPlayingSample ? <StopIcon size={12} /> : <PlayIcon size={12} />}
                      </button>
                    )}
                  </div>

                  {/* Dropdown Thời lượng (1m - 3m) */}
                  <div className="flex items-center gap-1.5 rounded-full border border-line bg-card pl-3 pr-1.5 py-0.5 text-tiny text-ink shadow-sm">
                    <span className="shrink-0">⏱️ {T.options.duration}:</span>
                    <Select
                      aria-label={T.options.duration}
                      variant="compact"
                      autoWidth
                      value={String(duration)}
                      onChange={(e) => setDuration(Number(e.target.value))}
                      className="border-0 bg-transparent min-h-[28px]"
                    >
                      {DURATION_CHOICES.map((opt) => (
                        <option key={opt.value} value={String(opt.value)}>
                          {opt.label}
                        </option>
                      ))}
                    </Select>
                  </div>

                  {/* Nhạc nền BGM (mặc định tự chọn 1 bài từ library/music/ + Playlist acrossfade) */}
                  <div className="flex items-center gap-1.5 rounded-full border border-line bg-card pl-3 pr-1.5 py-0.5 text-tiny text-ink shadow-sm">
                    <span className="shrink-0">🎵 {T.options.musicLabel}:</span>
                    <Select
                      aria-label={T.options.musicLabel}
                      variant="compact"
                      autoWidth
                      value={music === 'none' ? 'none' : selectedMusicId || 'auto'}
                      onChange={(e) => {
                        const val = e.target.value;
                        if (val === 'none') {
                          setMusic('none');
                        } else {
                          setMusic('auto');
                          setSelectedMusicId(val);
                        }
                      }}
                      className="border-0 bg-transparent min-h-[28px] max-w-[150px] truncate"
                    >
                      {musicList && musicList.length > 0 ? (
                        musicList.map((m) => (
                          <option key={m.id} value={m.id}>
                            {m.title}
                          </option>
                        ))
                      ) : (
                        <option value="auto">{T.options.musicAuto}</option>
                      )}
                      <option value="none">{T.options.musicNone}</option>
                    </Select>
                  </div>

                  {/* 60 fps */}
                  <Chip selected={fps === 60} onClick={() => setFps((f) => (f === 60 ? 30 : 60))}>
                    {fps === 60 ? T.options.fps60 : T.options.fps30}
                  </Chip>

                  {/* Outro */}
                  <Chip selected={outro} onClick={() => setOutro((o) => !o)}>
                    {outro ? T.options.outroOn : T.options.outroOff}
                  </Chip>
                </div>
              </div>

              {/* Nút Tạo Video chính */}
              <div className="flex justify-end">
                <Button
                  size="lg"
                  tone="brand"
                  disabled={!input.trim() || isSubmitting}
                  onClick={() => handleStartAuto(false)}
                  className="w-full sm:w-auto font-bold px-8 shadow-md"
                >
                  {isSubmitting ? T.creatingBtn : T.createBtn}
                </Button>
              </div>
            </div>
          )}

          {/* TRƯỜNG HỢP 2A: ĐANG DỪNG Ở BƯỚC CHỌN BÌNH LUẬN (TỰ CHỌN - WAITING_PICK) */}
          {jobId && isWaitingPick && manualPickData && (
            <Card className="p-6 shadow-md border-line animate-in fade-in zoom-in-95 duration-200">
              <div className="mb-4 flex flex-wrap items-center justify-between gap-2 border-b border-line pb-3">
                <div>
                  <h2 className="text-body font-bold text-ink">{T.manualPick.title}</h2>
                  <p className="text-tiny text-muted">
                    Chọn các bình luận và sắp xếp thứ tự đọc cho video
                  </p>
                </div>
                {/* Thanh thời lượng ≈ Xs / mục tiêu Ys */}
                <div className="flex items-center gap-2 rounded-full bg-subtle px-3 py-1 text-tiny font-semibold">
                  <span className={estimatedSec >= duration ? 'text-ok' : 'text-accent'}>
                    {T.manualPick.targetProgress(estimatedSec, duration)}
                  </span>
                  <div className="h-2 w-20 overflow-hidden rounded-full bg-line">
                    <div
                      className={cx(
                        'h-full transition-all duration-300',
                        estimatedSec >= duration ? 'bg-ok' : 'bg-brand',
                      )}
                      style={{ width: `${Math.min(100, (estimatedSec / duration) * 100)}%` }}
                    />
                  </div>
                </div>
              </div>

              {/* Thẻ bài gốc luôn ở đầu, mặc định được chọn */}
              <div className="mb-4 rounded-xl border-2 border-brand/40 bg-brand/5 p-4">
                <div className="flex items-start gap-3">
                  <input
                    type="checkbox"
                    checked={true}
                    disabled={true}
                    className="mt-1 h-4 w-4 rounded accent-brand"
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <Badge tone="yel">{T.manualPick.originalPost}</Badge>
                      <span className="font-bold text-small text-ink">
                        @{manualPickData.handle}
                      </span>
                    </div>
                    <p className="mt-2 text-small text-ink whitespace-pre-wrap">
                      {manualPickData.post_text}
                    </p>
                  </div>
                </div>
              </div>

              {/* Danh sách TẤT CẢ bình luận */}
              <div className="max-h-[50vh] space-y-2 overflow-y-auto pr-1">
                {orderedComments.map((c, index) => {
                  const isChecked = checkedCommentIds.includes(c.id);
                  const isExpanded = expandedCommentIds.has(c.id);
                  const hasReason = Boolean(c.filter_reason);
                  return (
                    <div
                      key={c.id}
                      draggable={true}
                      onDragStart={(e) => handleDragStart(e, index)}
                      onDragOver={handleDragOver}
                      onDrop={(e) => handleDrop(e, index)}
                      className={cx(
                        'group flex items-start gap-3 rounded-xl border p-3 transition-all',
                        c.parent && 'ml-6 border-l-2 border-l-brand/50',
                        isChecked ? 'border-line bg-card' : 'border-line/60 bg-card/50',
                        hasReason && 'opacity-60 bg-subtle/30 border-dashed',
                      )}
                    >
                      {/* Điều khiển đổi thứ tự */}
                      <div className="flex flex-col items-center gap-1 text-muted">
                        <button
                          type="button"
                          disabled={index === 0}
                          onClick={() => moveComment(index, -1)}
                          title={T.manualPick.moveUp}
                          className="text-tiny hover:text-ink disabled:opacity-20"
                        >
                          ▲
                        </button>
                        <span className="cursor-grab text-muted group-hover:text-ink">
                          <GripIcon size={14} />
                        </span>
                        <button
                          type="button"
                          disabled={index === orderedComments.length - 1}
                          onClick={() => moveComment(index, 1)}
                          title={T.manualPick.moveDown}
                          className="text-tiny hover:text-ink disabled:opacity-20"
                        >
                          ▼
                        </button>
                      </div>

                      {/* Ô tích */}
                      <input
                        type="checkbox"
                        checked={isChecked}
                        onChange={() => toggleComment(c.id)}
                        className="mt-1 h-4 w-4 rounded accent-brand cursor-pointer"
                      />

                      {/* Thông tin bình luận */}
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-semibold text-small text-ink">@{c.handle}</span>
                          {c.parent && <Badge tone="neutral">{T.manualPick.replyBadge}</Badge>}
                          {c.likes != null && c.likes > 0 && (
                            <span className="text-tiny text-muted">
                              ❤️ {T.manualPick.likes(c.likes)}
                            </span>
                          )}
                          {c.filter_reason && (
                            <span className="rounded bg-muted/20 px-1.5 py-0.5 text-tiny font-medium text-muted">
                              Lọc:{' '}
                              {T.manualPick.reasons[
                                c.filter_reason as keyof typeof T.manualPick.reasons
                              ] || c.filter_reason}
                            </span>
                          )}
                        </div>
                        <p
                          onClick={() => toggleExpand(c.id)}
                          className={cx(
                            'mt-1 text-small text-ink cursor-pointer',
                            !isExpanded && 'line-clamp-2',
                          )}
                        >
                          {c.text}
                        </p>
                        {c.text.length > 80 && (
                          <button
                            type="button"
                            onClick={() => toggleExpand(c.id)}
                            className="mt-0.5 text-tiny font-semibold text-brand hover:underline"
                          >
                            {isExpanded ? T.manualPick.collapse : T.manualPick.expand}
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Nút hành động */}
              <div className="mt-6 flex items-center justify-between border-t border-line pt-4">
                <Button tone="soft" size="md" onClick={handleCancel}>
                  {T.manualPick.cancel}
                </Button>
                <Button
                  tone="brand"
                  size="md"
                  disabled={checkedCommentIds.length === 0 || isSubmitting}
                  onClick={handleConfirmPick}
                  className="font-bold px-6 shadow-md"
                >
                  {isSubmitting ? T.creatingBtn : T.manualPick.submit}
                </Button>
              </div>
            </Card>
          )}

          {/* TRƯỜNG HỢP 2B: ĐANG CHẠY TIẾN TRÌNH CÁC BƯỚC */}
          {jobId && !isWaitingPick && !isFinished && (
            <div className="space-y-6 animate-in fade-in slide-in-from-bottom-2 duration-200">
              {/* Tin nhắn liên kết / trích đoạn người dùng vừa dán */}
              <div className="flex justify-end">
                <div className="max-w-[85%] rounded-2xl rounded-tr-sm bg-brand/15 px-4 py-3 text-small text-ink">
                  <p className="line-clamp-3 font-mono text-tiny break-all">{submittedInput}</p>
                </div>
              </div>

              {/* Thẻ tiến trình 6 bước */}
              <Card className="p-6 shadow-md border-line">
                <div className="mb-4 flex items-center justify-between border-b border-line pb-3">
                  <h2 className="text-body font-bold text-ink">Tiến trình tạo video</h2>
                  <span className="text-tiny font-semibold text-muted">
                    {progressPct > 0 && progressPct < 100 && T.progress.eta(remainingEta)}
                  </span>
                </div>

                <div className="space-y-4">
                  {STAGE_ORDER.map((stg) => {
                    const status = stageStatuses[stg];
                    const isCurrent = currentStage === stg && status === 'running';
                    return (
                      <div key={stg} className="flex items-start gap-3">
                        <div className="mt-0.5 shrink-0">
                          {status === 'done' ? (
                            <span className="flex h-5 w-5 items-center justify-center rounded-full bg-ok text-white">
                              <CheckIcon size={12} />
                            </span>
                          ) : status === 'running' ? (
                            <span className="flex h-5 w-5 items-center justify-center">
                              <span className="h-4 w-4 animate-spin motion-reduce:animate-none rounded-full border-2 border-brand border-t-transparent" />
                            </span>
                          ) : status === 'failed' ? (
                            <span className="flex h-5 w-5 items-center justify-center rounded-full bg-danger text-white">
                              <AlertIcon size={12} />
                            </span>
                          ) : (
                            <span className="flex h-5 w-5 items-center justify-center rounded-full border border-line bg-subtle text-muted" />
                          )}
                        </div>

                        <div className="flex-1 min-w-0">
                          <p
                            className={cx(
                              'text-small font-semibold',
                              isCurrent
                                ? 'text-brand'
                                : status === 'done'
                                  ? 'text-ink'
                                  : 'text-muted',
                            )}
                          >
                            {T.stages[stg]}
                          </p>

                          {/* Xem trước nhỏ khi ở bước pick */}
                          {stg === 'pick' && pickData && (
                            <div className="mt-2 rounded-xl bg-subtle/80 p-3 text-tiny">
                              <p className="font-bold text-ink">@{pickData.handle}</p>
                              {pickData.snippet && (
                                <p className="mt-0.5 line-clamp-2 text-muted">
                                  &ldquo;{pickData.snippet}&rdquo;
                                </p>
                              )}
                              <p className="mt-1 font-semibold text-brand">
                                Đã chọn {pickData.picked_count}/{pickData.total_comments} bình luận
                              </p>
                            </div>
                          )}

                          {/* Thanh % ở bước dựng render */}
                          {stg === 'render' && isCurrent && (
                            <div className="mt-2">
                              <Progress value={progressPct} label="Tiến độ dựng video" />
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>

                {/* Thông báo chi tiết hiện tại */}
                {stageMessage && !errorMessage && (
                  <p className="mt-4 text-center text-tiny text-muted">{stageMessage}</p>
                )}

                {/* Báo lỗi nếu có */}
                {errorMessage && (
                  <div className="mt-4 rounded-xl border border-danger/40 bg-danger/5 p-3 text-small text-danger">
                    <p className="font-semibold">{errorMessage}</p>
                  </div>
                )}

                {/* Nút hành động */}
                <div className="mt-6 flex justify-end gap-3 border-t border-line pt-4">
                  <Button size="sm" tone="soft" onClick={handleCancel}>
                    {T.progress.cancel}
                  </Button>
                  {errorMessage && (
                    <Button size="sm" tone="brand" onClick={handleRetry}>
                      {T.progress.retry}
                    </Button>
                  )}
                </div>
              </Card>
            </div>
          )}

          {/* TRƯỜNG HỢP 3: HOÀN THÀNH (THẺ KẾT QUẢ) */}
          {isFinished && output && (
            <div className="space-y-6 animate-in fade-in slide-in-from-bottom-2 duration-200">
              <div className="text-center">
                <div className="mx-auto mb-2 flex h-12 w-12 items-center justify-center rounded-full bg-ok text-white shadow-md">
                  <CheckIcon size={24} />
                </div>
                <h1 className="text-h2 font-extrabold text-ink">{T.result.title}</h1>
                <p className="mt-1 text-small font-semibold text-muted">
                  {T.result.summary?.(
                    output.picked_comments ?? pickData?.picked_count ?? 0,
                    output.total_comments ?? pickData?.total_comments ?? 0,
                    Math.round(output.duration ?? 0),
                  )}
                </p>
                {/* Cảnh báo nếu thời lượng thực tế hụt so với mục tiêu */}
                {(output.warning ||
                  (output.target_seconds &&
                    (output.duration ?? 0) < output.target_seconds - 5)) && (
                  <div className="mx-auto mt-2 flex max-w-md items-center justify-center gap-1.5 rounded-lg border border-accent/40 bg-accent/10 px-3 py-1.5 text-tiny font-medium text-accent">
                    <AlertIcon size={16} className="text-accent shrink-0" />
                    <span>
                      {output.warning ||
                        T.result.durationWarning?.(
                          output.target_seconds ?? 75,
                          Math.round(output.duration ?? 0),
                        )}
                    </span>
                  </div>
                )}
              </div>

              {/* Trình phát video 9:16 */}
              <div className="mx-auto max-w-[360px] overflow-hidden rounded-2xl border border-line bg-black shadow-2xl">
                {output.video ? (
                  <video
                    src={fileUrl(output.video)}
                    controls
                    playsInline
                    className="aspect-[9/16] w-full object-contain"
                  />
                ) : (
                  <div className="flex aspect-[9/16] items-center justify-center text-muted">
                    Không tìm thấy file video
                  </div>
                )}
              </div>

              {/* Các nút hành động chính */}
              <div className="space-y-3">
                {output.video && (
                  <a
                    href={fileUrl(output.video)}
                    download
                    className="flex w-full items-center justify-center gap-2 rounded-xl bg-brand py-3.5 text-body font-bold text-ink shadow-md transition-all hover:brightness-105 active:scale-[0.99]"
                  >
                    <DownloadIcon size={20} />
                    {T.result.downloadVideo}
                  </a>
                )}

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {output.publish && (
                    <Button size="md" tone="soft" onClick={handleCopyPublish}>
                      <CopyIcon size={16} />
                      {copiedPublish ? T.result.copiedPublish : T.result.copyPublish}
                    </Button>
                  )}

                  {output.cover && (
                    <a
                      href={fileUrl(output.cover)}
                      download
                      className="inline-flex items-center justify-center gap-2 rounded-xl border border-line bg-card py-2 text-small font-semibold text-ink transition-all hover:bg-subtle"
                    >
                      <DownloadIcon size={16} />
                      {T.result.downloadCover}
                    </a>
                  )}
                </div>

                <div className="flex flex-col sm:flex-row gap-3 pt-2">
                  {(output.project_slug || projectSlug) && (
                    <Link
                      to={`/postv/${output.project_slug || projectSlug}/export`}
                      className="inline-flex flex-1 items-center justify-center gap-2 rounded-xl border border-line bg-card py-2.5 text-small font-semibold text-ink transition-all hover:border-brand hover:text-brand"
                    >
                      <UploadIcon size={16} />
                      {T.result.editDetails}
                    </Link>
                  )}

                  <Button size="md" tone="soft" onClick={handleReset} className="flex-1">
                    {T.result.createAnother}
                  </Button>
                </div>
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
