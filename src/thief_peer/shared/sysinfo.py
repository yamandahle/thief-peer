"""Hardware spec collection for Step-0 declarations (PRD_6 §2.5, §3):
best-effort, standard-library-only introspection. GPU/VRAM detection shells
out to `nvidia-smi`; its absence (no NVIDIA GPU, or the tool isn't
installed) is reported honestly as `None`, never guessed -- Step-0 exists
so an auditor can trust the declared hardware (book Ch.5.5).
"""

import os
import platform
import subprocess


def collect_spec() -> dict:
    return {
        "os": f"{platform.system()} {platform.release()}",
        "cpu": platform.processor() or platform.machine(),
        "cpu_cores": os.cpu_count(),
        "ram_gb": _detect_ram_gb(),
        "gpu": _detect_gpu_name(),
        "vram_gb": _detect_vram_gb(),
    }


def _detect_ram_gb() -> float | None:
    system = platform.system()
    if system == "Windows":
        return _windows_ram_gb()
    if system == "Linux":
        return _linux_ram_gb()
    return None


def _windows_ram_gb() -> float | None:
    try:
        import ctypes

        class _MemoryStatusEx(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = _MemoryStatusEx()
        status.dwLength = ctypes.sizeof(_MemoryStatusEx)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
        return round(status.ullTotalPhys / (1024**3), 1)
    except Exception:
        return None


def _linux_ram_gb() -> float | None:
    try:
        with open("/proc/meminfo", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    kib = int(line.split()[1])
                    return round(kib / (1024**2), 1)
    except Exception:
        return None
    return None


def _nvidia_smi_query() -> tuple[str, float] | None:
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        name, mem_mib = result.stdout.strip().split(",")
        return name.strip(), round(float(mem_mib.strip()) / 1024, 1)
    except Exception:
        return None


def _detect_gpu_name() -> str | None:
    info = _nvidia_smi_query()
    return info[0] if info else None


def _detect_vram_gb() -> float | None:
    info = _nvidia_smi_query()
    return info[1] if info else None
