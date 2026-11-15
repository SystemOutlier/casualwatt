from huggingface_hub import InferenceClient

# Inizializzi il client (richiede un token gratuito di Hugging Face)
client = InferenceClient(token="IL_TUO_TOKEN_HF")

# Invii una richiesta di chat (es. a un modello Llama o Mistral ospitato da HF)
response = client.chat_completion(
    model="mistralai/Mistral-7B-Instruct-v0.3",
    messages=[
        {"role": "user", "content": "Qual è la relazione tra DrivingSkill e DrivQuality?"}
    ],
    max_tokens=500
)

# Estrai il testo
testo_risposta = response.choices[0].message.content
print(testo_risposta)

"""
Così la riga from client import HuggingFaceChatClient di agents.py funziona senza cancellarla. Nel file .env aggiungi HF_TOKEN=il_tuo_token (e non committare mai quel file). Poi in agents.py:

small = HuggingFaceChatClient("Qwen/Qwen3-8B")
gpt5 = small

Il nome del modello deve essere uno di quelli disponibili sul router: l'elenco si legge da https://router.huggingface.co/v1/models.
"""

#Mantieni il fallback lessicale (SequenceMatcher) come metodo principale e, se vuoi aggiungere valore scientifico alla tesi, implementa #sentence-transformers in locale come metodo secondario opzionale:

# evaluator.py - struttura consigliata
try:
    from sentence_transformers import SentenceTransformer
    _model = SentenceTransformer('all-MiniLM-L6-v2')
    SEMANTIC_AVAILABLE = True
except ImportError:
    SEMANTIC_AVAILABLE = False

def compute_similarity(text1, text2, method="auto"):
    if method == "semantic" and SEMANTIC_AVAILABLE:
        # Calcolo semantico locale
        emb1 = _model.encode(text1)
        emb2 = _model.encode(text2)
        return cosine_similarity(emb1, emb2)
    else:
        # Fallback lessicale (già funzionante)
        return SequenceMatcher(None, text1, text2).ratio()