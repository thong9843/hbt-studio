import { useQuery } from '@tanstack/react-query';
import { api } from '../api/endpoints';

/** Danh sách clip nền của PostV (query chung `['backgrounds']`). */
export function useBackgrounds() {
  return useQuery({ queryKey: ['backgrounds'], queryFn: api.listBackgrounds });
}
