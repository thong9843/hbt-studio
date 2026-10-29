import type { Fps } from '../api/types';
import { PostvRenderPanel } from '../components/postv/PostvRenderPanel';
import { Card } from '../components/ui/Card';
import { Chip } from '../components/ui/Chip';
import { Switch } from '../components/ui/Switch';
import { usePostvEditor } from '../hooks/postvEditor';
import { vi } from '../i18n/vi';

const T = vi.postv.export;
const FPS: Fps[] = [30, 50, 60];

/** Bước 5 · Xuất: chọn fps, outro và dựng bản đẹp. Lịch sử, bìa, nội dung đăng: PV6. */
export function PostvExportPage() {
  const { project, update } = usePostvEditor();
  const fps = project.settings.fps as Fps;
  const ready =
    project.post.text.trim() !== '' &&
    project.segments.some((s) => s.voice.trim() !== '') &&
    Boolean(project.voice.file);
  return (
    <Card as="section" aria-label={T.title} className="mx-auto max-w-[520px] space-y-4">
      <h2 className="text-h2 font-bold">{T.title}</h2>
      <p className="text-small text-muted">{T.help}</p>
      <div className="ui-field">
        <span className="ui-label" id="pv-fps-label">
          {T.fps}
        </span>
        <div className="flex flex-wrap gap-2" role="group" aria-labelledby="pv-fps-label">
          {FPS.map((value) => (
            <Chip
              key={value}
              selected={fps === value}
              onClick={() => update((p) => ({ ...p, settings: { ...p.settings, fps: value } }))}
            >
              {`${value} fps`}
            </Chip>
          ))}
        </div>
      </div>
      <Switch
        label={T.outro}
        checked={project.settings.outro}
        onChange={(checked) =>
          update((p) => ({ ...p, settings: { ...p.settings, outro: checked } }))
        }
      />
      <PostvRenderPanel
        label={T.final(fps)}
        tone="accent"
        options={{ preview: false, fps, outro: project.settings.outro }}
        blocked={ready ? null : T.notReady}
      />
    </Card>
  );
}
