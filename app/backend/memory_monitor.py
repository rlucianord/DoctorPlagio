"""Lightweight Windows memory telemetry for DoctorPlagio."""
from __future__ import annotations
import ctypes
import gc
import os
from typing import Any


def memory_snapshot() -> dict[str, Any]:
    try:
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]
        s = MEMORYSTATUSEX(); s.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(s)):
            return {"ram_percent": int(s.dwMemoryLoad), "ram_total_gb": round(s.ullTotalPhys/1024**3,2), "ram_available_gb": round(s.ullAvailPhys/1024**3,2), "ram_used_gb": round((s.ullTotalPhys-s.ullAvailPhys)/1024**3,2)}
    except Exception:
        pass
    return {}


def log_memory(label: str) -> dict[str, Any]:
    snap = memory_snapshot()
    if snap:
        print(f"🧠 [MEM] {label}: {snap['ram_percent']}% | usada {snap['ram_used_gb']} GB | disponible {snap['ram_available_gb']} GB")
    return snap


def collect_garbage(label: str = "gc") -> dict[str, Any]:
    collected = gc.collect()
    snap = log_memory(f"{label} (gc={collected})")
    return snap
