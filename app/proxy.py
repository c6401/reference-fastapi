from http.cookiejar import CookieJar, DefaultCookiePolicy
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

from app.config import settings

router = APIRouter(prefix="/proxy")

# Per-connection headers that must not be forwarded (RFC 9110 §7.6.1), plus Host,
# which httpx sets from the upstream URL.
HOP_BY_HOP = frozenset(
    {
        b"connection",
        b"keep-alive",
        b"proxy-authenticate",
        b"proxy-authorization",
        b"te",
        b"trailer",
        b"transfer-encoding",
        b"upgrade",
        b"host",
    }
)

# Uvicorn always adds its own Date and Server, so drop the upstream's to avoid duplicates.
RESPONSE_EXCLUDED = HOP_BY_HOP | {b"date", b"server"}

METHODS =["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]


def make_http_client(transport: httpx.AsyncBaseTransport | None = None) -> httpx.AsyncClient:
    """Client shared by all proxied requests.

    The jar accepts no cookies: a shared jar would replay one user's Set-Cookie on
    other users' requests. Cookies still pass through as plain headers.
    """
    return httpx.AsyncClient(
        timeout=settings.proxy_timeout,
        cookies=CookieJar(policy=DefaultCookiePolicy(allowed_domains=[])),
        transport=transport,
    )


def get_http_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.http_client


HttpClientDep = Annotated[httpx.AsyncClient, Depends(get_http_client)]


def upstream_headers(request: Request) -> list[tuple[bytes, bytes]]:
    """Headers sent upstream. Auth header swapping goes here."""
    headers = [(k, v) for k, v in request.headers.raw if k not in HOP_BY_HOP]
    if settings.proxy_upstream_authorization:
        headers = [(k, v) for k, v in headers if k != b"authorization"]
        headers.append((b"authorization", settings.proxy_upstream_authorization.encode()))
    return headers


@router.api_route("/{path:path}", methods=METHODS, include_in_schema=False)
async def proxy(path: str, request: Request, client: HttpClientDep) -> StreamingResponse:
    if not settings.proxy_upstream_url:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Proxy upstream is not configured")

    has_body = "content-length" in request.headers or "transfer-encoding" in request.headers
    upstream_request = client.build_request(
        request.method,
        httpx.URL(f"{settings.proxy_upstream_url.rstrip('/')}/{path}", query=request.url.query.encode()),
        headers=upstream_headers(request),
        content=request.stream() if has_body else None,
    )
    try:
        upstream = await client.send(upstream_request, stream=True)
    except httpx.RequestError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Upstream request failed: {exc!r}") from exc

    response = StreamingResponse(
        upstream.aiter_raw(),
        status_code=upstream.status_code,
        background=BackgroundTask(upstream.aclose),
    )
    # Raw list keeps repeated headers such as Set-Cookie; raw bytes keep Content-Encoding valid.
    response.raw_headers = [(k, v) for k, v in upstream.headers.raw if k.lower() not in RESPONSE_EXCLUDED]
    return response
