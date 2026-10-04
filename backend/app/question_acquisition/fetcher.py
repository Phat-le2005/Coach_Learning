"""Safe HTTP fetcher for external PDF artifacts with SSRF, DNS pinning, and redirect controls."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import hashlib
import ipaddress
from pathlib import Path
import socket
import tempfile
from urllib.parse import urljoin, urlparse

import httpcore
import httpcore._backends.sync
import httpx

from app.core.config import get_settings
from app.core.exceptions import ApplicationError

CHUNK_SIZE = 64 * 1024


@dataclass
class FetchResult:
    temp_file_path: Path
    file_size_bytes: int
    sha256: str
    mime_type: str


@dataclass
class ValidatedFetchTarget:
    url: str
    hostname: str
    port: int
    resolved_public_ips: list[str]


class PinnedSyncBackend(httpcore._backends.sync.SyncBackend):
    """Network backend that connects directly to a pre-validated IP while preserving hostname for TLS SNI."""

    def __init__(self, host_to_ip_map: dict[str, str]) -> None:
        super().__init__()
        self.host_to_ip_map = host_to_ip_map

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[httpcore._backends.sync.SOCKET_OPTION] | None = None,
    ) -> httpcore._backends.sync.NetworkStream:
        target_ip = self.host_to_ip_map.get(host, host)
        return super().connect_tcp(
            target_ip,
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )


class PinnedTransport(httpx.BaseTransport):
    """Transport that pins TCP connections to specific IP addresses to prevent DNS rebinding TOCTOU."""

    def __init__(self, host_to_ip_map: dict[str, str], verify: bool = True) -> None:
        super().__init__()
        backend = PinnedSyncBackend(host_to_ip_map)
        self._pool = httpcore.ConnectionPool(
            network_backend=backend,
            ssl_context=httpx.create_ssl_context(verify=verify),
        )

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        return self._pool.handle_request(request)

    def close(self) -> None:
        self._pool.close()


class SafePdfFetcher:
    """Safe streaming HTTP client for fetching PDF artifacts without SSRF vulnerability."""

    CONNECT_TIMEOUT: float = 5.0
    READ_TIMEOUT: float = 20.0
    MAX_REDIRECTS: int = 3
    DEFAULT_USER_AGENT: str = "EduMS-QuestionAcquisition/1.0"

    def __init__(
        self,
        *,
        allowed_domains: str | list[str] | None = None,
        max_bytes: int | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        settings = get_settings()
        if allowed_domains is None:
            raw_domains = settings.question_acquisition_allowed_domains
            domain_list = [d.strip().lower() for d in raw_domains.split(",") if d.strip()]
        elif isinstance(allowed_domains, str):
            domain_list = [d.strip().lower() for d in allowed_domains.split(",") if d.strip()]
        else:
            domain_list = [d.strip().lower() for d in allowed_domains if d.strip()]

        self.allowed_domains: list[str] = []
        for entry in domain_list:
            if entry == "*":
                raise ValueError("Bare wildcard '*' is not permitted in allowed_domains.")
            if "://" in entry or "/" in entry or ":" in entry:
                raise ValueError(
                    f"Invalid domain allowlist entry '{entry}': must be a hostname or wildcard domain (e.g. *.example.com)."
                )
            check_name = entry[2:] if entry.startswith("*.") else entry
            if (
                not check_name
                or ".." in check_name
                or check_name.startswith(".")
                or check_name.endswith(".")
            ):
                raise ValueError(f"Invalid domain allowlist entry '{entry}'.")
            self.allowed_domains.append(entry)

        self.max_bytes = max_bytes if max_bytes is not None else settings.question_acquisition_max_bytes
        self.transport = transport

    def validate_url_safety(self, url: str) -> ValidatedFetchTarget:
        """Validate URL scheme, domain allowlist, IP literal rejection, and SSRF restrictions."""
        if not self.allowed_domains:
            raise ApplicationError(
                409,
                "QUESTION_ACQUISITION_FETCH_DISABLED",
                "External URL fetching is disabled because no allowed domains are configured.",
            )

        parsed = urlparse(url)
        if parsed.scheme.lower() not in {"http", "https"}:
            raise ApplicationError(
                422,
                "QUESTION_ACQUISITION_INVALID_SCHEME",
                f"Unsupported URL scheme '{parsed.scheme}'. Only http and https are allowed.",
            )

        hostname = (parsed.hostname or "").strip().lower()
        if not hostname:
            raise ApplicationError(
                422,
                "QUESTION_ACQUISITION_INVALID_URL",
                "URL hostname is missing.",
            )

        # Reject all IP-literal targets for server-side acquisition fetch
        try:
            ipaddress.ip_address(hostname)
            raise ApplicationError(
                422,
                "QUESTION_ACQUISITION_IP_LITERAL_DISALLOWED",
                f"IP-literal URL target '{hostname}' is not allowed for acquisition fetch.",
            )
        except ValueError:
            pass

        # Check domain allowlist
        domain_matched = False
        for allowed in self.allowed_domains:
            if allowed.startswith("*."):
                suffix = allowed[1:]  # e.g. .example.com
                if hostname.endswith(suffix) or hostname == allowed[2:]:
                    domain_matched = True
                    break
            elif hostname == allowed:
                domain_matched = True
                break

        if not domain_matched:
            raise ApplicationError(
                422,
                "QUESTION_ACQUISITION_DOMAIN_NOT_ALLOWED",
                f"Domain '{hostname}' is not in the allowed acquisition domains list.",
            )

        # Block localhost and .local explicitly
        if hostname == "localhost" or hostname.endswith(".local"):
            raise ApplicationError(
                422,
                "QUESTION_ACQUISITION_SSRF_BLOCKED",
                "Access to localhost and local domain names is blocked.",
            )

        port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
        resolved_ips = self._validate_resolved_dns(hostname, port)

        return ValidatedFetchTarget(
            url=url,
            hostname=hostname,
            port=port,
            resolved_public_ips=resolved_ips,
        )

    def _validate_resolved_dns(self, hostname: str, port: int) -> list[str]:
        try:
            addr_info = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
        except socket.gaierror as exc:
            raise ApplicationError(
                422,
                "QUESTION_ACQUISITION_DNS_FAILURE",
                f"Failed to resolve hostname '{hostname}': {exc}",
            )

        public_ips: list[str] = []
        for item in addr_info:
            sockaddr = item[4]
            ip_str = sockaddr[0]
            try:
                ip_obj = ipaddress.ip_address(ip_str)
            except ValueError:
                continue

            # Any private, loopback, or restricted address causes total rejection of the target
            if (
                ip_obj.is_private
                or ip_obj.is_loopback
                or ip_obj.is_link_local
                or ip_obj.is_multicast
                or ip_obj.is_reserved
                or ip_obj.is_unspecified
            ):
                raise ApplicationError(
                    422,
                    "QUESTION_ACQUISITION_SSRF_BLOCKED",
                    f"Resolved target address '{ip_obj}' is in a private/restricted address range.",
                )

            # Check IPv4-mapped IPv6 addresses (e.g., ::ffff:127.0.0.1 or ::ffff:10.0.0.1)
            if isinstance(ip_obj, ipaddress.IPv6Address) and ip_obj.ipv4_mapped:
                mapped_v4 = ip_obj.ipv4_mapped
                if (
                    mapped_v4.is_private
                    or mapped_v4.is_loopback
                    or mapped_v4.is_link_local
                    or mapped_v4.is_reserved
                ):
                    raise ApplicationError(
                        422,
                        "QUESTION_ACQUISITION_SSRF_BLOCKED",
                        f"Resolved IPv4-mapped address '{mapped_v4}' is in a private/restricted address range.",
                    )

            public_ips.append(ip_str)

        if not public_ips:
            raise ApplicationError(
                422,
                "QUESTION_ACQUISITION_DNS_FAILURE",
                f"No usable addresses resolved for '{hostname}'.",
            )

        return public_ips

    def fetch_pdf(self, start_url: str) -> FetchResult:
        """Fetch external PDF following redirects safely up to MAX_REDIRECTS."""
        current_url = start_url
        headers = {
            "User-Agent": self.DEFAULT_USER_AGENT,
            "Accept": "application/pdf,*/*;q=0.8",
        }

        for redirect_idx in range(self.MAX_REDIRECTS + 1):
            target = self.validate_url_safety(current_url)

            # Select transport: mock transport if provided, otherwise pinned transport to verified public IP
            transport_to_use: httpx.BaseTransport
            transport_cleanup = None
            if self.transport is not None:
                transport_to_use = self.transport
            else:
                pinned_ip = target.resolved_public_ips[0]
                pinned_transport = PinnedTransport({target.hostname: pinned_ip})
                transport_to_use = pinned_transport
                transport_cleanup = pinned_transport

            client_kwargs = {
                "timeout": httpx.Timeout(self.READ_TIMEOUT, connect=self.CONNECT_TIMEOUT),
                "follow_redirects": False,
                "transport": transport_to_use,
            }

            try:
                with httpx.Client(**client_kwargs) as client:
                    with client.stream("GET", current_url, headers=headers) as response:
                        if response.status_code in {301, 302, 303, 307, 308}:
                            if redirect_idx >= self.MAX_REDIRECTS:
                                raise ApplicationError(
                                    422,
                                    "QUESTION_ACQUISITION_TOO_MANY_REDIRECTS",
                                    f"Maximum redirect limit ({self.MAX_REDIRECTS}) exceeded.",
                                )
                            loc = response.headers.get("Location")
                            if not loc:
                                raise ApplicationError(
                                    422,
                                    "QUESTION_ACQUISITION_INVALID_REDIRECT",
                                    "Redirect response missing Location header.",
                                )
                            current_url = urljoin(current_url, loc)
                            continue

                        if response.status_code != 200:
                            raise ApplicationError(
                                422,
                                "QUESTION_ACQUISITION_FETCH_FAILED",
                                f"Server returned HTTP status {response.status_code}.",
                            )

                        content_type = response.headers.get("Content-Type", "").lower()
                        if "text/html" in content_type:
                            raise ApplicationError(
                                422,
                                "QUESTION_ACQUISITION_NOT_PDF",
                                "Target URL returned HTML instead of PDF document.",
                            )

                        content_len = response.headers.get("Content-Length")
                        if content_len:
                            try:
                                if int(content_len) > self.max_bytes:
                                    raise ApplicationError(
                                        422,
                                        "QUESTION_ACQUISITION_FILE_TOO_LARGE",
                                        f"File size exceeds maximum allowed ({self.max_bytes} bytes).",
                                    )
                            except ValueError:
                                pass

                        # Stream into temp file
                        temp_file = tempfile.NamedTemporaryFile(
                            prefix="acq_", suffix=".tmp", delete=False
                        )
                        temp_path = Path(temp_file.name)
                        hasher = hashlib.sha256()
                        total_bytes = 0
                        magic_header = bytearray()

                        try:
                            for chunk in response.iter_bytes(chunk_size=CHUNK_SIZE):
                                if not chunk:
                                    continue
                                if len(magic_header) < 5:
                                    needed = 5 - len(magic_header)
                                    magic_header.extend(chunk[:needed])
                                    if len(magic_header) == 5 and not bytes(magic_header).startswith(
                                        b"%PDF-"
                                    ):
                                        raise ApplicationError(
                                            422,
                                            "QUESTION_ACQUISITION_NOT_PDF",
                                            "Payload does not begin with valid PDF magic bytes (%PDF-).",
                                        )
                                total_bytes += len(chunk)
                                if total_bytes > self.max_bytes:
                                    raise ApplicationError(
                                        422,
                                        "QUESTION_ACQUISITION_FILE_TOO_LARGE",
                                        f"Downloaded file exceeded maximum size ({self.max_bytes} bytes).",
                                    )
                                hasher.update(chunk)
                                temp_file.write(chunk)

                            temp_file.flush()
                            temp_file.close()

                            if total_bytes < 5 or not bytes(magic_header).startswith(b"%PDF-"):
                                raise ApplicationError(
                                    422,
                                    "QUESTION_ACQUISITION_NOT_PDF",
                                    "Downloaded file is empty or missing valid PDF magic header.",
                                )

                            return FetchResult(
                                temp_file_path=temp_path,
                                file_size_bytes=total_bytes,
                                sha256=hasher.hexdigest(),
                                mime_type="application/pdf",
                            )

                        except Exception:
                            temp_file.close()
                            temp_path.unlink(missing_ok=True)
                            raise

            except httpx.RequestError as exc:
                raise ApplicationError(
                    422,
                    "QUESTION_ACQUISITION_FETCH_FAILED",
                    f"Network request error: {exc}",
                )
            finally:
                if transport_cleanup is not None:
                    transport_cleanup.close()

        raise ApplicationError(
            422,
            "QUESTION_ACQUISITION_TOO_MANY_REDIRECTS",
            f"Maximum redirect limit ({self.MAX_REDIRECTS}) exceeded.",
        )
