from collections.abc import AsyncIterator, Callable

import httpx
import pytest
from httpx import AsyncClient

from app.config import settings
from app.main import app
from app.proxy import get_http_client, make_http_client

pytestmark = pytest.mark.anyio

UPSTREAM = "http://upstream.test/api"

Handler = Callable[[httpx.Request], httpx.Response]


class Upstream:
    """Fake upstream: records what the proxy sent and replies with `handler`."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.handler: Handler = lambda request: httpx.Response(200, json={"ok": True})

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        await request.aread()
        self.requests.append(request)
        response = self.handler(request)
        # Responses built from bytes are pre-read; re-wrap as a stream like a real server's.
        return httpx.Response(
            response.status_code,
            headers=response.headers.multi_items(),
            stream=httpx.ByteStream(response.content),
        )

    @property
    def last(self) -> httpx.Request:
        return self.requests[-1]


@pytest.fixture
async def upstream(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Upstream]:
    monkeypatch.setattr(settings, "proxy_upstream_url", UPSTREAM)
    monkeypatch.setattr(settings, "proxy_upstream_authorization", None)
    fake = Upstream()
    async with make_http_client(transport=httpx.MockTransport(fake)) as http_client:
        app.dependency_overrides[get_http_client] = lambda: http_client
        yield fake
    app.dependency_overrides.pop(get_http_client, None)


async def test_forwards_method_path_query_and_body(client: AsyncClient, upstream: Upstream) -> None:
    response = await client.post("/proxy/v1/things?a=1&a=2&b=x%20y", json={"name": "thing"})

    assert response.status_code == 200
    assert upstream.last.method == "POST"
    assert str(upstream.last.url) == f"{UPSTREAM}/v1/things?a=1&a=2&b=x%20y"
    assert upstream.last.content == b'{"name":"thing"}'


async def test_get_without_body(client: AsyncClient, upstream: Upstream) -> None:
    await client.get("/proxy/v1/things")

    assert upstream.last.method == "GET"
    assert upstream.last.content == b""
    assert "transfer-encoding" not in upstream.last.headers


async def test_returns_upstream_status_body_and_headers(client: AsyncClient, upstream: Upstream) -> None:
    upstream.handler = lambda request: httpx.Response(
        418,
        content=b"teapot",
        headers=[("x-upstream", "1"), ("set-cookie", "a=1"), ("set-cookie", "b=2"), ("connection", "close"), ("server", "up")],
    )

    response = await client.get("/proxy/anything")

    assert response.status_code == 418
    assert response.content == b"teapot"
    assert response.headers["x-upstream"] == "1"
    assert response.headers.get_list("set-cookie") == ["a=1", "b=2"]
    assert "connection" not in response.headers
    assert "server" not in response.headers


async def test_passes_authorization_through_by_default(client: AsyncClient, upstream: Upstream) -> None:
    await client.get("/proxy/me", headers={"authorization": "Bearer client-token"})

    assert upstream.last.headers["authorization"] == "Bearer client-token"


async def test_swaps_authorization_when_configured(
    client: AsyncClient, upstream: Upstream, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "proxy_upstream_authorization", "Bearer upstream-token")

    await client.get("/proxy/me", headers={"authorization": "Bearer client-token"})

    assert upstream.last.headers.get_list("authorization") == ["Bearer upstream-token"]


async def test_strips_hop_by_hop_headers_and_rewrites_host(client: AsyncClient, upstream: Upstream) -> None:
    await client.get("/proxy/me", headers={"x-custom": "kept", "proxy-authorization": "secret", "te": "trailers"})

    assert upstream.last.headers["x-custom"] == "kept"
    assert upstream.last.headers["host"] == "upstream.test"
    assert "proxy-authorization" not in upstream.last.headers
    assert "te" not in upstream.last.headers


async def test_cookies_pass_through_both_ways(client: AsyncClient, upstream: Upstream) -> None:
    upstream.handler = lambda request: httpx.Response(200, headers={"set-cookie": "session=from-upstream"})

    response = await client.get("/proxy/me", headers={"cookie": "session=from-client"})

    assert upstream.last.headers["cookie"] == "session=from-client"
    assert response.headers["set-cookie"] == "session=from-upstream"


async def test_cookies_do_not_leak_between_requests(client: AsyncClient, upstream: Upstream) -> None:
    upstream.handler = lambda request: httpx.Response(200, headers={"set-cookie": "session=alice-secret"})
    await client.get("/proxy/login")
    client.cookies.clear()  # the test client is a browser too; next request is another user

    await client.get("/proxy/me")

    assert "cookie" not in upstream.last.headers


async def test_upstream_unreachable_returns_502(client: AsyncClient, upstream: Upstream) -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    upstream.handler = fail

    response = await client.get("/proxy/me")

    assert response.status_code == 502


async def test_not_configured_returns_503(
    client: AsyncClient, upstream: Upstream, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "proxy_upstream_url", None)

    response = await client.get("/proxy/me")

    assert response.status_code == 503
    assert upstream.requests == []
