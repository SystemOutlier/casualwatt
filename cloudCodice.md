# SPECIFICA METODOLOGICA E IMPLEMENTATIVA: MODELLO CLOUD (E_cloud)
# Framework: CasualWatt v4 / GreenAgentTracker
# Target Repository: cwEnergyModular / energy/cloud_energy.py & cloud_estimator.py

---

## 1. QUADRO TEORICO E FORMALIZZAZIONE SCIENTIFICA

La stima dell'impronta termodinamica remota nei Data Center ($E_{\text{cloud}}$) implementa un'architettura Multi-Tier a disaccoppiamento di fase.
Il calcolo distingue nettamente le due fasi fondamentali dell'inferenza nei modelli di linguaggio causali (Transformer-based):

1. **Fase di Prefill ($n_{\text{in}}$):** Elaborazione parallela del prompt. Operazione strettamente Compute-Bound, limitata dalla potenza di calcolo pura dei Tensor Core della GPU ($FLOPs$).
2. **Fase di Decoding ($n_{\text{out}}$):** Generazione sequenziale e autoregressiva dei token. Operazione strettamente Memory-Bandwidth Bound, limitata dal throughput della memoria VRAM ($GB/s$).

### 1.1 Equazione Generale Multi-Tier

$$\begin{aligned} E_{\text{cloud}} = \begin{cases} E_{\text{EcoLogits\_LCA}} & \text{Tier 1: Modello e Provider catalogati su EcoLogits} \\ E_{\text{Analitico\_Fasi}}(n_{\text{in}}, n_{\text{out}}, N_{\text{active}}) & \text{Tier 2: Provider non censito / Fallback Analitico Calibrato} \\ \texttt{None} & \text{Tier 3: Telemetria e Stima non disponibili (Registrato come "N/A")} \end{cases} \end{aligned}$$

---

## 2. GERARCHIA MULTI-TIER DI STIMA

### Tier 1: Intercettazione Diretta EcoLogits (LCA Standard ISO 14044)
- **Logica:** Intercetta l'impronta energetica in kWh stimata dal client EcoLogits per i provider ufficialmente registrati (OpenAI, Anthropic, Mistral, Cohere, Google, HuggingFace).
- **Conversione Unità:** $E_{\text{cloud\_J}} = E_{\text{EcoLogits\_kWh}} \times 3.6 \times 10^6 \quad [\text{Joule}]$
- **Infrastruttura (PUE):** EcoLogits integra già internamente il Power Usage Effectiveness ($PUE = 1.09 - 1.20$) dell'infrastruttura hyperscale target. È severamente VIETATO riapplicare il PUE un secondo tempo.
- **Asimmetria Metrologica sul Gate G3:** Poiché EcoLogits intercetta nativamente l'energia calcolata sui token di output ($n_{\text{out}}$) e la latenza di server, l'esportatore registra la flag diagnostica:
  `cloud_input_tokens_included = false`

### Tier 2: Fallback Analitico per Fasi (SweetSpot / Model-Size Scaled)
Per i provider non censiti dal catalogo nativo EcoLogits (es. Groq LPU, OpenRouter proxy), l'engine attiva il modello analitico disaggregato:

$$E_{\text{cloud\_Analitico}} = PUE \cdot \left( E_{\text{prefill}}(n_{\text{in}}, N_{\text{active}}) + E_{\text{decode}}(n_{\text{out}}, N_{\text{active}}) \right) \quad [\text{Joule}]$$

Dove:
- **Prefill (Compute-Bound):** $E_{\text{prefill}} = n_{\text{in}} \cdot \left( \gamma_{\text{prefill}} \cdot N_{\text{active}} \right)$
- **Decoding (Memory-Bandwidth Bound):** $E_{\text{decode}} = n_{\text{out}} \cdot \left( \gamma_{\text{decode}} \cdot N_{\text{active}} \right)$
- **$PUE$ Nominal Default:** $1.20$ (Data center Hyperscale).
- **Coefficienti di Intensità ($N_{\text{active}}$):** Scalati linearmente sui parametri fisicamente attivi durante il forward pass (es. $\gamma_{\text{prefill}} = 1.2 \times 10^{-9} \text{ J/token/parametro}$, $\gamma_{\text{decode}} = 4.8 \times 10^{-9} \text{ J/token/parametro}$).

#### Regola MoE (Mixture-of-Experts)
Nei modelli con attivazione sparsa dei parametri (es. Mixtral 8x7B, DeepSeek-V3), la grandezza $N_{\text{active}}$ è espressa rigorosamente come:

$$N_{\text{active}} = N_{\text{total}} \cdot \frac{E_{\text{act}}}{E_{\text{tot}}}$$

*Esempio:* Per Mixtral 8x7B ($N_{\text{total}} = 46.7\text{B}$, $2$ esperti attivi su $8$), $N_{\text{active}} = 12.9\text{B}$. L'uso dell'intero conteggio $N_{\text{total}}$ è vietato per evitare sovrastime fino a $11.17\times$.

---

## 3. REGOLA RIGIDA DI NON-FALSIFICAZIONE (Gestione None vs 0.0 J)

1. **Zero Legittimo ($0.0\text{ J}$):** Ammesso ESCLUSIVAMENTE per l'energia di rete in modalità locale (`mode == "local"`), con confine dichiarato `"not-applicable (local mode)"`.
2. **Dato Cloud Mancante ($\texttt{None}$ / `"N/A"`):** Se sia il Tier 1 sia il Tier 2 falliscono o l'endpoint non è raggiungibile:
   - `cloud_energy_j = None` (scritto come `"N/A"` sul CSV).
   - `end_to_end_energy_j = None` (scritto come `"N/A"` sul CSV). Non deve MAI essere calcolato come somma parziale ingannevole ($E_{\text{locale}} + 0.0$).
   - `ece_per_joule = "N/A"` e `epcl_j_per_link = "N/A"`.
   - `cloud_notes` appende: `"Stima cloud non disponibile: metrics invalidated to prevent zero-cost bias"`.

---

## 4. SPECIFICA D'IMPLEMENTAZIONE PYTHON (cwEnergyModular)

```python
from dataclasses import dataclass
from typing import Optional, Dict, Any

@dataclass
class CloudEnergyResult:
    energy_j: Optional[float]
    provider: str
    model_name: str
    tier_used: str  # "Tier1_EcoLogits", "Tier2_Analytic_SweetSpot", "Unavailable"
    input_tokens: int
    output_tokens: int
    input_included: bool
    pue_applied: float
    notes: str

class CloudEnergyEstimator:
    """
    Stima l'energia dei Data Center remoti (E_cloud) disaccoppiando 
    Prefill (Compute-bound) e Decoding (Memory-bandwidth bound).
    """
    
    # Range di sensibilità coefficienti base (Joule / Token / Miliardo di parametri)
    GAMMA_PREFILL_PER_B = 1.2e-3   # Prefill: ~0.0012 J/token/B (Compute-bound)
    GAMMA_DECODE_PER_B  = 4.8e-3   # Decode:  ~0.0048 J/token/B (Memory-bound)
    DEFAULT_PUE = 1.20

    def estimate(
        self, 
        provider: str, 
        model_name: str, 
        n_in: int, 
        n_out: int, 
        n_active_params_b: Optional[float] = None,
        ecologits_raw_kwh: Optional[float] = None
    ) -> CloudEnergyResult:
        
        # --- TIER 1: ECOLOGITS DIRECT INTERCEPT ---
        if ecologits_raw_kwh is not None and ecologits_raw_kwh > 0.0:
            energy_j = round(ecologits_raw_kwh * 3.6e6, 6)
            return CloudEnergyResult(
                energy_j=energy_j,
                provider=provider,
                model_name=model_name,
                tier_used="Tier1_EcoLogits",
                input_tokens=n_in,
                output_tokens=n_out,
                input_included=False, # EcoLogits gate G3 asymmetry flag
                pue_applied=1.00,     # Internamente già incluso in EcoLogits
                notes="LCA EcoLogits intercept (ISO 14044); input tokens excluded from native model"
            )

        # --- TIER 2: ANALYTIC FALLBACK (SWEETSPOT DISAGGREGATED) ---
        if n_active_params_b is not None and n_active_params_b > 0:
            e_prefill = n_in * (self.GAMMA_PREFILL_PER_B * n_active_params_b)
            e_decode  = n_out * (self.GAMMA_DECODE_PER_B * n_active_params_b)
            e_cloud_raw = e_prefill + e_decode
            e_cloud_total = round(e_cloud_raw * self.DEFAULT_PUE, 6)
            
            return CloudEnergyResult(
                energy_j=e_cloud_total,
                provider=provider,
                model_name=model_name,
                tier_used="Tier2_Analytic_SweetSpot",
                input_tokens=n_in,
                output_tokens=n_out,
                input_included=True,
                pue_applied=self.DEFAULT_PUE,
                notes=f"Analytic phase-disaggregated fallback (N_active={n_active_params_b}B, PUE={self.DEFAULT_PUE})"
            )

        # --- TIER 3: SAFE FALLBACK (DATA MISSING) ---
        return CloudEnergyResult(
            energy_j=None,
            provider=provider,
            model_name=model_name,
            tier_used="Unavailable",
            input_tokens=n_in,
            output_tokens=n_out,
            input_included=False,
            pue_applied=1.00,
            notes="Cloud telemetry unavailable: returned None to prevent zero-cost falsification"
        )