import { createContext, useContext } from 'react';

export interface ToastApi {
  info: (message: string) => void;
  /** Lỗi API/mạng: hiện thông báo kèm gợi ý; có `retry` thì thêm nút "Thử lại". */
  error: (error: unknown, retry?: () => void) => void;
}

const noop: ToastApi = { info: () => {}, error: () => {} };

export const ToastContext = createContext<ToastApi>(noop);

export const useToast = () => useContext(ToastContext);
