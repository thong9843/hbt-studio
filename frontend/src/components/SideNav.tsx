import { useQuery } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { Link, NavLink, useMatch } from 'react-router-dom';
import { fetchHealth, type Health } from '../api/client';
import { api } from '../api/endpoints';
import { useNewProject } from '../hooks/newProject';
import { useTheme } from '../hooks/useTheme';
import { vi } from '../i18n/vi';
import {
  ChatIcon,
  EyeIcon,
  FilmIcon,
  FolderIcon,
  GripIcon,
  HomeIcon,
  MoonIcon,
  MusicIcon,
  PlusIcon,
  SettingsIcon,
  SunIcon,
  UploadIcon,
} from './icons';
import { Button } from './ui/Button';
import { Progress } from './ui/Progress';
import { cx } from './ui/cx';
import './ui/ui.css';

const ENV_ITEMS = [
  'ffmpeg',
  'whisper',
  'gpu',
  'vieneu',
] as const satisfies readonly (keyof Health)[];

/** Tiến độ dựng đang chạy, do AppShell truyền vào (Đợt 3d nối job thật). */
export interface RenderProgress {
  percent: number;
  step: string;
  /** Dòng "Còn ≈ …" hoặc "Đang ước tính…"; bỏ trống = không hiện. */
  remaining?: string;
  /** Có thì hiện nút Huỷ. */
  onCancel?: () => void;
}

interface Props {
  /** Thu còn biểu tượng (rộng 72) ở dưới 1280 px. */
  mini: boolean;
  /** Có job đang chạy thì hiện thẻ tiến độ; `null` thì ẩn. */
  render?: RenderProgress | null;
}

/** Mục thanh trái: biểu tượng + chữ; ở chế độ thu chỉ còn biểu tượng (vẫn có tên đọc). */
function NavItem({
  to,
  end,
  icon,
  label,
  mini,
}: {
  to: string;
  end?: boolean;
  icon: ReactNode;
  label: string;
  mini: boolean;
}) {
  const body = (
    <>
      <span className="shrink-0">{icon}</span>
      {mini ? <span className="sr-only">{label}</span> : <span className="truncate">{label}</span>}
    </>
  );
  const cls = cx('ui-nav-item', mini && 'justify-center px-0');
  return (
    <NavLink to={to} end={end} className={cls} title={mini ? label : undefined}>
      {body}
    </NavLink>
  );
}

/** Chấm môi trường. Không poll: chỉ lấy khi mở app và khi tab lấy lại focus (13.B3.2 luật 6). */
function Environment({ mini }: { mini: boolean }) {
  const { data, isError } = useQuery({
    queryKey: ['health'],
    queryFn: () => fetchHealth(),
    retry: false,
    refetchOnWindowFocus: true,
  });
  return (
    <ul aria-label={vi.nav.env} className={cx('space-y-1 px-3 py-2', mini && 'px-0')}>
      {ENV_ITEMS.map((key) => {
        const ok = data?.[key];
        const state =
          isError || data === undefined ? '?' : ok ? vi.health.available : vi.health.missing;
        return (
          <li
            key={key}
            title={`${vi.health.items[key]}: ${state}`}
            className={cx(
              'flex items-center gap-2 text-tiny font-semibold text-muted',
              mini && 'justify-center',
            )}
          >
            <span
              aria-hidden="true"
              className={cx(
                'h-2.5 w-2.5 shrink-0 rounded-full',
                ok ? 'bg-ok' : data ? 'border-2 border-danger' : 'bg-soft',
              )}
            />
            {mini ? (
              <span className="sr-only">
                {vi.health.items[key]}: {state}
              </span>
            ) : (
              <>
                {vi.health.items[key]}
                <span className="sr-only">: {state}</span>
              </>
            )}
          </li>
        );
      })}
    </ul>
  );
}

/** Khối dự án đang mở: tên + Soạn video / Âm thanh / Xuất video (chỉ khi ở /p/:slug). */
function OpenProject({ slug, mini }: { slug: string; mini: boolean }) {
  const { data } = useQuery({
    queryKey: ['projects'],
    queryFn: api.listProjects,
    staleTime: 30_000,
  });
  const name = data?.find((p) => p.slug === slug)?.title ?? slug;
  const base = `/p/${slug}`;
  return (
    <div aria-label={vi.nav.openProject} role="group" className="mt-2 space-y-1">
      {!mini && (
        <p className="truncate px-3 pt-2 text-tiny font-semibold text-muted" title={name}>
          {name}
        </p>
      )}
      <NavItem to={base} end icon={<FilmIcon />} label={vi.nav.compose} mini={mini} />
      <NavItem to={`${base}/audio`} icon={<MusicIcon />} label={vi.nav.audio} mini={mini} />
      <NavItem to={`${base}/export`} icon={<UploadIcon />} label={vi.nav.export} mini={mini} />
    </div>
  );
}

/** Khối dự án PostV đang mở: tên + 5 bước PostV (chỉ khi ở /postv/:slug). */
function OpenPostvProject({ slug, mini }: { slug: string; mini: boolean }) {
  const { data } = useQuery({
    queryKey: ['projects'],
    queryFn: api.listProjects,
    staleTime: 30_000,
  });
  const name = data?.find((p) => p.slug === slug)?.title ?? slug;
  const base = `/postv/${slug}`;
  const steps = vi.postv.steps;
  return (
    <div aria-label={vi.nav.openProject} role="group" className="mt-2 space-y-1">
      {!mini && (
        <p className="truncate px-3 pt-2 text-tiny font-semibold text-muted" title={name}>
          {name}
        </p>
      )}
      <NavItem to={base} end icon={<ChatIcon />} label={steps[0]} mini={mini} />
      <NavItem to={`${base}/pick`} icon={<GripIcon />} label={steps[1]} mini={mini} />
      <NavItem to={`${base}/script`} icon={<MusicIcon />} label={steps[2]} mini={mini} />
      <NavItem to={`${base}/preview`} icon={<EyeIcon />} label={steps[3]} mini={mini} />
      <NavItem to={`${base}/export`} icon={<UploadIcon />} label={steps[4]} mini={mini} />
    </div>
  );
}

/** Nút Sáng ↔ Tối: chữ và biểu tượng là chế độ hiện tại; thu 72 px chỉ còn biểu tượng. */
function ThemeToggle({ mini }: { mini: boolean }) {
  const { theme, toggle } = useTheme();
  const dark = theme === 'dark';
  const T = vi.nav.theme;
  const label = dark ? T.dark : T.light;
  const action = dark ? T.toLight : T.toDark;
  return (
    <button
      type="button"
      className={cx('ui-nav-item w-full', mini && 'justify-center px-0')}
      aria-pressed={dark}
      aria-label={action}
      title={mini ? action : undefined}
      onClick={toggle}
    >
      <span className="shrink-0">{dark ? <MoonIcon /> : <SunIcon />}</span>
      {!mini && <span className="truncate">{label}</span>}
    </button>
  );
}

/** Thẻ tiến độ dựng ở chân thanh trái; chỉ hiện khi có `render`. */
export function RenderCard({ render, mini }: { render: RenderProgress; mini: boolean }) {
  const pct = Math.round(render.percent);
  if (mini) {
    return (
      <div className="px-2 py-2" title={`${vi.nav.renderProgress}: ${pct}%`}>
        <Progress value={render.percent} label={vi.nav.renderProgressBar} />
      </div>
    );
  }
  return (
    <div className="ui-inner mx-3 my-2 p-3" role="status" aria-label={vi.nav.renderProgress}>
      <p className="text-tiny font-semibold text-muted">{vi.nav.renderProgress}</p>
      <p className="mb-2 mt-1 truncate text-small font-bold">
        <span className="tabular-nums">{pct}%</span>
        {render.step && <span> · {render.step}</span>}
      </p>
      <Progress value={render.percent} label={vi.nav.renderProgressBar} />
      {(render.remaining || render.onCancel) && (
        <p className="mt-2 flex items-center justify-between gap-2 text-tiny text-muted">
          <span className="tabular-nums">{render.remaining}</span>
          {render.onCancel && (
            <Button tone="soft" size="sm" onClick={render.onCancel}>
              {vi.nav.cancelRender}
            </Button>
          )}
        </p>
      )}
    </div>
  );
}

/** Thanh trái cố định: rộng 232, hoặc 72 chỉ biểu tượng (DESIGN-HBT.md mục 5). */
export function SideNav({ mini, render }: Props) {
  const { open: openNew } = useNewProject();
  const openVideo = useMatch('/p/:slug/*');
  const openPostv = useMatch('/postv/:slug/*');
  const videoSlug = openVideo?.params.slug;
  const postvSlug = openPostv?.params.slug;
  return (
    <aside
      className={cx(
        'sticky top-0 flex h-screen shrink-0 flex-col border-r border-line bg-nav',
        mini ? 'w-[72px] px-2' : 'w-[232px] px-3',
      )}
    >
      <Link
        to="/"
        aria-label={vi.appName}
        className={cx('ui-nav-item mt-4 min-h-[52px]', mini && 'justify-center px-0')}
      >
        <img src="/brand/hbt-logo-mark.png" alt="" className="h-9 w-auto shrink-0" />
        {!mini && <span className="text-body font-extrabold">{vi.appName}</span>}
      </Link>

      <button
        type="button"
        className={cx('ui-btn ui-btn-brand mt-3', mini && 'mx-auto !h-11 !w-11 !min-h-0 !p-0')}
        aria-label={vi.nav.newVideo}
        title={mini ? vi.nav.newVideo : undefined}
        onClick={() => openNew()}
      >
        <PlusIcon />
        {!mini && vi.nav.newVideo}
      </button>

      <nav aria-label={vi.nav.main} className="mt-4 flex-1 overflow-y-auto">
        <div className="space-y-1">
          <NavItem to="/" end icon={<HomeIcon />} label={vi.nav.home} mini={mini} />
          <NavItem to="/projects" icon={<FolderIcon />} label={vi.nav.projects} mini={mini} />
          <NavItem to="/postv" icon={<ChatIcon />} label={vi.nav.postv} mini={mini} />
        </div>
        {videoSlug && <OpenProject slug={videoSlug} mini={mini} />}
        {postvSlug && <OpenPostvProject slug={postvSlug} mini={mini} />}
        <div className="mt-2">
          <NavItem to="/settings" icon={<SettingsIcon />} label={vi.nav.settings} mini={mini} />
        </div>
      </nav>

      {render && <RenderCard render={render} mini={mini} />}
      <div className="py-1">
        <ThemeToggle mini={mini} />
      </div>
      <Environment mini={mini} />
    </aside>
  );
}
