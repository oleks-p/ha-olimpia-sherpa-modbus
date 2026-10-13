"""The probe tests talk to simulated units over local sockets and ptys.

When the Home Assistant test harness is installed it blocks all sockets for
every test. These tests need none of Home Assistant, so they lift that block
for themselves. Without the harness (the Python 3.11 job) this is a no-op.
"""
from __future__ import annotations

import pytest

try:
    import pytest_socket
except ImportError:  # plain pytest, as on the host's Python
    pytest_socket = None


@pytest.fixture(autouse=True)
def _allow_local_sockets():
    if pytest_socket is not None:
        pytest_socket.enable_socket()
        pytest_socket.socket_allow_hosts(["127.0.0.1"], allow_unix_socket=True)
    yield
