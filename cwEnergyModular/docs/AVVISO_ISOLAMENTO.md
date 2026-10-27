# Avviso di Isolamento Sistema per Benchmark Energetico

## Implementazione

Aggiunto avviso professionale all'avvio del benchmark per garantire misure accurate. L'avviso informa l'utente di non utilizzare il PC durante il benchmark.

## File modificati

### 1. `benchmark_unified.py` (linee 590-610)

Avviso visualizzato nel log all'inizio di `run_unified_benchmark()`:

```
======================================================================
AVVISO: BENCHMARK ENERGETICO IN CORSO
======================================================================
Per garantire misure accurate, NON utilizzare il PC durante il benchmark.
Evitare di:
  • Aprire applicazioni (browser, editor, file explorer)
  • Spostare finestre o ridimensionare finestre
  • Copiare file o scaricare contenuti
  • Eseguire altri programmi in background
  • Modificare impostazioni di sistema

Il benchmark misura il consumo energetico reale del package CPU.
Qualsiasi attività aggiuntiva altera le misure e invalida i risultati.
Durata stimata: ~X s (calibrazione + Y query)
======================================================================
```

### 2. `gui/benchmark_panel.py` (linee 500-515)

Avviso visualizzato nella GUI prima di avviare il worker del benchmark:

```
======================================================================
⚠ ATTENZIONE: BENCHMARK ENERGETICO IN CORSO
======================================================================
Per garantire misure accurate, NON utilizzare il PC durante il benchmark.
Evitare di aprire applicazioni, spostare finestre, copiare file o eseguire
altri programmi. Qualsiasi attività aggiuntiva altera le misure energetiche.
Il benchmark durerà alcuni minuti (calibrazione + query).
======================================================================
```

### 3. `gui/benchmark_panel.py` (linea 588)

Avviso durante la calibrazione idle (già presente, migliorato):

```
Calibrazione idle EMPIRICA: NON generare carico sul PC… 
(durata prevista: ~92 s = stabilizzazione + 3 finestre da 30 s; progressivo sotto)
```

## Motivazione scientifica

### Perché l'isolamento è critico

1. **Misura del package CPU**: CasualWatt misura l'energia reale del package CPU via:
   - Windows: contatore cumulativo EMI (energy/emi_backend.py)
   - Linux: Contatori RAPL (`/sys/class/powercap/intel-rapl/`)

2. **Attribuzione per processo**: L'energia viene attribuita a Ollama in base alla quota di tempo CPU:
   ```
   E_ollama = E_active * (dt_cpu_ollama / dt_cpu_busy)
   ```

3. **Impatto di attività esterne**: Se l'utente apre un browser o copia file:
   - `dt_cpu_busy` aumenta (più CPU time totale)
   - `dt_cpu_ollama` resta invariato (Ollama non usa più CPU)
   - Lo share `dt_cpu_ollama / dt_cpu_busy` diminuisce
   - **Risultato**: sottostima dell'energia attribuita a Ollama

4. **Calibrazione idle**: Durante la calibrazione idle (3 finestre da 30s), qualsiasi carico:
   - Aumenta la potenza misurata
   - Invalida la baseline `P_idle`
   - **Risultato**: sovrastima di `P_idle`, sottostima di `E_active`

### Conseguenze sulle misure

| Attività utente | Effetto su `P_idle` | Effetto su `E_ollama` | Validità risultato |
|---|---|---|---|
| Nessuna attività | ✓ Corretta | ✓ Corretta | ✓ Valido |
| Browser aperto | ✗ Sovrastimata | ✗ Sottostimata | ✗ Invalido |
| Copia file | ✗ Sovrastimata | ✗ Sottostimata | ✗ Invalido |
| Video in playback | ✗ Sovrastimata | ✗ Sottostimata | ✗ Invalido |
| Altre applicazioni | ✗ Sovrastimata | ✗ Sottostimata | ✗ Invalido |

## Best practices per l'utente

### Prima del benchmark

1. **Chiudere tutte le applicazioni non necessarie**
   - Browser web (Chrome, Firefox, Edge)
   - Editor di testo (VSCode, Notepad++)
   - File explorer (Esplora risorse)
   - Media player (VLC, Spotify)
   - Client di messaggistica (Teams, Slack, Discord)

2. **Disabilitare aggiornamenti automatici**
   - Windows Update
   - Aggiornamenti app (Steam, Epic Games, etc.)
   - Sync cloud (OneDrive, Dropbox, Google Drive)

3. **Verificare processi in background**
   - Aprire Task Manager (Ctrl+Shift+Esc)
   - Controllare scheda "Processi"
   - Terminare processi non essenziali

4. **Preparare l'ambiente**
   - Posizionare i prompt/dataset prima di avviare
   - Configurare i parametri del benchmark
   - Assicurarsi che Ollama sia già avviato con i modelli caricati

### Durante il benchmark

1. **NON toccare il PC**
   - Non muovere il mouse
   - Non premere tasti
   - Non cambiare finestra

2. **NON aprire applicazioni**
   - Anche solo aprire Task Manager altera le misure
   - Il rendering della GUI usa CPU/GPU

3. **Attendere il completamento**
   - Il benchmark mostra progresso nel log
   - Durata tipica: 2-10 minuti (dipende da numero query)
   - Non interrompere salvo errori

### Dopo il benchmark

1. **Verificare i risultati**
   - Controllare file CSV generato
   - Verificare che `idle_provenance` sia "calibrated" (non "manual_override")
   - Controllare che `cpu_time_share` sia ragionevole (0.1-0.9)

2. **Ripetere se necessario**
   - Se si sospetta interferenza, ripetere il benchmark
   - Confrontare risultati di esecuzioni diverse
   - Varianza > 10% indica possibili interferenze

## Note tecniche

### Durata stimata

La durata del benchmark è calcolata come:
```python
durata_stimata = total_tasks * 15 + 120  # secondi
```

Dove:
- `total_tasks` = numero di query (modelli × prompt)
- `15` = tempo medio per query (prefill + decode + valutazione)
- `120` = tempo calibrazione idle (92s) + overhead (28s)

Esempi:
- 1 modello × 10 prompt = 10 task → ~270s (4.5 min)
- 3 modelli × 10 prompt = 30 task → ~570s (9.5 min)
- 5 modelli × 20 prompt = 100 task → ~1620s (27 min)

### Messaggi di avanzamento

Durante il benchmark, il log mostra:
1. **Avviso iniziale** (questo documento)
2. **Configurazione** (modelli, prompt, parametri)
3. **Calibrazione idle** (3 finestre da 30s con progresso)
4. **Query in corso** (progresso: X/Y completate)
5. **Completamento** (risultati salvati in CSV)

### Interruzione del benchmark

Se è necessario interrompere:
- **GUI**: pulsante "Stop" (attende completamento query corrente)
- **CLI**: Ctrl+C (interruzione immediata, risultati parziali salvati)
- **Forza bruta**: chiudere la finestra (risultati persi)

**Nota**: l'interruzione non invalida le misure già completate, ma il CSV conterrà solo le query terminate.

## Riferimenti tesi

Questo avviso è menzionato in:
- **Capitolo 3 (Metodologia)**: §3.4 "Protocollo sperimentale"
- **Capitolo 6 (Validazione)**: §6.3 "Controllo interferenze"
- **Appendice A (Guida utente)**: "Best practices per misure accurate"

## Commit suggerito

```bash
git add benchmark_unified.py gui/benchmark_panel.py
git commit -m "FEAT: avviso isolamento sistema per benchmark energetico

- Avviso visibile all'avvio del benchmark (GUI + log)
- Spiegazione chiara del perché non usare il PC
- Lista attività da evitare (browser, file, app)
- Durata stimata del benchmark
- Miglioramento avviso durante calibrazione idle
- Motivazione scientifica: attribuzione CPU time share"
```

## Test

Per verificare che l'avviso funzioni:

1. **Avviare la GUI**
   ```bash
   cd cwEnergyModular
   python main.py
   ```

2. **Configurare un benchmark rapido**
   - 1 modello locale
   - 2 prompt
   - Temperatura 0.7

3. **Cliccare "Avvia benchmark"**

4. **Verificare nel log GUI**:
   ```
   ======================================================================
   ⚠ ATTENZIONE: BENCHMARK ENERGETICO IN CORSO
   ======================================================================
   Per garantire misure accurate, NON utilizzare il PC durante il benchmark.
   ...
   ======================================================================
   ```

5. **Verificare nel log console** (stesso messaggio)

## Conclusioni

L'avviso di isolamento sistema è **essenziale** per garantire:
- ✓ Misure energetiche accurate
- ✓ Attribuzione corretta a Ollama
- ✓ Calibrazione idle valida
- ✓ Risultati scientificamente validi
- ✓ Ripetibilità degli esperimenti

**Senza isolamento, i risultati del benchmark sono inaffidabili.**
