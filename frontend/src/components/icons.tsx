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
