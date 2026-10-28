import { createContext, useContext } from 'react';

export interface InfoOptions {
  /** Có `undo` thì thông báo hiện nút "Hoàn tác" và ở lại 8 giây thay vì 3. */
  undo?: () => void;
}

export interface ToastApi {
  info: (message: string, options?: InfoOptions) => void;
  /** Lỗi API/mạng: hiện thông báo kèm gợi ý; có `retry` thì thêm nút "Thử lại". */
  error: (error: unknown, retry?: () => void) => void;
}

const noop: ToastApi = { info: () => {}, error: () => {} };

export const ToastContext = createContext<ToastApi>(noop);

export const useToast = () => useContext(ToastContext);
