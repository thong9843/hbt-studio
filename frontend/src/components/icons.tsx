import type { ReactNode, SVGProps } from 'react';

/** Biểu tượng nét 1.8, 20 px (kiểu đường nét đơn giản, vẽ riêng cho HBT Studio; không dùng emoji). */
function Icon({ children, size = 20, ...rest }: SVGProps<SVGSVGElement> & { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...rest}
    >
      {children}
    </svg>
  );
}

type P = SVGProps<SVGSVGElement> & { size?: number };
const make = (body: ReactNode) =>
  function Glyph(props: P) {
    return <Icon {...props}>{body}</Icon>;
  };

export const GripIcon = make(
  <>
    <circle cx="9" cy="6" r="1" />
    <circle cx="15" cy="6" r="1" />
    <circle cx="9" cy="12" r="1" />
    <circle cx="15" cy="12" r="1" />
    <circle cx="9" cy="18" r="1" />
    <circle cx="15" cy="18" r="1" />
  </>,
);
export const ArrowLeftIcon = make(<path d="M19 12H5m6-6-6 6 6 6" />);
export const PlusIcon = make(<path d="M12 5v14M5 12h14" />);
export const TrashIcon = make(<path d="M4 7h16M10 11v6m4-6v6M6 7l1 13h10l1-13M9 7V4h6v3" />);
export const XIcon = make(<path d="M6 6l12 12M18 6 6 18" />);
export const CheckIcon = make(<path d="M5 12.5 10 17.5 19 7" />);
export const AlertIcon = make(
  <>
    <path d="M12 3 2 20h20L12 3Z" />
    <path d="M12 10v4m0 3h.01" />
  </>,
);
export const PlayIcon = make(<path d="M7 4.5v15l12-7.5-12-7.5Z" />);
export const StopIcon = make(<rect x="6" y="6" width="12" height="12" rx="1" />);
export const CopyIcon = make(
  <>
    <rect x="9" y="9" width="11" height="11" rx="2" />
    <path d="M5 15V6a2 2 0 0 1 2-2h8" />
  </>,
);
export const DownloadIcon = make(<path d="M12 4v11m-5-4 5 5 5-5M5 20h14" />);
export const ImageIcon = make(
  <>
    <rect x="3" y="4" width="18" height="16" rx="2" />
    <circle cx="9" cy="10" r="1.5" />
    <path d="m21 16-5-5-9 9" />
  </>,
);
export const EyeIcon = make(
  <>
    <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z" />
    <circle cx="12" cy="12" r="3" />
  </>,
);

// Biểu tượng thanh trái (Đợt 2)
export const ChatIcon = make(<path d="M4 5h16v11H10l-6 4V5Zm4 4h8m-8 3h5" />);
export const HomeIcon = make(<path d="M4 11 12 4l8 7v9h-5v-6H9v6H4v-9Z" />);
export const FolderIcon = make(
  <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z" />,
);
export const FilmIcon = make(
  <>
    <rect x="3" y="4" width="18" height="16" rx="2" />
    <path d="M7 4v16M17 4v16M3 9h4m10 0h4M3 15h4m10 0h4" />
  </>,
);
export const MusicIcon = make(
  <>
    <path d="M9 18V6l10-2v12" />
    <circle cx="7" cy="18" r="2" />
    <circle cx="17" cy="16" r="2" />
  </>,
);
export const UploadIcon = make(<path d="M12 16V5m-5 4 5-5 5 5M5 20h14" />);
export const SettingsIcon = make(
  <>
    <circle cx="12" cy="12" r="3" />
    <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1Z" />
  </>,
);
export const MoreIcon = make(
  <>
    <circle cx="5" cy="12" r="1.2" />
    <circle cx="12" cy="12" r="1.2" />
    <circle cx="19" cy="12" r="1.2" />
  </>,
);
export const SunIcon = make(
  <>
    <circle cx="12" cy="12" r="4.5" />
    <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
  </>,
);
export const MoonIcon = make(
  <>
    <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79Z" />
    <path d="M17.5 4.5v2M16.5 5.5h2" />
  </>,
);
export const PanelLeftCloseIcon = make(
  <>
    <rect x="3" y="3" width="18" height="18" rx="2" />
    <path d="M9 3v18M16 15l-3-3 3-3" />
  </>,
);
export const PanelLeftOpenIcon = make(
  <>
    <rect x="3" y="3" width="18" height="18" rx="2" />
    <path d="M9 3v18M13 9l3 3-3 3" />
  </>,
);
export const ChevronDownIcon = make(<path d="m6 9 6 6 6-6" />);
export const EditIcon = make(
  <>
    <path d="M12 20h9" />
    <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5Z" />
  </>,
);
export const MessagesSquareIcon = make(
  <>
    <path d="M14 9a2 2 0 0 1-2 2H6l-4 4V4c0-1.1.9-2 2-2h8a2 2 0 0 1 2 2z" />
    <path d="M18 9h2a2 2 0 0 1 2 2v11l-4-4h-6a2 2 0 0 1-2-2v-1" />
  </>,
);
export const ZapIcon = make(<path d="M13 2 3 14h9l-1 8 10-12h-9l1-8Z" />);
export const SmartphoneIcon = make(
  <>
    <rect x="6" y="2" width="12" height="20" rx="2.5" />
    <path d="M12 18h.01" />
  </>,
);
export const SparklesIcon = make(
  <>
    <path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3L12 3Z" />
    <path d="M5 3v4M3 5h4M19 17v4M17 19h4" />
  </>,
);
export const CpuIcon = make(
  <>
    <rect x="6" y="6" width="12" height="12" rx="2" />
    <rect x="9" y="9" width="6" height="6" rx="1" />
    <path d="M9 2v4m6-4v4M9 18v4m6-4v4M2 9h4m-4 6h4m12-6h4m-4 6h4" />
  </>,
);
export const SearchIcon = make(
  <>
    <circle cx="11" cy="11" r="7" />
    <path d="m21 21-4.3-4.3" />
  </>,
);
