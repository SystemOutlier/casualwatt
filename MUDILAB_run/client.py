"""Stub di compatibilita'.

`agents.py` importa `HuggingFaceChatClient` da `client.py`, file che non fa parte
del pacchetto originale della professoressa. L'import e' l'unico uso che ne fa
il codice: nessun agente viene istanziato su questo client. La classe esiste
solo per far passare l'import e solleva se qualcuno prova davvero a usarla.
"""


class HuggingFaceChatClient:
    def __init__(self, *args, **kwargs):
        raise NotImplementedError(
            "client.py originale non fornito: HuggingFaceChatClient e' uno stub"
        )
