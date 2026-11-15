# -*- coding: utf-8 -*-
"""
evaluator.py — Valutazione UNIVERSALE delle risposte (refactoring accademico).

REGIME A — CON ground truth (eval_mode = "ground_truth"):
  * acc_links = F1-score su TRIPLE CAUSALI estratte da ground truth e risposta
    (causal_extractor.py). NON keyword matching. Se la GT non contiene triple
    strutturate -> fallback dichiarato in ordine di preferenza:
      1) semantic_similarity (embedding MiniLM multilingua);
      2) lexical_similarity (SequenceMatcher) solo se embeddings assenti;
    il risultato NON viene mai presentato come valutazione strutturale.
  * cosine_sim = semantic_similarity (misura reale, non hardcoded).
  * judge_score = LLM-as-a-Judge Ollama temperatura 0.0 (se disponibile;
    altrimenti N/A e acc_comp ricalcolato senza di esso, dichiarato).
  * Formula approvata Regime A:
      acc_comp = 0.50*acc_links + 0.30*(judge_score/5) + 0.20*cosine_sim
    (pesi ridistribuiti e dichiarati se un componente e' N/A).
  * ETICHETTA della similarita': "semantic similarity between model response
    and ground truth" — proxy di correttezza, NON causal accuracy pura.

REGIME B — SENZA ground truth (eval_mode = "causal_agent_eval"):
  * cosine_sim NON calcolata e MAI forzata a valori fittizi -> N/A nel CSV.
  * acc_links = F1 sulle triple estratte dalla domanda/riferimenti quando
    possibile, altrimenti 0.0 (punteggio demandato al judge).
  * judge_score OBBLIGATORIO via LLM Judge (llm_judge.py). Formula:
      acc_comp = 0.65*acc_links + 0.35*(judge_score/5)

REGIME euristico keyword cause/effect: RIMOSSO dal calcolo (la funzione
storica resta solo come helper diagnostico has_cause/has_effect nel record).

Regime "skipped": nessuna valutazione, campi N/A, solo energia/latenza/token.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import List, Optional

import semantic_evaluator as _sem
import causal_extractor as _cx

try:  # soglia configurabile via env (.env/CW_SEMANTIC_THRESHOLD)
    from config import env_float
    SEMANTIC_THRESHOLD = env_float("CW_SEMANTIC_THRESHOLD", 0.75)
except Exception:
    SEMANTIC_THRESHOLD = 0.75

# Alias storico (usato da test_validazione_valutazione.py e script legacy):
# mantiene la stessa variabile, non un valore congelato a import-time.
_DEFAULT_THRESHOLD = SEMANTIC_THRESHOLD

NA = None  # rappresentazione N/A nei record (il writer CSV la rende "")


def detect_answer_type(ground_truth: str) -> str:
    """Rileva il tipo di risposta dalla ground truth.
    
    Regole:
    - GT numerica (solo numeri, eventualmente con segno/decimali) -> "number"
    - GT <= 6 parole -> "short_text"
    - Altrimenti -> "free_text"
    """
    if not ground_truth:
        return "free_text"
    gt = ground_truth.strip()
    # Controlla se è numerica (interi, decimali, con segno)
    # Supporta anche alternative separate da "|"
    alternatives = [alt.strip() for alt in gt.split("|")]
    all_numeric = all(
        re.fullmatch(r"[-+]?\d+(?:[.,]\d+)?", alt)
        for alt in alternatives
        if alt
    )
    if all_numeric and alternatives:
        return "number"
    # Conta parole (separatore: spazio)
    word_count = len(gt.split())
    if word_count <= 6:
        return "short_text"
    return "free_text"


def extract_final_number(text: str) -> Optional[str]:
    """Estrae il numero finale da un testo.
    
    Cerca pattern come "= 21", "risposta è 21", "answer: 21", "result 21".
    Se non trova questi pattern, prende l'ultimo numero del testo.
    Ritorna la stringa del numero (normalizzata con "." come decimale) o None.
    """
    if not text:
        return None
    
    # Pattern per "dopo =/risposta/answer/result"
    final_patterns = [
        r"(?:=|risposta|answer|result)\s*[:=]?\s*([-+]?\d+(?:[.,]\d+)?)",
    ]
    for pattern in final_patterns:
        matches = list(re.finditer(pattern, text, re.IGNORECASE))
        if matches:
            # Prendi l'ultimo match
            num_str = matches[-1].group(1)
            # Normalizza: sostituisci "," con "."
            return num_str.replace(",", ".")
    
    # Fallback: trova tutti i numeri e prendi l'ultimo
    all_numbers = re.findall(r"[-+]?\d+(?:[.,]\d+)?", text)
    if all_numbers:
        return all_numbers[-1].replace(",", ".")
    
    return None


def compare_numbers(response_num: str, ground_truth_num: str, 
                   tolerance: float = 1e-6) -> bool:
    """Confronta due numeri entro tolleranza relativa.
    
    tolerance: tolleranza relativa (default 1e-6).
    Ritorna True se i numeri sono uguali entro la tolleranza.
    """
    try:
        resp_val = float(response_num)
        gt_val = float(ground_truth_num)
    except (ValueError, TypeError):
        return False
    
    # Tolleranza relativa
    if gt_val == 0:
        return abs(resp_val) < tolerance
    relative_diff = abs(resp_val - gt_val) / abs(gt_val)
    return relative_diff < tolerance


def normalize_text_for_comparison(text: str) -> str:
    """Normalizza testo per confronto: minuscole, rimuovi accenti/punteggiatura/articoli.
    
    Usato per short_text: la GT normalizzata deve essere contenuta nella risposta normalizzata.
    """
    if not text:
        return ""
    # Minuscole
    t = text.lower()
    # Rimuovi accenti (normalizza Unicode)
    import unicodedata
    t = unicodedata.normalize('NFKD', t)
    t = ''.join(c for c in t if not unicodedata.combining(c))
    # Rimuovi punteggiatura (tieni solo lettere, numeri, spazi)
    t = re.sub(r'[^\w\s]', ' ', t)
    # Rimuovi articoli (italiano e inglese)
    articles = r'\b(a|an|the|il|lo|la|i|gli|le|un|uno|una)\b'
    t = re.sub(articles, ' ', t, flags=re.IGNORECASE)
    # Normalizza spazi
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def check_short_text_containment(response: str, ground_truth: str) -> tuple[bool, Optional[str]]:
    """Verifica se la GT normalizzata è contenuta nella risposta normalizzata.
    
    Supporta alternative separate da "|" nella GT: basta una corrispondenza.
    Ritorna (is_correct, matched_alternative).
    """
    if not ground_truth or not response:
        return False, None
    
    resp_norm = normalize_text_for_comparison(response)
    alternatives = [alt.strip() for alt in ground_truth.split("|") if alt.strip()]
    
    for alt in alternatives:
        alt_norm = normalize_text_for_comparison(alt)
        if alt_norm and alt_norm in resp_norm:
            return True, alt
    
    return False, None


@dataclass
class EvaluationResult:
    acc_links: Optional[float] = NA
    judge_score: Optional[float] = NA
    cosine_sim: Optional[float] = NA          # solo misura reale (regime A)
    semantic_similarity: Optional[float] = NA # metrica principale regime GT
    lexical_similarity: Optional[float] = NA  # metrica secondaria regime GT
    semantic_threshold: float = _DEFAULT_THRESHOLD
    eval_method: str = ""                     # embedding:... | lexical_only(fallback) | llm_judge...
    eval_mode: str = "skipped"                # ground_truth | causal_agent_eval | skipped
    is_tool: bool = False
    n_correct_links: Optional[int] = NA
    causal_accuracy: Optional[float] = NA
    explanation_quality: Optional[float] = NA
    acc_comp: Optional[float] = NA
    # accuracy binaria PRIMARIA: 1 = risposta corretta, 0 = errata, None = N/A
    # (nessuna GT confrontabile). Determinata PRIMA di acc_comp in ogni regime.
    is_correct: Optional[int] = NA
    has_cause: Optional[bool] = NA            # solo diagnostico, NON usato in acc_comp
    has_effect: Optional[bool] = NA           # solo diagnostico, NON usato in acc_comp
    # --- triple causali (tracciabilita' F1) ---
    triples_gt: Optional[int] = NA
    triples_response: Optional[int] = NA
    triples_matched: Optional[int] = NA
    f1_precision: Optional[float] = NA
    f1_recall: Optional[float] = NA
    acc_links_basis: str = ""                 # f1_triples | semantic_fallback | lexical_fallback | none
    # --- LLM Judge ---
    judge_model: str = ""
    evaluated_model: str = ""
    judge_equals_evaluated: Optional[bool] = NA
    judge_source: str = ""                    # ollama | unavailable | disabled
    notes: List[str] = field(default_factory=list)
    # --- answer_type e extracted_answer (nuovi) ---
    answer_type: str = "auto"                 # number | short_text | free_text | auto
    extracted_answer: Optional[str] = NA      # numero estratto (per number) o alternativa trovata (per short_text)


_CAUSE_RE = re.compile(r"\bcaus(?:e|es|ed|ing|al|ality)\b", re.IGNORECASE)
_EFFECT_RE = re.compile(r"\beffect(?:s|ed|ing|ive|ually)?\b", re.IGNORECASE)

GT_LABEL = ("semantic similarity between model response and ground truth "
            "(proxy of correctness, not pure causal accuracy)")


def detect_causal_terms(text: str):
    """SOLO diagnostico: presenza letterale 'cause'/'effect'. NON alimenta
    piu' alcuna metrica di accuratezza (heuristic_keyword_fallback rimosso)."""
    t = text or ""
    return bool(_CAUSE_RE.search(t)), bool(_EFFECT_RE.search(t))


def _normalize_answer(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"[^\w\sàèéìòù]", " ", s)
    s = re.sub(r"\b(a|an|the|il|lo|la|i|gli|le|un|uno|una)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _is_short_answer(text: str) -> bool:
    """True se il testo e' una risposta breve (numero o stringa <=3 token).

    Per risposte brevi la similarita' semantica con embeddings e' inaffidabile
    (es. '25' e '20' hanno coseno alto perche' entrambi numeri). Il confronto
    esatto/lessicale e' preferibile.
    """
    t = (text or "").strip()
    if not t:
        return False
    if re.fullmatch(r"[-+]?\d+(?:[.,]\d+)?", t):
        return True
    return len(t.split()) <= 3


def lexical_similarity(response_text: str, ground_truth: str) -> float:
    """Metrica SECONDARIA: similarità lessicale [0..1] (SequenceMatcher)."""
    gt_n = _normalize_answer(ground_truth)
    ans_n = _normalize_answer(response_text)
    if not gt_n:
        return 0.0
    if ans_n == gt_n or gt_n in ans_n:
        return 1.0
    return round(difflib.SequenceMatcher(None, ans_n, gt_n).ratio(), 6)


def compute_acc_comp(has_ground_truth: bool, acc_links: Optional[float],
                     judge_score: Optional[float],
                     cosine_sim: Optional[float] = None,
                     weights=None) -> Optional[float]:
    """Accuratezza composita con pesi DINAMICI (nessuna costante magica).

    Regime A (GT + cosine disponibile), default 0.50/0.30/0.20:
        w1*acc_links + w2*(judge/5) + w3*cosine
    Regime B (senza GT / cosine None), default 0.65/0.35:
        w1*acc_links + w2*(judge/5)
    ``weights`` consente di sovrascrivere i pesi (da config.py, C2). Se un
    componente e' N/A, i suoi pesi vengono RIDISTRIBUITI proporzionalmente sui
    componenti disponibili (comportamento dichiarato nelle note), mai
    sostituito da valori fittizi. Ritorna None se non c'e' nulla di calcolabile.
    """
    if weights is not None and len(weights) == 3:
        w_links_gt, w_judge_gt, w_cos = float(weights[0]), float(weights[1]), float(weights[2])
    else:
        w_links_gt, w_judge_gt, w_cos = 0.50, 0.30, 0.20
    if weights is not None and len(weights) == 2:
        w_links_b, w_judge_b = float(weights[0]), float(weights[1])
    else:
        w_links_b, w_judge_b = 0.65, 0.35
    parts = []  # (weight, normalized_value)
    if acc_links is not None:
        parts.append((w_links_gt if has_ground_truth else w_links_b,
                      max(0.0, min(1.0, acc_links))))
    if judge_score is not None:
        parts.append((w_judge_gt if has_ground_truth else w_judge_b,
                      max(0.0, min(1.0, judge_score / 5.0))))
    if has_ground_truth and cosine_sim is not None:
        parts.append((w_cos, max(0.0, min(1.0, cosine_sim))))

    if not parts:
        return None
    total_w = sum(w for w, _ in parts)
    score = sum(w * v for w, v in parts) / total_w  # rinormalizzazione onesta
    return round(score, 4)


def _f1_acc_links(text: str, ground_truth: str, res: EvaluationResult):
    """acc_links da F1 su triple causali, con fallback DICHJARATO in catena:
    semantic_similarity -> lexical_similarity. Ritorna (value, basis)."""
    t_gt = _cx.extract_triples(ground_truth)
    t_ans = _cx.extract_triples(text or "")
    res.triples_gt = len(t_gt)
    res.triples_response = len(t_ans)
    f1 = _cx.f1_on_triples(t_gt, t_ans)
    if f1 is not None:
        res.triples_matched = f1["n_matched"]
        res.f1_precision = f1["precision"]
        res.f1_recall = f1["recall"]
        return f1["f1"], "f1_triples"
    # GT senza triple strutturate: valutazione strutturale IMPOSSIBILE.
    res.notes.append(
        "acc_links: ground truth priva di triple causali strutturate; "
        "usa proxy SEMANTICO (non e' una valutazione strutturale di triple)"
    )
    sem = res.semantic_similarity
    if sem is not None:
        return sem, "semantic_fallback"
    lex = res.lexical_similarity
    if lex is not None:
        res.notes.append(
            "fallback LESSICALE (SequenceMatcher) dichiarato: embeddings non "
            "disponibili; NON presentare il risultato come valutazione "
            "strutturale o semantica"
        )
        return lex, "lexical_fallback"
    return 0.0, "none"


def _keyword_fallback_result(text: str, is_tool: bool, res: EvaluationResult,
                             weights=(0.6, 0.3, 0.1)) -> EvaluationResult:
    """REGIME DIAGNOSTICO 'heuristic_keyword_fallback' (legacy, NON usare nei
    benchmark: e' un proxy di struttura, non una ground-truth accuracy).

    Regole storiche approvate nella specifica originale:
      acc_links: 1.0 se compaiono sia 'cause' sia 'effect'; 0.5 se uno solo;
                 0.0 se nessuno.
      judge_score: is_tool=True & links=1.0 -> 4.5; non-tool & links=1.0 -> 4.0;
                   links=0.5 -> 3.0; links=0.0 -> 1.5.
      cosine_sim: 0.88 se is_tool, altrimenti 0.75 (costanti diagnostiche,
                  dichiarate come tali nelle note del record).
      acc_comp = w1*acc_links + w2*(judge/5) + w3*cosine (default 0.6/0.3/0.1).
    I campi semantic_similarity / lexical_similarity restano N/A: nessuna GT
    e' stata confrontata.
    """
    has_c, has_e = res.has_cause, res.has_effect
    if has_c and has_e:
        res.acc_links = 1.0
    elif has_c or has_e:
        res.acc_links = 0.5
    else:
        res.acc_links = 0.0
    if res.acc_links == 1.0:
        res.judge_score = 4.5 if is_tool else 4.0
    elif res.acc_links == 0.5:
        res.judge_score = 3.0
    else:
        res.judge_score = 1.5
    res.cosine_sim = 0.88 if is_tool else 0.75
    res.semantic_similarity = NA   # nessun confronto semantica vs GT
    res.lexical_similarity = NA
    res.explanation_quality = res.judge_score / 5.0
    res.causal_accuracy = res.acc_links
    res.is_correct = 1 if res.acc_links == 1.0 else 0
    res.n_correct_links = int(res.acc_links) if res.acc_links in (0.0, 1.0) else None
    res.acc_links_basis = "keyword_presence_only"
    res.eval_mode = "heuristic_keyword_fallback"
    res.eval_method = "keyword(cause/effect)+fixed-diagnostic-constants"
    w1, w2, w3 = (float(weights[0]), float(weights[1]), float(weights[2]))
    res.acc_comp = round(w1 * res.acc_links + w2 * (res.judge_score / 5.0)
                         + w3 * res.cosine_sim, 6)
    res.notes.append(
        "regime diagnostico keyword: presence of 'cause'/'effect' words, NOT a "
        "ground-truth accuracy; cosine_sim/judge_score are fixed diagnostic "
        f"constants; acc_comp={w1}*acc_links+{w2}*(judge/5)+{w3}*cosine "
        "(legacy formula); non usare per EPCL ne' per confronti causali formali"
    )
    return res


def evaluate_response(
    text: str,
    cause: str,
    effect: str,
    is_tool: bool = False,
    energy_j: float = 0.0,
    use_semantic: bool = False,  # NUOVO: abilita giudizio semantico
) -> dict:
    """
    Valuta accuratezza causale e metriche di efficienza energetica.
    
    Versione robusta con:
    - Gestione completa di None/NaN/stringhe vuote
    - Normalizzazione testo (minuscole, spazi, punteggiatura)
    - Fallback a cascata: semantico → lessicale → keyword
    - Metriche multiple per analisi comparativa
    """
    import re
    from difflib import SequenceMatcher
    
    # ==================================================================
    # 1. NORMALIZZAZIONE INPUT (gestione edge cases)
    # ==================================================================
    def normalize(text: str) -> str:
        """Normalizza il testo per confronto robusto."""
        if text is None:
            return ""
        text = str(text).strip().lower()
        # Rimuovi punteggiatura e spazi multipli
        text = re.sub(r'[^\w\s]', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        return text
    
    text_norm = normalize(text)
    cause_norm = normalize(cause)
    effect_norm = normalize(effect)
    
    # ==================================================================
    # 2. RILEVAZIONE LINK CAUSALI (3 livelli)
    # ==================================================================
    
    # Livello 1: Keyword matching (base)
    cause_in_text = cause_norm in text_norm if cause_norm else False
    effect_in_text = effect_norm in text_norm if effect_norm else False
    
    # Livello 2: Similarità lessicale (fuzzy)
    def best_lexical_match(target: str, source: str, threshold: float = 0.6) -> bool:
        """Verifica se una sottostringa simile a target è presente in source."""
        if not target or not source:
            return False
        # Prova con parole chiave separate
        target_words = target.split()
        for word in target_words:
            if len(word) < 3:
                continue
            # Cerca la parola o una molto simile
            if word in source:
                return True
            # Fallback: similarità con finestre scorrevoli
            for i in range(len(source) - len(word) + 1):
                window = source[i:i+len(word)]
                if SequenceMatcher(None, word, window).ratio() >= threshold:
                    return True
        return False
    
    cause_fuzzy = best_lexical_match(cause_norm, text_norm)
    effect_fuzzy = best_lexical_match(effect_norm, text_norm)
    
    # Livello 3: Similarità semantica (opzionale, richiede sentence-transformers)
    semantic_sim = 0.0
    if use_semantic:
        try:
            from semantic_judge import compute_similarity
            # Confronta la risposta con una frase "ground truth" generata
            ground_truth = f"{cause} influenza {effect}"
            result = compute_similarity(text, ground_truth, method="auto")
            semantic_sim = result['similarity']
        except Exception as e:
            logger.debug(f"Giudizio semantico non disponibile: {e}")
    
    # ==================================================================
    # 3. CALCOLO ACCURATEZZA COMPOSITA
    # ==================================================================
    
    # Accuratezza link causali (0, 0.5, 1)
    if (cause_in_text and effect_in_text) or (cause_fuzzy and effect_fuzzy):
        acc_links = 1.0
    elif cause_in_text or effect_in_text or cause_fuzzy or effect_fuzzy:
        acc_links = 0.5
    else:
        acc_links = 0.0
    
    # Judge score (qualità spiegazione)
    text_length = len(text_norm.split())
    if acc_links == 1.0 and text_length > 20:
        judge_score = 4.5 if is_tool else 4.0
    elif acc_links == 1.0:
        judge_score = 3.5
    elif acc_links == 0.5:
        judge_score = 2.5
    else:
        judge_score = 1.0
    
    # Cosine similarity (proxy: usa lessicale o semantico)
    if semantic_sim > 0:
        cosine_sim = semantic_sim
    else:
        # Stima basata su overlap di parole
        text_words = set(text_norm.split())
        target_words = set((cause_norm + " " + effect_norm).split())
        if text_words and target_words:
            cosine_sim = len(text_words & target_words) / len(text_words | target_words)
        else:
            cosine_sim = 0.0
    
    # Accuratezza composita (formula dalla tesi)
    acc_comp = (acc_links * 0.5 + 
                (judge_score / 5.0) * 0.3 + 
                cosine_sim * 0.2)
    
    # ==================================================================
    # 4. METRICHE ENERGETICHE
    # ==================================================================
    
    # ECE: Efficiency-Causal Effectiveness (accuratezza per joule)
    if energy_j > 0:
        ece = acc_comp / energy_j
    else:
        ece = float('inf') if acc_comp > 0 else 0.0
    
    # EPCL: Energy Per Causal Link
    n_correct_links = 1 if acc_links == 1.0 else 0
    if n_correct_links > 0:
        epcl = energy_j / n_correct_links
    else:
        epcl = float('inf')
    
    # ==================================================================
    # 5. RETURN STRUCTURED
    # ==================================================================
    return {
        # Accuratezza
        "acc_links": acc_links,
        "judge_score": judge_score,
        "cosine_sim": cosine_sim,
        "acc_comp": acc_comp,
        "n_correct_links": n_correct_links,
        
        # Dettagli diagnostici
        "cause_detected_exact": cause_in_text,
        "effect_detected_exact": effect_in_text,
        "cause_detected_fuzzy": cause_fuzzy,
        "effect_detected_fuzzy": effect_fuzzy,
        "semantic_similarity": semantic_sim,
        "text_length_words": text_length,
        
        # Metriche energetiche
        "ece": ece,
        "epcl": epcl,
        "energy_j": energy_j,
        
        # Metadata
        "is_tool": is_tool,
        "eval_method": "semantic" if semantic_sim > 0 else "lexical_fuzzy"
    }


def _run_judge(question: str, answer: str, res: EvaluationResult, judge_fn):
    """Esegue il giudice e compila i campi tracciabilita'/bias."""
    try:
        if judge_fn is None:
            import llm_judge as _lj
            judge_fn = _lj.call_llm_judge
        score, info = judge_fn(question or "", answer or "", None)
    except Exception as exc:  # il giudice non deve MAI far fallire la valutazione
        score, info = None, {"reason": f"{type(exc).__name__}: {exc}",
                             "judge_model": ""}
    res.judge_model = str(info.get("judge_model", ""))
    res.judge_source = "ollama" if info.get("ok") else \
        ("disabled" if "ENABLED" in str(info.get("reason", "")) else "unavailable")
    if res.judge_model and res.evaluated_model:
        same = res.judge_model.strip().lower() == res.evaluated_model.strip().lower()
        res.judge_equals_evaluated = same
        if same:
            res.notes.append(
                "Self-evaluation bias possible: judge model equals evaluated model."
            )
    return score, info


def evaluate_skipped(reason: str = "") -> EvaluationResult:
    """Risultato esplicito N/A (usato nei percorsi d'errore del runner)."""
    res = EvaluationResult(eval_mode="skipped")
    res.eval_method = "none"
    if reason:
        res.notes.append(f"valutazione non eseguita: {reason}")
    return res
