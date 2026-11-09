import { useQuery } from '@tanstack/react-query';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api, fileUrl } from '../api/endpoints';
import type { PostvQuickOptions, PostvStage, PostvStageEvent } from '../api/types';
import {
  AlertIcon,
  CheckIcon,
  CopyIcon,
  DownloadIcon,
  FolderIcon,
  PlusIcon,
  UploadIcon,
} from '../components/icons';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { Chip } from '../components/ui/Chip';
import { Progress } from '../components/ui/Progress';
import { cx } from '../components/ui/cx';
import { vi } from '../i18n/vi';

const T = vi.postvQuick;

const STAGE_ORDER: PostvStage[] = ['fetch', 'pick', 'script', 'voice', 'render', 'done'];

interface PickSnippetData {
  handle?: string;
  snippet?: string;
  picked_count?: number;
  total_comments?: number;
  estimated_seconds?: number;
}

interface CompletedOutput {
  video?: string;
  cover?: string;
  youtube_cover?: string;
  publish?: string;
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

  // Danh sách video gần đây
  const { data: projects = [], refetch: refetchProjects } = useQuery({
    queryKey: ['projects'],
    queryFn: api.listProjects,
    staleTime: 10_000,
  });
  const postvProjects = projects.filter((p) => p.kind === 'postv');

  // Danh sách giọng đọc VieNeu
  const { data: voiceList } = useQuery({
    queryKey: ['voices'],
    queryFn: api.listVoices,
    staleTime: 60_000,
  });
  const { data: voicePref } = useQuery({
    queryKey: ['voice-preference'],
    queryFn: api.getVoicePreference,
    staleTime: 60_000,
  });

  // Trạng thái nhập liệu & tuỳ chọn
  const [input, setInput] = useState('');
  const [selectedVoice, setSelectedVoice] = useState<string | null>(null);
  const [duration, setDuration] = useState<number>(75);
  const [music, setMusic] = useState<'auto' | 'none'>('auto');
  const [fps, setFps] = useState<30 | 60>(60);
  const [outro, setOutro] = useState<boolean>(true);

  // Khởi tạo giọng đọc từ preference hoặc danh sách
  useEffect(() => {
    if (!selectedVoice) {
      if (voicePref?.voice_id) {
        setSelectedVoice(voicePref.voice_id);
      } else if (voiceList?.voices && voiceList.voices.length > 0) {
        setSelectedVoice(voiceList.voices[0].id);
      }
    }
  }, [voicePref, voiceList, selectedVoice]);

  // Trạng thái chuỗi tự động
  const [jobId, setJobId] = useState<string | null>(null);
  const [projectSlug, setProjectSlug] = useState<string | null>(null);
  const [submittedInput, setSubmittedInput] = useState<string>('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [duplicateSlug, setDuplicateSlug] = useState<string | null>(null);

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
                else if (i === currIdx) next[stg] = payload.status;
                else next[stg] = 'waiting';
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
            } else if (payload.stage === 'done') {
              setOutput(payload.data);
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
                if (final.output) {
                  setOutput(final.output as CompletedOutput);
                }
                void refetchProjects();
              } else if (final.status === 'failed') {
                setErrorMessage(final.error || 'Có lỗi xảy ra trong quá trình tạo video');
              }
            })
            .catch(() => {});
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
        (j) => (j.kind === 'postv_quick' || j.kind === 'postv_auto') && j.status === 'running',
      );
      if (runningJob) {
        hasRestoredJobRef.current = true;
        setJobId(runningJob.id);
        setProjectSlug(runningJob.slug);
        setSubmittedInput(`Dự án: ${runningJob.slug}`);
        connectSSE(runningJob.id);
      }
    }
  }, [activeJobs, jobId, connectSSE]);

  // Dọn dẹp SSE khi unmount
  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
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
      fps,
      outro,
      max_comments: 5,
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

  // Reset về trạng thái khung chat ban đầu
  const handleReset = () => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }
    setJobId(null);
    setProjectSlug(null);
    setSubmittedInput('');
    setIsFinished(false);
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

  // Nhãn hiển thị cho giọng đang chọn
  const voiceLabel =
    voiceList?.voices?.find((v) => v.id === selectedVoice)?.label || selectedVoice || 'Tự động';

  // Chuyển đổi qua lại các giọng
  const cycleVoice = () => {
    if (!voiceList?.voices || voiceList.voices.length === 0) return;
    const idx = voiceList.voices.findIndex((v) => v.id === selectedVoice);
    const nextIdx = (idx + 1) % voiceList.voices.length;
    setSelectedVoice(voiceList.voices[nextIdx].id);
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
            return (
              <div
                key={p.slug}
                onClick={() => {
                  setDrawerOpen(false);
                  navigate(`/postv/${p.slug}`);
                }}
                className={cx(
                  'group flex cursor-pointer items-center gap-3 rounded-xl border border-line bg-card p-2.5 transition-all hover:border-brand/60 hover:shadow-sm',
                  projectSlug === p.slug && 'border-brand bg-brand/5',
                )}
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
                  <Chip
                    title="Bấm để đổi giọng"
                    selected={true}
                    onClick={cycleVoice}
                    className="cursor-pointer"
                  >
                    🎙️ {T.options.voice}: {voiceLabel}
                  </Chip>

                  {/* Độ dài */}
                  <div className="flex items-center gap-1 rounded-full bg-subtle p-0.5">
                    {[60, 75, 90].map((sec) => (
                      <button
                        key={sec}
                        type="button"
                        onClick={() => setDuration(sec)}
                        className={cx(
                          'rounded-full px-2.5 py-0.5 text-tiny font-semibold transition-all',
                          duration === sec
                            ? 'bg-card text-ink shadow-sm'
                            : 'text-muted hover:text-ink',
                        )}
                      >
                        {sec} s
                      </button>
                    ))}
                  </div>

                  {/* Nhạc */}
                  <Chip
                    selected={music === 'auto'}
                    onClick={() => setMusic((m) => (m === 'auto' ? 'none' : 'auto'))}
                  >
                    {music === 'auto' ? T.options.musicAuto : T.options.musicNone}
                  </Chip>

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

          {/* TRƯỜNG HỢP 2: ĐANG CHẠY CHUỖI TỰ ĐỘNG HOẶC ĐÃ HOÀN THÀNH */}
          {jobId && (
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
                {!isFinished && (
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
                )}
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
                  {T.result.summary(
                    output.picked_comments ?? pickData?.picked_count ?? 0,
                    output.total_comments ?? pickData?.total_comments ?? 0,
                    Math.round(output.duration ?? 0),
                  )}
                </p>
                {((output.target_seconds &&
                  output.duration &&
                  output.duration < output.target_seconds - 5) ||
                  output.warning) && (
                  <div className="mx-auto mt-2 max-w-md rounded-xl border border-accent/40 bg-accent/10 p-2.5 text-tiny text-ink">
                    <div className="flex items-center justify-center gap-2 font-medium">
                      <AlertIcon size={16} className="text-accent shrink-0" />
                      <span>
                        {output.warning ||
                          T.result.durationWarning(
                            output.target_seconds!,
                            Math.round(output.duration!),
                          )}
                      </span>
                    </div>
                  </div>
                )}
              </div>

              {/* Trình phát video dọc 9:16 (tối đa 360x640) */}
              <div className="mx-auto aspect-[9/16] w-full max-w-[340px] overflow-hidden rounded-2xl bg-black shadow-xl border border-line">
                {output.video && (
                  <video
                    src={fileUrl(output.video)}
                    controls
                    playsInline
                    className="h-full w-full object-contain"
                  />
                )}
              </div>

              {/* Các nút hành động */}
              <div className="mx-auto max-w-md space-y-3">
                {/* Tải video (chính) */}
                {output.video && (
                  <a
                    href={fileUrl(output.video)}
                    download
                    className="flex w-full items-center justify-center gap-2 rounded-xl bg-brand py-3 text-body font-bold text-ink shadow-md transition-all hover:brightness-105 active:scale-[0.98]"
                  >
                    <DownloadIcon size={20} />
                    {T.result.downloadVideo}
                  </a>
                )}

                <div className="grid grid-cols-2 gap-3">
                  {/* Sao chép nội dung đăng */}
                  <Button tone="soft" onClick={handleCopyPublish} className="w-full">
                    <CopyIcon size={16} />
                    {copiedPublish ? T.result.copiedPublish : T.result.copyPublish}
                  </Button>

                  {/* Tải ảnh bìa */}
                  {output.cover && (
                    <a
                      href={fileUrl(output.cover)}
                      download
                      className="ui-btn ui-btn-soft w-full text-center"
                    >
                      <DownloadIcon size={16} />
                      {T.result.downloadCover}
                    </a>
                  )}
                </div>

                <div className="grid grid-cols-2 gap-3 pt-2">
                  {/* Chỉnh chi tiết (mở màn 5 bước cũ) */}
                  {projectSlug && (
                    <Link
                      to={`/postv/${projectSlug}/export`}
                      className="ui-btn ui-btn-soft w-full text-center"
                    >
                      <UploadIcon size={16} />
                      {T.result.editDetails}
                    </Link>
                  )}

                  {/* Làm lại với tuỳ chọn khác */}
                  <Button tone="soft" onClick={handleReset} className="w-full">
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
