"""DELETE /projects/{slug}/renders/{job_id}: xoá một lần xuất (Đợt 5, 13.B13)."""

import pytest

from tests.test_api import (
    FakeRender,
    client,  # noqa: F401
    complete_project,
)
from tests.test_project_summary import make_render, new_project, summary


def url(slug, job_id):
    return f"/api/projects/{slug}/renders/{job_id}"


def test_delete_removes_the_whole_render_folder_only(client):  # noqa: F811
    slug, folder = new_project(client)
    make_render(folder, "aaaa11112222", "2026-10-01T10:00:00Z", cover=True)
    make_render(folder, "bbbb11112222", "2026-10-02T10:00:00Z")
    (folder / "renders" / "aaaa11112222" / "publish.txt").write_text("x", encoding="utf-8")
    (folder / "build").mkdir()
    (folder / "build" / "timing.json").write_text("{}", encoding="utf-8")
    (folder / "backups").mkdir()
    (folder / "backups" / "b1.json").write_text("{}", encoding="utf-8")

    assert client.delete(url(slug, "aaaa11112222")).status_code == 204

    assert not (folder / "renders" / "aaaa11112222").exists()
    assert (folder / "renders" / "bbbb11112222" / "video.mp4").is_file()
    assert (folder / "build" / "timing.json").is_file()
    assert (folder / "backups" / "b1.json").is_file()
    assert [r["job_id"] for r in client.get(f"/api/projects/{slug}/renders").json()] == [
        "bbbb11112222"
    ]
    assert list((folder / "renders").glob(".deleting-*")) == []


def test_cli_style_job_ids_can_be_deleted(client):  # noqa: F811
    slug, folder = new_project(client)
    make_render(folder, "20261026-103538-preview", "2026-10-01T10:00:00Z", preview=True)
    assert client.delete(url(slug, "20261026-103538-preview")).status_code == 204
    assert not (folder / "renders" / "20261026-103538-preview").exists()


def test_unknown_render_and_unknown_project_are_404(client):  # noqa: F811
    slug, _ = new_project(client)
    assert client.delete(url(slug, "khongco123456")).status_code == 404
    assert client.delete(url("khong-co", "aaaa11112222")).status_code == 404


# ".." trần bị client HTTP gộp thành /projects/{slug} trước khi tới máy chủ nên không đưa vào
# đây (test_storage_blocks_traversal_and_symlink_escape kiểm trực tiếp).
@pytest.mark.parametrize(
    "job_id",
    ["%2e%2e", "..%2fbuild", "a%2f..%2f..%2fbuild", "a.b", "-x", "a" * 65, "a%5c..%5cbuild"],
)
def test_bad_job_ids_are_blocked_and_nothing_is_deleted(client, job_id):  # noqa: F811
    slug, folder = new_project(client)
    make_render(folder, "aaaa11112222", "2026-10-01T10:00:00Z")
    (folder / "build").mkdir()
    (folder / "build" / "timing.json").write_text("{}", encoding="utf-8")
    r = client.delete(url(slug, job_id))
    assert r.status_code in (404, 422)
    assert (folder / "build" / "timing.json").is_file()
    assert (folder / "renders" / "aaaa11112222" / "video.mp4").is_file()
    assert (folder / "project.json").is_file()


def test_storage_blocks_traversal_and_symlink_escape(client, tmp_path):  # noqa: F811
    from hbt.storage import Unprocessable

    slug, folder = new_project(client)
    storage = client.app.state.hbt.storage
    for bad in ("..", "../build", "a/b", ".", ""):
        with pytest.raises(Unprocessable):
            storage.delete_render(slug, bad)
    assert (folder / "project.json").is_file()


def test_running_or_queued_job_is_409(client):  # noqa: F811
    fake = FakeRender()
    client.app.state.hbt.jobs._render = fake
    client.app.state.hbt.jobs._tool_check = None
    slug = complete_project(client)
    a = client.post(f"/api/projects/{slug}/render", json={"preview": True}).json()["job_id"]
    assert fake.started.wait(5)
    b = client.post(f"/api/projects/{slug}/render").json()["job_id"]
    folder = client.app.state.hbt.storage.project_dir(slug)
    make_render(folder, a, "2026-10-01T10:00:00Z", preview=True)  # thư mục đã có file của job a
    make_render(folder, b, "2026-10-02T10:00:00Z")

    for job_id in (a, b):  # đang chạy / đang chờ
        r = client.delete(url(slug, job_id))
        assert r.status_code == 409 and "đang dựng" in r.json()["detail"]
        assert (folder / "renders" / job_id / "video.mp4").is_file()
    client.post(f"/api/jobs/{b}/cancel")
    client.post(f"/api/jobs/{a}/cancel")


def test_locked_files_give_409_and_leave_the_folder_untouched(client, monkeypatch):  # noqa: F811
    from pathlib import Path

    slug, folder = new_project(client)
    make_render(folder, "aaaa11112222", "2026-10-01T10:00:00Z", cover=True)
    real = Path.rename

    def locked(self, target):
        if self.name == "aaaa11112222":
            raise PermissionError(32, "The process cannot access the file")
        return real(self, target)

    monkeypatch.setattr(Path, "rename", locked)
    r = client.delete(url(slug, "aaaa11112222"))
    assert r.status_code == 409 and "đang mở" in r.json()["detail"]
    assert (folder / "renders" / "aaaa11112222" / "video.mp4").is_file()
    assert (folder / "renders" / "aaaa11112222" / "cover_9x16.jpg").is_file()


def test_last_final_and_cover_are_recomputed_after_delete(client):  # noqa: F811
    slug, folder = new_project(client)
    make_render(folder, "old111111111", "2026-10-01T10:00:00Z", cover=True)
    make_render(folder, "new222222222", "2026-10-02T10:00:00Z", cover=True)
    make_render(folder, "prev33333333", "2026-10-03T10:00:00Z", preview=True)
    item = summary(client, slug)
    assert item["last_final"]["job_id"] == "new222222222"
    assert item["cover"].endswith("renders/new222222222/cover_9x16.jpg")

    assert client.delete(url(slug, "new222222222")).status_code == 204
    item = summary(client, slug)
    assert item["last_final"]["job_id"] == "old111111111"
    assert item["cover"].endswith("renders/old111111111/cover_9x16.jpg")
    assert item["last_render"]["job_id"] == "prev33333333"

    assert client.delete(url(slug, "old111111111")).status_code == 204
    item = summary(client, slug)
    assert item["last_final"] is None and item["cover"] is None
    assert item["last_render"]["job_id"] == "prev33333333"
