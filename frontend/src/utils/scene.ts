/**
 * Chuyển đổi giữa hai cách đánh số cảnh. Đây là NƠI DUY NHẤT trong giao diện làm việc này.
 *
 * - API dùng **chỉ số từ 0** (`scene_index`, `scenes[i]`, `/scenes/{scene_index}/preview.png`).
 * - Người dùng thấy **số thứ tự từ 1** ("Cảnh 1"…), cũng như `thumbnail.scene` trong project.json.
 * - Tên file ảnh trên đĩa là `scene-01…` (số thứ tự từ 1); do backend đặt, giao diện không tự ghép.
 */

function assertInteger(value: number, name: string): void {
  if (!Number.isInteger(value)) throw new RangeError(`${name} phải là số nguyên, nhận ${value}`);
}

/** Chỉ số của API (từ 0) → số hiển thị cho người dùng (từ 1). */
export function sceneNumber(sceneIndex: number): number {
  assertInteger(sceneIndex, 'scene_index');
  if (sceneIndex < 0) throw new RangeError(`scene_index không được âm, nhận ${sceneIndex}`);
  return sceneIndex + 1;
}

/** Số hiển thị / nhập bởi người dùng (từ 1) → chỉ số gửi cho API (từ 0). */
export function sceneIndex(sceneNumberFromUser: number): number {
  assertInteger(sceneNumberFromUser, 'số cảnh');
  if (sceneNumberFromUser < 1) {
    throw new RangeError(`số cảnh phải từ 1 trở lên, nhận ${sceneNumberFromUser}`);
  }
  return sceneNumberFromUser - 1;
}
