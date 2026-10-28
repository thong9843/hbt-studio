import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/endpoints';
import { MusicCard } from '../components/audio/MusicCard';
import { MusicStartCard } from '../components/audio/MusicStartCard';
import { VoiceCard } from '../components/audio/VoiceCard';
import { PreviewPane } from '../components/compose/PreviewPane';
import { EyeIcon } from '../components/icons';
import { Button } from '../components/ui/Button';
import { Drawer } from '../components/ui/Drawer';
import { useEstimateLine } from '../hooks/useEstimates';
import { useProjectEditor } from '../hooks/projectEditor';
import { useMediaQuery } from '../hooks/useMediaQuery';
import { vi } from '../i18n/vi';
import { primaryActionState } from '../utils/blockers';

/** Từ 1024 px cột xem trước nằm cạnh; dưới đó thành ngăn kéo (như màn Soạn video). */
const PREVIEW_INLINE_QUERY = '(min-width: 1024px)';

/**
 * Màn Âm thanh: [Giọng đọc + Điểm bắt đầu nhạc] · [Nhạc nền] · xem trước 9:16 dùng lại của Soạn video.
 * Lấy lịch sử dựng đúng một lần khi mở màn (không poll).
 */
export function AudioTab() {
  const editor = useProjectEditor();
  const navigate = useNavigate();
  const { project } = editor;
  const inline = useMediaQuery(PREVIEW_INLINE_QUERY);
  const [selected, setSelected] = useState(0);
  const [drawer, setDrawer] = useState(false);

  const renders = useQuery({
    queryKey: ['renders', project.slug],
    queryFn: () => api.listRenders(project.slug),
    refetchOnWindowFocus: false,
  });
  const latest = renders.data?.[0];

  const count = project.scenes.length;
  const index = Math.min(selected, count - 1);
  const estimateLine = useEstimateLine(project);
  const action = primaryActionState(project);
  const preview = (
    <PreviewPane
      slug={project.slug}
      sceneIndex={index}
      sceneCount={count}
      scene={project.scenes[index]}
      theme={project.theme}
      imageVersion={editor.imageVersion}
      blockedReason={action.enabled ? undefined : action.reason}
      onPrev={() => setSelected(Math.max(0, index - 1))}
      onNext={() => setSelected(Math.min(count - 1, index + 1))}
      estimate={estimateLine}
      onGoExport={(auto) =>
        navigate(`/p/${project.slug}/export`, auto ? { state: { auto } } : undefined)
      }
    />
  );

  return (
    <div className="space-y-5">
      <div
        className={
          inline
            ? 'grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)_300px] gap-[18px]'
            : 'grid grid-cols-1 gap-[18px] min-[700px]:grid-cols-2'
        }
      >
        <div className="min-w-0 space-y-[18px] self-start">
          <VoiceCard latest={latest} />
          <MusicStartCard music={project.music} latest={latest} />
        </div>
        <div className="min-w-0 self-start">
          <MusicCard />
        </div>
        {inline && <div className="sticky top-5 self-start">{preview}</div>}
      </div>

      {!inline && (
        <>
          <Button
            tone="ink"
            className="fixed bottom-6 right-6 z-30 shadow-lg"
            icon={<EyeIcon size={20} />}
            onClick={() => setDrawer(true)}
          >
            {vi.compose.preview.open}
          </Button>
          <Drawer open={drawer} onClose={() => setDrawer(false)} title={vi.compose.preview.title}>
            {preview}
          </Drawer>
        </>
      )}
    </div>
  );
}
