"""Telemetria do PC para o painel: CPU, RAM e GPU (NVIDIA)."""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import time
from typing import Any

_BOOT = time.time()


def _gpu() -> dict[str, Any] | None:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return None
    try:
        out = subprocess.run(
            [exe, "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5, check=True,
        ).stdout.strip().splitlines()[0]
        name, util, used, total, temp = [x.strip() for x in out.split(",")]
        return {"name": name, "util": float(util), "mem_used_mb": float(used),
                "mem_total_mb": float(total), "temp_c": float(temp)}
    except (subprocess.SubprocessError, ValueError, IndexError, OSError):
        return None


def _snapshot() -> dict[str, Any]:
    data: dict[str, Any] = {"uptime_s": int(time.time() - _BOOT), "gpu": _gpu()}
    try:
        import psutil

        vm = psutil.virtual_memory()
        data.update(
            cpu=psutil.cpu_percent(interval=0.3),
            ram_used_gb=round(vm.used / 1024**3, 1),
            ram_total_gb=round(vm.total / 1024**3, 1),
            ram_percent=vm.percent,
        )
    except ImportError:
        data.update(cpu=None, ram_used_gb=None, ram_total_gb=None, ram_percent=None)
    return data


async def snapshot() -> dict[str, Any]:
    return await asyncio.to_thread(_snapshot)
