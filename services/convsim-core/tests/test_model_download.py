# SPDX-License-Identifier: Apache-2.0
"""Tests for model download service: SHA-256 verification and download lifecycle."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

import convsim_core.runtime  # noqa: F401 — register built-in adapters
from convsim_core.app import create_app
from convsim_core.config import ServiceConfig
from convsim_core.services.model_download_service import (
    ERROR_CODE_CHECKSUM,
    ERROR_CODE_HTTP,
    ERROR_CODE_NETWORK,
    ERROR_CODE_UNKNOWN,
    classify_download_error,
    execute_download,
    verify_sha256,
)
from convsim_core.services.model_manager_service import (
    create_install_record,
    get_install_record,
    mark_install_ready,
)
from convsim_core.storage.database import Database


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def db(tmp_path):
    database = Database.open(str(tmp_path / "db"))
    yield database
    database.close()


@pytest.fixture()
def tmp_config(tmp_path):
    return ServiceConfig(
        host="127.0.0.1",
        port=7355,
        data_dir=str(tmp_path / "data"),
        log_dir=str(tmp_path / "logs"),
        db_dir=str(tmp_path / "db"),
        models_dir=str(tmp_path / "models"),
    )


@pytest.fixture()
def client(tmp_config):
    app = create_app(tmp_config)
    with TestClient(app) as c:
        yield c


def _insert_registry_model(conn, model_id: str, sha256: str = "a" * 64) -> None:
    conn.execute(
        """INSERT OR IGNORE INTO model_registry
           (id, name, provider, license_spdx, sha256, source_type)
           VALUES (?, ?, 'test', 'MIT', ?, 'registry')""",
        (model_id, model_id, sha256),
    )
    conn.commit()


def _sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ── verify_sha256: unit tests ─────────────────────────────────────────────────


def test_verify_sha256_passes_for_correct_checksum(tmp_path):
    data = b"hello model weights"
    f = tmp_path / "model.gguf"
    f.write_bytes(data)
    assert verify_sha256(f, _sha256_of(data)) is True


def test_verify_sha256_fails_for_wrong_checksum(tmp_path):
    data = b"correct content"
    f = tmp_path / "model.gguf"
    f.write_bytes(data)
    assert verify_sha256(f, "a" * 64) is False


def test_verify_sha256_case_insensitive(tmp_path):
    data = b"case test"
    f = tmp_path / "model.gguf"
    f.write_bytes(data)
    correct = _sha256_of(data).upper()
    assert verify_sha256(f, correct) is True


def test_verify_sha256_empty_file(tmp_path):
    f = tmp_path / "empty.gguf"
    f.write_bytes(b"")
    expected = hashlib.sha256(b"").hexdigest()
    assert verify_sha256(f, expected) is True


def test_verify_sha256_large_file(tmp_path):
    data = b"x" * (3 * 65_536 + 17)  # spans multiple 64 KB chunks
    f = tmp_path / "big.gguf"
    f.write_bytes(data)
    assert verify_sha256(f, _sha256_of(data)) is True
    assert verify_sha256(f, "0" * 64) is False


# ── classify_download_error: the machine-readable kind next to the message ────


def _http_status_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "http://example.test/model.gguf")
    response = httpx.Response(status, request=request)
    return httpx.HTTPStatusError(f"HTTP {status}", request=request, response=response)


# Every httpx transport error. The classifier counts each one as a network
# failure: a connection, DNS, timeout or protocol failure between the engine
# and the download server.
_NETWORK_ERRORS = [
    httpx.ConnectError("All connection attempts failed"),   # refused connection
    httpx.ConnectError("[Errno -2] Name or service not known"),  # DNS failure
    httpx.ConnectTimeout(""),
    httpx.ReadTimeout(""),
    httpx.WriteTimeout(""),
    httpx.PoolTimeout(""),
    httpx.ReadError(""),
    httpx.WriteError(""),
    httpx.CloseError(""),
    httpx.RemoteProtocolError("peer closed connection without sending complete message body"),
    httpx.LocalProtocolError(""),
    httpx.ProxyError(""),
    httpx.UnsupportedProtocol(""),
]

# Every other httpx exception. None of them is a lost connection, so each is
# UNKNOWN and keeps httpx's own text. The first three reach execute_download:
# a redirect loop, a body that does not decode as its Content-Encoding says,
# and a registry URL httpx cannot parse. The rest mean the code misused the
# httpx API, which is a bug.
_UNKNOWN_HTTPX_ERRORS = [
    httpx.TooManyRedirects("Exceeded maximum allowed redirects."),
    httpx.DecodingError("Error -3 while decompressing data: incorrect header check"),
    httpx.InvalidURL("Invalid port: ':1'"),
    httpx.CookieConflict("Multiple cookies exist with name=session"),
    httpx.StreamConsumed(),
    httpx.StreamClosed(),
    httpx.ResponseNotRead(),
    httpx.RequestNotRead(),
]

_HTTP_STATUSES = [403, 404, 429, 500, 503]


def _concrete_httpx_exception_classes() -> set[type[BaseException]]:
    """Every exception class the installed httpx exports that has no subclass there."""
    classes = {
        obj
        for obj in vars(httpx).values()
        if isinstance(obj, type) and issubclass(obj, BaseException)
    }
    return {c for c in classes if not any(o is not c and issubclass(o, c) for o in classes)}


def test_every_concrete_httpx_exception_class_has_a_case_below():
    # Each exception class httpx exports, under httpx.HTTPError or not, must
    # appear in one of the case lists above, so its classification is asserted.
    # If httpx adds a class, or a case is dropped from a list, this fails.
    #
    # Parent classes (HTTPError, RequestError, TransportError, NetworkError,
    # TimeoutException, ProtocolError, StreamError) are left out because httpx
    # raises their subclasses. The one exception is ProtocolError, which httpx
    # raises itself only from digest authentication, and the download sends no
    # credentials.
    covered = {type(e) for e in _NETWORK_ERRORS + _UNKNOWN_HTTPX_ERRORS}
    covered |= {type(_http_status_error(status)) for status in _HTTP_STATUSES}
    assert {c.__name__ for c in _concrete_httpx_exception_classes()} == {
        c.__name__ for c in covered
    }


@pytest.mark.parametrize(
    "exc",
    _NETWORK_ERRORS,
    ids=lambda e: type(e).__name__ + (f":{e}" if str(e) else ""),
)
def test_classify_transport_errors_as_network(exc):
    code, message = classify_download_error(exc)
    assert code == ERROR_CODE_NETWORK
    assert message.strip(), "a network failure must carry a human-readable message"


def test_classify_read_timeout_has_a_message_although_httpx_renders_none():
    exc = httpx.ReadTimeout("")
    assert str(exc) == ""  # what the service used to record verbatim
    code, message = classify_download_error(exc)
    assert code == ERROR_CODE_NETWORK
    assert message == "The download timed out waiting for the server."


def test_classify_names_the_failure_and_keeps_httpx_detail():
    code, message = classify_download_error(
        httpx.ConnectError("[Errno -2] Name or service not known")
    )
    assert code == ERROR_CODE_NETWORK
    assert message == (
        "Could not connect to the download server. ([Errno -2] Name or service not known)"
    )


@pytest.mark.parametrize("status", _HTTP_STATUSES)
def test_classify_http_status_errors_are_not_network(status):
    code, message = classify_download_error(_http_status_error(status))
    assert code == ERROR_CODE_HTTP
    assert f"HTTP {status}" in message


def test_classify_follows_an_explicit_cause_and_keeps_the_wrapper_message():
    # The engine download wraps a lost connection in a RuntimeError of its own.
    wrapper = "Cannot reach GitHub to fetch the latest release. Check your internet connection."
    try:
        try:
            raise httpx.ConnectError("All connection attempts failed")
        except httpx.ConnectError as inner:
            raise RuntimeError(wrapper) from inner
    except RuntimeError as exc:
        code, message = classify_download_error(exc)
    assert code == ERROR_CODE_NETWORK
    assert message == wrapper


def test_classify_does_not_follow_an_implicit_context():
    # An error raised while handling a network error, without `from`, is not
    # itself a network failure.
    try:
        try:
            raise httpx.ReadTimeout("")
        except httpx.ReadTimeout:
            raise ValueError("bad bookkeeping")
    except ValueError as exc:
        code, _ = classify_download_error(exc)
    assert code == ERROR_CODE_UNKNOWN


def test_classify_other_exceptions_are_unknown_with_a_message():
    code, message = classify_download_error(OSError(28, "No space left on device"))
    assert code == ERROR_CODE_UNKNOWN
    assert message == "[Errno 28] No space left on device"

    code, message = classify_download_error(RuntimeError(""))
    assert code == ERROR_CODE_UNKNOWN
    assert message == "Download failed (RuntimeError)."


@pytest.mark.parametrize("exc", _UNKNOWN_HTTPX_ERRORS, ids=lambda e: type(e).__name__)
def test_classify_other_httpx_errors_are_unknown_and_keep_their_text(exc):
    code, message = classify_download_error(exc)
    assert code == ERROR_CODE_UNKNOWN
    assert message.strip()
    assert message == str(exc)


@pytest.mark.parametrize("cls", [httpx.DecodingError, httpx.TooManyRedirects])
def test_classify_unknown_httpx_error_without_text_names_its_class(cls):
    code, message = classify_download_error(cls(""))
    assert code == ERROR_CODE_UNKNOWN
    assert message == f"Download failed ({cls.__name__})."


def _make_failing_client(exc: BaseException) -> httpx.AsyncClient:
    """A mock client whose stream() raises *exc* on entry, like a transport failure."""
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(side_effect=exc)
    mock_cm.__aexit__ = AsyncMock(return_value=None)
    mock_client = MagicMock(spec=httpx.AsyncClient)
    mock_client.stream = MagicMock(return_value=mock_cm)
    mock_client.aclose = AsyncMock()
    return mock_client


@pytest.mark.asyncio
async def test_execute_download_records_network_code_and_message_on_read_timeout(db, tmp_path):
    conn = db.connection()
    install_id = create_install_record(conn, None, "test.gguf", "")

    await execute_download(
        conn,
        install_id,
        "http://slow.test/model.gguf",
        "a" * 64,
        tmp_path / "models",
        "test.gguf",
        _client=_make_failing_client(httpx.ReadTimeout("")),
    )

    record = get_install_record(conn, install_id)
    assert record["install_status"] == "failed"
    assert record["error_code"] == ERROR_CODE_NETWORK
    assert record["error_message"], "a ReadTimeout must not leave the message empty"


@pytest.mark.asyncio
async def test_execute_download_records_http_code_on_status_error(db, tmp_path):
    conn = db.connection()
    install_id = create_install_record(conn, None, "test.gguf", "")

    mock_client = _make_mock_client(b"unused")
    response = mock_client.stream.return_value.__aenter__.return_value
    response.raise_for_status = MagicMock(side_effect=_http_status_error(404))

    await execute_download(
        conn,
        install_id,
        "http://example.test/missing.gguf",
        "a" * 64,
        tmp_path / "models",
        "test.gguf",
        _client=mock_client,
    )

    record = get_install_record(conn, install_id)
    assert record["install_status"] == "failed"
    assert record["error_code"] == ERROR_CODE_HTTP
    assert record["error_message"]


@pytest.mark.asyncio
async def test_execute_download_records_unknown_code_on_a_disk_error(db, tmp_path):
    conn = db.connection()
    install_id = create_install_record(conn, None, "test.gguf", "")

    with patch(
        "convsim_core.services.model_download_service.open",
        side_effect=OSError(28, "No space left on device"),
        create=True,
    ):
        await execute_download(
            conn,
            install_id,
            "http://example.test/model.gguf",
            "a" * 64,
            tmp_path / "models",
            "test.gguf",
            _client=_make_mock_client(b"weights"),
        )

    record = get_install_record(conn, install_id)
    assert record["install_status"] == "failed"
    assert record["error_code"] == ERROR_CODE_UNKNOWN
    assert record["error_message"] == "[Errno 28] No space left on device"


@pytest.mark.asyncio
async def test_execute_download_records_checksum_code_on_mismatch(db, tmp_path):
    conn = db.connection()
    install_id = create_install_record(conn, None, "test.gguf", "")

    await execute_download(
        conn,
        install_id,
        "http://example.test/model.gguf",
        "b" * 64,
        tmp_path / "models",
        "test.gguf",
        _client=_make_mock_client(b"corrupted download"),
    )

    record = get_install_record(conn, install_id)
    assert record["install_status"] == "checksum_mismatch"
    assert record["error_code"] == ERROR_CODE_CHECKSUM


@pytest.mark.asyncio
async def test_execute_download_success_leaves_no_error_code(db, tmp_path):
    content = b"fake gguf weights"
    conn = db.connection()
    install_id = create_install_record(conn, None, "test.gguf", "")

    await execute_download(
        conn,
        install_id,
        "http://example.test/model.gguf",
        _sha256_of(content),
        tmp_path / "models",
        "test.gguf",
        _client=_make_mock_client(content),
    )

    record = get_install_record(conn, install_id)
    assert record["install_status"] == "ready"
    assert record["error_code"] is None


# ── execute_download against real sockets: the exceptions httpx really raises ─
#
# The mocks above hand-pick an exception. These run the real httpx transport
# against local sockets, so the classes and texts are the ones a player's
# failed download produces ("All connection attempts failed", an empty
# ReadTimeout, a body cut short), not the ones a test author expects.


def _closed_port() -> int:
    """A local port nothing listens on, so a connection to it is refused."""
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextlib.asynccontextmanager
async def _serve(handler):
    """Run *handler* as a local HTTP server and yield its base URL."""
    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.close()
        await server.wait_closed()


async def _download_from(conn, install_id, url, tmp_path, timeout=2.0):
    # trust_env=False: the test talks to 127.0.0.1 directly, never via a proxy.
    # follow_redirects=True: as the client execute_download makes for itself.
    async with httpx.AsyncClient(
        trust_env=False, follow_redirects=True, timeout=timeout
    ) as client:
        await execute_download(
            conn, install_id, url, "a" * 64, tmp_path / "models", "test.gguf",
            _client=client,
        )
    return get_install_record(conn, install_id)


@pytest.mark.asyncio
async def test_real_refused_connection_is_recorded_as_network(db, tmp_path):
    conn = db.connection()
    install_id = create_install_record(conn, None, "test.gguf", "")

    record = await _download_from(
        conn, install_id, f"http://127.0.0.1:{_closed_port()}/model.gguf", tmp_path
    )

    assert record["install_status"] == "failed"
    assert record["error_code"] == ERROR_CODE_NETWORK
    assert record["error_message"].startswith("Could not connect to the download server.")
    assert not (tmp_path / "models" / "test.gguf.part").exists()


@pytest.mark.asyncio
async def test_real_read_timeout_is_recorded_as_network_with_a_message(db, tmp_path):
    conn = db.connection()
    install_id = create_install_record(conn, None, "test.gguf", "")

    # Accept the request and never answer it: httpx raises ReadTimeout(""). The
    # handler returns when the client gives up and closes the connection.
    async def _silent(reader, writer):
        await reader.read()
        writer.close()

    async with _serve(_silent) as base:
        record = await _download_from(
            conn, install_id, f"{base}/model.gguf", tmp_path, timeout=0.3
        )

    assert record["install_status"] == "failed"
    assert record["error_code"] == ERROR_CODE_NETWORK
    assert record["error_message"] == "The download timed out waiting for the server."


@pytest.mark.asyncio
async def test_real_connection_cut_mid_body_is_recorded_as_network(db, tmp_path):
    conn = db.connection()
    install_id = create_install_record(conn, None, "test.gguf", "")

    async def _cut(reader, writer):
        await reader.readuntil(b"\r\n\r\n")
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 100000\r\n\r\n" + b"x" * 100)
        await writer.drain()
        writer.close()

    async with _serve(_cut) as base:
        record = await _download_from(conn, install_id, f"{base}/model.gguf", tmp_path)

    assert record["install_status"] == "failed"
    assert record["error_code"] == ERROR_CODE_NETWORK
    assert record["error_message"].startswith(
        "The download stopped because of a network error."
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("status_line", [b"404 Not Found", b"503 Service Unavailable"])
async def test_real_http_error_status_is_recorded_as_http(db, tmp_path, status_line):
    conn = db.connection()
    install_id = create_install_record(conn, None, "test.gguf", "")

    async def _answer(reader, writer):
        await reader.readuntil(b"\r\n\r\n")
        writer.write(b"HTTP/1.1 " + status_line + b"\r\nContent-Length: 0\r\n\r\n")
        await writer.drain()
        writer.close()

    async with _serve(_answer) as base:
        record = await _download_from(conn, install_id, f"{base}/model.gguf", tmp_path)

    assert record["install_status"] == "failed"
    assert record["error_code"] == ERROR_CODE_HTTP
    assert f"HTTP {status_line.split()[0].decode()}" in record["error_message"]


@pytest.mark.asyncio
async def test_real_redirect_loop_is_recorded_as_unknown_with_httpx_text(db, tmp_path):
    conn = db.connection()
    install_id = create_install_record(conn, None, "test.gguf", "")

    # Answer every request with a redirect to the same path, on as many
    # requests as the client sends over the connection.
    async def _loop(reader, writer):
        with contextlib.suppress(asyncio.IncompleteReadError, ConnectionError):
            while True:
                await reader.readuntil(b"\r\n\r\n")
                writer.write(
                    b"HTTP/1.1 302 Found\r\nLocation: /model.gguf\r\n"
                    b"Content-Length: 0\r\n\r\n"
                )
                await writer.drain()
        writer.close()

    async with _serve(_loop) as base:
        record = await _download_from(conn, install_id, f"{base}/model.gguf", tmp_path)

    assert record["install_status"] == "failed"
    assert record["error_code"] == ERROR_CODE_UNKNOWN
    assert record["error_message"] == "Exceeded maximum allowed redirects."


@pytest.mark.asyncio
async def test_real_undecodable_body_is_recorded_as_unknown_with_httpx_text(db, tmp_path):
    conn = db.connection()
    install_id = create_install_record(conn, None, "test.gguf", "")

    # Claim a gzip body and send bytes that are not gzip: httpx raises
    # DecodingError while the body streams to the .part file.
    async def _not_gzip(reader, writer):
        await reader.readuntil(b"\r\n\r\n")
        body = b"these bytes are not gzip"
        writer.write(
            b"HTTP/1.1 200 OK\r\nContent-Encoding: gzip\r\n"
            b"Content-Length: %d\r\n\r\n" % len(body) + body
        )
        await writer.drain()
        writer.close()

    async with _serve(_not_gzip) as base:
        record = await _download_from(conn, install_id, f"{base}/model.gguf", tmp_path)

    assert record["install_status"] == "failed"
    assert record["error_code"] == ERROR_CODE_UNKNOWN
    assert record["error_message"].startswith("Error -3 while decompressing data")
    assert not (tmp_path / "models" / "test.gguf.part").exists()


# ── execute_download: mocked HTTP download ────────────────────────────────────


def _make_mock_client(content: bytes, content_length: bool = True) -> httpx.AsyncClient:
    """Return a mock httpx.AsyncClient that streams *content* from any GET request."""
    chunk_size = 1024

    async def _aiter_bytes(chunk_size=None):
        offset = 0
        while offset < len(content):
            yield content[offset : offset + (chunk_size or 65_536)]
            offset += chunk_size or 65_536

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.headers = (
        {"content-length": str(len(content))} if content_length else {}
    )
    mock_response.aiter_bytes = _aiter_bytes

    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_response)
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    mock_client = MagicMock(spec=httpx.AsyncClient)
    mock_client.stream = MagicMock(return_value=mock_cm)
    mock_client.aclose = AsyncMock()
    return mock_client


@pytest.mark.asyncio
async def test_execute_download_success(db, tmp_path):
    content = b"fake gguf weights"
    sha = _sha256_of(content)
    conn = db.connection()
    install_id = create_install_record(conn, None, "test.gguf", "")

    mock_client = _make_mock_client(content)
    dest_dir = tmp_path / "models"

    await execute_download(
        conn,
        install_id,
        "http://example.test/model.gguf",
        sha,
        dest_dir,
        "test.gguf",
        _client=mock_client,
    )

    record = get_install_record(conn, install_id)
    assert record is not None
    assert record["install_status"] == "ready"
    assert record["verified_sha256"] == sha
    assert record["size_bytes"] == len(content)
    assert (dest_dir / "test.gguf").exists()
    assert not (dest_dir / "test.gguf.part").exists()


@pytest.mark.asyncio
async def test_execute_download_checksum_mismatch(db, tmp_path):
    content = b"corrupted download"
    wrong_sha = "b" * 64
    conn = db.connection()
    install_id = create_install_record(conn, None, "test.gguf", "")
    dest_dir = tmp_path / "models"

    mock_client = _make_mock_client(content)

    await execute_download(
        conn,
        install_id,
        "http://example.test/model.gguf",
        wrong_sha,
        dest_dir,
        "test.gguf",
        _client=mock_client,
    )

    record = get_install_record(conn, install_id)
    assert record is not None
    assert record["install_status"] == "checksum_mismatch"
    assert "mismatch" in (record["error_message"] or "")
    # File must be deleted, not left on disk.
    assert not (dest_dir / "test.gguf").exists()
    assert not (dest_dir / "test.gguf.part").exists()


@pytest.mark.asyncio
async def test_execute_download_cancel(db, tmp_path):
    content = b"x" * 200_000
    sha = _sha256_of(content)
    conn = db.connection()
    install_id = create_install_record(conn, None, "test.gguf", "")
    dest_dir = tmp_path / "models"
    cancel_event = asyncio.Event()

    # Pre-set the event so the first chunk causes cancel.
    cancel_event.set()
    mock_client = _make_mock_client(content)

    await execute_download(
        conn,
        install_id,
        "http://example.test/model.gguf",
        sha,
        dest_dir,
        "test.gguf",
        cancel_event=cancel_event,
        _client=mock_client,
    )

    record = get_install_record(conn, install_id)
    assert record is not None
    assert record["install_status"] == "cancelled"
    assert not (dest_dir / "test.gguf.part").exists()


@pytest.mark.asyncio
async def test_execute_download_network_error(db, tmp_path):
    conn = db.connection()
    install_id = create_install_record(conn, None, "test.gguf", "")
    dest_dir = tmp_path / "models"

    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    mock_client = MagicMock(spec=httpx.AsyncClient)
    mock_client.stream = MagicMock(return_value=mock_cm)
    mock_client.aclose = AsyncMock()

    await execute_download(
        conn,
        install_id,
        "http://unreachable.test/model.gguf",
        "a" * 64,
        dest_dir,
        "test.gguf",
        _client=mock_client,
    )

    record = get_install_record(conn, install_id)
    assert record is not None
    assert record["install_status"] == "failed"
    assert record["error_message"] is not None


@pytest.mark.asyncio
async def test_execute_download_no_part_file_left_on_mismatch(db, tmp_path):
    content = b"data that will fail checksum"
    conn = db.connection()
    install_id = create_install_record(conn, None, "test.gguf", "")
    dest_dir = tmp_path / "models"

    mock_client = _make_mock_client(content)

    await execute_download(
        conn,
        install_id,
        "http://example.test/model.gguf",
        "f" * 64,
        dest_dir,
        "test.gguf",
        _client=mock_client,
    )

    assert not (dest_dir / "test.gguf.part").exists()


@pytest.mark.asyncio
async def test_execute_download_sets_downloading_status_before_completion(db, tmp_path):
    """The install record must be set to 'downloading' immediately after the task starts."""
    content = b"model data"
    sha = _sha256_of(content)
    conn = db.connection()
    install_id = create_install_record(conn, None, "m.gguf", "")
    dest_dir = tmp_path / "models"

    status_during_download: list[str] = []

    async def _aiter_bytes(chunk_size=None):
        # Check the DB status while "in" the download.
        r = conn.execute(
            "SELECT install_status FROM installed_models WHERE id = ?", (install_id,)
        ).fetchone()
        status_during_download.append(r[0])
        yield content

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.headers = {"content-length": str(len(content))}
    mock_response.aiter_bytes = _aiter_bytes

    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_response)
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    mock_client = MagicMock(spec=httpx.AsyncClient)
    mock_client.stream = MagicMock(return_value=mock_cm)
    mock_client.aclose = AsyncMock()

    await execute_download(
        conn, install_id, "http://x.test/m.gguf", sha, dest_dir, "m.gguf", _client=mock_client
    )

    assert status_during_download == ["downloading"]


# ── Resume: interrupted .part continues from its byte offset ──────────────────


def _make_mock_client_with_response(
    *, status_code: int, chunks: bytes, extra_headers: dict[str, str] | None = None
) -> httpx.AsyncClient:
    """Mock client whose GET yields *chunks* with a given status and headers."""

    async def _aiter_bytes(chunk_size=None):
        yield chunks

    headers = {"content-length": str(len(chunks))}
    if extra_headers:
        headers.update(extra_headers)

    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.raise_for_status = MagicMock()
    mock_response.headers = headers
    mock_response.aiter_bytes = _aiter_bytes

    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_response)
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    mock_client = MagicMock(spec=httpx.AsyncClient)
    mock_client.stream = MagicMock(return_value=mock_cm)
    mock_client.aclose = AsyncMock()
    return mock_client


@pytest.mark.asyncio
async def test_execute_download_resumes_from_part_offset(db, tmp_path):
    """A surviving .part file is continued via a Range request, not restarted."""
    first_half = b"the-first-half-of-the-weights"
    second_half = b"and-the-remaining-second-half"
    full = first_half + second_half
    sha = _sha256_of(full)
    conn = db.connection()
    install_id = create_install_record(conn, None, "test.gguf", "")

    dest_dir = tmp_path / "models"
    dest_dir.mkdir(parents=True, exist_ok=True)
    # Simulate an interrupted download: the first half is already on disk.
    (dest_dir / "test.gguf.part").write_bytes(first_half)

    total = len(full)
    mock_client = _make_mock_client_with_response(
        status_code=206,
        chunks=second_half,
        extra_headers={"content-range": f"bytes {len(first_half)}-{total - 1}/{total}"},
    )

    await execute_download(
        conn, install_id, "http://example.test/model.gguf", sha, dest_dir, "test.gguf",
        _client=mock_client,
    )

    # The Range header must have been sent from the existing offset.
    _, kwargs = mock_client.stream.call_args
    assert kwargs["headers"]["Range"] == f"bytes={len(first_half)}-"

    record = get_install_record(conn, install_id)
    assert record["install_status"] == "ready"
    assert record["size_bytes"] == total
    assert (dest_dir / "test.gguf").read_bytes() == full
    assert not (dest_dir / "test.gguf.part").exists()


@pytest.mark.asyncio
async def test_execute_download_restarts_when_server_ignores_range(db, tmp_path):
    """If the server answers 200 (Range ignored), the stale .part is overwritten."""
    full = b"a-complete-fresh-download-of-the-model"
    sha = _sha256_of(full)
    conn = db.connection()
    install_id = create_install_record(conn, None, "test.gguf", "")

    dest_dir = tmp_path / "models"
    dest_dir.mkdir(parents=True, exist_ok=True)
    # A stale/partial .part exists, but the server will ignore the Range header.
    (dest_dir / "test.gguf.part").write_bytes(b"stale-bytes-that-must-be-discarded")

    mock_client = _make_mock_client_with_response(status_code=200, chunks=full)

    await execute_download(
        conn, install_id, "http://example.test/model.gguf", sha, dest_dir, "test.gguf",
        _client=mock_client,
    )

    record = get_install_record(conn, install_id)
    assert record["install_status"] == "ready"
    assert record["size_bytes"] == len(full)
    assert (dest_dir / "test.gguf").read_bytes() == full


# ── Network policy: download must not work in PLAY mode ──────────────────────


@pytest.mark.asyncio
async def test_execute_download_uses_explicit_download_mode(db, tmp_path, monkeypatch):
    """execute_download must call require_network(EXPLICIT_DOWNLOAD), not PLAY."""
    import convsim_core.network_policy as policy

    monkeypatch.setattr(policy, "LOCAL_MODE", True)
    conn = db.connection()
    install_id = create_install_record(conn, None, "test.gguf", "")
    dest_dir = tmp_path / "models"

    mock_client = _make_mock_client(b"data")

    # With LOCAL_MODE=True only PLAY calls are blocked; EXPLICIT_DOWNLOAD still passes.
    # So execute_download must NOT raise even in LOCAL_MODE.
    # (If it used PLAY mode, it would raise NetworkBlockedError here.)
    await execute_download(
        conn,
        install_id,
        "http://example.test/model.gguf",
        _sha256_of(b"data"),
        dest_dir,
        "test.gguf",
        _client=mock_client,
    )
    # If we reach here without exception, network policy was respected.
    record = get_install_record(conn, install_id)
    assert record["install_status"] == "ready"


# ── GET /api/models/install/{install_id} ─────────────────────────────────────


def test_get_install_status_not_found(client):
    resp = client.get("/api/models/install/9999")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "INSTALL_NOT_FOUND"


def test_get_install_status_returns_record(client):
    conn = client.app.state.db.connection()
    install_id = create_install_record(conn, None, "m.gguf", "/tmp/m.gguf")
    resp = client.get(f"/api/models/install/{install_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == install_id
    assert body["install_status"] == "pending"
    assert body["filename"] == "m.gguf"


def test_get_install_status_shows_progress_fields(client):
    conn = client.app.state.db.connection()
    install_id = create_install_record(conn, None, "m.gguf", "")
    resp = client.get(f"/api/models/install/{install_id}")
    body = resp.json()
    assert "progress_bytes" in body
    assert "error_message" in body
    assert "verified_sha256" in body


def test_get_install_status_shows_ready_after_mark_ready(client):
    conn = client.app.state.db.connection()
    install_id = create_install_record(conn, None, "m.gguf", "")
    mark_install_ready(conn, install_id, 12345, "a" * 64, "/tmp/m.gguf")
    resp = client.get(f"/api/models/install/{install_id}")
    body = resp.json()
    assert body["install_status"] == "ready"
    assert body["verified_sha256"] == "a" * 64
    assert body["size_bytes"] == 12345


# ── DELETE /api/models/install/{install_id} ───────────────────────────────────


def test_cancel_install_not_found(client):
    resp = client.delete("/api/models/install/9999")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "INSTALL_NOT_FOUND"


def test_cancel_install_pending_record(client):
    conn = client.app.state.db.connection()
    install_id = create_install_record(conn, None, "m.gguf", "")
    resp = client.delete(f"/api/models/install/{install_id}")
    assert resp.status_code == 204
    record = get_install_record(conn, install_id)
    assert record["install_status"] == "cancelled"


def test_cancel_install_terminal_state_returns_409(client):
    conn = client.app.state.db.connection()
    install_id = create_install_record(conn, None, "m.gguf", "")
    mark_install_ready(conn, install_id, 100, "a" * 64, "/tmp/m.gguf")
    resp = client.delete(f"/api/models/install/{install_id}")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "INSTALL_NOT_CANCELLABLE"


def test_cancel_install_failed_state_returns_409(client):
    conn = client.app.state.db.connection()
    install_id = create_install_record(conn, None, "m.gguf", "")
    from convsim_core.services.model_manager_service import mark_install_failed
    mark_install_failed(conn, install_id, "some error")
    resp = client.delete(f"/api/models/install/{install_id}")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "INSTALL_NOT_CANCELLABLE"


# ── POST /api/models/install guards (explicit-download mode) ──────────────────


def test_install_does_not_download_when_sha256_pending(client):
    """A PENDING sha256 must block download at the API layer, no network call made."""
    conn = client.app.state.db.connection()
    conn.execute(
        """INSERT INTO model_registry (id, name, provider, license_spdx, sha256, source_type)
           VALUES ('pending-m', 'Pending', 'test', 'MIT', 'PENDING', 'registry')"""
    )
    conn.commit()
    resp = client.post("/api/models/install", json={"registry_id": "pending-m"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "MISSING_CHECKSUM"


def test_install_does_not_download_when_url_missing(client):
    """A registry entry with a valid checksum but no download URL must be rejected."""
    conn = client.app.state.db.connection()
    _insert_registry_model(conn, "no-url-model", "c" * 64)
    resp = client.post("/api/models/install", json={"registry_id": "no-url-model"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "MISSING_DOWNLOAD_URL"
    # No install record must be created for a model that cannot be downloaded.
    rows = conn.execute(
        "SELECT id FROM installed_models WHERE registry_id = 'no-url-model'"
    ).fetchall()
    assert rows == []


def test_install_accepted_model_creates_install_record(client):
    conn = client.app.state.db.connection()
    _insert_registry_model(conn, "valid-model", "c" * 64)
    conn.execute(
        "UPDATE model_registry SET download_url = 'http://example.test/m.gguf' WHERE id = 'valid-model'"
    )
    conn.commit()

    # Suppress the fire-and-forget download so the freshly created record is
    # observed deterministically without racing (or making a real network call
    # from) the background task.
    with patch(
        "convsim_core.routers.models._spawn_download_task",
        side_effect=lambda coro: coro.close(),
    ):
        resp = client.post("/api/models/install", json={"registry_id": "valid-model"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "pending"
    install_id = body["install_id"]
    record = get_install_record(conn, install_id)
    assert record is not None
    assert record["install_status"] == "pending"
