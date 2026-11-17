"""SSRF-safe fetching of user-supplied URLs.

Every hop (including redirects) is validated: http(s) only, ports 80/443, no credentials in
the URL, and every resolved IP must be globally routable. Known residual risk: DNS can change
between our check and the connection (rebinding); mitigate in production by egress rules."""
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx

MAX_BYTES = 1_500_000
MAX_REDIRECTS = 3
TIMEOUT = 8.0
ALLOWED_PORTS = {80, 443}
RESOLVER = socket.getaddrinfo  # module-level so tests can replace it
UA = "Mozilla/5.0 (compatible; JobVerifier/0.1; hackathon project)"


class UnsafeURL(Exception):
    pass


class FetchError(Exception):
    pass


@dataclass
class Fetched:
    status: int
    url: str
    text: str
    truncated: bool = False


def _check_ip(ip_str: str) -> None:
    ip = ipaddress.ip_address(ip_str.split("%")[0])
    if getattr(ip, "ipv4_mapped", None):
        ip = ip.ipv4_mapped
    if not ip.is_global or ip.is_multicast:
        raise UnsafeURL(f"Blocked non-public address: {ip}")


def validate_url(url: str, resolver=None) -> None:
    p = urlparse(url)
    if p.scheme not in ("http", "https"):
        raise UnsafeURL("Only http(s) URLs are allowed")
    host = p.hostname
    if not host:
        raise UnsafeURL("URL has no host")
    if p.username or p.password:
        raise UnsafeURL("Credentials in URL are not allowed")
    try:
        port = p.port or (443 if p.scheme == "https" else 80)
    except ValueError:
        raise UnsafeURL("Invalid port")
    if port not in ALLOWED_PORTS:
        raise UnsafeURL(f"Port {port} is not allowed")
    try:
        ipaddress.ip_address(host)
        _check_ip(host)
        return
    except UnsafeURL:
        raise
    except ValueError:
        pass  # a hostname: resolve it and check every address
    try:
        infos = (resolver or RESOLVER)(host, port, type=socket.SOCK_STREAM)
    except OSError:
        raise FetchError(f"Could not resolve host: {host}")
    if not infos:
        raise FetchError(f"Could not resolve host: {host}")
    for info in infos:
        _check_ip(info[4][0])


def safe_get(url: str, client: httpx.Client | None = None, resolver=None,
             accept: str = "text/html,application/json;q=0.9,*/*;q=0.5") -> Fetched:
    own = client is None
    client = client or httpx.Client(timeout=TIMEOUT, follow_redirects=False)
    try:
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            validate_url(current, resolver)
            with client.stream("GET", current,
                               headers={"User-Agent": UA, "Accept": accept}) as r:
                loc = r.headers.get("location")
                if r.status_code in (301, 302, 303, 307, 308) and loc:
                    current = urljoin(current, loc)
                    continue
                buf, truncated = bytearray(), False
                for chunk in r.iter_bytes():
                    buf += chunk
                    if len(buf) > MAX_BYTES:
                        truncated = True
                        break
                text = bytes(buf[:MAX_BYTES]).decode(r.encoding or "utf-8", errors="replace")
                return Fetched(r.status_code, current, text, truncated)
        raise FetchError("Too many redirects")
    except httpx.HTTPError as e:
        raise FetchError(str(e))
    finally:
        if own:
            client.close()
