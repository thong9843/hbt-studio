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

/** Tiến độ dựng đang chạy, do AppLayout / AppShell truyền vào. */
export interface RenderProgress {
  percent: number;
  step: string;
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

/**
 * Sidebar thống nhất (Navigation Shell):
 * - Có nút Mở rộng (224px) / Thu gọn (64px) rõ ràng ngay ở đầu thanh, lưu vào localStorage, hoạt động trên mọi trang.
 * - Chân Sidebar phân biệt sắc nét icon Bánh răng (Cài đặt) và Mặt trăng / Mặt trời (Sáng/Tối).
 */
export function Sidebar({ mini, onToggleMini, render }: SidebarProps) {
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
            <div className="min-w-0">
              <span className="block truncate text-body font-extrabold tracking-tight">
                {vi.appName}
              </span>
              <span className="block truncate text-[11px] font-semibold text-muted">
                Creator Workstation
              </span>
            </div>
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

      {render && <RenderCard render={render} mini={mini} />}
      <div className="space-y-1 border-t border-line py-2">
        <NavItem to="/settings" icon={<SettingsIcon />} label={vi.nav.settings} mini={mini} />
        <ThemeToggle mini={mini} />
      </div>
      <Environment mini={mini} />
      <QuickCreateDrawer open={quickOpen} onClose={() => setQuickOpen(false)} />
    </aside>
  );
}
