"""Modalita' orchestrata: due agenti, l'inferenza causale la chiama il codice.

Perche' esiste. Nella pipeline originale il terzo passo e' un agente che deve
*chiamare* `cau_inference`; con i modelli locali disponibili quel passaggio non
avviene: llama3.1:8b e qwen2.5-coder:7b scrivono la chiamata come testo e il
framework non esegue nulla, quindi il numero finale e' del modello. Qui il numero
lo calcola lo stesso `cau_inference` della relatrice, chiamato direttamente, e
l'agente causale scrive solo la spiegazione. E' la via B discussa nella nota:
non sostituisce `run_query.py`, che resta la pipeline originale.

Cosa resta vero:
  - il classificatore e il traduttore sono quelli delle copie, con i loro prompt;
  - `cau_inference`, `funtions.py` e il grafo sono quelli della relatrice;
  - l'unica cosa che cambia e' chi esegue la chiamata al tool.

Misura. Ogni passo e' una finestra energetica a se': due bordi del contatore
(`read_measurement_edge`) attorno alla chiamata e `profile_window` fra i due,
piu' i token da `usage_details`. I joule sono quelli del package CPU letti da
`cwEnergyModular`: se il modulo non c'e' (per esempio dove gira la relatrice) la
misura non blocca il run, dichiara il motivo e il resto del JSON resta valido.
La baseline non e' calibrata per default: senza `--calibra-idle` la riga ha
`idle_provenance = uncalibrated`, `baseline_energy_j = 0` e la sola energia
grezza del package. `--calibra-idle` aggiunge le tre finestre da 30 s di P1.3
(~90 s) e rende valida l'energia attiva. Il campionatore a 20 Hz resta acceso
per tutta la durata: e' un osservatore che costa CPU e lo dichiara la nota.
Il primo bordo di misura costa 4-5 s la prima volta (cache di psutil fredda):
si paga fuori dalla finestra e si dichiara, altrimenti quei secondi entrano
nell'energia del run senza appartenere a nessun passo.

Determinismo. I tre passi girano con `temperature = 0` (vedi `OPZIONI`): alla
temperatura predefinita di Ollama il traduttore cambia dizionario fra un run e
l'altro e il numero finale cambia con lui. Le opzioni finiscono nel JSON, quindi
ogni riga dice con che campionamento e' stata prodotta. `run_query.py`, che resta
la pipeline della relatrice, non viene toccato: li' la temperatura e' quella del
suo ambiente.

Via B ibrida. `MUDILAB_MODEL_SPIEGAZIONE` sceglie un secondo modello per la sola
spiegazione, lasciando il primo ai due passi che decidono la domanda. Serve a
misurare l'ipotesi "un modello piccolo al posto del grande" dove puo' reggere:
con llama3.2:1b e 3b il classificatore sbaglia l'etichetta (influence, coherence
invece di backward_reasoning) e il numero cambia, mentre la spiegazione e' circa
il 70% dell'energia dell'8B. `--riscalda-modelli` paga il caricamento dei due modelli
fuori dalla finestra, altrimenti il primo passo di una configurazione assorbe il
caricamento (~2150 J per l'8B) e due configurazioni non sono confrontabili.
`--scarta-primo-run` esegue una volta la pipeline senza misura prima di quella
misurata e ne scarta il risultato: copre cosi' il caricamento e anche la cache
dei prompt, che e' un secondo costo nascosto, e nei confronti e' il flag usato.
Il prompt della traduzione sono 1346 token: a cache calda Ollama ne riusa 1320 e
ne elabora 26 in 1,3 s, a cache fredda ne riusa 5 e ne elabora 1341 in 39 s
(34 token/s), a parita' di risposta e di token. Ricaricare i modelli svuota
quella cache, quindi due configurazioni confrontate su un solo run finiscono per
misurare la cache, non il modello: il primo run 8B+1B, senza
`--scarta-primo-run`, era 1800,9 J contro i 236-259 della seconda esecuzione.
Misurando, fra due run della stessa configurazione lo scarto in joule e' del 10%
(stesso output, stessi token): le configurazioni si confrontano a quel livello.

Uso:  python run_orchestrato.py "<query>" [--orig "cartella dei file originali"]
                                [--senza-misura] [--calibra-idle]
                                [--riscalda-modelli] [--scarta-primo-run]
      MUDILAB_COPIE=1 per usare le copie (come run_query.py).
      MUDILAB_MODEL=<modello Ollama> per scegliere il modello.
      MUDILAB_MODEL_SPIEGAZIONE=<modello Ollama> per la sola spiegazione.

Il caricamento delle due sorgenti e l'iniezione dei client stanno in
run_query.py: qui si importa quel modulo invece di duplicarlo (l'import non
esegue la pipeline, c'e' la guardia __main__).
"""

import asyncio
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

# le copie stanno nella cartella che finisce nello zip per la relatrice: un
# __pycache__ la' dentro non deve nascere (era gia' una regola per MUDILAB/).
sys.dont_write_bytecode = True

# I due flag tolgono se stessi da argv PRIMA che run_query.py lo legga: quel
# modulo legge sys.argv all'import e tutto il resto diventa la query.
MISURA = "--senza-misura" not in sys.argv[1:]
CALIBRA = "--calibra-idle" in sys.argv[1:]
RISCALDA = "--riscalda-modelli" in sys.argv[1:]
SCARTA = "--scarta-primo-run" in sys.argv[1:]
sys.argv = [sys.argv[0]] + [a for a in sys.argv[1:]
                            if a not in ("--senza-misura", "--calibra-idle",
                                         "--riscalda-modelli", "--scarta-primo-run")]


def _carica_runner():
    spec = importlib.util.spec_from_file_location("run_query", HERE / "run_query.py")
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = modulo
    spec.loader.exec_module(modulo)
    return modulo


rq = _carica_runner()
agenti = rq.mudilab_agents
tools = sys.modules["tools"]

# Le cinque etichette che `cau_inference` sa instradare (tools.py:51-118 nella
# copia). L'ordine non conta: il testo del classificatore viene cercato per
# sottostringa perche' un modello piccolo risponde con una frase invece che con
# una parola sola (visto con tinyllama:latest).
ETICHETTE = ("backward_reasoning", "intervention", "coherence", "influence", "counterfactual")

# Temperatura 0 sui tre passi. Motivo misurato: a quella predefinita di Ollama
# (0,8) il traduttore ha risposto in tre run con due dizionari diversi, e il
# numero finale cambia di conseguenza (Age=Senior 0.212, Age=Adult 0.651): tutti
# e due corretti, ma per due domande diverse. Con 0 la misura e' ripetibile. Il
# client non ha un parametro di costruzione per la temperatura: si passa a ogni
# `run` in `options` (OpenAIChatCompletionOptions, _chat_completion_client.py:219).
OPZIONI = {"temperature": 0.0}

# Modello della sola spiegazione. Vuoto = lo stesso dei due passi di routing,
# cioe' il comportamento delle misure precedenti.
MODELLO_SPIEGAZIONE = os.environ.get("MUDILAB_MODEL_SPIEGAZIONE") or rq.ACTIVE_MODEL


def costruisci_spiegatore():
    """Agente di sola spiegazione, con un client suo se il modello cambia.

    Gli agenti delle copie portano il client costruito all'import, e il prompt
    non si legge dall'oggetto: per usare un altro modello si ricostruisce
    l'agente con `causal_prompt`, che e' la stringa della copia. Senza modello
    separato si riusa l'agente gia' caricato, cosi' le misure di prima restano
    confrontabili.
    """
    if MODELLO_SPIEGAZIONE == rq.ACTIVE_MODEL:
        return agenti.causal_A_senza_tool
    from agent_framework import Agent
    from agent_framework.openai import OpenAIChatCompletionClient

    cliente = OpenAIChatCompletionClient(
        model=MODELLO_SPIEGAZIONE,
        base_url=os.environ.get("MUDILAB_BASE_URL", "http://localhost:11434/v1"),
        api_key=os.environ.get("MUDILAB_API_KEY", "ollama"))
    return Agent(name="Causal_Relator_Spiegazione", client=cliente,
                 instructions=agenti.causal_prompt)


def _ping_modello(modello: str) -> None:
    """Una generazione di un token, direttamente su Ollama.

    Non passa dagli agenti: `causal_A_senza_tool.run("ok")` con il suo prompt
    ha generato per 93 s, perche' `max_tokens: 1` non e' stato rispettato e il
    modello ha continuato. Qui serve solo caricare il modello in RAM.
    """
    import urllib.request

    base = os.environ.get("MUDILAB_BASE_URL", "http://localhost:11434/v1").rstrip("/")
    corpo = json.dumps({
        "model": modello,
        "messages": [{"role": "user", "content": "ok"}],
        "max_tokens": 1, "temperature": 0, "stream": False,
    }).encode()
    req = urllib.request.Request(base + "/chat/completions", data=corpo,
                                headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        r.read()


async def riscalda_modelli(misura) -> None:
    """Carica in RAM i due modelli fuori dalla finestra di misura.

    Il primo uso di un modello paga il caricamento: per llama3.1:8b freddo sono
    ~76 s e ~2150 J, cinque volte un run caldo. Dentro la finestra finirebbe nel
    primo passo. **Questo non scalda la cache dei prompt**: la traduzione da
    1341 token a cache fredda costa 39 s di sola elaborazione del prompt
    (34 token/s) contro 1,3 s a cache calda, quindi la prima esecuzione di una
    configurazione va scartata (`--scarta-primo-run`) e si misura la seconda.
    """
    for nome, modello in (("routing", rq.ACTIVE_MODEL),
                          ("spiegazione", MODELLO_SPIEGAZIONE)):
        t0 = time.perf_counter()
        try:
            await asyncio.to_thread(_ping_modello, modello)
        except Exception as e:
            misura.note.append(f"riscaldamento {nome} fallito: {type(e).__name__}: {e}")
        else:
            misura.note.append(
                f"riscaldamento {nome} ({modello}) scartato: "
                f"{time.perf_counter() - t0:.3f} s")


def etichette_nel_testo(testo: str) -> list:
    """Etichette ammesse citate nella risposta, in ordine di comparsa.

    Si cerca per sottostringa perche' un modello piccolo risponde con una frase
    invece che con una parola sola (tinyllama:latest: "You have classified the
    query ... as: - Influence: ..."). Vale la PRIMA citata, che e' quella che il
    modello dichiara; le altre restano nel JSON, cosi' un testo ambiguo si vede
    invece di essere interpretato in silenzio.
    """
    basso = (testo or "").lower()
    posizioni = sorted((basso.find(e), e) for e in ETICHETTE if e in basso)
    return [e for _, e in posizioni]


def etichetta_dal_testo(testo: str) -> str:
    """La prima etichetta ammessa citata nella risposta del classificatore."""
    trovate = etichette_nel_testo(testo)
    if not trovate:
        raise ValueError(f"nessuna delle {len(ETICHETTE)} etichette nel testo: {testo[:200]!r}")
    return trovate[0]


def dizionario_dal_testo(testo: str) -> dict:
    """Il dizionario {input, output} del traduttore, validato prima di usarlo.

    La lettura riusa `_parse_features` della copia di tools.py: accetta gia' i
    blocchi markdown e rifiuta il testo che non e' un dizionario.
    """
    dati = tools._parse_features(testo)
    if set(dati) != {"input", "output"}:
        raise ValueError(f"chiavi {sorted(dati)} invece di ['input', 'output']")
    if not isinstance(dati["input"], dict):
        raise ValueError(f"'input' non e' un dizionario: {dati['input']!r}")
    if not isinstance(dati["output"], dict) or len(dati["output"]) != 1:
        raise ValueError(f"'output' deve essere un dizionario di una chiave: {dati['output']!r}")
    return dati


def token_di(risposta) -> dict:
    """Token dichiarati dal modello per quel passo (None se il client non li da')."""
    uso = getattr(risposta, "usage_details", None)
    if not uso:
        return {}
    chiavi = ("input_token_count", "output_token_count", "total_token_count",
              "cache_read_input_token_count")
    return {k: uso[k] for k in chiavi if uso.get(k) is not None}


class Misura:
    """Una finestra energetica per passo, sul contatore del package CPU.

    Non solleva mai: ogni guasto finisce in `errore` o in `note` e il run
    prosegue. Un esperimento senza energia e' recuperabile, un run perso no.
    """

    def __init__(self, attiva: bool, calibra: bool):
        self.attiva = attiva
        self.calibra = calibra
        self.errore = ""      # bloccante: la misura non e' possibile
        self.note = []        # non bloccante: cosa e' stato fatto o saltato
        self.session = None
        self.profiler = None

    @property
    def disponibile(self) -> bool:
        return self.session is not None and self.profiler is not None and not self.errore

    def avvia(self) -> None:
        if not self.attiva:
            self.note.append("misura disattivata (--senza-misura)")
            return
        try:
            sys.path.insert(0, str(ROOT / "cwEnergyModular"))
            from energy.energy_session import SESSION
            from energy.local_energy import CasualWattLocalEnergyProfiler
        except Exception as e:
            self.errore = f"cwEnergyModular non disponibile: {type(e).__name__}: {e}"
            return
        self.session = SESSION
        self.profiler = CasualWattLocalEnergyProfiler()
        try:
            SESSION.start()
        except Exception as e:
            self.errore = f"sessione non avviata: {type(e).__name__}: {e}"
            return
        self.note.append(f"canale {getattr(SESSION, 'source_method', 'sconosciuto')}")
        # Il primo bordo costa 4-5 s: il primo `find_worker_tree` popola la cache
        # di psutil (misurato: 4,541 s contro 0,018-0,037 s dai bordi successivi).
        # Se resta dentro la finestra totale, quei secondi a potenza di riposo
        # finiscono nell'energia del run senza essere di nessun passo: 70,4 J su
        # 532,4 J, cioe' il 13%, attribuiti al modello per costruzione. Si paga
        # una volta qui, si dichiara in nota, e la finestra totale parte dopo.
        t_risc = time.perf_counter()
        try:
            SESSION.read_measurement_edge()
        except Exception as e:
            self.note.append(f"bordo di riscaldamento fallito: {type(e).__name__}: {e}")
        else:
            self.note.append(
                f"bordo di riscaldamento scartato: {time.perf_counter() - t_risc:.3f} s")
        if self.calibra:
            # tre finestre da 30 s a riposo (P1.3): ~90 s, per questo non e' il default
            try:
                SESSION.settle_idle()
                potenza = SESSION.calibrate_idle()
                self.note.append(f"baseline calibrata: {potenza:.3f} W")
            except Exception as e:
                self.note.append(f"calibrazione idle fallita: {type(e).__name__}: {e}")
        else:
            self.note.append("baseline non calibrata: solo energia del package")

    def bordo(self):
        """Bordo di misura, o None se la misura non e' disponibile."""
        if not self.disponibile:
            return None
        try:
            return self.session.read_measurement_edge()
        except Exception as e:
            self.errore = f"bordo non letto: {type(e).__name__}: {e}"
            return None

    def riga(self, t0: float, t1: float, e0, e1) -> dict:
        """I campi energetici della finestra [t0, t1] (vuoto se non misurata)."""
        if not self.disponibile:
            return {"misura": self.errore or "non disponibile"}
        try:
            r = self.profiler.profile_window(t0, t1, edge_start=e0, edge_end=e1)
        except Exception as e:
            return {"misura": f"profile_window: {type(e).__name__}: {e}"}
        return {
            "energia_pkg_j": round(r.package_energy_j, 6),
            "energia_pkg_raw_j": (None if r.package_energy_raw_j is None
                                  else round(r.package_energy_raw_j, 6)),
            "energia_attiva_j": round(r.active_energy_j, 6),
            "attiva_valida": r.active_valid,
            "canale": r.energy_calculation_method,
            "finestra": r.package_window_source,
            "idle": r.idle_provenance,
        }

    def chiudi(self) -> None:
        """Chiusura definitiva del contatore e del campionatore (una sola volta)."""
        if self.session is None:
            return
        try:
            self.session.close()
        except Exception as e:
            self.note.append(f"chiusura sessione: {type(e).__name__}: {e}")

    def riepilogo(self) -> dict:
        return {
            "attiva": self.attiva,
            "disponibile": self.disponibile,
            "errore": self.errore,
            "note": list(self.note),
        }


async def _passo(misura: Misura, nome: str, attesa) -> tuple:
    """Esegue un passo misurandone la finestra e restituisce (risposta, passo)."""
    e0 = misura.bordo()
    t0 = time.perf_counter()
    risposta = await attesa
    t1 = time.perf_counter()
    e1 = misura.bordo()
    passo = {
        "step": nome,
        "seconds": round(t1 - t0, 3),
        "tokens": token_di(risposta),
        "misura": misura.riga(t0, t1, e0, e1),
        "text": risposta.text,
    }
    return risposta, passo


async def run(task: str, misura: Misura, opzioni_passi: dict | None = None,
              path_rete: str | None = None, spiegazione: bool = True,
              traduttore=None, classificatore=None) -> dict:
    """Esegue la pipeline; `opzioni_passi` sovrascrive OPZIONI per singolo passo.

    `spiegazione=False` salta il terzo passo: il numero e' gia' esatto, quello
    che si risparmia e' la prosa. E' un'opzione, non il comportamento: il
    default resta quello misurato il 29-31/10, e il valore finisce nel JSON,
    cosi' due run con la stessa etichetta non nascondono due pipeline diverse.

    Aggiunto per le varianti in varianti/: b_vincolata passa response_format sui
    due passi di routing senza toccare i prompt ne' la spiegazione. None e' il
    comportamento di sempre, quindi i risultati gia' registrati restano
    confrontabili. Il valore finisce nel JSON: ogni riga dice con quali vincoli
    di uscita e' stata prodotta.

    `path_rete` sceglie la rete bayesiana data al tool. Serve al benchmark, che
    contiene anche query sulla rete con le CPT perturbate: l'oracolo e la
    pipeline devono leggere la stessa rete, altrimenti il confronto misura due
    reti diverse. None e' la rete di default delle copie, cioe' il
    comportamento misurato il 29-31/10.

    `traduttore` sostituisce il passo di traduzione con uno verificabile, come
    quelli in `traduzione_controllata.py`: se dato, l'agente del primo passo viene
    da `traduttore.agente(path_rete)` (prompt della relatrice + vocabolario letto
    dal grafo + richiesta di citazione) e il dizionario non passa da
    `dizionario_dal_testo` ma da `traduttore.valida`, che scarta cio' che non e'
    nel grafo o non e' citato e scrive le voci scartate nel JSON sotto
    `controllo_traduzione`. None e' il comportamento di sempre. Non c'e' un
    ripiegamento sul dizionario non verificato: se la verifica rifiuta, la riga
    esce fallita con il motivo, perche' una riga passata con una mappatura
    inventata sembrerebbe buona.

    `classificatore` sostituisce il secondo passo come `traduttore` sostituisce il
    primo: l'agente viene da `classificatore.agente()` e il testo della query resta
    quello passato da sempre. Serve perche' lo screening dell'1-11 su dev misura
    che l'etichetta e' giusta 20/20 su tre rami su quattro e 1/21 sul quarto
    (cond_prob, che finisce in `coherence`): il guasto e' del classificatore, non
    del modello in generale, e si cura sulle sue istruzioni. None e' il
    comportamento di sempre.
    """
    def _opz(nome: str) -> dict:
        return {**OPZIONI, **(opzioni_passi or {}).get(nome, {})}

    steps = []
    risultato = {
        "modalita": "orchestrata",
        "model": rq.ACTIVE_MODEL,
        "modello_spiegazione": MODELLO_SPIEGAZIONE,
        "source": rq.SOURCE,
        "opzioni": dict(OPZIONI),
        "opzioni_passi": opzioni_passi,
        "spiegazione": spiegazione,
        "rete": path_rete,
        "task": task,
    }

    spiegatore = costruisci_spiegatore() if spiegazione else None
    if RISCALDA:
        await riscalda_modelli(misura)

    e_tot0 = misura.bordo()
    t_tot0 = time.perf_counter()

    # stesso ordine della pipeline originale (FINAL.ipynb cella 12,
    # run_query.py:197 e :206): prima il traduttore, poi il classificatore.
    # I due passi leggono entrambi la sola query e non si scambiano nulla.
    agente_traduttore = (traduttore.agente(path_rete) if traduttore
                         else agenti.translator_senza_tool)
    risposta, passo = await _passo(misura, "translator", agente_traduttore.run(
        f"Create a dictionary following your instruction of the query:{task}",
        options=_opz("translator")))
    steps.append(passo)
    grezzo_traduzione = risposta.text

    risposta, passo = await _passo(misura, "classificator", (
        classificatore.agente() if classificatore else agenti.classificator).run(
        f"classify the following query using your instructions:{task}", options=_opz("classificator")))
    steps.append(passo)
    grezzo_etichetta = risposta.text

    esito_traduzione = None
    try:
        etichetta = etichetta_dal_testo(grezzo_etichetta)
        if traduttore:
            traduzione, esito_traduzione = traduttore.valida(
                grezzo_traduzione, etichetta, task, path_rete)
            if traduzione is None:
                raise ValueError(f"controllo_traduzione: {esito_traduzione['motivo']}")
        else:
            traduzione = dizionario_dal_testo(grezzo_traduzione)
    except ValueError as e:
        # i due passi costano gia' un modello: il JSON esce lo stesso, con il
        # testo grezzo, cosi' si vede che cosa ha risposto e non solo che e' fallito
        risultato.update({
            "errore": f"{type(e).__name__}: {e}",
            "controllo_traduzione": esito_traduzione,
            "seconds_total": round(time.perf_counter() - t_tot0, 3),
            "misura": misura.riepilogo(),
            "steps": steps,
        })
        return risultato

    e0 = misura.bordo()
    t0 = time.perf_counter()
    try:
        numero = tools.cau_inference.func(etichetta, json.dumps(traduzione), path_rete)
    except Exception as e:
        risultato.update({
            "etichetta": etichetta,
            "traduzione": traduzione,
            "controllo_traduzione": esito_traduzione,
            "errore": f"cau_inference: {type(e).__name__}: {e}",
            "seconds_total": round(time.perf_counter() - t_tot0, 3),
            "misura": misura.riepilogo(),
            "steps": steps,
        })
        return risultato
    t1 = time.perf_counter()
    steps.append({
        "step": "cau_inference",
        "seconds": round(t1 - t0, 3),
        "tokens": {},
        "misura": misura.riga(t0, t1, e0, misura.bordo()),
        "text": str(numero),
    })

    if spiegazione:
        risposta, passo = await _passo(misura, "causal_A", spiegatore.run(
            f"User task: {task}\n"
            f"The exact causal inference has already been executed by the code, not by you,"
            f" and returned: {numero}\n"
            f"(label {etichetta}, features {json.dumps(traduzione)}).\n"
            "Report that number as it is, then add the causal explanation in prose.\n"
            "Rules: do not write code and do not show tool calls; do not invent probabilities,"
            " coefficients or intermediate effects; the only number you may state is the one above.",
            options=_opz("causal_A")
        ))
        steps.append(passo)

    t_tot1 = time.perf_counter()
    totale = misura.riga(t_tot0, t_tot1, e_tot0, misura.bordo())
    # La finestra totale non e' la somma dei passi: la differenza e' il costo
    # dei bordi di misura, del parsing e dei vuoti fra un passo e l'altro.
    # Dichiararla evita di attribuire ai passi joule che non sono loro.
    fuori = None
    if "energia_pkg_j" in totale:
        somma = sum(s["misura"].get("energia_pkg_j") or 0.0 for s in steps)
        fuori = round(totale["energia_pkg_j"] - somma, 6)
    risultato.update({
        "etichetta": etichetta,
        "etichette_nel_testo": etichette_nel_testo(grezzo_etichetta),
        "traduzione": traduzione,
        "controllo_traduzione": esito_traduzione,
        "numero": numero,
        "seconds_total": round(t_tot1 - t_tot0, 3),
        "misura": misura.riepilogo(),
        "totale": totale,
        "fuori_dai_passi_j": fuori,
        "steps": steps,
    })
    return risultato


if __name__ == "__main__":
    query = " ".join(rq._args) or (
        "Given that the driving quality is normal, how likely is it that the age "
        "of the driver is senior?"
    )
    async def _esegui():
        if SCARTA:
            # stessa pipeline, stessa query, senza misura: popola la cache dei
            # prompt di Ollama (39 s di prompt processing a cache fredda contro
            # 1,3 s calda) e carica i modelli. Il numero che produce non si usa.
            # Nello stesso event loop: il client httpx resta legato al primo
            # loop, e un secondo `asyncio.run` fallisce con "Event loop is closed".
            caldo = Misura(False, False)
            caldo.avvia()
            try:
                await run(query, caldo)
            except Exception as e:
                print(f"run di riscaldamento fallito: {type(e).__name__}: {e}",
                      file=sys.stderr)
            finally:
                caldo.chiudi()
        misura = Misura(MISURA, CALIBRA)
        misura.avvia()
        try:
            return await run(query, misura)
        finally:
            misura.chiudi()

    esito = asyncio.run(_esegui())
    print(json.dumps(esito, indent=2, ensure_ascii=False))
    raise SystemExit(2 if "errore" in esito else 0)
