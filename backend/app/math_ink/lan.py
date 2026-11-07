"""Opt-in LAN origins from addresses assigned to this host, never client Host headers."""
import ipaddress
import socket
import sys

NETWORKS = tuple(ipaddress.IPv4Network(net) for net in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))


def host_addresses():
    if sys.platform == "win32":
        # Read the current OS interface table, not a cached hostname/DNS answer.
        # Microsoft GetIpAddrTable / MIB_IPADDRROW, no extra Python dependency.
        import ctypes as c
        class Row(c.Structure):
            _fields_ = [(name, c.c_uint32) for name in ("address", "index", "mask", "broadcast", "size")] + [("unused", c.c_uint16), ("type", c.c_uint16)]
        class Table(c.Structure):
            _fields_ = [("count", c.c_uint32), ("rows", Row * 1)]
        size = c.c_uint32()
        call = c.windll.iphlpapi.GetIpAddrTable
        call(None, c.byref(size), False)
        for _ in range(3):
            if not 4 <= size.value <= 1024 * 1024:
                raise OSError("Invalid network interface table size")
            buffer = c.create_string_buffer(size.value)
            result = call(buffer, c.byref(size), False)
            if result == 122:  # ERROR_INSUFFICIENT_BUFFER: interface changed mid-read.
                continue
            if result:
                raise OSError(result, "Cannot read local interface table")
            count = c.c_uint32.from_buffer(buffer).value
            offset, stride = Table.rows.offset, c.sizeof(Row)
            if offset + count * stride > len(buffer):
                raise OSError("Invalid network interface table")
            return {socket.inet_ntoa(buffer.raw[offset + i * stride:offset + i * stride + 4]) for i in range(count)}
        raise OSError("Network changed repeatedly during discovery")
    addresses = set()
    for record in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
        # A hostname resolving to a foreign address must never authorize that origin.
        address = record[4][0]
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
                probe.bind((address, 0))
            addresses.add(address)
        except OSError:
            continue
    return addresses


def lan_origins(settings):
    if not settings.lan_mode or settings.app_env == "production":
        return set()
    hosts = {"localhost", "127.0.0.1"}
    try:
        for value in host_addresses():
            address = ipaddress.IPv4Address(value)
            if any(address in network for network in NETWORKS):
                hosts.add(str(address))
    except (OSError, ValueError):
        pass  # No wildcard fallback when network detection fails.
    return {f"http://{host}:{settings.lan_frontend_port}" for host in hosts}
