import { useQuery } from '@tanstack/react-query';
import { api } from '../api/endpoints';

/** Dự án có bản nháp GĐ2 không. Không sinh lỗi khi không có (API luôn 200). */
export function useDraftExists(slug: string | undefined) {
  const { data } = useQuery({
    queryKey: ['draft-exists', slug],
    queryFn: () => api.draftExists(slug as string),
    enabled: Boolean(slug),
    staleTime: 30_000,
    retry: false,
  });
  return data?.exists === true;
}

/** Bản nháp kèm trạng thái duyệt ảnh. Chỉ gọi khi đã biết dự án có nháp. */
export function useDraft(slug: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: ['draft', slug],
    queryFn: () => api.getDraft(slug as string),
    enabled: Boolean(slug) && enabled,
    retry: false,
  });
}
