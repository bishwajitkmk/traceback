"""Destination rules for outbound replay requests (PRD §6.6, §12).

The replay service is an SSRF boundary. Rules are enforced twice:
1. When a target is registered (URL shape, literal IPs, known metadata hosts).
2. At connect time, on every resolved address, inside the HTTP client's network
   backend (`GuardedBackend`). This is authoritative: it covers DNS names that
   resolve to internal addresses, DNS rebinding between check and use, and
   redirects, because every TCP connection goes through it.
"""

import ipaddress
import socket
from collections.abc import Iterable
from urllib.parse import urlsplit

import httpcore

from app.core.errors import ValidationFailed

# Always blocked, even in local-development mode.
METADATA_IPS = {
    ipaddress.ip_address("169.254.169.254"),  # AWS, GCP, Azure, DigitalOcean, …
    ipaddress.ip_address("169.254.170.2"),  # AWS ECS task metadata
    ipaddress.ip_address("100.100.100.200"),  # Alibaba Cloud
    ipaddress.ip_address("fd00:ec2::254"),  # AWS IPv6
}
METADATA_HOSTNAMES = {
    "metadata.google.internal",
    "metadata",
    "instance-data",
    "instance-data.ec2.internal",
}
CGNAT = ipaddress.ip_network("100.64.0.0/10")


class BlockedDestination(Exception):
    """Raised when a connection would reach a prohibited address."""


def blocked_reason(ip_text: str, allow_private: bool) -> str | None:
    """Why connecting to this IP is not allowed, or None if it is."""
    ip = ipaddress.ip_address(ip_text.split("%")[0])
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if ip in METADATA_IPS:
        return f"{ip} is a cloud metadata endpoint"
    if ip.is_unspecified or ip.is_multicast or ip.is_link_local or ip.is_reserved:
        return f"{ip} is not a routable unicast address"
    if ip.is_loopback or ip.is_private or (isinstance(ip, ipaddress.IPv4Address) and ip in CGNAT):
        if not allow_private:
            return f"{ip} is a loopback or private-network address"
    elif not ip.is_global:
        return f"{ip} is not a public address"
    return None


def allow_private_for(environment: str, private_networks_enabled: bool) -> bool:
    """Private networks are reachable only for local targets in local-development mode."""
    return private_networks_enabled and environment == "local"


def validate_target_url(url: str, environment: str, private_networks_enabled: bool) -> str:
    """Validate a target base URL at registration; return it normalized (no trailing slash)."""
    try:
        parts = urlsplit(url)
        port = parts.port  # raises on an invalid port
    except ValueError:
        raise ValidationFailed(
            "base_url", "Enter a full URL, e.g. https://staging.example.com."
        ) from None
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValidationFailed("base_url", "Enter a full http:// or https:// URL.")
    if parts.username or parts.password:
        raise ValidationFailed("base_url", "Credentials in the URL are not allowed.")
    if parts.query or parts.fragment:
        raise ValidationFailed("base_url", "The base URL cannot contain a query or fragment.")
    del port

    host = parts.hostname.rstrip(".").lower()
    allow_private = allow_private_for(environment, private_networks_enabled)
    if host in METADATA_HOSTNAMES:
        raise ValidationFailed("base_url", "Cloud metadata endpoints can never be replay targets.")
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        reason = blocked_reason(str(literal), allow_private)
        if reason:
            raise ValidationFailed("base_url", _target_message(reason))
    elif (host == "localhost" or host.endswith(".localhost")) and not allow_private:
        raise ValidationFailed("base_url", _target_message("localhost is a loopback address"))
    return url.rstrip("/")


def _target_message(reason: str) -> str:
    return (
        f"This target is not allowed: {reason}. Loopback and private addresses are only "
        "accepted for 'local' targets when the server runs in local-development mode."
    )


class GuardedBackend(httpcore.NetworkBackend):
    """httpcore network backend that validates every resolved address before connecting."""

    def __init__(self, allow_private: bool) -> None:
        self._inner = httpcore.SyncBackend()
        self._allow_private = allow_private

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.NetworkStream:
        if host.rstrip(".").lower() in METADATA_HOSTNAMES:
            raise BlockedDestination(f"{host} is a cloud metadata endpoint")
        try:
            infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise httpcore.ConnectError(f"Could not resolve {host}: {exc}") from exc
        addresses = list(dict.fromkeys(str(info[4][0]) for info in infos))
        # Reject if ANY answer is prohibited, so mixed DNS answers cannot slip through.
        for address in addresses:
            reason = blocked_reason(address, self._allow_private)
            if reason:
                raise BlockedDestination(reason)
        last_error: Exception | None = None
        for address in addresses:
            try:
                # Connect to the vetted IP itself; TLS still verifies against `host`.
                return self._inner.connect_tcp(
                    address, port, timeout, local_address, socket_options
                )
            except (httpcore.ConnectError, httpcore.ConnectTimeout) as exc:
                last_error = exc
        raise last_error or httpcore.ConnectError(f"Could not connect to {host}")

    def connect_unix_socket(self, *args: object, **kwargs: object) -> httpcore.NetworkStream:
        raise BlockedDestination("unix sockets are not allowed")

    def sleep(self, seconds: float) -> None:
        self._inner.sleep(seconds)
