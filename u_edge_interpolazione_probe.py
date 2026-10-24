"""Verifica numerica dei tre errori di bordo che P4.6 separa.

Perché esiste questo file
-------------------------
Il protocollo v4 (P4.6, `experiment_results/protocollo_v4_20261024.md`)
maggiora il termine di bordo con la formula congelata

    u_edge,b = 2 · P_peak,b · δt_edge,b ,   δt_edge,b = Δt_tick,b / 2

e, nella rettifica del 2026-10-24, dichiara che quel termine copre l'errore di
**disallineamento** e non l'errore di **interpolazione**, aggiungendo che esiste
un terzo errore, di **copertura**, che il valore congelato non copre. Le tre
affermazioni erano accompagnate da numeri ("errore massimo 3,0e-11 J",
"1,4062 J a f = 0,25", "1,8750 J a f = 0,5", "0,9375 J per la rampa") prodotti
da un calcolo non tracciato: per AGENTS.md un'analisi non tracciata è un numero
che nessuno può rigenerare, quindi non è evidenza. Questo file è l'harness che
li rigenera, e sostituisce quel calcolo. Il `3,0e-11 J` pubblicato nel protocollo
non è riproducibile come valore assoluto: è il residuo floating point di una
griglia non dichiarata, e questo harness, a `n = 2 000 001`, dà `7,4e-11 J`. Stesso
ordine di grandezza, quindi il numero pubblicato era plausibile, ma
dipendente dalla discretizzazione: la forma corretta in cui riscriverlo nel
protocollo è **relativa** (residuo / grandezza del contatore), che è invariante
rispetto alla griglia entro un fattore ~sqrt(n).

Cosa verifica, in relazioni matematiche e non in asserzioni
-----------------------------------------------------------
1. A potenza costante il contatore cumulativo E(t) = P·t è **lineare** in t, e
   l'interpolazione lineare di una funzione lineare fra i due estremi è esatta:
   l'errore è identicamente nullo in aritmetica esatta, per qualunque livello di
   potenza e per qualunque griglia. Ciò che si misura è solo il residuo floating
   point di `np.cumsum`, che va letto in **relativo** alla grandezza del
   contatore (`P · Δt_tick`) e che in assoluto *cresce* con la densità di griglia
   perché l'arrotondamento si accumula su più passi. Il criterio di superamento è
   relativo (< 1e-10), non assoluto: un criterio assoluto del tipo
   "residuo < 1e-9 J" mescola l'unità di misura con la precisione.
2. Per un gradino di ampiezza ΔP posto a frazione f del tick, l'errore massimo
   fra il cumulativo vero e la sua interpolazione lineare agli estremi è

       max_t |E(t) − interp(t)| = ΔP · f · (1 − f) · Δt_tick

   con massimo in f = 1/2 pari a ΔP · Δt_tick / 4. Il livello di potenza non
   compare: è la variazione dentro il tick che produce l'errore, non la sua
   grandezza. Questa è la ragione per cui la formula congelata, che usa
   P_peak, non può essere un limite dell'errore di interpolazione.
3. Per una rampa lineare da 0 a ΔP sul tick l'errore massimo è
   ΔP · Δt_tick / 8, metà del gradino a f = 1/2.
4. Il termine di disallineamento con i numeri di produzione (P_peak = 35 W,
   Δt_tick = 0,30 s misurati sul percorso EMI, non i 0,05 s dichiarati da
   `POWER_SAMPLE_INTERVAL_S`, `energy_session.py:80`) vale 10,5 J per due bordi.
5. Il termine di copertura, cioè il clamp di `_emi_cum_at` che fuori copertura
   ma entro 1 s restituisce il valore estremo (`energy_session.py:1111-1116`)
   attribuendo energia zero al tratto, arriva a P_peak · 1 s = 35 J: più grande
   degli altri due, e non coperto dal valore congelato.

Uso: `python u_edge_interpolazione_probe.py`. Non tocca hardware, non legge il
registro EMI, non dipende da Ollama: è aritmetica su forme d'onda sintetiche,
quindi è eseguibile ovunque e il suo output è riproducibile bit per bit.
"""

from __future__ import annotations

import sys

import numpy as np

# Numeri di produzione citati da P4.6. P_peak è la potenza TOTALE di picco del
# blocco (il contatore EMI accumula potenza totale, quindi il limite deve usare
# quella totale, non la netta). dt_tick è l'intervallo MISURATO sul percorso di
# produzione, 0,28-0,34 s, non i 0,05 s dichiarati dalla costante del modulo.
P_PEAK_W = 35.0
DT_TICK_S = 0.30
D_GRADINO_W = 25.0
CLAMP_COPERTURA_S = 1.0  # raggio del clamp di _emi_cum_at

N_GRIGLIA = 2_000_001  # dispari: include esattamente il punto medio del tick


def cumulativo(potenza: np.ndarray, t: np.ndarray) -> np.ndarray:
    """Integrale cumulativo di una forma d'onda campionata, regola trapezoidale.

    E[k] = somma dei trapezi fino a t[k], con E[0] = 0: è ciò che fa un
    contatore energetico che parte da zero all'inizio della finestra.
    """
    dt = np.diff(t)
    incrementi = (potenza[1:] + potenza[:-1]) / 2.0 * dt
    return np.concatenate([[0.0], np.cumsum(incrementi)])


def interpolante_estremi(e_cum: np.ndarray, t: np.ndarray) -> np.ndarray:
    """Retta che passa per i due valori di contatore agli estremi del tick.

    È ciò che produce `_emi_cum_at` quando il bordo cade fra due campioni del
    buffer (`energy_session.py:1103-1124`): interpolazione lineare fra il
    campione precedente e il successivo, quindi fra gli estremi del tick se la
    griglia è allineata ai campioni.
    """
    return e_cum[0] + (e_cum[-1] - e_cum[0]) * (t - t[0]) / (t[-1] - t[0])


def errore_massimo(potenza: np.ndarray, t: np.ndarray) -> float:
    """max_t |E(t) − interpolante(t)| sulla griglia, in joule."""
    e_cum = cumulativo(potenza, t)
    return float(np.max(np.abs(e_cum - interpolante_estremi(e_cum, t))))


def verifica_1_potenza_costante() -> bool:
    """A potenza costante l'errore di interpolazione è nullo.

    Non è un risultato empirico: E(t) = P·t è lineare, e l'interpolazione
    lineare fra due punti di una retta restituisce la retta. Il criterio di
    superamento è quindi **relativo**: il residuo va confrontato con la
    grandezza del contatore a fine tick, `P · Δt_tick`, non con 1 J. Un residuo
    assoluto di 7e-11 J è trascurabile rispetto a 10,5 J (7e-12 in relativo);
    lo stesso residuo sarebbe enorme se il contatore valesse 1e-9 J.

    Due proprietà del residuo floating point vanno dichiarate, perché entrambe
    contraddicono l'intuizione e la versione precedente di questo harness le
    asseriva al contrario:

    * il residuo **assoluto cresce** al crescere della densità di griglia, non
      decresce. `np.cumsum` accumula l'arrotondamento di ogni passo, quindi il
      residuo scala come ~sqrt(n) passi: infittire la griglia peggiora il numero
      assoluto senza avvicinarlo a zero. L'errore in aritmetica esatta è
      identicamente zero per qualunque n; ciò che si osserva è solo
      arrotondamento, e la convergenza a zero va cercata sul residuo
      **relativo** a parità di algoritmo, non sul assoluto.
    * il residuo assoluto **scala con il livello di potenza** (raddoppiare P lo
      raddoppia: 7,4e-11 / 1,5e-10 / 3,0e-10 J per P = 35 / 70 / 140 W). Ciò che
      NON dipende da P è il residuo **relativo**, ed è questa la forma corretta
      dell'affermazione "il livello di potenza non compare": l'errore esatto è
      nullo per ogni P, e la parte non nulla è proporzionale alla grandezza
      della quantità integrata.
    """
    print("1. Potenza costante P = %.1f W su tick = %.2f s" % (P_PEAK_W, DT_TICK_S))
    print("   criterio: residuo RELATIVO a P·Δt_tick = %.1f J (grandezza del contatore)"
          % (P_PEAK_W * DT_TICK_S))
    t = np.linspace(0.0, DT_TICK_S, N_GRIGLIA)
    err = errore_massimo(np.full_like(t, P_PEAK_W), t)
    rel = err / (P_PEAK_W * DT_TICK_S)
    print("   n = %9d   residuo assoluto = %.3e J   relativo = %.3e"
          % (N_GRIGLIA, err, rel))
    print("   il residuo ASSOLUTO cresce con la griglia (cumsum accumula arrotondamento)")
    print("   su ~sqrt(n) passi; il RELATIVO resta a livello di precisione macchina:")
    residui = []
    for n in (10_001, 100_001, 1_000_001):
        tt = np.linspace(0.0, DT_TICK_S, n)
        r_ass = errore_massimo(np.full_like(tt, P_PEAK_W), tt)
        residui.append((n, r_ass, r_ass / (P_PEAK_W * DT_TICK_S)))
        print("   n = %9d   residuo assoluto = %.3e J   relativo = %.3e" % residui[-1])
    # La soglia 1e-10 è relativa: corrisponde a 1e-9 J su un contatore da 10,5 J,
    # cioè undici ordini di grandezza sotto il più piccolo termine fisico in gioco
    # (u_edge = 10,5 J). Sotto questa soglia il residuo è aritmetica, non fisica.
    TOLL_RELATIVA = 1e-10
    ok = all(r[2] < TOLL_RELATIVA for r in residui) and rel < TOLL_RELATIVA
    print("   esito: %s — tutti i residui relativi < %.0e (tolleranza dichiarata)"
          % ("PASSA" if ok else "FALLISCE", TOLL_RELATIVA))
    print("   dipendenza dal livello di potenza: assoluto proporzionale a P, relativo no")
    for p in (70.0, 140.0):
        e2 = errore_massimo(np.full_like(t, p), t)
        print("     P = %6.1f W -> assoluto %.3e J, relativo %.3e" % (p, e2, e2 / (p * DT_TICK_S)))
    print("   numero canonico per il protocollo: a n = %d, P = %.0f W, "
          "Δt_tick = %.2f s il residuo è %.1e J (%.1e relativo)"
          % (N_GRIGLIA, P_PEAK_W, DT_TICK_S, err, rel))
    return ok


def verifica_2_gradino() -> bool:
    """Gradino ΔP a frazione f del tick: errore = ΔP · f · (1 − f) · Δt_tick.

    Verifica l'identità analitica punto per punto, non solo il suo massimo.
    """
    print("\n2. Gradino ΔP = %.1f W posto a frazione f del tick" % D_GRADINO_W)
    t = np.linspace(0.0, DT_TICK_S, N_GRIGLIA)
    ok = True
    print("      f     numerico      analitico      scarto")
    for f in (0.10, 0.25, 0.40, 0.50, 0.60, 0.75, 0.90):
        potenza = np.where(t < f * DT_TICK_S, 0.0, D_GRADINO_W)
        num = errore_massimo(potenza, t)
        ana = D_GRADINO_W * f * (1.0 - f) * DT_TICK_S
        scarto = abs(num - ana)
        # la griglia discreta non centra esattamente il gradino: tollero il
        # passo di discretizzazione moltiplicato per ΔP, che è il massimo
        # errore di posizione del gradino stesso
        toll = D_GRADINO_W * DT_TICK_S / (N_GRIGLIA - 1)
        ok = ok and scarto <= toll
        print("   %5.2f    %8.4f J    %8.4f J    %.2e" % (f, num, ana, scarto))
    limite = D_GRADINO_W * DT_TICK_S / 4.0
    print("   limite ΔP·Δt_tick/4 = %.4f J, raggiunto a f = 0,5" % limite)
    print("   esito: %s — identità verificata, tolleranza = passo di griglia"
          % ("PASSA" if ok else "FALLISCE"))
    return ok


def verifica_3_rampa() -> bool:
    """Rampa lineare da 0 a ΔP sul tick: errore massimo = ΔP · Δt_tick / 8.

    È metà del gradino a f = 1/2, come dichiara P4.6.
    """
    print("\n3. Rampa lineare da 0 a ΔP = %.1f W sul tick" % D_GRADINO_W)
    t = np.linspace(0.0, DT_TICK_S, N_GRIGLIA)
    num = errore_massimo(D_GRADINO_W * t / DT_TICK_S, t)
    ana = D_GRADINO_W * DT_TICK_S / 8.0
    print("   numerico %.4f J   analitico %.4f J   scarto %.2e"
          % (num, ana, abs(num - ana)))
    ok = abs(num - ana) <= D_GRADINO_W * DT_TICK_S / (N_GRIGLIA - 1)
    print("   esito: %s" % ("PASSA" if ok else "FALLISCE"))
    return ok


def verifica_4_disallineamento() -> bool:
    """Il termine congelato 2 · P_peak · δt_edge con i numeri di produzione.

    Non è una verifica numerica ma un controllo di coerenza con la formula di
    P4.6: serve a dire in joule quanto vale il budget congelato, perché è con
    quel numero che si confrontano i tre errori.
    """
    print("\n4. Termine di disallineamento congelato (P4.6)")
    delta_t_edge = DT_TICK_S / 2.0
    u_edge = 2.0 * P_PEAK_W * delta_t_edge
    print("   δt_edge = Δt_tick/2 = %.3f s" % delta_t_edge)
    print("   u_edge,b = 2 · %.1f W · %.3f s = %.2f J" % (P_PEAK_W, delta_t_edge, u_edge))
    ok = abs(u_edge - 10.5) < 1e-9
    print("   esito: %s — coincide con i 10,5 J dichiarati nel protocollo"
          % ("PASSA" if ok else "FALLISCE"))
    return ok


def verifica_5_copertura() -> bool:
    """Il clamp di copertura è più grande del termine congelato.

    `_emi_cum_at` non estrapola: fuori copertura ma entro 1 s restituisce il
    valore estremo del buffer, cioè attribuisce energia zero al tratto non
    coperto. Il worst case è P_peak · 1 s.
    """
    print("\n5. Termine di copertura (clamp di _emi_cum_at, non coperto dal valore congelato)")
    worst = P_PEAK_W * CLAMP_COPERTURA_S
    u_edge = 2.0 * P_PEAK_W * (DT_TICK_S / 2.0)
    print("   worst case = P_peak · 1 s = %.1f W · %.1f s = %.2f J"
          % (P_PEAK_W, CLAMP_COPERTURA_S, worst))
    print("   rapporto con u_edge congelato = %.2f volte" % (worst / u_edge))
    ok = worst > u_edge
    print("   esito: %s — il termine di copertura supera il budget congelato,"
          % ("PASSA" if ok else "FALLISCE"))
    print("          che quindi non maggiora tutti e tre gli errori (P4.6 lo dichiara)")
    return ok


def main() -> int:
    print("=" * 74)
    print("Tre errori di bordo di P4.6: interpolazione, disallineamento, copertura")
    print("griglia %d punti, tick %.2f s, P_peak %.1f W, ΔP gradino %.1f W"
          % (N_GRIGLIA, DT_TICK_S, P_PEAK_W, D_GRADINO_W))
    print("=" * 74)
    esiti = [
        verifica_1_potenza_costante(),
        verifica_2_gradino(),
        verifica_3_rampa(),
        verifica_4_disallineamento(),
        verifica_5_copertura(),
    ]
    print("\n" + "=" * 74)
    print("esito complessivo: %d/%d verifiche superate" % (sum(esiti), len(esiti)))
    print("=" * 74)
    print("\nConclusione di metodo. L'errore di interpolazione dipende dalla")
    print("VARIAZIONE di potenza dentro il tick e non dal suo livello (verifica 1:")
    print("identicamente nullo a potenza costante per ogni P; il residuo misurato")
    print("è aritmetica floating point, < 1e-11 in relativo, e in assoluto è")
    print("proporzionale a P). La formula congelata usa P_peak, quindi non può")
    print("esserne un limite: maggiora il disallineamento (verifica 4). La")
    print("copertura resta fuori dal budget congelato (verifica 5) ed è eliminata")
    print("alla radice dalla via (b) di P4.6, cioè dalla lettura sincrona del")
    print("contatore ai bordi di finestra, requisito vincolante di P5.")
    return 0 if all(esiti) else 1


if __name__ == "__main__":
    sys.exit(main())
