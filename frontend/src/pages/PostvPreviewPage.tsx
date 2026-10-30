import { useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/endpoints';
import { ClipTile } from '../components/postv/BackgroundLibrary';
import { PostvCardPreview } from '../components/postv/PostvCardPreview';
import { PostvRenderPanel } from '../components/postv/PostvRenderPanel';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { Chip } from '../components/ui/Chip';
import { Input } from '../components/ui/Field';
import { Switch } from '../components/ui/Switch';
import { PlayIcon } from '../components/icons';
import { usePostvEditor } from '../hooks/postvEditor';
import { useBackgrounds } from '../hooks/useBackgrounds';
import { vi } from '../i18n/vi';
import { totalSeconds } from '../utils/postvSegments';

const HEAD_SECONDS = 10;

/** Bước 4 · Xem trước: chọn nền gameplay, chữ thẻ tiêu đề, hiệu ứng thẻ, phụ đề, che từ, xem trước tĩnh 9:16. */
export function PostvPreviewPage() {
  const { project, update, savedCount } = usePostvEditor();
  const t = vi.postv.preview;
  const clips = useBackgrounds();
  const [tab, setTab] = useState<string>('hook'); // 'hook' | 'post' | id bình luận
  const [viewMode, setViewMode] = useState<'full' | 'card'>('full');
  const [playingBleep, setPlayingBleep] = useState(false);

  const picked = project.comments.filter((c) => c.picked);
  const manual = project.background.mode === 'manual';
  const library = clips.data ?? [];
  const chosen = manual
    ? library.filter((c) => project.background.clip_ids.includes(c.id))
    : library;
  const total = chosen.reduce((sum, c) => sum + c.duration, 0);
  const need = Math.ceil(totalSeconds(project.segments));
  const ready =
    project.post.text.trim() !== '' &&
    project.segments.some((s) => s.voice.trim() !== '') &&
    Boolean(project.voice.file) &&
    chosen.length > 0;

  const setMode = (mode: 'auto' | 'manual') =>
    update((p) => ({ ...p, background: { ...p.background, mode } }));
  const toggleClip = (id: string) =>
    update((p) => {
      const ids = p.background.clip_ids;
      const next = ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id];
      return { ...p, background: { ...p.background, clip_ids: next } };
    });

  const playBleep = () => {
    setPlayingBleep(true);
    const audio = new Audio(api.postvBleepUrl());
    audio.onended = () => setPlayingBleep(false);
    audio.onerror = () => setPlayingBleep(false);
    audio.play().catch(() => setPlayingBleep(false));
  };

  const tabs = [
    { key: 'hook', label: t.tabs.hook },
    { key: 'post', label: t.tabs.post },
    ...picked.map((c) => ({ key: c.id, label: c.handle || c.id })),
  ];
  const active = tabs.some((x) => x.key === tab) ? tab : 'hook';
  const kind = active === 'hook' || active === 'post' ? active : 'comment';

  const captionPreset = project.style?.caption?.preset ?? 'hbt';
  const highlightColor =
    project.style?.caption?.highlight_color ?? (captionPreset === 'sample' ? '#38E178' : '#FFD43B');
  const captionsEnabled = project.settings?.captions ?? true;
  const censorEnabled = project.settings?.censor?.enabled ?? true;
  const censorText = project.settings?.censor?.text ?? 'blur';
  const cardAnimation = project.settings?.card_animation ?? 'smooth';

  return (
    <div className="grid gap-4 min-[1024px]:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)_300px]">
      <Card as="section" aria-label={t.background} className="flex min-w-0 flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="mr-auto text-h2 font-bold">{t.background}</h2>
          <Chip small selected={!manual} onClick={() => setMode('auto')}>
            {t.auto}
          </Chip>
          <Chip small selected={manual} onClick={() => setMode('manual')}>
            {t.manual}
          </Chip>
        </div>
        {clips.data && library.length === 0 && (
          <div className="ui-inner flex flex-wrap items-center gap-3 p-3">
            <p className="min-w-0 flex-1 text-small font-semibold">{t.libraryEmpty}</p>
            <Link to="/postv" className="ui-btn ui-btn-soft">
              {t.openLibrary}
            </Link>
          </div>
        )}
        {manual && library.length > 0 && (
          <ul className="flex flex-wrap gap-3" aria-label={t.background}>
            {library.map((c) => (
              <ClipTile
                key={c.id}
                clip={c}
                selected={project.background.clip_ids.includes(c.id)}
                onToggle={() => toggleClip(c.id)}
              />
            ))}
          </ul>
        )}
        {library.length > 0 && (
          <p className="text-small font-semibold" role="status">
            {chosen.length === 0
              ? t.noneChosen
              : [
                  t.summary(chosen.length, total),
                  need > 0 ? (total >= need ? t.enough(need) : t.notEnough(need)) : null,
                ]
                  .filter(Boolean)
                  .join(' · ')}
          </p>
        )}
      </Card>

      <Card as="section" aria-label={t.cards} className="flex min-w-0 flex-col gap-4">
        <h2 className="text-h2 font-bold">{t.cards}</h2>
        <Input
          label={t.hookText}
          placeholder={t.hookHint}
          value={project.hook.text}
          onChange={(e) => update((p) => ({ ...p, hook: { ...p.hook, text: e.target.value } }))}
        />
        <Input
          label={t.hookAccent}
          value={project.hook.accent}
          onChange={(e) => update((p) => ({ ...p, hook: { ...p.hook, accent: e.target.value } }))}
        />
        <div className="ui-field">
          <span className="ui-label" id="pv-anim-label">
            {t.animation}
          </span>
          <div className="flex flex-wrap gap-2" role="group" aria-labelledby="pv-anim-label">
            {(['smooth', 'bounce'] as const).map((value) => (
              <Chip
                key={value}
                selected={cardAnimation === value}
                onClick={() =>
                  update((p) => ({ ...p, settings: { ...p.settings, card_animation: value } }))
                }
              >
                {t[value]}
              </Chip>
            ))}
          </div>
        </div>

        <div className="space-y-3 border-t border-line pt-3">
          <div className="flex items-center justify-between">
            <span className="font-bold">{t.captions}</span>
            <Switch
              label={t.captions}
              checked={captionsEnabled}
              onChange={(checked) =>
                update((p) => ({ ...p, settings: { ...p.settings, captions: checked } }))
              }
            />
          </div>
          {captionsEnabled && (
            <div className="space-y-3 pl-1">
              <div className="ui-field">
                <span className="ui-label" id="pv-cap-preset">
                  {t.captionPreset}
                </span>
                <div className="flex flex-wrap gap-2" role="group" aria-labelledby="pv-cap-preset">
                  <Chip
                    small
                    selected={captionPreset === 'hbt'}
                    onClick={() =>
                      update((p) => ({
                        ...p,
                        style: {
                          ...(p.style ?? {}),
                          caption: { ...(p.style?.caption ?? {}), preset: 'hbt' },
                        },
                      }))
                    }
                  >
                    {t.presetHbt}
                  </Chip>
                  <Chip
                    small
                    selected={captionPreset === 'sample'}
                    onClick={() =>
                      update((p) => ({
                        ...p,
                        style: {
                          ...(p.style ?? {}),
                          caption: { ...(p.style?.caption ?? {}), preset: 'sample' },
                        },
                      }))
                    }
                  >
                    {t.presetSample}
                  </Chip>
                </div>
              </div>
              <Input
                label={t.captionColor}
                value={highlightColor}
                onChange={(e) =>
                  update((p) => ({
                    ...p,
                    style: {
                      ...(p.style ?? {}),
                      caption: { ...(p.style?.caption ?? {}), highlight_color: e.target.value },
                    },
                  }))
                }
              />
            </div>
          )}
        </div>

        <div className="space-y-3 border-t border-line pt-3">
          <div className="flex items-center justify-between">
            <span className="font-bold">{t.censor}</span>
            <Switch
              label={t.censor}
              checked={censorEnabled}
              onChange={(checked) =>
                update((p) => ({
                  ...p,
                  settings: {
                    ...p.settings,
                    censor: {
                      ...(p.settings?.censor ?? { sfx: 'bleep', blur_card: true, text: 'blur' }),
                      enabled: checked,
                    },
                  },
                }))
              }
            />
          </div>
          {censorEnabled && (
            <div className="space-y-3 pl-1">
              <div className="ui-field">
                <span className="ui-label" id="pv-censor-text">
                  {t.censorText}
                </span>
                <div className="flex flex-wrap gap-2" role="group" aria-labelledby="pv-censor-text">
                  <Chip
                    small
                    selected={censorText === 'blur'}
                    onClick={() =>
                      update((p) => ({
                        ...p,
                        settings: {
                          ...p.settings,
                          censor: {
                            ...(p.settings?.censor ?? {
                              enabled: true,
                              sfx: 'bleep',
                              blur_card: true,
                            }),
                            text: 'blur',
                          },
                        },
                      }))
                    }
                  >
                    {t.censorBlur}
                  </Chip>
                  <Chip
                    small
                    selected={censorText === 'stars'}
                    onClick={() =>
                      update((p) => ({
                        ...p,
                        settings: {
                          ...p.settings,
                          censor: {
                            ...(p.settings?.censor ?? {
                              enabled: true,
                              sfx: 'bleep',
                              blur_card: true,
                            }),
                            text: 'stars',
                          },
                        },
                      }))
                    }
                  >
                    {t.censorStars}
                  </Chip>
                </div>
              </div>
              <div>
                <Button
                  tone="soft"
                  size="sm"
                  icon={<PlayIcon size={16} />}
                  onClick={playBleep}
                  busy={playingBleep}
                >
                  {t.testBleep}
                </Button>
              </div>
            </div>
          )}
        </div>
      </Card>

      <aside aria-label={t.previewOf} className="flex flex-col gap-3">
        <PostvRenderPanel
          label={t.quick}
          options={{ preview: true, preview_seconds: HEAD_SECONDS }}
          blocked={ready ? null : t.notReady}
        />
        <div className="flex flex-wrap justify-center gap-2" role="group" aria-label={t.viewMode}>
          <Chip small selected={viewMode === 'full'} onClick={() => setViewMode('full')}>
            {t.viewStatic}
          </Chip>
          <Chip small selected={viewMode === 'card'} onClick={() => setViewMode('card')}>
            {t.viewCard}
          </Chip>
        </div>
        <div className="flex flex-wrap justify-center gap-2" role="group" aria-label={t.previewOf}>
          {tabs.map((x) => (
            <Chip key={x.key} small selected={active === x.key} onClick={() => setTab(x.key)}>
              {x.label}
            </Chip>
          ))}
        </div>
        <PostvCardPreview
          slug={project.slug}
          kind={kind}
          refId={kind === 'comment' ? active : undefined}
          version={savedCount}
          caption={viewMode === 'full' ? t.viewStatic : t.viewCard}
          fullPreview={viewMode === 'full'}
        />
      </aside>
    </div>
  );
}
