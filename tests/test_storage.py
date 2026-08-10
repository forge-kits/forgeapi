"""Tests for Storage facade and LocalDriver."""
import pytest
import tempfile
from pathlib import Path

from forgeapi.storage.drivers.local import LocalDriver
from forgeapi.storage.storage import _Storage


@pytest.fixture
def tmp_root(tmp_path):
    return str(tmp_path / "storage")


@pytest.fixture
def driver(tmp_root):
    return LocalDriver(root=tmp_root, base_url="/files")


@pytest.fixture
def storage(tmp_root):
    s = _Storage()
    s.configure(driver="local", root=tmp_root, base_url="/files")
    return s


# ---------------------------------------------------------------------------
# LocalDriver
# ---------------------------------------------------------------------------

class TestLocalDriver:
    @pytest.mark.anyio
    async def test_put_creates_file(self, driver, tmp_root):
        await driver.put("docs/hello.txt", b"hello")
        assert (Path(tmp_root) / "docs/hello.txt").exists()

    @pytest.mark.anyio
    async def test_put_creates_nested_dirs(self, driver, tmp_root):
        await driver.put("a/b/c/file.txt", b"x")
        assert (Path(tmp_root) / "a/b/c/file.txt").exists()

    @pytest.mark.anyio
    async def test_put_returns_path(self, driver):
        result = await driver.put("test.txt", b"data")
        assert result == "test.txt"

    @pytest.mark.anyio
    async def test_get_returns_bytes(self, driver):
        await driver.put("hello.txt", b"world")
        data = await driver.get("hello.txt")
        assert data == b"world"

    @pytest.mark.anyio
    async def test_exists_true(self, driver):
        await driver.put("x.txt", b"1")
        assert await driver.exists("x.txt") is True

    @pytest.mark.anyio
    async def test_exists_false(self, driver):
        assert await driver.exists("nonexistent.txt") is False

    @pytest.mark.anyio
    async def test_delete_removes_file(self, driver, tmp_root):
        await driver.put("bye.txt", b"bye")
        result = await driver.delete("bye.txt")
        assert result is True
        assert not (Path(tmp_root) / "bye.txt").exists()

    @pytest.mark.anyio
    async def test_delete_nonexistent_returns_false(self, driver):
        result = await driver.delete("ghost.txt")
        assert result is False

    @pytest.mark.anyio
    async def test_list_returns_files(self, driver):
        await driver.put("folder/a.txt", b"a")
        await driver.put("folder/b.txt", b"b")
        files = await driver.list("folder")
        assert sorted(files) == ["folder/a.txt", "folder/b.txt"]

    @pytest.mark.anyio
    async def test_list_empty_directory(self, driver):
        files = await driver.list("nothing")
        assert files == []

    def test_url_format(self, driver):
        assert driver.url("avatars/user.jpg") == "/files/avatars/user.jpg"


# ---------------------------------------------------------------------------
# _Storage facade
# ---------------------------------------------------------------------------

class TestStorageFacade:
    @pytest.mark.anyio
    async def test_put_and_get(self, storage):
        await storage.put("test.bin", b"\x00\x01\x02")
        assert await storage.get("test.bin") == b"\x00\x01\x02"

    @pytest.mark.anyio
    async def test_exists_and_missing(self, storage):
        await storage.put("exists.txt", b"yes")
        assert await storage.exists("exists.txt") is True
        assert await storage.missing("exists.txt") is False
        assert await storage.missing("nope.txt") is True

    @pytest.mark.anyio
    async def test_delete(self, storage):
        await storage.put("del.txt", b"bye")
        assert await storage.delete("del.txt") is True
        assert await storage.exists("del.txt") is False

    @pytest.mark.anyio
    async def test_list(self, storage):
        await storage.put("dir/one.txt", b"1")
        await storage.put("dir/two.txt", b"2")
        files = await storage.list("dir")
        assert len(files) == 2

    def test_url(self, storage):
        assert storage.url("img.png") == "/files/img.png"

    def test_disk_unknown_raises(self, storage):
        with pytest.raises(KeyError, match="'unknown'"):
            storage.disk("unknown")

    @pytest.mark.anyio
    async def test_add_disk_and_use(self, storage, tmp_root):
        second = LocalDriver(root=tmp_root + "/second", base_url="/cdn")
        storage.add_disk("cdn", second)
        await storage.disk("cdn").put("file.txt", b"cdn")
        data = await storage.disk("cdn").get("file.txt")
        assert data == b"cdn"

    def test_default_driver_is_local_if_unconfigured(self, tmp_root):
        s = _Storage()
        assert s._backend is not None  # auto-creates LocalDriver

    def test_unknown_driver_raises(self):
        s = _Storage()
        with pytest.raises(ValueError, match="Unknown storage driver"):
            s.configure(driver="ftp")
