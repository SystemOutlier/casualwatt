# Prototipi e Script Storici

Questa cartella contiene script prototipo e versioni iniziali sviluppate durante l'esplorazione del problema della misurazione energetica di LLM locali.

## File presenti

### `ollama_llama_server.py`

**Script prototipo** per tracciamento energia Ollama su Windows 11 (sviluppato prima di CasualWatt).

#### Cosa fa

Stima il consumo energetico di Ollama usando un **power model TDP-based**:

```python
ollama_power_watts = power_idle + (ollama_cpu_percent / 100) * (tdp_watts - power_idle)
```

Dove:
- `power_idle = 10W` (stima fissa hardcoded)
- `tdp_watts = 45W` (TDP nominale i9-13900HK)
- `ollama_cpu_percent` = CPU% dei processi Ollama via psutil

#### Caratteristiche

- ✓ Rileva sia `ollama.exe` che `ollama_llama_server.exe`
- ✓ Usa psutil per CPU% e processo tracking
- ✓ Calcola energia stimata in Joule
- ✓ Monitoraggio in tempo reale con output console

#### Limiti fondamentali

Questo approccio è una **STIMA**, non una misura reale:

1. **Relazione non lineare**: La potenza CPU non è lineare con CPU%
   - A 50% CPU%, la potenza non è 50% del TDP
   - Dipende da frequenza, voltaggio, efficienza termica

2. **TDP ≠ potenza reale**: Il TDP è il massimo sostenuto, non la potenza tipica
   - i9-13900HK: TDP 45W, ma può andare da 8W (idle) a 115W (PL2 turbo)
   - Lo script usa 45W fisso, ma la potenza reale varia continuamente

3. **Nessuna misura hardware**: Non legge alcun contatore reale
   - Non sa quanta energia sta VERAMENTE consumando la CPU
   - Può solo "indovinare" basandosi su CPU%

4. **Nessuna calibrazione empirica**: 
   - Idle fisso a 10W (non calibrato sulla macchina reale)
   - Nessuna misurazione dello stato di riposo

5. **Nessuna separazione fasi**:
   - Non distingue prefill da decode
   - Non scorpora LLM Judge

6. **Accuracy bassa**: ~30-40% di errore (tipico dei power model TDP-based)

#### Confronto con CasualWatt

| Caratteristica | Questo script | CasualWatt |
|---|---|---|
| **Tipo** | Stima TDP-based | Misura hardware reale |
| **Sorgente** | `psutil.cpu_percent()` | LHM "CPU Package" / RAPL |
| **Formula** | `idle + cpu% * (TDP - idle)` | Integrazione trapezoidale sensori reali |
| **Accuracy** | Bassa (~30-40% errore) | Alta (<5% errore) |
| **Calibrazione idle** | Fissa (10W hardcoded) | Empirica (3 finestre ≥30s, mediana) |
| **Attribuzione processo** | CPU% diretto | CPU time share su energia REALE |
| **Separazione prefill/decode** | No | Sì (via latenze Ollama) |
| **Judge scorporation** | No | Sì |
| **Validazione scientifica** | Nessuna | Cross-platform, wattmetro esterno |

#### Valore storico

Questo script dimostra il **percorso evolutivo** che ha portato a CasualWatt:

1. **Fase 1**: "Volevo misurare l'energia di Ollama"
2. **Fase 2**: "Ho provato con stima TDP-based" (questo script)
3. **Fase 3**: "Ho capito che è inaccurato"
4. **Fase 4**: "Ho studiato CodeCarbon, EnviroLLM, py-power-profile"
5. **Fase 5**: "Ho sviluppato CasualWatt con misura hardware reale"

La genesi è documentata in:
- [DECISIONI.md - DM-1](../Tesi-latex/qoder-bozza/DECISIONI.md) (CodeCarbon scartato per stima)
- [DECISIONI.md - DM-5](../Tesi-latex/qoder-bozza/DECISIONI.md) (EnviroLLM confrontato)
- [STRUTTURA.md - §4.11](../Tesi-latex/qoder-bozza/STRUTTURA.md) (Genesi della scelta)

#### Perché non è stato integrato in CasualWatt

CasualWatt è **intrinsecamente superiore** sotto ogni aspetto:

- ✓ Misura REALE (non stima)
- ✓ Calibrazione empirica (non hardcoded)
- ✓ Attribuzione corretta (CPU time share su energia reale)
- ✓ Separazione fasi (prefill/decode)
- ✓ Judge scorporation
- ✓ Validazione scientifica

Integrare questo script avrebbe **degradato** la qualità di CasualWatt da "misura hardware" a "stima TDP".

#### Esecuzione (solo per riferimento storico)

```bash
cd CWProject
python prototypes/ollama_llama_server.py
```

Output tipico:
```
Inizio monitoraggio su Windows 11 per i processi Ollama (10s)...
TDP Nominale impostato: 45.0W
| Carico Ollama: 234.5% | Assorbimento Stimato: 28.32W | Joule: 28.3200J
| Carico Ollama: 312.8% | Assorbimento Stimato: 35.67W | Joule: 35.6700J
...
------------------------------------------------------------
MONITORAGGIO TERMINATO.
Energia totale stimata per Ollama: 285.42 Joule
```

**Nota**: I valori sono STIME, non misure reali. L'errore può essere ±30-40%.

## Conclusione

Questa cartella serve come **archivio storico** dell'evoluzione del progetto CasualWatt.

Gli script qui contenuti:
- ✓ Documentano il percorso di sviluppo
- ✓ Mostrano i limiti degli approcci TDP-based
- ✓ Giustificano la scelta di CasualWatt (misura hardware)
- ✗ NON devono essere usati per misurazioni scientifiche

Per misurazioni reali, usare **CasualWatt** (`cwEnergyModular/`).
