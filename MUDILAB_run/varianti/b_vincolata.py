"""Via B con uscita vincolata sui due passi che decidono la domanda.

Perche' esiste. I tre fallimenti misurati sono tutti di forma, non di calcolo:
tinyllama:latest risponde con prosa invece dell'etichetta (0 etichette su 12
query, output_classificatore_tinyllama_latest_v1.txt), llama3.2:1b e 3b scelgono
un'etichetta sbagliata (influence, coherence), e in via A il traduttore produce
argomenti inventati (trinomial_cdf). Un vincolo di decodifica attacca esattamente
questi tre guasti senza cambiare modello ne' prompt.

Cosa cambia rispetto a b_base. **Solo `options.response_format`** sui passi
`translator` e `classificator`: i prompt della relatrice restano identici, il
trasporto resta /v1, la misura energetica resta la stessa, la spiegazione resta
libera. Il client del framework passa lo schema invariato quando il tipo e'
`json_schema` (agent_framework_openai/_chat_completion_client.py:876-878), quindi
non serve un client nuovo ne' una chiamata nativa.

Nessun fallback silenzioso. Se Ollama rifiuta lo schema, l'eccezione esce e il
run e' registrato come fallito: non si ripiega di nascosto sull'uscita libera,
altrimenti il confronto misura due cose con la stessa etichetta.

Da verificare al primo run (smoke test, non ancora fatto): che /v1 di Ollama
0.33.1 onori `response_format` con `json_schema`. Il supporto e' dichiarato dal
client, non e' stato provato su questo host.

Gli schemi non impongono tutto: JSON Schema non sa dire "una sola chiave con un
nome presente nel grafo", quindi `output` ha minProperties/maxProperties 1 e la
validazione dei nomi resta dov'e' oggi, in tools_corretto. Il vincolo riduce lo
spazio di uscita, non sostituisce la validazione.
"""

from varianti import core

ro = core()

NOME = "b_vincolata"
DESCRIZIONE = "via B con schema JSON su etichetta e dizionario, prompt invariati"
CAMBIA = "options.response_format sui passi translator e classificator"

ETICHETTE = ("backward_reasoning", "intervention", "coherence", "influence", "counterfactual")

SCHEMA_ETICHETTA = {
    "type": "json_schema",
    "json_schema": {
        "name": "etichetta_causale",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {"label": {"type": "string", "enum": list(ETICHETTE)}},
            "required": ["label"],
            "additionalProperties": False,
        },
    },
}

SCHEMA_TRADUZIONE = {
    "type": "json_schema",
    "json_schema": {
        "name": "traduzione_query",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "input": {"type": "object", "additionalProperties": {"type": "string"}},
                "output": {
                    "type": "object",
                    "minProperties": 1,
                    "maxProperties": 1,
                    "additionalProperties": {"type": "string"},
                },
            },
            "required": ["input", "output"],
            "additionalProperties": False,
        },
    },
}

OPZIONI_PASSI = {
    "translator": {"response_format": SCHEMA_TRADUZIONE},
    "classificator": {"response_format": SCHEMA_ETICHETTA},
}


async def run(task: str, misura, **kw) -> dict:
    # kw porta path_rete dal benchmark: la variante vincola l'uscita, non la rete
    return await ro.run(task, misura, opzioni_passi=OPZIONI_PASSI, **kw)