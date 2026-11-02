import { useQuery } from '@tanstack/react-query';
import { api } from '../api/endpoints';

/** Dự án có bản nháp GĐ2 không. Không sinh lỗi khi không có (API luôn 200). */
export function useDraftState(slug: string | undefined) {
  const { data, isSuccess } = useQuery({
    queryKey: ['draft-exists', slug],
    queryFn: () => api.draftExists(slug as string),
    enabled: Boolean(slug),
    staleTime: 30_000,
    retry: false,
  });
  return { exists: data?.exists === true, loaded: isSuccess };
}

/** Như `useDraftState`, chỉ trả có / không (chưa biết thì coi như không). */
export function useDraftExists(slug: string | undefined) {
  return useDraftState(slug).exists;
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
