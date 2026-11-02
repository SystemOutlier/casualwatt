"""Variante di riferimento: la via B come e' stata misurata il 29-31/10.

Perche' esiste. Ogni confronto ha bisogno di un punto fermo. Questa variante non
cambia niente rispetto a run_orchestrato.py: il codice chiama cau_inference, il
modello traduce, classifica e scrive la spiegazione. Serve a verificare che lo
scheletro delle varianti riproduca i numeri gia' registrati (0.212 sul caso di
riferimento) prima di attribuire una differenza a una variante nuova.

Misurata: llama3.1:8b 487-539 J / 17,3-19,0 s; ibrido 8B+1B 236-259 J / 8,7-9,1 s
(run_orchestrato_ctl_A3/A4 e B2/B3_20261029.json).
"""

from varianti import core

ro = core()

NOME = "b_base"
DESCRIZIONE = "via B: il codice chiama cau_inference, il modello fa semantica e spiegazione"
CAMBIA = "niente: e' il riferimento"


async def run(task: str, misura, **kw) -> dict:
    return await ro.run(task, misura, **kw)