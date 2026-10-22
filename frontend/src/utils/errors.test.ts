import { describe, expect, it } from 'vitest';
import { ApiError } from '../api/client';
import { describeError, errorHint } from './errors';

describe('error hints', () => {
  it('suggests a fix per status code', () => {
    expect(errorHint(new ApiError(503, 'x'))).toMatch(/FFmpeg/);
    expect(errorHint(new ApiError(409, 'x'))).toMatch(/dựng/);
    expect(errorHint(new ApiError(413, 'x'))).toMatch(/lớn/);
    expect(errorHint(new ApiError(404, 'x'))).toMatch(/Không tìm thấy/);
    expect(errorHint(new ApiError(422, 'x'))).toMatch(/hợp lệ/);
    expect(errorHint(new ApiError(500, 'x'))).toBeNull();
  });

  it('tells the user to start the dev server when fetch cannot connect', () => {
    const d = describeError(new TypeError('Failed to fetch'));
    expect(d.message).toMatch(/npm run dev/);
  });

  it('passes the API message through', () => {
    expect(describeError(new ApiError(409, 'Project đang được dựng')).message).toBe(
      'Project đang được dựng',
    );
  });
});
