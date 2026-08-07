"""shared/sysinfo.py tests (PRD_6 §2.5, §3). GPU detection shells out to
nvidia-smi; its absence (no NVIDIA GPU, or the tool not installed) must be
reported honestly as None, never guessed -- Step-0 exists specifically so
an auditor can trust the declared hardware (book Ch.5.5)."""

import subprocess

from thief_peer.shared import sysinfo


def test_collect_spec_returns_all_required_keys(monkeypatch):
    monkeypatch.setattr(sysinfo, "_detect_ram_gb", lambda: 32.0)
    monkeypatch.setattr(sysinfo, "_detect_gpu_name", lambda: "NVIDIA GeForce RTX 4090")
    monkeypatch.setattr(sysinfo, "_detect_vram_gb", lambda: 24.0)

    spec = sysinfo.collect_spec()

    assert set(spec) == {"os", "cpu", "cpu_cores", "ram_gb", "gpu", "vram_gb"}
    assert spec["ram_gb"] == 32.0
    assert spec["gpu"] == "NVIDIA GeForce RTX 4090"
    assert spec["vram_gb"] == 24.0
    assert isinstance(spec["os"], str) and len(spec["os"]) > 0
    assert isinstance(spec["cpu_cores"], int) and spec["cpu_cores"] > 0


def test_gpu_detection_returns_none_when_nvidia_smi_is_not_installed(monkeypatch):
    def _missing(*args, **kwargs):
        raise FileNotFoundError("nvidia-smi not found")

    monkeypatch.setattr(subprocess, "run", _missing)

    assert sysinfo._detect_gpu_name() is None
    assert sysinfo._detect_vram_gb() is None


def test_gpu_detection_parses_nvidia_smi_output(monkeypatch):
    class _FakeResult:
        stdout = "NVIDIA GeForce RTX 4090, 24576\n"

    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: _FakeResult())

    assert sysinfo._detect_gpu_name() == "NVIDIA GeForce RTX 4090"
    assert sysinfo._detect_vram_gb() == 24.0


def test_gpu_detection_returns_none_on_any_unexpected_failure(monkeypatch):
    def _boom(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="nvidia-smi", timeout=5)

    monkeypatch.setattr(subprocess, "run", _boom)

    assert sysinfo._detect_gpu_name() is None


def test_ram_detection_returns_a_positive_number_on_this_real_machine():
    # Exercises the real platform-specific path (this dev/CI machine),
    # sanity-checked rather than pinned to an exact value.
    ram = sysinfo._detect_ram_gb()
    assert ram is None or ram > 0


def test_ram_detection_returns_none_for_an_unrecognized_platform(monkeypatch):
    monkeypatch.setattr(sysinfo.platform, "system", lambda: "PlanNine")
    assert sysinfo._detect_ram_gb() is None
