# -*- coding: utf-8 -*-
"""Idle characterization for P4.4 gate background handling."""
from __future__ import annotations
import hashlib
import json
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List

import machine_state as ms


@dataclass
class IdleCharacterization:
    schema_version: int = 1
    timestamp: str = ""
    machine_id: str = ""
    windows: int = 0
    window_s: float = 0.0
    cpu_samples: List[float] = None
    q95_cpu_pct: float = 0.0
    quiet_threshold_pct: float = 0.0
    warmup_cpu_max_pct: float = 0.0
    quiet_consecutive: int = 3
    quiet_window_s: float = 3.0
    quiet_cap_s: float = 600.0
    margin_pct: float = 1.0
    sha256: str = ""

    def __post_init__(self):
        if self.cpu_samples is None:
            self.cpu_samples = []
        if not self.timestamp:
            self.timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        if not self.machine_id:
            import platform
            self.machine_id = platform.node()


def compute_quiet_threshold(cpu_samples: List[float], margin_pct: float = 1.0) -> float:
    """Compute quiet_threshold_pct = ceil(Q95(cpu_samples) + margin_pct)."""
    import math
    if not cpu_samples:
        return 5.0  # fallback
    sorted_samples = sorted(cpu_samples)
    idx = max(0, int(len(sorted_samples) * 0.95) - 1)
    q95 = sorted_samples[idx]
    return math.ceil(q95 + margin_pct)


def compute_warmup_cpu_threshold(cpu_samples: List[float], margin_pct: float = 1.0) -> float:
    """Compute warmup_cpu_max_pct = ceil(Q95(cpu_samples) + margin_pct).
    
    This is the same formula as quiet_threshold_pct: the warmup CPU threshold
    should be based on the machine's actual idle behavior, not a hardcoded value.
    """
    import math
    if not cpu_samples:
        return 2.0  # fallback
    sorted_samples = sorted(cpu_samples)
    idx = max(0, int(len(sorted_samples) * 0.95) - 1)
    q95 = sorted_samples[idx]
    return math.ceil(q95 + margin_pct)


def characterize_idle(
    output_dir: Path,
    windows: int = 30,
    window_s: float = 10.0,
    margin_pct: float = 1.0,
    force: bool = False,
) -> int:
    """Run idle characterization and write idle_characterization.json atomically."""
    output_file = output_dir / "idle_characterization.json"
    if output_file.exists() and not force:
        print(f"[ARRESTO] {output_file} exists. Use --force to overwrite.", file=sys.stderr)
        return 1
    
    # Collect CPU samples
    all_samples: List[float] = []
    for _ in range(windows):
        samples = ms.total_cpu_samples(duration_s=window_s, interval_s=1.0)
        all_samples.extend(samples)
    
    q95 = sorted(all_samples)[max(0, int(len(all_samples) * 0.95) - 1)]
    quiet_threshold = compute_quiet_threshold(all_samples, margin_pct)
    warmup_cpu_threshold = compute_warmup_cpu_threshold(all_samples, margin_pct)
    
    char = IdleCharacterization(
        windows=windows,
        window_s=window_s,
        cpu_samples=all_samples,
        q95_cpu_pct=round(q95, 1),
        quiet_threshold_pct=quiet_threshold,
        warmup_cpu_max_pct=warmup_cpu_threshold,
        margin_pct=margin_pct,
    )
    
    # Atomic write: write .tmp, compute hash, insert hash, rename
    tmp_file = output_file.with_suffix(".tmp")
    char_dict = asdict(char)
    # Remove sha256 from dict for hash computation
    hash_dict = {k: v for k, v in char_dict.items() if k != "sha256"}
    hash_text = json.dumps(hash_dict, sort_keys=True, separators=(",", ":")).encode()
    char.sha256 = hashlib.sha256(hash_text).hexdigest()
    
    tmp_file.write_text(json.dumps(asdict(char), indent=2, ensure_ascii=False), encoding="utf-8")
    tmp_file.replace(output_file)
    
    print(f"Idle characterization written to {output_file}")
    print(f"  quiet_threshold_pct = {char.quiet_threshold_pct}")
    print(f"  warmup_cpu_max_pct = {char.warmup_cpu_max_pct}")
    print(f"  sha256 = {char.sha256}")
    return 0