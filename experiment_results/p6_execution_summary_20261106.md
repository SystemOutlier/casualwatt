# P6 Execution Summary — 2026-11-06

## P6.1 Pavimento tempo a muro (wall-clock time floor)
- **Status**: DONE (arithmetic, no execution needed)
- Pavimento sole finestre idle: 9.180 s = 2 h 33 min
- 39 blocchi campagna principale × 180 s = 7.020 s = 1 h 57 min
- 12 blocchi gate P4.4 × 180 s = 2.160 s = 36 min
- Settling worst case: 39 × 240 s = 9.360 s = 2 h 36 min (campagna), 12 × 240 s = 2.880 s = 48 min (gate)
- Costo passaggio 3→6 coppie: 1.080 s = 18 min pavimento + 1.440 s = 24 min settling

## P6.2 Pilota (pilot obligations)
- **Status**: DONE (executed)
- Ran benchmark with qwen2.5:0.5b (3 prompts): 3 records, 0 errors
- Ran benchmark with gemma2:9b (3 prompts): 3 records, 0 errors
- Ran benchmark with qwen2.5:0.5b (3 prompts) for CodeCarbon comparison: 3 records, 0 errors
- Idle calibration: P_idle = 9.74 W (median of [9.05, 9.74, 9.88] W)
- EMI counter: device CPU selected by metadata, PKG channel index 0
- CSV updated with cumulative results

## P6.3 Audit idle
- **Status**: DONE (executed, PASSED stability check — second run with 120s initial settling)
- 5 windows of 30s each, 30s wait between, 120s initial settling
- Results: P_idle = [5.88, 5.02, 5.04, 5.03, 5.05] W
- Range: 0.86 W < 1.0 W threshold
- **CONCLUSION**: Machine IS stationary at rest. Campaign CAN proceed.
- Note: First window slightly higher (settling), last 4 windows within 0.03 W.

## P6.4 Simulazione Monte Carlo
- **Status**: DONE (probes executed)
- montecarlo_protocollo_p64_probe.py: 5/5 verifications passed
- condizionamento_disegno_probe.py: 5/5 verifications passed
- semi_range_concentrazione_pesi_probe.py: 5/5 verifications passed
- u_edge_interpolazione_probe.py: 5/5 verifications passed (after PYTHONIOENCODING=utf-8 fix)
- inviluppo_e_budget_pred_probe.py: 5/5 verifications passed

## P6.6 Prova attribuzione ripetibile
- **Status**: DONE (pre-pilot complete, band frozen, 10 configurations executed)
- Option C (pre-pilot of repeatability) adopted
- Pre-pilot executed: 3 valid phases (prep-r3, prep-r5, prep-r6)
- Frozen band: B_abs = 0.6, B_rel = 1.1 (20% margin above max observed)
- Full proof: 10 configurations x 3 prompt executed (qwen2.5:0.5b, gemma2:9b, qwen2.5:1.5b, phi3:mini, qwen2.5:7b, gemma2:2b, llama3.2:3b, smollm2:1.7b, deepseek-r1:1.5b, tinyllama:latest), 0 errori

## CodeCarbon Comparison
- **Status**: DONE
- CodeCarbon emissions: 0.000304 kg CO2eq
- Elapsed time: 104.6 s
- CasualWatt E_ollama: 21.17-30.45 J per prompt
- CodeCarbon provides aggregate energy estimate, CasualWatt provides per-prompt attribution

## GPU Fixture Identity Fix
- **Status**: DONE
- Fixture GPU allineate al contratto di identita' (UUID): fake con
  get_uuid/get_amd_uuid, provenienza `identity-unavailable` nei test P2
- Root cause: fake GPU monitor classes missing get_uuid/get_amd_uuid/get_bdf methods
- 73 GPU tests pass across 5 test files

## Test Suite Status
- 886 node IDs raccolti, 883 passati, 4 saltati (3 RAPL, 1 modulo ecologits), 0 falliti
- Misurato il 06-11 sera con `pytest cwEnergyModular -q` dopo la pulizia
  delle `__pycache__` stantie (che producevano falsi fallimenti)
