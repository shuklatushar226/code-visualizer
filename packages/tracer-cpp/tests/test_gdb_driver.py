"""Unit tests for the GDB/MI transport wrapper."""

from cpp_tracer.gdb_driver import GdbDriver


class _FakeGdb:
    def __init__(self) -> None:
        self.calls: list[tuple[str, float]] = []

    def write(self, command: str, *, timeout_sec: float):
        self.calls.append((command, timeout_sec))
        return [{"type": "result", "message": "done"}]


def test_send_all_allows_slow_gdb_startup() -> None:
    driver = object.__new__(GdbDriver)
    fake = _FakeGdb()
    driver._gdb = fake

    response = driver._send_all(
        "-file-exec-and-symbols /tmp/main.bin",
        timeout_sec=5,
    )

    assert response == [{"type": "result", "message": "done"}]
    assert fake.calls == [("-file-exec-and-symbols /tmp/main.bin", 5)]
