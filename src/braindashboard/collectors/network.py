from __future__ import annotations

import socket
from dataclasses import dataclass
from datetime import UTC, datetime
from time import monotonic, perf_counter
from typing import Protocol, cast

import psutil


class NetIoCounter(Protocol):
    bytes_sent: int
    bytes_recv: int
    packets_sent: int
    packets_recv: int


@dataclass(frozen=True)
class NetworkSnapshot:
    timestamp: datetime
    interface_name: str
    bytes_sent_per_second: float
    bytes_recv_per_second: float
    packets_sent_per_second: float
    packets_recv_per_second: float
    internet_reachable: bool
    internet_latency_ms: float | None


class NetworkCollector:
    def __init__(
        self,
        internet_check_host: str = "1.1.1.1",
        internet_check_port: int = 53,
        internet_check_timeout_seconds: float = 0.5,
    ) -> None:
        self.internet_check_host = internet_check_host
        self.internet_check_port = internet_check_port
        self.internet_check_timeout_seconds = internet_check_timeout_seconds
        self._previous_samples: dict[str, tuple[float, int, int, int, int]] = {}

    def collect(self) -> NetworkSnapshot:
        timestamp = datetime.now(UTC)
        interface_name, counters = _select_interface()
        now = monotonic()
        previous = self._previous_samples.get(interface_name)
        current_sample = (
            now,
            counters.bytes_sent,
            counters.bytes_recv,
            counters.packets_sent,
            counters.packets_recv,
        )
        self._previous_samples[interface_name] = current_sample

        if previous is None:
            sent_per_second = 0.0
            recv_per_second = 0.0
            packets_sent_per_second = 0.0
            packets_recv_per_second = 0.0
        else:
            elapsed = max(now - previous[0], 0.001)
            sent_per_second = max(counters.bytes_sent - previous[1], 0) / elapsed
            recv_per_second = max(counters.bytes_recv - previous[2], 0) / elapsed
            packets_sent_per_second = max(counters.packets_sent - previous[3], 0) / elapsed
            packets_recv_per_second = max(counters.packets_recv - previous[4], 0) / elapsed

        internet_reachable, internet_latency_ms = self._check_internet()

        return NetworkSnapshot(
            timestamp=timestamp,
            interface_name=interface_name,
            bytes_sent_per_second=round(sent_per_second, 2),
            bytes_recv_per_second=round(recv_per_second, 2),
            packets_sent_per_second=round(packets_sent_per_second, 2),
            packets_recv_per_second=round(packets_recv_per_second, 2),
            internet_reachable=internet_reachable,
            internet_latency_ms=internet_latency_ms,
        )

    def _check_internet(self) -> tuple[bool, float | None]:
        start = perf_counter()
        try:
            with socket.create_connection(
                (self.internet_check_host, self.internet_check_port),
                timeout=self.internet_check_timeout_seconds,
            ):
                return True, round((perf_counter() - start) * 1000, 2)
        except OSError:
            return False, None


def _select_interface() -> tuple[str, NetIoCounter]:
    per_interface = psutil.net_io_counters(pernic=True)
    stats = psutil.net_if_stats()
    candidates = [
        (name, counters)
        for name, counters in per_interface.items()
        if stats.get(name) is not None
        and stats[name].isup
        and not _is_loopback_interface(name)
    ]

    if not candidates:
        total = psutil.net_io_counters(pernic=False)
        return "all", cast(NetIoCounter, total)

    interface_name, counters = max(
        candidates,
        key=lambda item: item[1].bytes_sent + item[1].bytes_recv,
    )
    return interface_name, cast(NetIoCounter, counters)


def _is_loopback_interface(name: str) -> bool:
    normalized_name = name.lower()
    return normalized_name == "lo" or normalized_name.startswith("loopback")