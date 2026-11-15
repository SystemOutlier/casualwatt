# Emenda P4.4 — Background Controlled Campaign Design

> **Spec for:** P4.4 gate background handling emenda
> **Date:** 2026-11-14
> **Status:** Approved with emendments (Sections 1-3)

---

## 1. Problem Statement

The P4.4 gate campaign (2026-11-07/08/09) failed because the machine never reaches the quiet precondition: structural background load of 5-30% CPU (peaks to 46.9%) persists across all 200+ readings within the 600s cap. The current `quiet_threshold_pct = 5.0` and `quiet_consecutive = 3` are unreachable.

**Root cause:** The quiet precondition treats background as transient noise, but on this machine it's structural.

**Requirement:** Allow CasualWatt to operate in any background condition while maintaining measurement rigor and preserving the load/control pair design of F.12.

---

## 2. Architecture Overview

### Two-Mode Design

| Policy | Precondition | Baseline | Output Metric | Aggregability |
|--------|--------------|----------|---------------|---------------|
| `block` | 3 consecutive CPU windows ≤ `quiet_threshold_pct` (3s each); cap 600s; noisy window resets count | Coeval, in same quiet state | `E_net` | Comparable with historical gate |
| `background_controlled` | Background declared stable: same process set/CPU config for ≥ `background_stability_windows`; no undeclared variation | Coeval, ≥3 non-overlapping windows in same background state | `E_net_background_controlled` | NOT aggregatable to `E_net` without separate sensitivity analysis |

### Key Principles

1. **F.12 criterion is IMMUTABLE** — only policy coherence validation added before applying standard criterion
2. **Budget vs Baseline distinction**: `budget_base_w/j` = pre-registered tolerance threshold (measured once before campaign); baseline = per-block noise estimate for E_net calculation
3. **Provenance chain**: `characterize` → `idle_characterization.json` (SHA-256) → `plan.json` v2 (schema `casualwatt.p44_gate_plan.v2`) → `execute`
4. **Controlled breaking change**: v1 plans non-executable, campaign 20261114 archived (not converted)

---

## 3. Section 1: Protocol Changes (Approved with Emendations)

### 3.1 Renamed Policy

- `background_controlled` ≠ "quiet not required"
- `background_controlled` = "background declared stable, different precondition verified"

### 3.2 control_gate.py Changes

- `evaluate_gate()` does NOT change F.12 formula
- Validates policy coherence: for `block` → quiet satisfied + baseline in same state; for `background_controlled` → ≥3 valid baseline windows, same background state, outlier filter applied, labeled `E_net_background_controlled`
- Policy is metadata, not a branch changing thresholds/quorum/budget

### 3.3 CSV Schema (Append-only)

**BLOCK_SUMMARY_COLUMNS: 36 → 44** (8 new columns appended):
```
background_load_policy
baseline_windows_used
baseline_outlier_rule
baseline_outliers_excluded
baseline_state_hash
quiet_threshold_pct
quiet_letture
quiet_wait_s
```

---

## 4. Section 2: Implementation Details (Approved with Emendations)

### 4.1 wait_for_quiet() in machine_state.py

**Parameters from plan (not hardcoded):**
- `quiet_window_s = 3.0` (window duration)
- `quiet_cpu_sample_interval_s = 1.0` (CPU sample interval within window)
- `quiet_consecutive_windows = 3` (consecutive quiet windows required)
- `quiet_cap_s = 600.0` (max wait time)

**Semantics:**
- A window is quiet if `background_load_from_samples(samples, threshold) == False`
- Quiet reached after 3 consecutive quiet windows
- A noisy window resets the count to 0
- Extend existing `_attendi_quiete()` preserving seams: `campiona`, `top_fn`, `clock`, `sleep`, `on_log`

### 4.2 Baseline Measurement

**Fixed target (NO cherry-picking):**
- `baseline_windows_target = 5`
- `baseline_windows_min = 3`
- `baseline_outlier_rule = "iqr_1p5"` (or "2sigma")

**Process:**
1. Measure exactly `baseline_windows_target` windows
2. Apply declared outlier filter
3. Use ALL valid windows (no "use best")
4. If valid < `baseline_windows_min` → block unusable → ARRESTO (exit 3)

**Energy baseline formula:**
```
E_baseline = P_baseline_mean * block["control_dt_w_s"]
```
where `block["control_dt_w_s"]` is the ACTUAL control window duration, NOT the baseline window duration.

### 4.3 run_block() Integration (NOT parallel pipeline)

```python
def run_block(block_spec, session, policy, quiet_params,
              baseline_params, plan_budget):
    if policy == "block":
        quiet = wait_for_quiet(session, **quiet_params)
        if not quiet.success:
            raise QuietNotReachedError("quiete non raggiunta entro quiet_cap_s")

    baseline = measure_baseline_windows(session, policy, **baseline_params)
    block = execute_declared_block(block_spec, session)

    e_baseline_j = baseline.power_w * block["control_dt_w_s"]

    if block["block_kind"] == "control":
        block["control_e_net_j"] = (
            block["package_energy_j"] - e_baseline_j
        )
        block["energy_metric"] = (
            "E_net" if policy == "block"
            else "E_net_background_controlled"
        )

    block["baseline_pre_w"] = baseline.power_w
    block["baseline_provenance"] = baseline.to_dict()
    block["background_load_policy"] = policy
    block["quiet_letture"] = quiet.readings_count if policy == "block" else ""
    block["quiet_wait_s"] = quiet.wait_s if policy == "block" else ""

    # Budget PRE-REGISTERED, NOT recalculated from baseline
    block["budget_base_w"] = plan_budget["budget_base_w"]
    block["budget_base_j"] = plan_budget["budget_base_j"]

    return block
```

### 4.4 Validation (NO assert)

- Replace `assert` with explicit `ValueError`/`SystemExit` (asserts disabled with `-O`)
- Validate ALL blocks, not just controls
- For `block` policy: require `quiet_letture` and `baseline_state_hash`
- For `background_controlled`: explicit `energy_metric` field, not string search

### 4.5 background_signature

```python
components = {
    "processes": tuple(sorted(
        (int(p["pid"]), str(p["name"]))
        for p in relevant_processes
    )),
    "power_plan": power_plan,
    "power_state": power_state,
    "plan_version": plan_version,
    "idle_characterization_sha256": idle_characterization_sha256,
}
signature = hashlib.sha256(
    json.dumps(components, sort_keys=True, separators=(",", ":")).encode()
).hexdigest()
```
- NO CPU%, NO temperature in signature (diagnostic only)
- Full SHA-256 (not truncated)

---

## 5. Section 3: Exit Codes, Errors, Tests (Approved with Emendations)

### 5.1 Exit Code Contract

| Command / Condition | Code | Meaning |
|---|---:|---|
| `characterize` success | 0 | Characterization written, hash computed |
| `characterize` failure | 1 | Environmental, read, or write error |
| `plan` success | 0 | Plan written and frozen |
| `plan` rejected | 2 | Characterization missing, invalid, hash mismatch, or incoherent plan |
| `execute` success | 0 | Campaign completed, gate evaluated |
| `execute` gate failed | 1 | Campaign completed, F.12 not passed |
| `execute` not runnable | 2 | Quorum or data missing |
| `execute` pre-measurement arrest | 3 | Quiet not reached, invalid baseline, non-compliant plan, output exists |

**Key:** `QuietNotReachedError` and `BaselineError` → ALWAYS exit 3 (validity arrest before/during measurement), not exit 1.

### 5.2 BaselineError Handling

- `BaselineError` → ARRESTO, exit 3
- NO block substitution (K=1 substitution is for counter/request failures, not invalid baseline)
- NO usable measurement row
- Diagnostic artifact written before exit
- Reason recorded in `analysis.json`, `gate_result_frozen.json`, report with: policy, measured windows, valid windows, outlier rule, background signature, arrest reason

### 5.3 Atomic Characterization Write

```text
1. Write idle_characterization.json.tmp
2. Compute SHA-256 of final file
3. Insert hash in manifest
4. Atomic rename .tmp → .json
```
- If target exists → refuse unless `--force` explicit
- Consistent with `execute` rule: existing output not appended/overwritten

### 5.4 Test Acceptance Criteria (NO target counts)

- All existing tests in `test_quiet_gate_p44.py`, `test_gate_p44_end_to_end.py`, `test_control_gate_p45.py` pass WITHOUT semantic changes to F.12
- Every new rule: ≥1 positive test, ≥1 negative test, ≥1 provenance test
- ZERO hardware deps (no real hardware, real time, real processes, real counter)
- Seams `campiona`, `top_fn`, `clock`, `sleep`, `on_log` remain injectable
- E2E tests verify order: characterize → plan → quiet/baseline → block → gate
- Migration tests: historical 36-col CSV read and migrated to 44-col with empty cells for new fields

### 5.5 Versioning (Controlled Breaking Change)

```json
{
  "schema": "casualwatt.p44_gate_plan.v2",
  "requires_idle_characterization": true,
  "background_load_policy": "block"
}
```

- v1 plans archived, NOT executable with new runner
- `plan` produces ONLY v2 plans
- `execute` rejects v1 with explicit message: "piano precedente all'emenda; rigenerare con `characterize` + `plan`"
- Campaign 20261114 archived, NOT converted

---

## 6. Files to Modify

### Production Code
- `cwEnergyModular/machine_state.py` — add `wait_for_quiet()`, `measure_baseline_windows()`, `compute_background_signature()`
- `cwEnergyModular/tools/run_gate_p44.py` — add `characterize` command, hash validation, policy routing, exit codes
- `cwEnergyModular/control_gate.py` — add policy coherence validation in `evaluate_gate()`, keep F.12 immutable
- `cwEnergyModular/casualwatt_csv_export.py` — extend `BLOCK_SUMMARY_COLUMNS` 36→44 (append-only)

### New Artifacts
- `idle_characterization.json` (schema v1)
- `plan.json` v2 (schema `casualwatt.p44_gate_plan.v2`)

### Tests
- `tests/test_quiet_gate_p44.py` — extend for new quiet/baseline logic
- `tests/test_gate_p44_end_to_end.py` — E2E with both policies
- `tests/test_control_gate_p45.py` — policy coherence validation
- New: `tests/test_characterize_idle.py`, `tests/test_baseline_measurement.py`, `tests/test_policy_coherence.py`, `tests/test_csv_migration.py`

---

## 7. Implementation Order

1. **Characterize command** (`run_gate_p44.py characterize`) + idle characterization schema + atomic write
2. **Plan v2 schema** + hash validation in `plan` command
3. **machine_state.py** extensions: `wait_for_quiet()`, `measure_baseline_windows()`, `compute_background_signature()`
4. **Policy routing** in `run_gate_p44.py execute` + exit code contract
5. **control_gate.py** policy coherence validation (F.12 unchanged)
6. **CSV columns** extension (append-only, migration-safe)
7. **Test suite** per acceptance criteria
8. **Run campaign**: v1 if quiet reachable, v2 if background structural