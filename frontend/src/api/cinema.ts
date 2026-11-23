import { apiGet, apiRequest } from './client';
import type {
  CinemaContactSheetResponse,
  CinemaHardwareProfile,
  CinemaPreflightReport,
  CinemaRenderBeatResponse,
  HbtCoreScript,
  StickvAspect,
  StickvProject,
  StickvTheme,
} from './types';

export interface CinemaSourcePayload {
  stickv_project?: StickvProject;
  stickv_slug?: string;
  core_script?: HbtCoreScript;
  aspect?: StickvAspect;
  fps?: number;
  theme?: StickvTheme;
}

export const cinemaApi = {
  getHardware: () => apiGet<CinemaHardwareProfile>('/cinema/hardware'),

  runPreflight: (payload: CinemaSourcePayload & { auto_fix?: boolean }) =>
    apiRequest<CinemaPreflightReport>('POST', '/cinema/preflight', { json: payload }),

  generateContactSheet: (
    payload: CinemaSourcePayload & { cols?: number; run_preflight?: boolean },
  ) => apiRequest<CinemaContactSheetResponse>('POST', '/cinema/contact-sheet', { json: payload }),

  renderBeat: (
    payload: CinemaSourcePayload & {
      beat_id?: string;
      beat_index?: number;
      preview?: boolean;
    },
  ) => apiRequest<CinemaRenderBeatResponse>('POST', '/cinema/render-beat', { json: payload }),
};
