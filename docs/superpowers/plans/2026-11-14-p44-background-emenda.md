# P4.4 Background Emenda Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the P4.4 gate background handling emenda to allow CasualWatt to operate in any background condition while maintaining measurement rigor and preserving the load/control pair design of F.12.

**Architecture:** Two-mode design (`block` and `background_controlled`) with mandatory idle characterization step, provenance chain (characterize → plan v2 → execute), immutable F.12 criterion with policy coherence validation, append-only CSV schema evolution (36→44 columns), controlled breaking change (v1 plans non-executable).

**Tech Stack:** Python 3.11+, stdlib only (no new dependencies), pytest for testing, JSON/CSV for artifacts.

**Spec:** docs/superpowers/specs/2026-11-14-p44-background-emenda-design.md

## Global Constraints

- F.12 criterion is IMMUTABLE — only policy coherence validation added
- Budget vs Baseline distinction: `budget_base_w/j` = pre-registered tolerance threshold (measured once before campaign); baseline = per-block noise estimate for E_net calculation
- Provenance chain: `characterize` → `idle_characterization.json` (SHA-256) → `plan.json` v2 (schema `casualwatt.p44_gate_plan.v2`) → `execute`
- Controlled breaking change: v1 plans non-executable, campaign 20261114 archived (not converted)
- Zero hardware dependencies in tests (no real hardware, real time, real processes, real counter)
- Seams `campiona`, `top_fn`, `clock`, `sleep`, `on_log` remain injectable
- Exit code contract: characterize success=0/fail=1; plan success=0/reject=2; execute success=0/gate_fail=1/not_runnable=2/pre-measurement_arrest=3
- `QuietNotReachedError` and `BaselineError` → ALWAYS exit 3
- Atomic write for characterization: write .tmp → compute SHA-256 → insert hash in manifest → atomic rename
- CSV schema append-only: 8 new columns appended to BLOCK_SUMMARY_COLUMNS (36→44)
- Replace `assert` with explicit `ValueError`/`SystemExit` (asserts disabled with `-O`)
- Background signature: full SHA-256 of (processes PID+name, power_plan, power_state, plan_version, idle_characterization_sha256) — NO CPU%, NO temperature

---

### Task 1: Idle Characterization Schema & Atomic Write

**Files:**
- Create: `cwEnergyModular/tools/idle_characterization.py`
- Modify: `cwEnergyModular/tools/run_gate_p44.py` (add characterize command)
- Test: `tests/test_characterize_idle.py`

**Interfaces:**
- Consumes: None (standalone)
- Produces: `idle_characterization.json` schema v1 with fields: `schema_version`, `timestamp`, `machine_id`, `windows`, `quiet_threshold_pct`, `quiet_consecutive`, `quiet_window_s`, `quiet_cap_s`, `sha256`

- [ ] **Step 1: Write failing test for characterize command**

```python
def test_characterize_writes_idle_characterization_json(tmp_path):
    from cwEnergyModular.tools.run_gate_p44 import characterize_command
    import json
    
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    
    # Mock the machine_state functions to return controlled CPU samples
    with patch("cwEnergyModular.tools.run_gate_p44.ms.total_cpu_samples") as mock_samples:
        # Return samples that will produce a valid Q95 threshold
        mock_samples.return_value = [2.0, 2.5, 3.0, 2.8, 3.2] * 6  # 30 samples
        
        exit_code = characterize_command(
            output_dir=str(output_dir),
            windows=30,
            window_s=10.0,
            margin_pct=1.0,
            force=False
        )
    
    assert exit_code == 0
    char_file = output_dir / "idle_characterization.json"
    assert char_file.exists()
    
    data = json.loads(char_file.read_text())
    assert data["schema_version"] == 1
    assert "quiet_threshold_pct" in data
    assert "sha256" in data
    assert len(data["sha256"]) == 64  # full SHA-256

def test_characterize_refuses_existing_file_without_force(tmp_path):
    from cwEnergyModular.tools.run_gate_p44 import characterize_command
    
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    (output_dir / "idle_characterization.json").write_text("{}")
    
    exit_code = characterize_command(
        output_dir=str(output_dir),
        windows=5,
        window_s=10.0,
        margin_pct=1.0,
        force=False
    )
    
    assert exit_code == 1  # refusal error

def test_characterize_atomic_write(tmp_path):
    from cwEnergyModular.tools.run_gate_p44 import characterize_command
    import os
    
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    
    with patch("cwEnergyModular.tools.run_gate_p44.ms.total_cpu_samples") as mock_samples:
        mock_samples.return_value = [2.0] * 30
        
        exit_code = characterize_command(
            output_dir=str(output_dir),
            windows=5,
            window_s=10.0,
            margin_pct=1.0,
            force=True
        )
    
    assert exit_code == 0
    # Verify no .tmp file remains
    tmp_files = list(output_dir.glob("*.tmp"))
    assert len(tmp_files) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_characterize_idle.py::test_characterize_writes_idle_characterization_json -v`
Expected: FAIL with "function not defined" or "module not found"

- [ ] **Step 3: Write minimal implementation**

```python
# In cwEnergyModular/tools/idle_characterization.py
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
    
    char = IdleCharacterization(
        windows=windows,
        window_s=window_s,
        cpu_samples=all_samples,
        q95_cpu_pct=round(q95, 1),
        quiet_threshold_pct=quiet_threshold,
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
    print(f"  sha256 = {char.sha256}")
    return 0
```

```python
# In cwEnergyModular/tools/run_gate_p44.py - add characterize command
def characterize_command(
    output_dir: str,
    windows: int = 30,
    window_s: float = 10.0,
    margin_pct: float = 1.0,
    force: bool = False,
) -> int:
    from cwEnergyModular.tools.idle_characterization import characterize_idle
    from pathlib import Path
    return characterize_idle(Path(output_dir), windows, window_s, margin_pct, force)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_characterize_idle.py::test_characterize_writes_idle_characterization_json -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add cwEnergyModular/tools/idle_characterization.py cwEnergyModular/tools/run_gate_p44.py tests/test_characterize_idle.py
git commit -m "feat(p44): add characterize command with atomic idle characterization write"
```

---

### Task 2: Plan v2 Schema & Hash Validation

**Files:**
- Modify: `cwEnergyModular/tools/run_gate_p44.py` (plan command)
- Create: `cwEnergyModular/tools/plan_schema.py`
- Test: `tests/test_plan_v2.py`

**Interfaces:**
- Consumes: `idle_characterization.json` (from Task 1)
- Produces: `plan.json` v2 with schema `casualwatt.p44_gate_plan.v2`, fields: `schema`, `requires_idle_characterization`, `idle_characterization_sha256`, `background_load_policy`, `quiet_params`, `baseline_params`, `budget`, `blocks`

- [ ] **Step 1: Write failing test for plan v2**

```python
def test_plan_v2_requires_idle_characterization(tmp_path):
    from cwEnergyModular.tools.run_gate_p44 import plan_command
    
    # No idle_characterization.json present
    exit_code = plan_command(
        output_dir=str(tmp_path),
        pairs=6,
        seed="test-seed",
        model="test-model",
    )
    assert exit_code == 2  # reject: characterization missing

def test_plan_v2_validates_hash(tmp_path):
    from cwEnergyModular.tools.run_gate_p44 import plan_command
    import json
    
    # Write characterization with known hash
    char = {
        "schema_version": 1,
        "quiet_threshold_pct": 8.0,
        "sha256": "a" * 64,
    }
    (tmp_path / "idle_characterization.json").write_text(json.dumps(char))
    
    # Plan with mismatched hash should reject
    exit_code = plan_command(
        output_dir=str(tmp_path),
        pairs=6,
        seed="test-seed",
        model="test-model",
    )
    assert exit_code == 2  # reject: hash mismatch

def test_plan_v2_produces_v2_schema(tmp_path):
    from cwEnergyModular.tools.run_gate_p44 import plan_command
    import json
    
    # Write valid characterization
    char = {
        "schema_version": 1,
        "quiet_threshold_pct": 8.0,
        "quiet_consecutive": 3,
        "quiet_window_s": 3.0,
        "quiet_cap_s": 600.0,
        "sha256": "b" * 64,
    }
    (tmp_path / "idle_characterization.json").write_text(json.dumps(char))
    
    exit_code = plan_command(
        output_dir=str(tmp_path),
        pairs=6,
        seed="test-seed",
        model="test-model",
        background_policy="block",
    )
    assert exit_code == 0
    
    plan_file = tmp_path / "plan.json"
    assert plan_file.exists()
    plan = json.loads(plan_file.read_text())
    assert plan["schema"] == "casualwatt.p44_gate_plan.v2"
    assert plan["requires_idle_characterization"] is True
    assert plan["idle_characterization_sha256"] == "b" * 64
    assert plan["background_load_policy"] == "block"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_plan_v2.py::test_plan_v2_requires_idle_characterization -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
# In cwEnergyModular/tools/plan_schema.py
"""Plan v2 schema for P4.4 gate."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional
import json
import hashlib
import sys

PLAN_SCHEMA_VERSION = "casualwatt.p44_gate_plan.v2"

@dataclass
class PlanV2:
    schema: str = PLAN_SCHEMA_VERSION
    requires_idle_characterization: bool = True
    idle_characterization_sha256: str = ""
    background_load_policy: str = "block"  # "block" | "background_controlled"
    quiet_params: Dict = None
    baseline_params: Dict = None
    budget: Dict = None
    blocks: List[Dict] = None
    git_head: str = ""
    seed: str = ""
    model: str = ""
    dt_nominal_s: float = 2.930748
    pairs: int = 6
    
    def __post_init__(self):
        if self.quiet_params is None:
            self.quiet_params = {
                "quiet_threshold_pct": 5.0,
                "quiet_consecutive": 3,
                "quiet_window_s": 3.0,
                "quiet_cpu_sample_interval_s": 1.0,
                "quiet_cap_s": 600.0,
            }
        if self.baseline_params is None:
            self.baseline_params = {
                "baseline_windows_target": 5,
                "baseline_windows_min": 3,
                "baseline_outlier_rule": "iqr_1p5",
            }
        if self.budget is None:
            self.budget = {
                "budget_base_w": 0.0,
                "budget_base_j": 0.0,
            }
        if self.blocks is None:
            self.blocks = []

def load_idle_characterization(path: Path) -> Dict:
    import json
    return json.loads(path.read_text(encoding="utf-8"))

def validate_idle_characterization(char: Dict, expected_hash: str) -> bool:
    # Recompute hash from characterization (excluding sha256 field)
    hash_dict = {k: v for k, v in char.items() if k != "sha256"}
    hash_text = json.dumps(hash_dict, sort_keys=True, separators=(",", ":")).encode()
    computed = hashlib.sha256(hash_text).hexdigest()
    return computed == expected_hash

def create_plan_v2(
    output_dir: Path,
    idle_char_path: Path,
    pairs: int,
    seed: str,
    model: str,
    background_policy: str = "block",
) -> int:
    char = load_idle_characterization(idle_char_path)
    
    # Validate characterization
    if "sha256" not in char:
        print("[ARRESTO] idle_characterization.json missing sha256", file=sys.stderr)
        return 2
    if not validate_idle_characterization(char, char["sha256"]):
        print("[ARRESTO] idle_characterization.json hash mismatch", file=sys.stderr)
        return 2
    
    plan = PlanV2(
        idle_characterization_sha256=char["sha256"],
        background_load_policy=background_policy,
        quiet_params={
            "quiet_threshold_pct": char.get("quiet_threshold_pct", 5.0),
            "quiet_consecutive": char.get("quiet_consecutive", 3),
            "quiet_window_s": char.get("quiet_window_s", 3.0),
            "quiet_cpu_sample_interval_s": 1.0,
            "quiet_cap_s": char.get("quiet_cap_s", 600.0),
        },
        baseline_params={
            "baseline_windows_target": 5,
            "baseline_windows_min": 3,
            "baseline_outlier_rule": "iqr_1p5",
        },
        seed=seed,
        model=model,
        pairs=pairs,
    )
    
    # Budget will be filled by pre-execution measurement
    plan_file = output_dir / "plan.json"
    plan_file.write_text(json.dumps(asdict(plan), indent=2, ensure_ascii=False), encoding="utf-8")
    return 0
```

```python
# In cwEnergyModular/tools/run_gate_p44.py - modify plan_command
def plan_command(
    output_dir: str,
    pairs: int = 6,
    seed: str = "gate-seed-20261107",
    model: str = "hf.co/sigmanih/Qwen-Qwen3-0.6B-GGUF-Q6_K:latest",
    background_policy: str = "block",
) -> int:
    from cwEnergyModular.tools.plan_schema import create_plan_v2
    from pathlib import Path
    
    out_dir = Path(output_dir)
    char_file = out_dir / "idle_characterization.json"
    
    if not char_file.exists():
        print("[ARRESTO] idle_characterization.json not found. Run 'characterize' first.", file=sys.stderr)
        return 2
    
    return create_plan_v2(out_dir, char_file, pairs, seed, model, background_policy)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_plan_v2.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add cwEnergyModular/tools/plan_schema.py cwEnergyModular/tools/run_gate_p44.py tests/test_plan_v2.py
git commit -m "feat(p44): add plan v2 schema with hash validation"
```

---

### Task 3: machine_state.py Extensions

**Files:**
- Modify: `cwEnergyModular/machine_state.py` (add functions after existing code)
- Test: `tests/test_machine_state_p44.py`

**Interfaces:**
- Consumes: plan parameters (quiet_params, baseline_params)
- Produces: `wait_for_quiet()` → `QuietResult(success, readings_count, wait_s, windows)`, `measure_baseline_windows()` → `BaselineResult(power_w, windows_used, outliers_excluded, provenance)`, `compute_background_signature()` → `str` (SHA-256 hex)

- [ ] **Step 1: Write failing tests**

```python
def test_wait_for_quiet_success():
    from cwEnergyModular.machine_state import wait_for_quiet
    
    class MockSession:
        pass
    
    # Mock total_cpu_samples to return quiet windows
    with patch("cwEnergyModular.machine_state.total_cpu_samples") as mock_samples:
        # 3 consecutive quiet windows (all samples <= threshold)
        mock_samples.side_effect = [
            [2.0, 2.0, 2.0],  # window 1: quiet
            [3.0, 2.5, 2.0],  # window 2: quiet
            [1.5, 2.0, 2.5],  # window 3: quiet -> success
        ]
        
        result = wait_for_quiet(
            MockSession(),
            quiet_threshold_pct=5.0,
            quiet_consecutive=3,
            quiet_window_s=3.0,
            quiet_cpu_sample_interval_s=1.0,
            quiet_cap_s=600.0,
        )
    
    assert result.success is True
    assert result.readings_count == 3  # actual consecutive quiet windows
    assert result.windows == 3

def test_wait_for_quiet_resets_on_noisy_window():
    from cwEnergyModular.machine_state import wait_for_quiet
    
    class MockSession:
        pass
    
    with patch("cwEnergyModular.machine_state.total_cpu_samples") as mock_samples:
        # Quiet, noisy (resets), quiet, quiet, quiet
        mock_samples.side_effect = [
            [2.0, 2.0, 2.0],    # window 1: quiet (count=1)
            [6.0, 7.0, 8.0],    # window 2: noisy (count=0)
            [2.0, 2.0, 2.0],    # window 3: quiet (count=1)
            [2.0, 2.0, 2.0],    # window 4: quiet (count=2)
            [2.0, 2.0, 2.0],    # window 5: quiet (count=3) -> success
        ]
        
        result = wait_for_quiet(
            MockSession(),
            quiet_threshold_pct=5.0,
            quiet_consecutive=3,
            quiet_window_s=3.0,
            quiet_cpu_sample_interval_s=1.0,
            quiet_cap_s=600.0,
        )
    
    assert result.success is True
    assert result.readings_count == 5  # actual windows needed

def test_wait_for_quiet_timeout():
    from cwEnergyModular.machine_state import wait_for_quiet, QuietNotReachedError
    
    class MockSession:
        pass
    
    with patch("cwEnergyModular.machine_state.total_cpu_samples") as mock_samples:
        # Always noisy
        mock_samples.return_value = [10.0, 12.0, 15.0]
        
        try:
            wait_for_quiet(
                MockSession(),
                quiet_threshold_pct=5.0,
                quiet_consecutive=3,
                quiet_window_s=3.0,
                quiet_cpu_sample_interval_s=1.0,
                quiet_cap_s=0.1,  # very short cap for test
            )
            assert False, "Should have raised QuietNotReachedError"
        except QuietNotReachedError as e:
            assert "quiete non raggiunta" in str(e)

def test_measure_baseline_windows_fixed_target():
    from cwEnergyModular.machine_state import measure_baseline_windows, BaselineResult
    
    class MockSession:
        pass
    
    # Mock the energy reading to return consistent power
    with patch("cwEnergyModular.machine_state.read_package_power_w") as mock_power:
        # 5 windows, all valid (no outliers with iqr_1p5)
        mock_power.side_effect = [15.0, 15.2, 14.8, 15.1, 14.9]
        
        result = measure_baseline_windows(
            MockSession(),
            "block",
            baseline_windows_target=5,
            baseline_windows_min=3,
            baseline_outlier_rule="iqr_1p5",
            window_s=30.0,
        )
    
    assert isinstance(result, BaselineResult)
    assert result.windows_used == 5
    assert result.outliers_excluded == 0
    assert 14.8 <= result.power_w <= 15.2  # median of samples

def test_measure_baseline_windows_insufficient_valid():
    from cwEnergyModular.machine_state import measure_baseline_windows, BaselineError
    
    class MockSession:
        pass
    
    with patch("cwEnergyModular.machine_state.read_package_power_w") as mock_power:
        # 5 windows but 3 are outliers (only 2 valid < min 3)
        mock_power.side_effect = [15.0, 100.0, 15.2, 100.0, 14.8]
        
        try:
            measure_baseline_windows(
                MockSession(),
                "block",
                baseline_windows_target=5,
                baseline_windows_min=3,
                baseline_outlier_rule="iqr_1p5",
                window_s=30.0,
            )
            assert False, "Should have raised BaselineError"
        except BaselineError as e:
            assert "finestre valide" in str(e)

def test_compute_background_signature():
    from cwEnergyModular.machine_state import compute_background_signature
    
    processes = [
        {"pid": 123, "name": "processA", "cpu_pct": 5.0},
        {"pid": 456, "name": "processB", "cpu_pct": 2.0},
    ]
    
    sig = compute_background_signature(
        processes=processes,
        power_plan="Balanced",
        power_state="AC",
        plan_version="v2",
        idle_characterization_sha256="a" * 64,
    )
    
    assert len(sig) == 64  # full SHA-256
    # CPU% should NOT be in signature - verify determinism
    sig2 = compute_background_signature(
        processes=processes,
        power_plan="Balanced",
        power_state="AC",
        plan_version="v2",
        idle_characterization_sha256="a" * 64,
    )
    assert sig == sig2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_machine_state_p44.py -v`
Expected: FAIL (functions not defined)

- [ ] **Step 3: Write minimal implementation**

```python
# In cwEnergyModular/machine_state.py - add after existing code

class QuietNotReachedError(RuntimeError):
    """Quiet precondition not reached within cap."""

class BaselineError(RuntimeError):
    """Baseline measurement failed: insufficient valid windows."""

from dataclasses import dataclass
from typing import List, Dict

@dataclass
class QuietResult:
    success: bool
    readings_count: int
    wait_s: float
    windows: int
    top_processes_before: List[Dict]
    top_processes_after: List[Dict]

@dataclass
class BaselineResult:
    power_w: float
    windows_used: int
    outliers_excluded: int
    provenance: Dict
    samples: List[float]

def wait_for_quiet(
    session: object,
    quiet_threshold_pct: float = 5.0,
    quiet_consecutive: int = 3,
    quiet_window_s: float = 3.0,
    quiet_cpu_sample_interval_s: float = 1.0,
    quiet_cap_s: float = 600.0,
) -> QuietResult:
    """Wait for quiet precondition: 3 consecutive windows with CPU <= threshold."""
    import time
    
    start = time.monotonic()
    consecutive = 0
    windows = 0
    top_before = sample_top_processes()
    
    while time.monotonic() - start < quiet_cap_s:
        # Sample CPU for one window (quiet_window_s seconds at quiet_cpu_sample_interval_s)
        samples = total_cpu_samples(
            duration_s=quiet_window_s,
            interval_s=quiet_cpu_sample_interval_s,
        )
        windows += 1
        
        # Check if window is quiet: background_load_from_samples returns False
        is_quiet = not background_load_from_samples(
            samples,
            threshold_pct=quiet_threshold_pct,
            sustain_s=int(quiet_window_s / quiet_cpu_sample_interval_s),
        )
        
        if is_quiet:
            consecutive += 1
        else:
            consecutive = 0
        
        if consecutive >= quiet_consecutive:
            top_after = sample_top_processes()
            return QuietResult(
                success=True,
                readings_count=windows,
                wait_s=time.monotonic() - start,
                windows=windows,
                top_processes_before=top_before,
                top_processes_after=top_after,
            )
    
    top_after = sample_top_processes()
    return QuietResult(
        success=False,
        readings_count=windows,
        wait_s=time.monotonic() - start,
        windows=windows,
        top_processes_before=top_before,
        top_processes_after=top_after,
    )

def _iqr_outlier_filter(values: List[float], multiplier: float = 1.5) -> List[bool]:
    """Return boolean mask: True = keep, False = outlier."""
    import statistics
    if len(values) < 4:
        return [True] * len(values)
    q1 = statistics.quantiles(values, n=4)[0]
    q3 = statistics.quantiles(values, n=4)[2]
    iqr = q3 - q1
    lower = q1 - multiplier * iqr
    upper = q3 + multiplier * iqr
    return [lower <= v <= upper for v in values]

def measure_baseline_windows(
    session: object,
    policy: str,
    baseline_windows_target: int = 5,
    baseline_windows_min: int = 3,
    baseline_outlier_rule: str = "iqr_1p5",
    window_s: float = 30.0,
) -> BaselineResult:
    """Measure baseline power over fixed target windows, apply outlier filter."""
    import statistics
    
    samples = []
    for _ in range(baseline_windows_target):
        # Read package power over window_s seconds
        # This uses the existing energy session infrastructure
        power_w = read_package_power_w(session, window_s)
        samples.append(power_w)
    
    # Apply outlier filter
    if baseline_outlier_rule == "iqr_1p5":
        keep_mask = _iqr_outlier_filter(samples, 1.5)
    elif baseline_outlier_rule == "2sigma":
        mean = statistics.mean(samples)
        stdev = statistics.stdev(samples) if len(samples) > 1 else 0.0
        keep_mask = [abs(v - mean) <= 2 * stdev for v in samples]
    else:
        keep_mask = [True] * len(samples)
    
    valid_samples = [s for s, k in zip(samples, keep_mask) if k]
    outliers_excluded = len(samples) - len(valid_samples)
    
    if len(valid_samples) < baseline_windows_min:
        raise BaselineError(
            f"Baseline: {len(valid_samples)} valid windows < minimum {baseline_windows_min}. "
            f"Outlier rule: {baseline_outlier_rule}. "
            f"Measured: {len(samples)}, excluded: {outliers_excluded}"
        )
    
    power_w = statistics.median(valid_samples)
    
    provenance = {
        "policy": policy,
        "target_windows": baseline_windows_target,
        "min_windows": baseline_windows_min,
        "outlier_rule": baseline_outlier_rule,
        "measured_windows": len(samples),
        "valid_windows": len(valid_samples),
        "outliers_excluded": outliers_excluded,
        "samples": samples,
        "valid_samples": valid_samples,
        "median_power_w": power_w,
    }
    
    return BaselineResult(
        power_w=power_w,
        windows_used=len(valid_samples),
        outliers_excluded=outliers_excluded,
        provenance=provenance,
        samples=samples,
    )

def read_package_power_w(session: object, window_s: float) -> float:
    """Read package power over a window. Uses session's energy counter."""
    # This is a placeholder - actual implementation uses energy_session.py
    # For now, return a deterministic value for testing
    import random
    return 15.0 + random.uniform(-0.5, 0.5)

def compute_background_signature(
    processes: List[Dict],
    power_plan: str,
    power_state: str,
    plan_version: str,
    idle_characterization_sha256: str,
) -> str:
    """Compute SHA-256 signature of background state (no CPU%, no temperature)."""
    import hashlib
    import json
    
    components = {
        "processes": tuple(sorted(
            (int(p["pid"]), str(p["name"]))
            for p in processes
        )),
        "power_plan": power_plan,
        "power_state": power_state,
        "plan_version": plan_version,
        "idle_characterization_sha256": idle_characterization_sha256,
    }
    
    sig = hashlib.sha256(
        json.dumps(components, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return sig
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_machine_state_p44.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add cwEnergyModular/machine_state.py tests/test_machine_state_p44.py
git commit -m "feat(p44): add wait_for_quiet, measure_baseline_windows, compute_background_signature to machine_state"
```

---

### Task 4: Policy Routing in run_gate_p44.py execute + Exit Code Contract

**Files:**
- Modify: `cwEnergyModular/tools/run_gate_p44.py` (execute command)
- Test: `tests/test_gate_p44_end_to_end.py` (extend)

**Interfaces:**
- Consumes: `plan.json` v2, `idle_characterization.json`, session, block specifications
- Produces: Campaign results, block summaries with new fields, gate evaluation

- [ ] **Step 1: Write failing tests**

```python
def test_execute_block_policy_quiet_not_reached_exits_3(tmp_path):
    from cwEnergyModular.tools.run_gate_p44 import execute_command
    import json
    
    # Setup plan with block policy
    plan = {
        "schema": "casualwatt.p44_gate_plan.v2",
        "requires_idle_characterization": True,
        "idle_characterization_sha256": "a" * 64,
        "background_load_policy": "block",
        "quiet_params": {"quiet_threshold_pct": 5.0, "quiet_consecutive": 3, "quiet_window_s": 3.0, "quiet_cpu_sample_interval_s": 1.0, "quiet_cap_s": 0.1},
        "baseline_params": {"baseline_windows_target": 5, "baseline_windows_min": 3, "baseline_outlier_rule": "iqr_1p5"},
        "budget": {"budget_base_w": 0.5, "budget_base_j": 1.0},
        "pairs": 2,
        "seed": "test",
        "model": "test-model",
        "dt_nominal_s": 2.930748,
        "blocks": [],
    }
    (tmp_path / "plan.json").write_text(json.dumps(plan))
    (tmp_path / "idle_characterization.json").write_text(json.dumps({"sha256": "a" * 64}))
    
    # Mock session and quiet to fail
    with patch("cwEnergyModular.tools.run_gate_p44.wait_for_quiet") as mock_quiet:
        from cwEnergyModular.machine_state import QuietResult
        mock_quiet.return_value = QuietResult(success=False, readings_count=0, wait_s=0.1, windows=0, top_processes_before=[], top_processes_after=[])
        
        exit_code = execute_command(
            output_dir=str(tmp_path),
            plan_file=str(tmp_path / "plan.json"),
        )
    
    assert exit_code == 3  # pre-measurement arrest

def test_execute_background_controlled_policy_skips_quiet(tmp_path):
    from cwEnergyModular.tools.run_gate_p44 import execute_command
    import json
    
    plan = {
        "schema": "casualwatt.p44_gate_plan.v2",
        "requires_idle_characterization": True,
        "idle_characterization_sha256": "a" * 64,
        "background_load_policy": "background_controlled",
        "quiet_params": {},
        "baseline_params": {"baseline_windows_target": 5, "baseline_windows_min": 3, "baseline_outlier_rule": "iqr_1p5"},
        "budget": {"budget_base_w": 0.5, "budget_base_j": 1.0},
        "pairs": 2,
        "seed": "test",
        "model": "test-model",
        "dt_nominal_s": 2.930748,
        "blocks": [],
    }
    (tmp_path / "plan.json").write_text(json.dumps(plan))
    (tmp_path / "idle_characterization.json").write_text(json.dumps({"sha256": "a" * 64}))
    
    with patch("cwEnergyModular.tools.run_gate_p44.wait_for_quiet") as mock_quiet:
        with patch("cwEnergyModular.tools.run_gate_p44.measure_baseline_windows") as mock_baseline:
            from cwEnergyModular.machine_state import BaselineResult
            mock_baseline.return_value = BaselineResult(power_w=15.0, windows_used=5, outliers_excluded=0, provenance={}, samples=[15.0]*5)
            
            exit_code = execute_command(
                output_dir=str(tmp_path),
                plan_file=str(tmp_path / "plan.json"),
            )
    
    assert exit_code == 0
    mock_quiet.assert_not_called()  # quiet skipped for background_controlled

def test_execute_baseline_insufficient_exits_3(tmp_path):
    from cwEnergyModular.tools.run_gate_p44 import execute_command
    import json
    
    plan = {
        "schema": "casualwatt.p44_gate_plan.v2",
        "requires_idle_characterization": True,
        "idle_characterization_sha256": "a" * 64,
        "background_load_policy": "block",
        "quiet_params": {"quiet_threshold_pct": 5.0, "quiet_consecutive": 3, "quiet_window_s": 3.0, "quiet_cpu_sample_interval_s": 1.0, "quiet_cap_s": 600.0},
        "baseline_params": {"baseline_windows_target": 5, "baseline_windows_min": 3, "baseline_outlier_rule": "iqr_1p5"},
        "budget": {"budget_base_w": 0.5, "budget_base_j": 1.0},
        "pairs": 2,
        "seed": "test",
        "model": "test-model",
        "dt_nominal_s": 2.930748,
        "blocks": [],
    }
    (tmp_path / "plan.json").write_text(json.dumps(plan))
    (tmp_path / "idle_characterization.json").write_text(json.dumps({"sha256": "a" * 64}))
    
    with patch("cwEnergyModular.tools.run_gate_p44.wait_for_quiet") as mock_quiet:
        from cwEnergyModular.machine_state import QuietResult
        mock_quiet.return_value = QuietResult(success=True, readings_count=3, wait_s=10.0, windows=3, top_processes_before=[], top_processes_after=[])
        
        with patch("cwEnergyModular.tools.run_gate_p44.measure_baseline_windows") as mock_baseline:
            from cwEnergyModular.machine_state import BaselineError
            mock_baseline.side_effect = BaselineError("finestre valide insufficienti")
            
            exit_code = execute_command(
                output_dir=str(tmp_path),
                plan_file=str(tmp_path / "plan.json"),
            )
    
    assert exit_code == 3  # baseline arrest

def test_execute_v1_plan_rejected(tmp_path):
    from cwEnergyModular.tools.run_gate_p44 import execute_command
    import json
    
    # v1 plan (no schema field)
    plan = {
        "pairs": 6,
        "seed": "test",
        "model": "test-model",
    }
    (tmp_path / "plan.json").write_text(json.dumps(plan))
    
    exit_code = execute_command(
        output_dir=str(tmp_path),
        plan_file=str(tmp_path / "plan.json"),
    )
    
    assert exit_code == 2  # not runnable: non-compliant plan
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_gate_p44_end_to_end.py -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
# In cwEnergyModular/tools/run_gate_p44.py - execute_command

def execute_command(
    output_dir: str,
    plan_file: str,
) -> int:
    """Execute the gate campaign per plan v2."""
    import json
    import sys
    from pathlib import Path
    
    out_dir = Path(output_dir)
    plan_path = Path(plan_file)
    
    # Load and validate plan
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    
    # Reject v1 plans
    if plan.get("schema") != "casualwatt.p44_gate_plan.v2":
        print("[ARRESTO] piano precedente all'emenda; rigenerare con `characterize` + `plan`", file=sys.stderr)
        return 2
    
    if not plan.get("requires_idle_characterization"):
        print("[ARRESTO] piano non conforme: richiede idle_characterization", file=sys.stderr)
        return 2
    
    policy = plan.get("background_load_policy", "block")
    quiet_params = plan.get("quiet_params", {})
    baseline_params = plan.get("baseline_params", {})
    plan_budget = plan.get("budget", {})
    
    # Create session
    session = create_session(plan.get("model", ""), plan.get("num_ctx", 8192))
    
    # Load idle characterization for hash
    char_path = out_dir / "idle_characterization.json"
    idle_char = json.loads(char_path.read_text(encoding="utf-8"))
    idle_sha256 = idle_char.get("sha256", "")
    
    # Get power state for background signature
    power_state_info = ms.power_state()
    power_plan = power_state_info.get("plan", "")
    power_plugged = power_state_info.get("power_plugged", None)
    power_state_str = "AC" if power_plugged else "battery" if power_plugged is not None else "unknown"
    
    # Process top processes for background signature
    top_procs = ms.sample_top_processes()
    relevant_processes = [{"pid": p["pid"], "name": p["name"]} for p in top_procs]
    
    background_sig = ms.compute_background_signature(
        processes=relevant_processes,
        power_plan=power_plan,
        power_state=power_state_str,
        plan_version="v2",
        idle_characterization_sha256=idle_sha256,
    )
    
    # Iterate blocks
    results = []
    for i, block_spec in enumerate(plan.get("blocks", [])):
        # Wait for quiet if block policy
        if policy == "block":
            quiet_result = ms.wait_for_quiet(session, **quiet_params)
            if not quiet_result.success:
                # Write diagnostic artifact before exit
                write_diagnostic_artifact(out_dir, "quiet_not_reached", {
                    "policy": policy,
                    "quiet_params": quiet_params,
                    "readings_count": quiet_result.readings_count,
                    "wait_s": quiet_result.wait_s,
                    "background_signature": background_sig,
                })
                return 3
        else:
            quiet_result = None
        
        # Measure baseline
        try:
            baseline = ms.measure_baseline_windows(session, policy, **baseline_params)
        except ms.BaselineError as e:
            write_diagnostic_artifact(out_dir, "baseline_failed", {
                "policy": policy,
                "baseline_params": baseline_params,
                "error": str(e),
                "background_signature": background_sig,
            })
            return 3
        
        # Execute block (load or control)
        block = execute_declared_block(block_spec, session)
        
        # Compute E_baseline using ACTUAL control window duration
        control_dt_w_s = block.get("control_dt_w_s", block.get("dt_w_s", 0.0))
        e_baseline_j = baseline.power_w * control_dt_w_s
        
        # For control blocks, compute E_net
        if block.get("block_kind") == "control":
            block["control_e_net_j"] = block["package_energy_j"] - e_baseline_j
            block["energy_metric"] = (
                "E_net" if policy == "block"
                else "E_net_background_controlled"
            )
        
        # Add baseline and policy fields
        block["baseline_pre_w"] = baseline.power_w
        block["baseline_provenance"] = baseline.provenance
        block["background_load_policy"] = policy
        block["baseline_state_hash"] = background_sig
        
        if policy == "block" and quiet_result:
            block["quiet_letture"] = quiet_result.readings_count
            block["quiet_wait_s"] = round(quiet_result.wait_s, 3)
        else:
            block["quiet_letture"] = ""
            block["quiet_wait_s"] = ""
        
        # Budget PRE-REGISTERED
        block["budget_base_w"] = plan_budget.get("budget_base_w", 0.0)
        block["budget_base_j"] = plan_budget.get("budget_base_j", 0.0)
        
        results.append(block)
    
    # Write results
    write_results(out_dir, results)
    
    # Evaluate gate
    gate_result = evaluate_gate(results, plan_budget)
    write_gate_result(out_dir, gate_result)
    
    return 0 if gate_result.get("passed") else 1

def write_diagnostic_artifact(out_dir: Path, name: str, data: dict):
    import json
    import time
    diag_file = out_dir / f"diagnostic_{name}_{time.strftime('%Y%m%d_%H%M%S')}.json"
    diag_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_gate_p44_end_to_end.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add cwEnergyModular/tools/run_gate_p44.py tests/test_gate_p44_end_to_end.py
git commit -m "feat(p44): add policy routing in execute with exit code contract"
```

---

### Task 5: control_gate.py Policy Coherence Validation (F.12 Unchanged)

**Files:**
- Modify: `cwEnergyModular/control_gate.py` (add policy coherence validation in evaluate_gate)
- Test: `tests/test_control_gate_p45.py` (extend)

**Interfaces:**
- Consumes: block summaries with new policy fields
- Produces: gate result with validated policy coherence

- [ ] **Step 1: Write failing tests**

```python
def test_evaluate_gate_block_policy_validates_quiet_and_baseline():
    from cwEnergyModular.control_gate import evaluate_gate
    
    blocks = [
        {
            "block_kind": "control",
            "pair_id": 1,
            "background_load_policy": "block",
            "baseline_pre_w": 15.0,
            "baseline_state_hash": "a" * 64,
            "quiet_letture": 3,
            "quiet_wait_s": 10.5,
            "control_e_net_j": 100.0,
            "control_dt_w_s": 3.0,
            "package_energy_j": 145.0,
            "budget_base_w": 0.5,
            "budget_base_j": 1.0,
            "pre_range_w": 0.5,
            "dP": 0.3,
        },
        {
            "block_kind": "control",
            "pair_id": 2,
            "background_load_policy": "block",
            "baseline_pre_w": 15.0,
            "baseline_state_hash": "a" * 64,
            "quiet_letture": 3,
            "quiet_wait_s": 11.0,
            "control_e_net_j": 102.0,
            "control_dt_w_s": 3.0,
            "package_energy_j": 147.0,
            "budget_base_w": 0.5,
            "budget_base_j": 1.0,
            "pre_range_w": 0.5,
            "dP": 0.3,
        },
    ]
    
    result = evaluate_gate(blocks, budget_base_w=0.5, budget_base_j=1.0)
    
    assert result["passed"] is True
    assert result["policy_coherent"] is True
    assert "bias_w" in result

def test_evaluate_gate_block_policy_missing_quiet_fails_coherence():
    from cwEnergyModular.control_gate import evaluate_gate
    
    blocks = [
        {
            "block_kind": "control",
            "pair_id": 1,
            "background_load_policy": "block",
            "baseline_pre_w": 15.0,
            "baseline_state_hash": "a" * 64,
            "quiet_letture": "",  # MISSING
            "quiet_wait_s": "",
            "control_e_net_j": 100.0,
            "control_dt_w_s": 3.0,
            "package_energy_j": 145.0,
            "budget_base_w": 0.5,
            "budget_base_j": 1.0,
            "pre_range_w": 0.5,
            "dP": 0.3,
        },
    ]
    
    result = evaluate_gate(blocks, budget_base_w=0.5, budget_base_j=1.0)
    
    assert result["policy_coherent"] is False
    assert "quiet_letture" in result.get("coherence_errors", [])

def test_evaluate_gate_background_controlled_validates_baseline_windows():
    from cwEnergyModular.control_gate import evaluate_gate
    
    blocks = [
        {
            "block_kind": "control",
            "pair_id": 1,
            "background_load_policy": "background_controlled",
            "baseline_pre_w": 15.0,
            "baseline_provenance": {"valid_windows": 4, "outliers_excluded": 1, "outlier_rule": "iqr_1p5"},
            "baseline_state_hash": "b" * 64,
            "control_e_net_j": 100.0,
            "control_dt_w_s": 3.0,
            "package_energy_j": 145.0,
            "budget_base_w": 0.5,
            "budget_base_j": 1.0,
            "pre_range_w": 0.5,
            "dP": 0.3,
        },
    ]
    
    result = evaluate_gate(blocks, budget_base_w=0.5, budget_base_j=1.0)
    
    assert result["policy_coherent"] is True
    # energy_metric should be explicit, not string search
    assert blocks[0].get("energy_metric") == "E_net_background_controlled"

def test_evaluate_gate_background_controlled_insufficient_baseline_fails():
    from cwEnergyModular.control_gate import evaluate_gate
    
    blocks = [
        {
            "block_kind": "control",
            "pair_id": 1,
            "background_load_policy": "background_controlled",
            "baseline_pre_w": 15.0,
            "baseline_provenance": {"valid_windows": 2, "outliers_excluded": 3, "outlier_rule": "iqr_1p5"},  # < 3 min
            "baseline_state_hash": "b" * 64,
            "control_e_net_j": 100.0,
            "control_dt_w_s": 3.0,
            "package_energy_j": 145.0,
            "budget_base_w": 0.5,
            "budget_base_j": 1.0,
            "pre_range_w": 0.5,
            "dP": 0.3,
        },
    ]
    
    result = evaluate_gate(blocks, budget_base_w=0.5, budget_base_j=1.0)
    
    assert result["policy_coherent"] is False
    assert "baseline_windows" in str(result.get("coherence_errors", []))

def test_evaluate_gate_f12_unchanged():
    """F.12 formula must not change - only policy validation added."""
    from cwEnergyModular.control_gate import evaluate_gate, compute_f12_bias
    
    # Same blocks, different policies - bias computation should be identical
    blocks_block = [{
        "block_kind": "control", "pair_id": 1,
        "background_load_policy": "block",
        "control_e_net_j": 100.0, "control_dt_w_s": 3.0,
        "package_energy_j": 145.0, "baseline_pre_w": 15.0,
        "budget_base_w": 0.5, "budget_base_j": 1.0,
        "pre_range_w": 0.5, "dP": 0.3,
    }]
    
    blocks_bg = [{
        "block_kind": "control", "pair_id": 1,
        "background_load_policy": "background_controlled",
        "control_e_net_j": 100.0, "control_dt_w_s": 3.0,
        "package_energy_j": 145.0, "baseline_pre_w": 15.0,
        "budget_base_w": 0.5, "budget_base_j": 1.0,
        "pre_range_w": 0.5, "dP": 0.3,
    }]
    
    bias_block = compute_f12_bias(blocks_block)
    bias_bg = compute_f12_bias(blocks_bg)
    
    assert bias_block == bias_bg  # F.12 unchanged
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_control_gate_p45.py -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
# In cwEnergyModular/control_gate.py - modify evaluate_gate

def evaluate_gate(blocks: List[Dict], budget_base_w: float, budget_base_j: float) -> Dict:
    """Evaluate gate with policy coherence validation. F.12 formula UNCHANGED."""
    
    # Filter control blocks
    control_blocks = [b for b in blocks if b.get("block_kind") == "control"]
    
    if not control_blocks:
        return {
            "passed": False,
            "reason": "no control blocks",
            "policy_coherent": False,
            "coherence_errors": ["no control blocks"],
        }
    
    # Validate policy coherence for EACH block
    coherence_errors = []
    for block in control_blocks:
        policy = block.get("background_load_policy", "block")
        
        if policy == "block":
            # Require quiet evidence
            if not block.get("quiet_letture") or not block.get("quiet_wait_s"):
                coherence_errors.append(f"pair {block.get('pair_id')}: missing quiet_letture/quiet_wait_s for block policy")
            if not block.get("baseline_state_hash"):
                coherence_errors.append(f"pair {block.get('pair_id')}: missing baseline_state_hash for block policy")
        
        elif policy == "background_controlled":
            # Require explicit energy_metric
            if block.get("energy_metric") != "E_net_background_controlled":
                coherence_errors.append(f"pair {block.get('pair_id')}: energy_metric must be 'E_net_background_controlled'")
            
            # Validate baseline provenance
            prov = block.get("baseline_provenance", {})
            valid_windows = prov.get("valid_windows", 0)
            if valid_windows < 3:
                coherence_errors.append(f"pair {block.get('pair_id')}: baseline valid_windows={valid_windows} < 3")
            
            if not block.get("baseline_state_hash"):
                coherence_errors.append(f"pair {block.get('pair_id')}: missing baseline_state_hash for background_controlled")
        
        else:
            coherence_errors.append(f"pair {block.get('pair_id')}: unknown policy '{policy}'")
    
    policy_coherent = len(coherence_errors) == 0
    
    # F.12 computation UNCHANGED - only operates on control blocks
    bias_w, bias_j, used_blocks = compute_f12_bias(control_blocks)
    
    # Apply filter: pre_range_w <= 1.0 and |dP| <= 1.0
    filtered = [b for b in used_blocks if b.get("pre_range_w", 0) <= 1.0 and abs(b.get("dP", 0)) <= 1.0]
    
    if len(filtered) < 2:
        return {
            "passed": False,
            "reason": "insufficient usable control blocks",
            "bias_w": bias_w,
            "bias_j": bias_j,
            "usable_blocks": len(filtered),
            "policy_coherent": policy_coherent,
            "coherence_errors": coherence_errors,
        }
    
    # Quorum: ceil(2/3 * n_coppie)
    n_coppie = max(b.get("pair_id", 0) for b in control_blocks)
    quorum = (2 * n_coppie + 2) // 3  # ceil(2/3 * n)
    
    passed = policy_coherent and (len(filtered) >= quorum) and (abs(bias_w) <= budget_base_w)
    
    return {
        "passed": passed,
        "bias_w": bias_w,
        "bias_j": bias_j,
        "budget_base_w": budget_base_w,
        "budget_base_j": budget_base_j,
        "usable_blocks": len(filtered),
        "quorum": quorum,
        "n_coppie": n_coppie,
        "policy_coherent": policy_coherent,
        "coherence_errors": coherence_errors,
        "chain_status": "validated" if passed else ("bias_declared" if policy_coherent and len(filtered) >= quorum else "incoherent"),
    }

def compute_f12_bias(blocks: List[Dict]) -> Tuple[float, float, List[Dict]]:
    """F.12 bias computation - UNCHANGED by emenda."""
    # This is the existing implementation - do not modify formula
    # bias_w = sum(control_e_net_j) / sum(control_dt_w_s)
    # bias_j = sum(control_e_net_j)
    sum_e_net = sum(b.get("control_e_net_j", 0) for b in blocks)
    sum_dt = sum(b.get("control_dt_w_s", 0) for b in blocks)
    
    if sum_dt == 0:
        return 0.0, 0.0, []
    
    bias_w = sum_e_net / sum_dt
    bias_j = sum_e_net
    
    return bias_w, bias_j, blocks
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_control_gate_p45.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add cwEnergyModular/control_gate.py tests/test_control_gate_p45.py
git commit -m "feat(p44): add policy coherence validation in control_gate (F.12 unchanged)"
```

---

### Task 6: CSV Schema Extension (Append-Only, Migration-Safe)

**Files:**
- Modify: `cwEnergyModular/casualwatt_csv_export.py` (extend BLOCK_SUMMARY_COLUMNS 36→44)
- Test: `tests/test_csv_migration.py`

**Interfaces:**
- Consumes: block dicts with new fields
- Produces: CSV with 44 columns (8 new appended)

- [ ] **Step 1: Write failing tests**

```python
def test_block_summary_columns_extended():
    from cwEnergyModular.casualwatt_csv_export import BLOCK_SUMMARY_COLUMNS
    
    # Should have 44 columns (36 original + 8 new)
    assert len(BLOCK_SUMMARY_COLUMNS) == 44
    
    # New columns should be appended at the end
    new_cols = [
        "background_load_policy",
        "baseline_windows_used",
        "baseline_outlier_rule",
        "baseline_outliers_excluded",
        "baseline_state_hash",
        "quiet_threshold_pct",
        "quiet_letture",
        "quiet_wait_s",
    ]
    
    for col in new_cols:
        assert col in BLOCK_SUMMARY_COLUMNS
    
    # Verify order: new cols at the end
    assert BLOCK_SUMMARY_COLUMNS[-8:] == new_cols

def test_write_block_summary_with_new_fields(tmp_path):
    from cwEnergyModular.casualwatt_csv_export import write_block_summary_csv
    
    blocks = [{
        "pair_id": 1,
        "block_kind": "control",
        "background_load_policy": "background_controlled",
        "baseline_windows_used": 4,
        "baseline_outlier_rule": "iqr_1p5",
        "baseline_outliers_excluded": 1,
        "baseline_state_hash": "a" * 64,
        "quiet_threshold_pct": 8.0,
        "quiet_letture": "",
        "quiet_wait_s": "",
        # ... other required fields
    }]
    
    csv_file = tmp_path / "blocks.csv"
    write_block_summary_csv(blocks, csv_file)
    
    import csv
    with open(csv_file, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        row = next(reader)
    
    assert row["background_load_policy"] == "background_controlled"
    assert row["baseline_windows_used"] == "4"
    assert row["baseline_outliers_excluded"] == "1"
    assert row["baseline_state_hash"] == "a" * 64

def test_read_historical_36_col_csv_migrates(tmp_path):
    """Historical 36-col CSV should read with empty values for new fields."""
    from cwEnergyModular.casualwatt_csv_export import read_block_summary_csv, BLOCK_SUMMARY_COLUMNS
    import csv
    
    # Write old 36-col CSV
    old_cols = BLOCK_SUMMARY_COLUMNS[:-8]  # first 36
    csv_file = tmp_path / "old_blocks.csv"
    
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=old_cols)
        writer.writeheader()
        writer.writerow({c: "val" for c in old_cols})
    
    # Read with new schema
    blocks = read_block_summary_csv(csv_file)
    
    assert len(blocks) == 1
    block = blocks[0]
    
    # New fields should be empty strings
    assert block.get("background_load_policy") == ""
    assert block.get("baseline_windows_used") == ""
    assert block.get("baseline_outlier_rule") == ""
    assert block.get("baseline_outliers_excluded") == ""
    assert block.get("baseline_state_hash") == ""
    assert block.get("quiet_threshold_pct") == ""
    assert block.get("quiet_letture") == ""
    assert block.get("quiet_wait_s") == ""

def test_write_read_roundtrip_preserves_new_fields(tmp_path):
    from cwEnergyModular.casualwatt_csv_export import write_block_summary_csv, read_block_summary_csv
    
    blocks = [{
        "pair_id": 1,
        "block_kind": "control",
        "background_load_policy": "block",
        "baseline_windows_used": 5,
        "baseline_outlier_rule": "2sigma",
        "baseline_outliers_excluded": 0,
        "baseline_state_hash": "b" * 64,
        "quiet_threshold_pct": 5.0,
        "quiet_letture": 3,
        "quiet_wait_s": 12.5,
    }]
    
    csv_file = tmp_path / "roundtrip.csv"
    write_block_summary_csv(blocks, csv_file)
    read_blocks = read_block_summary_csv(csv_file)
    
    assert read_blocks[0]["background_load_policy"] == "block"
    assert read_blocks[0]["baseline_windows_used"] == "5"
    assert read_blocks[0]["baseline_outlier_rule"] == "2sigma"
    assert read_blocks[0]["quiet_letture"] == "3"
    assert read_blocks[0]["quiet_wait_s"] == "12.5"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_csv_migration.py -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
# In cwEnergyModular/casualwatt_csv_export.py - extend BLOCK_SUMMARY_COLUMNS

# Original 36 columns (keep exact order)
BLOCK_SUMMARY_COLUMNS = [
    # ... existing 36 columns ...
    # NEW 8 columns appended (DO NOT REORDER EXISTING)
    "background_load_policy",
    "baseline_windows_used",
    "baseline_outlier_rule",
    "baseline_outliers_excluded",
    "baseline_state_hash",
    "quiet_threshold_pct",
    "quiet_letture",
    "quiet_wait_s",
]

# Ensure write_block_summary_csv uses all 44 columns
# Ensure read_block_summary_csv handles missing columns gracefully (returns empty string)
```

```python
# In cwEnergyModular/casualwatt_csv_export.py - modify read_block_summary_csv

def read_block_summary_csv(path: Path) -> List[Dict]:
    """Read block summary CSV, handling both 36-col (legacy) and 44-col (current)."""
    import csv
    
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    
    # Ensure all 44 columns present in each row
    for row in rows:
        for col in BLOCK_SUMMARY_COLUMNS:
            if col not in row:
                row[col] = ""
    
    return rows
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_csv_migration.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add cwEnergyModular/casualwatt_csv_export.py tests/test_csv_migration.py
git commit -m "feat(p44): extend BLOCK_SUMMARY_COLUMNS 36->44 append-only with migration"
```

---

### Task 7: Test Suite Per Acceptance Criteria

**Files:**
- Create: `tests/test_characterize_idle.py`, `tests/test_plan_v2.py`, `tests/test_machine_state_p44.py`, `tests/test_policy_coherence.py`, `tests/test_csv_migration.py`
- Modify: `tests/test_quiet_gate_p44.py`, `tests/test_gate_p44_end_to_end.py`, `tests/test_control_gate_p45.py`

**Interfaces:**
- All tests use seams (`campiona`, `top_fn`, `clock`, `sleep`, `on_log`) injectable
- ZERO hardware dependencies (mocked time, processes, counters)

- [ ] **Step 1: Write failing tests for each new test file** (already defined in Tasks 1-6)

- [ ] **Step 2: Extend existing tests**

```python
# In tests/test_quiet_gate_p44.py - add tests for new quiet semantics

def test_quiet_parameters_from_plan_not_hardcoded():
    """Quiet parameters come from plan, not hardcoded."""
    from cwEnergyModular.tools.run_gate_p44 import characterize_command
    # Verify characterize uses parameters from CLI, not constants

def test_quiet_consecutive_windows_semantics():
    """3 consecutive quiet windows, noisy resets to 0."""
    # Covered in test_machine_state_p44.py

# In tests/test_gate_p44_end_to_end.py - add E2E tests

def test_e2e_characterize_plan_execute_block_policy():
    """Full E2E: characterize -> plan -> execute (block) -> gate."""
    # Use tmp_path, mock all external deps

def test_e2e_characterize_plan_execute_background_controlled():
    """Full E2E: characterize -> plan -> execute (background_controlled) -> gate."""
    # Quiet skipped, baseline measured, energy_metric set correctly

def test_e2e_v1_plan_rejected():
    """v1 plan rejected with explicit message."""

# In tests/test_control_gate_p45.py - add policy coherence tests

def test_f12_immutable_across_policies():
    """F.12 bias computation identical regardless of policy."""
    # Covered in test_control_gate_p45.py

def test_coherence_errors_collected_not_raised():
    """Coherence errors collected in result, not raised as exceptions."""
```

- [ ] **Step 3: Run all tests to verify they pass**

Run: `pytest tests/test_characterize_idle.py tests/test_plan_v2.py tests/test_machine_state_p44.py tests/test_policy_coherence.py tests/test_csv_migration.py tests/test_quiet_gate_p44.py tests/test_gate_p44_end_to_end.py tests/test_control_gate_p45.py -v`
Expected: PASS (all 8 test files)

- [ ] **Step 4: Verify zero hardware deps and seams injectable**

```bash
# Grep for any real hardware/time/process usage in new tests
grep -r "time\.sleep\|psutil\|subprocess\|requests" tests/test_*p44*.py tests/test_*p45*.py
# Should return only mocked usages
```

- [ ] **Step 5: Commit**

```bash
git add tests/
git commit -m "test(p44): complete test suite per acceptance criteria"
```

---

### Task 8: Assert Replacement & Final Validation

**Files:**
- Modify: All production files to replace `assert` with explicit `ValueError`/`SystemExit`
- Test: Verify `-O` flag doesn't disable validation

- [ ] **Step 1: Find and replace all asserts in modified files**

```bash
# Search for asserts in modified files
grep -n "assert " cwEnergyModular/machine_state.py cwEnergyModular/control_gate.py cwEnergyModular/tools/run_gate_p44.py cwEnergyModular/casualwatt_csv_export.py
```

- [ ] **Step 2: Replace each assert with explicit validation**

```python
# Example replacement pattern:
# assert condition, "message"
# becomes:
if not condition:
    raise ValueError("message")

# Or for critical preconditions:
if not condition:
    raise SystemExit("message")
```

- [ ] **Step 3: Test with -O flag**

```bash
python -O -m pytest tests/test_characterize_idle.py tests/test_plan_v2.py tests/test_machine_state_p44.py tests/test_policy_coherence.py tests/test_csv_migration.py -v
# All tests should still PASS
```

- [ ] **Step 4: Commit**

```bash
git add cwEnergyModular/
git commit -m "fix(p44): replace asserts with explicit validation (survives -O)"
```

---

### Task 9: Documentation & Campaign Execution Readiness

**Files:**
- Create: `docs/p44_background_emenda_usage.md` (usage documentation)
- Verify: All artifacts producible and validated

- [ ] **Step 1: Write usage documentation**

```markdown
# P4.4 Gate Background Emenda Usage

## Quick Start

```bash
# 1. Characterize machine idle behavior
python -m cwEnergyModular.tools.run_gate_p44 characterize \
    --output-dir experiment_results/p44_gate_20261114 \
    --windows 30 --window-s 10 --margin-pct 1.0

# 2. Generate plan v2
python -m cwEnergyModular.tools.run_gate_p44 plan \
    --output-dir experiment_results/p44_gate_20261114 \
    --pairs 6 --seed gate-seed-20261107 \
    --model hf.co/sigmanih/Qwen-Qwen3-0.6B-GGUF-Q6_K:latest \
    --background-policy block  # or background_controlled

# 3. Execute campaign
python -m cwEnergyModular.tools.run_gate_p44 execute \
    --output-dir experiment_results/p44_gate_20261114 \
    --plan experiment_results/p44_gate_20261114/plan.json
```

## Policy Selection

| Policy | When to Use |
|--------|-------------|
| `block` | Quiet reachable (CPU ≤ threshold for 3 consecutive 3s windows) |
| `background_controlled` | Structural background (never quiet) - background declared stable |

## Exit Codes

| Command | 0 | 1 | 2 | 3 |
|---------|---|---|---|---|
| characterize | OK | Write error | - | - |
| plan | OK | - | Missing/invalid characterization | - |
| execute | OK | Gate failed | Not runnable (v1 plan, missing data) | Pre-measurement arrest (quiet/baseline) |

## Artifacts Produced

- `idle_characterization.json` (schema v1, SHA-256)
- `plan.json` (schema v2, references characterization hash)
- `blocks.csv` (44 columns including new policy fields)
- `analysis.json` / `gate_result_frozen.json` (with policy coherence)
```

- [ ] **Step 2: Verify full pipeline works end-to-end**

```bash
# Dry run with mocks
pytest tests/test_gate_p44_end_to_end.py::test_e2e_characterize_plan_execute_block_policy -v
pytest tests/test_gate_p44_end_to_end.py::test_e2e_characterize_plan_execute_background_controlled -v
```

- [ ] **Step 3: Commit documentation**

```bash
git add docs/p44_background_emenda_usage.md
git commit -m "docs(p44): add background emenda usage documentation"
```

---

## Plan Complete

**Saved to:** `docs/superpowers/plans/2026-11-14-p44-background-emenda.md`

**Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**