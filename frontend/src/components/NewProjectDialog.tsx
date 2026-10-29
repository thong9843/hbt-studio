import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useState, type FormEvent, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/endpoints';
import type { ProjectKind } from '../api/types';
import { NewProjectContext } from '../hooks/newProject';
import { vi } from '../i18n/vi';
import { projectHref } from '../utils/projectHref';
import { ErrorNote } from './ErrorNote';
import { Button } from './ui/Button';
import { Chip } from './ui/Chip';
import { Dialog } from './ui/Dialog';
import { Input } from './ui/Field';

const OTHER = 'other';
const DEFAULT_SCENES = 8;
const SCENE_COUNTS = Array.from({ length: 10 }, (_, i) => i + 3);

/** Hộp "Video mới": tên, series (3 + Khác), số cảnh 3–12. Tạo xong mở thẳng trang soạn. */
export function NewProjectDialog({
  open,
  onClose,
  initialKind = 'video',
}: {
  open: boolean;
  onClose: () => void;
  initialKind?: ProjectKind;
}) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const t = vi.projects.dialog;
  const [title, setTitle] = useState('');
  const [preset, setPreset] = useState<string>('');
  const [custom, setCustom] = useState('');
  const [sceneCount, setSceneCount] = useState(DEFAULT_SCENES);
  const [kind, setKind] = useState<ProjectKind>(initialKind);

  // Mở từ trang PostV thì chọn sẵn PostV.
  useEffect(() => {
    if (open) setKind(initialKind);
  }, [open, initialKind]);

  const series = preset === OTHER ? custom.trim() : preset;
  const create = useMutation({
    mutationFn: () =>
      api.createProject(
        kind === 'postv'
          ? { title: title.trim(), series, kind }
          : { title: title.trim(), series, scene_count: sceneCount },
      ),
    onSuccess: (project) => {
      void queryClient.invalidateQueries({ queryKey: ['projects'] });
      reset();
      onClose();
      navigate(projectHref({ slug: project.slug, kind }));
    },
  });

  function reset() {
    setTitle('');
    setPreset('');
    setCustom('');
    setSceneCount(DEFAULT_SCENES);
    setKind(initialKind);
    create.reset();
  }

  const close = () => {
    if (create.isPending) return;
    reset();
    onClose();
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (title.trim() && !create.isPending) create.mutate();
  };

  return (
    <Dialog
      open={open}
      onClose={close}
      title={t.title}
      className="max-w-[480px]"
      footer={
        <>
          <Button tone="soft" onClick={close}>
            {vi.common.cancel}
          </Button>
          <Button
            tone="ink"
            type="submit"
            form="new-project-form"
            busy={create.isPending}
            disabled={!title.trim()}
          >
            {t.submit}
          </Button>
        </>
      }
    >
      <form id="new-project-form" onSubmit={submit} className="space-y-5">
        <Input
          label={t.name}
          data-autofocus
          required
          placeholder={t.namePlaceholder}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
        <div className="ui-field">
          <span className="ui-label" id="np-series-label">
            {t.series}
          </span>
          <div className="flex flex-wrap gap-2" role="group" aria-labelledby="np-series-label">
            {[...t.seriesPresets, t.seriesOther].map((label, i) => {
              const value = i < t.seriesPresets.length ? label : OTHER;
              return (
                <Chip
                  key={value}
                  selected={preset === value}
                  onClick={() => setPreset(preset === value ? '' : value)}
                >
                  {label}
                </Chip>
              );
            })}
          </div>
          {preset === OTHER && (
            <Input
              aria-label={t.seriesOther}
              placeholder={t.seriesPlaceholder}
              value={custom}
              onChange={(e) => setCustom(e.target.value)}
            />
          )}
        </div>
        <div className="ui-field">
          <span className="ui-label" id="np-kind-label">
            {t.kind}
          </span>
          <div className="flex flex-wrap gap-2" role="group" aria-labelledby="np-kind-label">
            <Chip selected={kind === 'video'} onClick={() => setKind('video')}>
              {t.kindVideo}
            </Chip>
            <Chip selected={kind === 'postv'} onClick={() => setKind('postv')}>
              {t.kindPostv}
            </Chip>
          </div>
        </div>
        {kind === 'video' && (
          <div className="ui-field">
            <span className="ui-label" id="np-scenes-label">
              {t.scenes}
            </span>
            <div className="flex flex-wrap gap-2" role="group" aria-labelledby="np-scenes-label">
              {SCENE_COUNTS.map((n) => (
                <Chip key={n} small selected={sceneCount === n} onClick={() => setSceneCount(n)}>
                  {n}
                </Chip>
              ))}
            </div>
          </div>
        )}
        <ErrorNote error={create.error} />
      </form>
    </Dialog>
  );
}

/** Giữ trạng thái mở của hộp; đặt trong AppShell để mọi màn gọi được `useNewProject().open`. */
export function NewProjectProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState<ProjectKind>('video');
  const openDialog = useCallback((k?: ProjectKind) => {
    setKind(k === 'postv' ? 'postv' : 'video'); // nút truyền cả sự kiện bấm: chỉ nhận đúng 'postv'
    setOpen(true);
  }, []);
  const value = useMemo(() => ({ open: openDialog }), [openDialog]);
  return (
    <NewProjectContext.Provider value={value}>
      {children}
      <NewProjectDialog open={open} onClose={() => setOpen(false)} initialKind={kind} />
    </NewProjectContext.Provider>
  );
}
