import { useQuery } from '@tanstack/react-query';
import { useState, type ReactNode } from 'react';
import { Link, NavLink, useMatch } from 'react-router-dom';
import { fetchHealth, type Health } from '../../api/client';
import { api } from '../../api/endpoints';
import { useNewProject } from '../../hooks/newProject';
import { useDraftExists } from '../../hooks/useDraft';
import { useTheme } from '../../hooks/useTheme';
import { vi } from '../../i18n/vi';
import {
  ChatIcon,
  EyeIcon,
  FilmIcon,
  FolderIcon,
  GripIcon,
  HomeIcon,
  ImageIcon,
  MessagesSquareIcon,
  MoonIcon,
  MusicIcon,
  PanelLeftCloseIcon,
  PanelLeftOpenIcon,
  PlusIcon,
  SettingsIcon,
  SmartphoneIcon,
  SparklesIcon,
  SunIcon,
  UploadIcon,
  ZapIcon,
} from '../icons';
import { Button } from '../ui/Button';
import { Progress } from '../ui/Progress';
import { cx } from '../ui/cx';
import { QuickCreateDrawer } from './QuickCreateDrawer';
import '../ui/ui.css';

export const SIDEBAR_COLLAPSED_KEY = 'hbt_sidebar_collapsed';

const ENV_ITEMS = [
  'ffmpeg',
  'whisper',
  'gpu',
  'vieneu',
] as const satisfies readonly (keyof Health)[];

/** Tiến độ dựng đang chạy, do AppLayout / SidebarRenderStatus truyền vào. */
export interface RenderProgress {
  percent: number;
  step: string;
  /** Động cơ sở hữu job (`core | postv | chatting | stickv`). */
  engine?: 'core' | 'postv' | 'chatting' | 'stickv';
  /** Tên dự án hiển thị gọn 1 dòng. */
  title?: string;
  /** Đường dẫn nhảy thẳng tới dự án đang chạy. */
  route?: string;
  /** Dòng "Còn ≈ …" hoặc "Đang ước tính…"; bỏ trống = không hiện. */
  remaining?: string;
  /** Có thì hiện nút Huỷ. */
  onCancel?: () => void;
}

export interface SidebarProps {
  /** Thu còn biểu tượng (rộng 64px) hoặc phóng rộng (224px). */
  mini: boolean;
  /** Bấm nút mở rộng / thu gọn Sidebar. */
  onToggleMini?: () => void;
  /** Có job đang chạy thì hiện thẻ tiến độ; `null` thì ẩn. */
  render?: RenderProgress | null;
  /** Widget tiến độ tự đăng ký external store (tránh re-render toàn Sidebar). */
  renderSlot?: ReactNode;
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
  const hasDraft = useDraftExists(slug);
  return (
    <div aria-label={vi.nav.openProject} role="group" className="mt-2 space-y-1">
      {!mini && (
        <p className="truncate px-3 pt-2 text-tiny font-semibold text-muted" title={name}>
          {name}
        </p>
      )}
      <NavItem to={base} end icon={<FilmIcon />} label={vi.nav.compose} mini={mini} />
      {hasDraft && (
        <NavItem to={`${base}/images`} icon={<ImageIcon />} label={vi.nav.images} mini={mini} />
      )}
      <NavItem to={`${base}/audio`} icon={<MusicIcon />} label={vi.nav.audio} mini={mini} />
      <NavItem to={`${base}/export`} icon={<UploadIcon />} label={vi.nav.export} mini={mini} />
    </div>
  );
}

/** Khối dự án PostV đang mở: tên + 5 bước PostV (chỉ khi ở /postv/:slug hoặc khi bật Chế độ nâng cao). */
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

/** Nút Sáng ↔ Tối: chữ và biểu tượng Mặt trăng / Mặt trời sắc nét, tách biệt hẳn icon Bánh răng Cài đặt. */
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
      <span className="shrink-0" data-testid={dark ? 'theme-icon-moon' : 'theme-icon-sun'}>
        {dark ? <MoonIcon /> : <SunIcon />}
      </span>
      {!mini && <span className="truncate">{label}</span>}
    </button>
  );
}

const ENGINE_BADGE_MAP: Record<
  'core' | 'postv' | 'chatting' | 'stickv',
  { label: string; badgeClass: string }
> = {
  core: {
    label: 'HBT Core',
    badgeClass: 'bg-red-500/15 text-red-500 border-red-500/30',
  },
  postv: {
    label: 'PostV',
    badgeClass: 'bg-purple-500/15 text-purple-400 border-purple-500/30',
  },
  chatting: {
    label: 'Chatting',
    badgeClass: 'bg-sky-500/15 text-sky-400 border-sky-500/30',
  },
  stickv: {
    label: 'StickV',
    badgeClass: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
  },
};

/** Khối tiến độ tổng cố định ở Sidebar trái cho cả 4 động cơ (hỗ trợ cả 224px & Icon Rail 64px). */
export function SidebarRenderStatus({ render, mini }: { render: RenderProgress; mini: boolean }) {
  const pct = Math.max(0, Math.min(100, Math.round(render.percent)));
  const engineInfo = render.engine ? ENGINE_BADGE_MAP[render.engine] : null;
  const projectLabel = render.title || '';
  const tooltip = [engineInfo?.label || vi.nav.renderProgress, projectLabel, `${pct}%`, render.step]
    .filter(Boolean)
    .join(' · ');

  if (mini) {
    const r = 16;
    const c = 2 * Math.PI * r;
    const offset = c * (1 - pct / 100);
    const ring = (
      <div
        role="progressbar"
        aria-label={vi.nav.renderProgressBar}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct}
        title={tooltip}
        className="relative mx-auto flex h-10 w-10 items-center justify-center rounded-full bg-soft/70 text-[10px] font-bold tabular-nums text-text"
      >
        <svg viewBox="0 0 40 40" className="h-10 w-10 -rotate-90" aria-hidden="true">
          <circle
            cx="20"
            cy="20"
            r={r}
            fill="none"
            stroke="currentColor"
            strokeWidth="3"
            className="text-border-subtle"
          />
          <circle
            cx="20"
            cy="20"
            r={r}
            fill="none"
            stroke="var(--brand)"
            strokeWidth="3"
            strokeLinecap="round"
            strokeDasharray={c}
            strokeDashoffset={offset}
          />
        </svg>
        <span className="absolute inset-0 flex items-center justify-center">{pct}%</span>
      </div>
    );
    return (
      <div className="px-2 py-2">
        {render.route ? (
          <Link
            to={render.route}
            title={tooltip}
            aria-label={`Đi tới dự án: ${tooltip}`}
            className="block rounded-full transition-transform hover:scale-105"
          >
            {ring}
          </Link>
        ) : (
          ring
        )}
      </div>
    );
  }

  return (
    <div
      className="ui-inner mx-3 my-2 space-y-2 border border-line/80 p-3"
      role="status"
      aria-label={vi.nav.renderProgress}
    >
      <div className="flex items-center justify-between gap-2">
        {engineInfo ? (
          <span
            className={cx(
              'inline-flex items-center rounded-pill border px-2 py-0.5 text-[10px] font-extrabold uppercase tracking-wider',
              engineInfo.badgeClass,
            )}
          >
            {engineInfo.label}
          </span>
        ) : (
          <p className="text-tiny font-semibold text-muted">{vi.nav.renderProgress}</p>
        )}
        <span className="tabular-nums text-tiny font-extrabold text-brand">{pct}%</span>
      </div>

      {projectLabel && (
        <p className="truncate text-tiny font-bold text-text" title={projectLabel}>
          {projectLabel}
        </p>
      )}

      <p className="truncate text-[11px] font-semibold text-muted" title={render.step}>
        {render.step || vi.nav.renderProgress}
      </p>

      <Progress value={pct} label={vi.nav.renderProgressBar} />

      <div className="flex items-center justify-between gap-1.5 pt-0.5">
        {render.route ? (
          <Link
            to={render.route}
            className="truncate text-[11px] font-bold text-text hover:text-brand hover:underline"
          >
            Đi tới dự án →
          </Link>
        ) : (
          <span className="truncate text-tiny text-muted tabular-nums">{render.remaining}</span>
        )}
        <div className="flex shrink-0 items-center gap-1.5">
          {render.route && render.remaining && (
            <span className="text-[10px] text-muted tabular-nums">{render.remaining}</span>
          )}
          {render.onCancel && (
            <Button tone="soft" size="sm" onClick={render.onCancel}>
              {vi.nav.cancelRender}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

/** Alias tương thích cho các test đơn lẻ đang mount `RenderCard`. */
export function RenderCard({ render, mini }: { render: RenderProgress; mini: boolean }) {
  return <SidebarRenderStatus render={render} mini={mini} />;
}

/**
 * Sidebar thống nhất (Navigation Shell):
 * - Có nút Mở rộng (224px) / Thu gọn (64px) rõ ràng ngay ở đầu thanh, lưu vào localStorage, hoạt động trên mọi trang.
 * - Chân Sidebar phân biệt sắc nét icon Bánh răng (Cài đặt) và Mặt trăng / Mặt trời (Sáng/Tối).
 */
export function Sidebar({ mini, onToggleMini, render, renderSlot }: SidebarProps) {
  const { open: openNew } = useNewProject();
  const [quickOpen, setQuickOpen] = useState(false);
  const openVideo = useMatch('/p/:slug/*');
  const openPostv = useMatch('/postv/:slug/*');
  const videoSlug = openVideo?.params.slug;
  const postvSlug = openPostv?.params.slug;
  const isAdvanced = (() => {
    try {
      return localStorage.getItem('hbt_advanced_mode') === 'true';
    } catch {
      return false;
    }
  })();
  const { data: allProjects } = useQuery({
    queryKey: ['projects'],
    queryFn: api.listProjects,
    staleTime: 30_000,
  });
  const latestPostvSlug = allProjects?.find((p) => p.kind === 'postv')?.slug;
  const showPostvProjectSlug = postvSlug || (isAdvanced ? latestPostvSlug : undefined);
  const toggleLabel = mini ? vi.nav.expandSidebar : vi.nav.collapseSidebar;

  return (
    <aside
      className={cx(
        'sticky top-0 flex h-screen shrink-0 flex-col border-r border-border-subtle bg-nav transition-[width] duration-[180ms] motion-reduce:transition-none',
        mini ? 'w-[64px] px-1.5' : 'w-[224px] px-3',
      )}
    >
      <div
        className={cx(
          'mt-3 flex items-center gap-1',
          mini ? 'flex-col justify-center' : 'justify-between',
        )}
      >
        <Link
          to="/"
          aria-label={vi.appName}
          className={cx(
            'ui-nav-item min-h-[48px] min-w-0 flex-1',
            mini && 'w-full justify-center px-0',
          )}
        >
          <img src="/brand/hbt-logo-mark.png" alt="" className="h-8 w-auto shrink-0 rounded-lg" />
          {!mini && (
            <span className="whitespace-nowrap text-[15px] font-bold tracking-tight text-text">
              {vi.appName}
            </span>
          )}
        </Link>

        {onToggleMini && (
          <button
            type="button"
            onClick={onToggleMini}
            aria-label={toggleLabel}
            aria-expanded={!mini}
            title={toggleLabel}
            className="ui-icon-btn ui-icon-btn-sm shrink-0 text-muted hover:text-text"
          >
            {mini ? <PanelLeftOpenIcon size={18} /> : <PanelLeftCloseIcon size={18} />}
          </button>
        )}
      </div>

      <div className={cx('mt-2.5 flex gap-2', mini ? 'flex-col items-center' : 'items-center')}>
        <button
          type="button"
          className={cx(
            'ui-btn ui-btn-brand flex-1',
            mini && 'mx-auto !h-10 !w-10 !min-h-0 !flex-none !p-0',
          )}
          aria-label={vi.nav.newVideo}
          title={mini ? vi.nav.newVideo : 'Tạo dự án HBT / PostV thủ công'}
          onClick={() => openNew()}
        >
          <PlusIcon />
          {!mini && vi.nav.newVideo}
        </button>
        {!mini && (
          <button
            type="button"
            className="ui-btn ui-btn-magic !min-h-[40px] !px-3"
            aria-label="Tạo nhanh"
            title="Mở bảng chọn nhanh 3 động cơ AI"
            onClick={() => setQuickOpen(true)}
          >
            <ZapIcon size={16} />
          </button>
        )}
      </div>

      <nav aria-label={vi.nav.main} className="mt-3 flex-1 overflow-y-auto">
        <div className="space-y-1">
          <NavItem to="/" end icon={<HomeIcon />} label={vi.nav.home} mini={mini} />
          <NavItem to="/core" icon={<ZapIcon />} label={vi.nav.hbtCore} mini={mini} />
          <NavItem to="/postv" icon={<SmartphoneIcon />} label={vi.nav.postv} mini={mini} />
          <NavItem
            to="/chatting"
            icon={<MessagesSquareIcon />}
            label={vi.nav.chatting}
            mini={mini}
          />
          <NavItem to="/stickv" icon={<SparklesIcon />} label={vi.nav.stickv} mini={mini} />
          <NavItem to="/library" icon={<FolderIcon />} label={vi.nav.library} mini={mini} />
        </div>
        {videoSlug && <OpenProject slug={videoSlug} mini={mini} />}
        {showPostvProjectSlug && <OpenPostvProject slug={showPostvProjectSlug} mini={mini} />}
      </nav>

      {render ? <RenderCard render={render} mini={mini} /> : renderSlot}
      <div className="space-y-1 border-t border-line py-2">
        <NavItem to="/settings" icon={<SettingsIcon />} label={vi.nav.settings} mini={mini} />
        <ThemeToggle mini={mini} />
      </div>
      <Environment mini={mini} />
      <QuickCreateDrawer open={quickOpen} onClose={() => setQuickOpen(false)} />
    </aside>
  );
}
