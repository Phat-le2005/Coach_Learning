"""Safe HTTP fetcher for external PDF artifacts with SSRF and redirect controls."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import ipaddress
from pathlib import Path
import socket
import tempfile
from urllib.parse import urljoin, urlparse

import httpx

from app.core.config import get_settings
from app.core.exceptions import ApplicationError


@dataclass
class FetchResult:
    temp_file_path: Path
    file_size_bytes: int
    sha256: str
    mime_type: str


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
            self.allowed_domains = [
                d.strip().lower() for d in raw_domains.split(",") if d.strip()
            ]
        elif isinstance(allowed_domains, str):
            self.allowed_domains = [
                d.strip().lower() for d in allowed_domains.split(",") if d.strip()
            ]
        else:
            self.allowed_domains = [d.strip().lower() for d in allowed_domains if d.strip()]

        self.max_bytes = max_bytes if max_bytes is not None else settings.question_acquisition_max_bytes
        self.transport = transport

    def validate_url_safety(self, url: str) -> str:
        """Validate URL scheme, domain allowlist, and SSRF restrictions."""
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

        # Check domain allowlist
        domain_matched = False
        for allowed in self.allowed_domains:
            if allowed == "*":
                domain_matched = True
                break
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

        # Check IP literal directly
        try:
            ip_obj = ipaddress.ip_address(hostname)
            self._validate_ip_address(ip_obj)
        except ValueError:
            # Hostname is not an IP literal, resolve via DNS
            port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
            self._validate_resolved_dns(hostname, port)

        return url

    def _validate_ip_address(self, ip_obj: ipaddress.IPv4Address | ipaddress.IPv6Address) -> None:
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

    def _validate_resolved_dns(self, hostname: str, port: int) -> None:
        try:
            addr_info = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
        except socket.gaierror as exc:
            raise ApplicationError(
                422,
                "QUESTION_ACQUISITION_DNS_FAILURE",
                f"Failed to resolve hostname '{hostname}': {exc}",
            )

        for item in addr_info:
            sockaddr = item[4]
            ip_str = sockaddr[0]
            try:
                ip_obj = ipaddress.ip_address(ip_str)
                self._validate_ip_address(ip_obj)
            except ValueError:
                continue

    def fetch_pdf(self, start_url: str) -> FetchResult:
        """Fetch external PDF following redirects safely up to MAX_REDIRECTS."""
        current_url = start_url
        headers = {
            "User-Agent": self.DEFAULT_USER_AGENT,
            "Accept": "application/pdf,*/*;q=0.8",
        }
        client_kwargs = {
            "timeout": httpx.Timeout(self.READ_TIMEOUT, connect=self.CONNECT_TIMEOUT),
            "follow_redirects": False,
        }
        if self.transport is not None:
            client_kwargs["transport"] = self.transport

        with httpx.Client(**client_kwargs) as client:
            for redirect_idx in range(self.MAX_REDIRECTS + 1):
                self.validate_url_safety(current_url)

                try:
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
                        fd, temp_path_str = tempfile.mkstemp(prefix="acq_", suffix=".tmp")
                        temp_path = Path(temp_path_str)
                        hasher = hashlib.sha256()
                        total_bytes = 0
                        first_chunk = True

                        try:
                            with open(fd, "wb") as f:
                                for chunk in response.iter_bytes(chunk_size=16384):
                                    if not chunk:
                                        continue
                                    if first_chunk:
                                        first_chunk = False
                                        # Magic header verification
                                        if not chunk.startswith(b"%PDF-"):
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
                                    f.write(chunk)

                            if total_bytes == 0:
                                raise ApplicationError(
                                    422,
                                    "QUESTION_ACQUISITION_NOT_PDF",
                                    "Downloaded file is empty.",
                                )

                            return FetchResult(
                                temp_file_path=temp_path,
                                file_size_bytes=total_bytes,
                                sha256=hasher.hexdigest(),
                                mime_type="application/pdf",
                            )

                        except Exception:
                            temp_path.unlink(missing_ok=True)
                            raise

                except httpx.RequestError as exc:
                    raise ApplicationError(
                        422,
                        "QUESTION_ACQUISITION_FETCH_FAILED",
                        f"Network request error: {exc}",
                    )

            raise ApplicationError(
                422,
                "QUESTION_ACQUISITION_TOO_MANY_REDIRECTS",
                f"Maximum redirect limit ({self.MAX_REDIRECTS}) exceeded.",
            )
