"""
Phase 10B.1 — System Diagnostic Skills
Unit tests for the four new tools added to core_diagnostics.

All psutil and subprocess calls are mocked.
No real process inspection, disk access, or GPU subprocess is performed.
"""

import subprocess
import pytest
from unittest.mock import MagicMock, patch

from backend.skills.core_diagnostics import (
    get_disk_usage,
    get_top_processes,
    get_network_stats,
    get_gpu_status,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_disk():
    """Simulates psutil.disk_usage for a healthy disk."""
    m = MagicMock()
    m.total = 500 * 1024 ** 3    # 500 GB
    m.used  = 200 * 1024 ** 3    # 200 GB
    m.free  = 300 * 1024 ** 3    # 300 GB
    m.percent = 40.0
    with patch("psutil.disk_usage", return_value=m):
        yield m


@pytest.fixture()
def mock_processes():
    """Simulates psutil.process_iter with three stable processes."""
    def _make(pid, name, cpu, mem):
        p = MagicMock()
        p.info = {
            "pid": pid, "name": name,
            "cpu_percent": cpu, "memory_percent": mem, "status": "running",
        }
        return p

    procs = [
        _make(1,  "sentinel",  35.0, 12.5),
        _make(42, "python",    20.0,  8.0),
        _make(99, "chrome",     5.0,  3.2),
    ]
    with patch("psutil.process_iter", return_value=procs):
        yield procs


@pytest.fixture()
def mock_net_io():
    """Simulates psutil.net_io_counters."""
    m = MagicMock()
    m.bytes_sent  = 100 * 1024 ** 2   # 100 MB
    m.bytes_recv  = 250 * 1024 ** 2   # 250 MB
    m.packets_sent = 80000
    m.packets_recv = 120000
    m.errin = 0; m.errout = 0
    m.dropin = 2; m.dropout = 0
    with patch("psutil.net_io_counters", return_value=m):
        yield m


def _nvidia_result(stdout: str, returncode: int = 0) -> MagicMock:
    m = MagicMock()
    m.stdout = stdout
    m.returncode = returncode
    return m


# ---------------------------------------------------------------------------
# get_disk_usage
# ---------------------------------------------------------------------------

class TestGetDiskUsage:
    def test_returns_all_fields(self, mock_disk):
        result = get_disk_usage("/")
        for field in ("path", "total_gb", "used_gb", "free_gb", "percent_used"):
            assert field in result, f"Missing field: {field}"

    def test_values_are_numeric(self, mock_disk):
        result = get_disk_usage("/")
        assert isinstance(result["total_gb"], float)
        assert isinstance(result["percent_used"], float)

    def test_path_is_echoed(self, mock_disk):
        result = get_disk_usage("/home")
        assert result["path"] == "/home"

    def test_invalid_path_returns_error_dict(self):
        with patch("psutil.disk_usage", side_effect=FileNotFoundError):
            result = get_disk_usage("/nonexistent/xyz")
        assert "error" in result
        assert "total_gb" not in result

    def test_permission_error_returns_error_dict(self):
        with patch("psutil.disk_usage", side_effect=PermissionError):
            result = get_disk_usage("/root")
        assert "error" in result

    def test_empty_path_uses_default(self, mock_disk):
        result = get_disk_usage("")
        assert "error" not in result   # should have fallen back to default


# ---------------------------------------------------------------------------
# get_top_processes
# ---------------------------------------------------------------------------

class TestGetTopProcesses:
    def test_returns_list(self, mock_processes):
        result = get_top_processes()
        assert isinstance(result, list)

    def test_respects_limit(self, mock_processes):
        result = get_top_processes(limit=2)
        assert len(result) <= 2

    def test_clamps_large_limit(self, mock_processes):
        result = get_top_processes(limit=9999)
        assert len(result) <= 50

    def test_clamps_zero_limit(self, mock_processes):
        result = get_top_processes(limit=0)
        assert len(result) >= 1

    def test_sorted_by_cpu_descending(self, mock_processes):
        result = get_top_processes(sort_by="cpu")
        cpu_vals = [p["cpu_percent"] for p in result]
        assert cpu_vals == sorted(cpu_vals, reverse=True)

    def test_sorted_by_memory_descending(self, mock_processes):
        result = get_top_processes(sort_by="memory")
        mem_vals = [p["memory_percent"] for p in result]
        assert mem_vals == sorted(mem_vals, reverse=True)

    def test_sorted_by_name_ascending(self, mock_processes):
        result = get_top_processes(sort_by="name")
        names = [p["name"] for p in result]
        assert names == sorted(names)

    def test_invalid_sort_field_falls_back_to_cpu(self, mock_processes):
        result = get_top_processes(sort_by="INVALID")
        assert isinstance(result, list)

    def test_no_sensitive_fields_exposed(self, mock_processes):
        result = get_top_processes()
        for proc in result:
            assert "cmdline" not in proc
            assert "username" not in proc
            assert "open_files" not in proc
            assert "environ" not in proc

    def test_process_disappears_mid_iteration(self):
        """NoSuchProcess raised during iteration must be skipped silently."""
        import psutil
        from unittest.mock import PropertyMock
        vanishing = MagicMock()
        type(vanishing).info = PropertyMock(
            side_effect=psutil.NoSuchProcess(pid=1)
        )
        with patch("psutil.process_iter", return_value=[vanishing]):
            result = get_top_processes()
        assert result == []

    def test_access_denied_is_skipped(self):
        import psutil
        from unittest.mock import PropertyMock
        denied = MagicMock()
        type(denied).info = PropertyMock(side_effect=psutil.AccessDenied(pid=2))
        with patch("psutil.process_iter", return_value=[denied]):
            result = get_top_processes()
        assert result == []


# ---------------------------------------------------------------------------
# get_network_stats
# ---------------------------------------------------------------------------

class TestGetNetworkStats:
    def test_returns_all_fields(self, mock_net_io):
        result = get_network_stats()
        for field in (
            "bytes_sent_mb", "bytes_recv_mb",
            "packets_sent", "packets_recv",
            "errors_in", "errors_out",
            "drops_in", "drops_out",
        ):
            assert field in result, f"Missing field: {field}"

    def test_bytes_are_float_mb(self, mock_net_io):
        result = get_network_stats()
        assert isinstance(result["bytes_sent_mb"], float)
        assert isinstance(result["bytes_recv_mb"], float)

    def test_no_ip_addresses_exposed(self, mock_net_io):
        result = get_network_stats()
        result_str = str(result)
        # Must not contain connection-level data
        assert "connections" not in result_str
        assert "local_address" not in result_str
        assert "remote_address" not in result_str

    def test_no_net_connections_called(self, mock_net_io):
        """Verify we never call the privacy-sensitive net_connections()."""
        with patch("psutil.net_connections") as mock_conn:
            get_network_stats()
            mock_conn.assert_not_called()


# ---------------------------------------------------------------------------
# get_gpu_status
# ---------------------------------------------------------------------------

_SINGLE_GPU_CSV = "0, NVIDIA GeForce RTX 3080, 45, 4096, 10240, 65\n"
_MULTI_GPU_CSV  = (
    "0, NVIDIA RTX 3080, 45, 4096, 10240, 65\n"
    "1, NVIDIA RTX 3090, 30, 2048,  8192, 55\n"
)
_MALFORMED_CSV  = "bad,data\n"


class TestGetGpuStatus:
    def test_nvidia_smi_not_found(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = get_gpu_status()
        assert result["available"] is False
        assert "not found" in result["reason"]

    def test_nvidia_smi_timeout(self):
        with patch("subprocess.run",
                   side_effect=subprocess.TimeoutExpired("nvidia-smi", 5)):
            result = get_gpu_status()
        assert result["available"] is False
        assert "timed out" in result["reason"]

    def test_nvidia_smi_nonzero_exit(self):
        with patch("subprocess.run",
                   return_value=_nvidia_result("", returncode=1)):
            result = get_gpu_status()
        assert result["available"] is False

    def test_single_gpu_parsed(self):
        with patch("subprocess.run",
                   return_value=_nvidia_result(_SINGLE_GPU_CSV)):
            result = get_gpu_status()
        assert result["available"] is True
        assert len(result["gpus"]) == 1
        gpu = result["gpus"][0]
        assert gpu["index"] == 0
        assert gpu["utilization_percent"] == 45
        assert gpu["memory_used_mb"] == 4096
        assert gpu["memory_total_mb"] == 10240
        assert gpu["temperature_c"] == 65

    def test_multi_gpu_parsed(self):
        with patch("subprocess.run",
                   return_value=_nvidia_result(_MULTI_GPU_CSV)):
            result = get_gpu_status()
        assert result["available"] is True
        assert len(result["gpus"]) == 2

    def test_malformed_lines_skipped(self):
        with patch("subprocess.run",
                   return_value=_nvidia_result(_MALFORMED_CSV)):
            result = get_gpu_status()
        # Should not crash — returns available=True with empty gpu list
        assert "available" in result

    def test_unexpected_exception_handled(self):
        with patch("subprocess.run", side_effect=OSError("permission denied")):
            result = get_gpu_status()
        assert result["available"] is False
        assert "reason" in result

    def test_shell_not_used(self):
        """nvidia-smi must never be invoked with shell=True."""
        with patch("subprocess.run",
                   return_value=_nvidia_result(_SINGLE_GPU_CSV)) as mock_run:
            get_gpu_status()
            call_kwargs = mock_run.call_args[1]
            assert call_kwargs.get("shell") is not True
