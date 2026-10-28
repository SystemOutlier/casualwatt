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


def evaluate_response(text: str, is_tool: bool = False,
                      ground_truth: Optional[str] = None,
                      mode: str = "auto", question: str = "",
                      evaluated_model: str = "",
                      judge_fn=None,
                      answer_type: str = "auto",
                      use_semantic: bool = False) -> EvaluationResult:
    """Valutazione UNIVERSALE.

    mode:
      * "auto": ground_truth presente -> REGIME A ("ground_truth");
                altrimenti -> REGIME B ("causal_agent_eval") con LLM Judge.
      * "skip": forza N/A anche con GT presente.
      * "causal" / "heuristic_keyword_fallback": REGIME LEGACY diagnostico
        ('heuristic_keyword_fallback'): euristica keyword cause/effect con
        costanti fisse. NON e' una ground-truth accuracy e NON va usato nei
        benchmark ufficiali; mantenuto solo per retrocompatibilita' dei test
        storici (main.py --selftest, test_validazione_valutazione.py).
    judge_fn: iniettabile per i test (firma: (question, answer, model?) ->
              (score|None, info dict)). Default: llm_judge.call_llm_judge.
    answer_type: "number" | "short_text" | "free_text" | "auto" (default "auto").
                 Determina la strategia di valutazione nel REGIME A.
    use_semantic: se False (default), NON carica sentence-transformers durante
                  il benchmark (risparmio energetico). La valutazione semantica
                  va fatta POST-HOC con semantic_judge.py. Se True, abilita il
                  giudizio semantico con embedding (solo per uso post-hoc).
    Non solleva MAI eccezioni.
    """
    # Robustezza: normalizza input None/NaN/empty
    if text is None:
        text = ""
    if ground_truth is None or ground_truth == "":
        ground_truth = NA
    # NaN check (se ground_truth e' un float NaN)
    try:
        import math
        if isinstance(ground_truth, float) and math.isnan(ground_truth):
            ground_truth = NA
    except Exception:
        pass

    mode = (mode or "auto").strip().lower()
    res = EvaluationResult(is_tool=bool(is_tool),
                           evaluated_model=evaluated_model or "")
    res._answer_type_param = answer_type  # passa al REGIME A
    res.has_cause, res.has_effect = detect_causal_terms(text)  # solo diagnostico

    if mode == "skip":
        res.eval_mode, res.eval_method = "skipped", "none"
        res.notes.append("valutazione saltata per richiesta esplicita")
        return res

    # --- C2: pesi acc_comp configurabili (dichiarati nelle note della riga) -
    try:
        import config as _cfg
        w_gt = tuple(_cfg.ACC_COMP_WEIGHTS_GT)      # (links, judge, cosine)
        w_nogt = tuple(_cfg.ACC_COMP_WEIGHTS_NOGT)  # (links, judge)
    except Exception:
        w_gt, w_nogt = (0.50, 0.30, 0.20), (0.65, 0.35)

    # --- REGIME LEGACY keyword (alias storico 'causal') ----------------------
    if mode in ("causal", "heuristic_keyword_fallback"):
        return _keyword_fallback_result(text, bool(is_tool), res)

    # ------------------------- REGIME A: ground truth -----------------------
    if ground_truth not in (None, "", NA):
        res.eval_mode = "ground_truth"
        gt_str = str(ground_truth).strip()
        ans_str = (text or "").strip()
        
        # Determina answer_type (da parametro o auto-detect)
        # answer_type viene passato come parametro aggiuntivo (vedi sotto)
        answer_type = getattr(res, '_answer_type_param', 'auto')
        if answer_type == "auto":
            answer_type = detect_answer_type(gt_str)
        res.answer_type = answer_type
        
        # Valutazione basata su answer_type
        if answer_type == "number":
            # Estrai numero dalla risposta e confronta con GT
            extracted = extract_final_number(ans_str)
            res.extracted_answer = extracted
            if extracted is not None:
                # Confronta con tutte le alternative numeriche nella GT
                alternatives = [alt.strip() for alt in gt_str.split("|") if alt.strip()]
                correct = any(
                    compare_numbers(extracted, alt)
                    for alt in alternatives
                )
                res.is_correct = 1 if correct else 0
                res.acc_comp = 1.0 if correct else 0.0
                res.eval_method = f"number_extraction+comparison(tol=1e-6)"
                res.notes.append(
                    f"answer_type=number: estratto '{extracted}' da risposta, "
                    f"confronto con GT '{gt_str}' -> is_correct={res.is_correct}"
                )
            else:
                res.is_correct = 0
                res.acc_comp = 0.0
                res.eval_method = "number_extraction_failed"
                res.notes.append("answer_type=number: nessun numero estratto dalla risposta")
            # Per number: acc_comp = is_correct (0 o 1), niente altre componenti
            res.causal_accuracy = res.acc_comp
            res.acc_links = res.acc_comp
            res.acc_links_basis = "exact_number_match"
            res.n_correct_links = 1 if res.is_correct else 0
            res.semantic_similarity = NA
            res.cosine_sim = NA
            res.lexical_similarity = NA
            res.judge_score = NA
            res.explanation_quality = NA
            return res
        
        elif answer_type == "short_text":
            # Normalizza e verifica contenimento
            correct, matched_alt = check_short_text_containment(ans_str, gt_str)
            res.is_correct = 1 if correct else 0
            res.extracted_answer = matched_alt
            res.acc_comp = 1.0 if correct else 0.0
            res.eval_method = "short_text_normalization+containment"
            res.notes.append(
                f"answer_type=short_text: normalizzazione e contenimento -> "
                f"is_correct={res.is_correct}" + (f", matched='{matched_alt}'" if matched_alt else "")
            )
            # Per short_text: acc_comp = is_correct (0 o 1), niente altre componenti
            res.causal_accuracy = res.acc_comp
            res.acc_links = res.acc_comp
            res.acc_links_basis = "exact_text_containment"
            res.n_correct_links = 1 if res.is_correct else 0
            res.semantic_similarity = NA
            res.cosine_sim = NA
            res.lexical_similarity = NA
            res.judge_score = NA
            res.explanation_quality = NA
            return res
        
        else:  # answer_type == "free_text"
            # Calcola sempre la similarita' lessicale (leggera, nessun modello)
            res.lexical_similarity = lexical_similarity(text or "", str(ground_truth))
            
            # Valutazione semantica: SOLO se use_semantic=True (post-hoc)
            # Di default (False), non carica sentence-transformers per risparmiare energia
            if use_semantic:
                sem = _sem.semantic_similarity(text or "", str(ground_truth))
                res.semantic_similarity = sem
                res.cosine_sim = sem
            else:
                sem = NA
                res.semantic_similarity = NA
                res.cosine_sim = NA
                res.notes.append(
                    "answer_type=free_text: use_semantic=False (default), "
                    "valutazione semantica saltata per risparmiare energia durante "
                    "il benchmark. Usa semantic_judge.py per valutazione POST-HOC."
                )
            
            thr = _DEFAULT_THRESHOLD
            if sem is None:
                if use_semantic:
                    res.eval_method = "no_embeddings"
                    res.is_correct = NA
                    res.notes.append(
                        f"answer_type=free_text: embeddings non disponibili "
                        f"({_sem.init_error() or 'motivo non specificato'}): "
                        f"is_correct=N/A, NON usare similarità lessicale come accuratezza"
                    )
                else:
                    # use_semantic=False: fallback a lessicale per is_correct
                    res.eval_method = "lexical_only(use_semantic=False)"
                    res.is_correct = 1 if res.lexical_similarity >= 0.85 else 0
                    res.notes.append(
                        f"answer_type=free_text: use_semantic=False, "
                        f"fallback lessicale per is_correct (lexical_similarity="
                        f"{res.lexical_similarity:.3f}, threshold=0.85)"
                    )
            else:
                res.eval_method = _sem.method_label()
                res.is_correct = 1 if sem >= thr else 0
                res.notes.append(
                    f"answer_type=free_text: semantic_similarity={sem:.3f}, "
                    f"threshold={thr}, is_correct={res.is_correct}"
                )
            res.causal_accuracy = sem
            res.acc_links, res.acc_links_basis = _f1_acc_links(text, str(ground_truth), res)
            res.n_correct_links = res.triples_matched if res.triples_matched is not None else \
                (1 if res.is_correct else 0)
            # judge opzionale ma tentato
            j_score, j_info = _run_judge(question, text, res, judge_fn)
            res.judge_score = j_score
            res.explanation_quality = (j_score / 5.0) if j_score is not None else NA
            res.acc_comp = compute_acc_comp(True, res.acc_links, j_score, sem,
                                            weights=(w_gt[0], w_gt[1], w_gt[2]))
            res.notes.append(GT_LABEL)
            res.notes.append(
                f"regime A (free_text): acc_comp={w_gt[0]}*acc_links+{w_gt[1]}*(judge/5)"
                f"+{w_gt[2]}*cosine (pesi da config; componenti N/A rinormalizzati)"
            )
            return res

    # ----------------- REGIME B: senza GT -> LLM-as-a-Judge -----------------
    res.eval_mode = "causal_agent_eval"
    res.eval_method = "llm_judge(ollama,T=0)+triple_f1(self-consistency)"
    res.cosine_sim = NA               # MAI forzato: N/A nel CSV
    res.semantic_similarity = NA      # idem: nessuna GT da confrontare
    res.lexical_similarity = NA
    # acc_links: struttura causale auto-consistente nella risposta
    # (triples estratte; senza triple riconoscibili -> 0.0, punteggio al judge)
    t_ans = _cx.extract_triples(text or "")
    res.triples_response = len(t_ans)
    res.triples_gt = NA               # inesistente in regime B
    if t_ans:
        # C3: 1.0 qui significa SOLO "struttura causale presente ed
        # estraibile" — NON e' una misura di correttezza (nessuna GT con cui
        # confrontare). Campo dichiaratamente diagnostico; non usare per EPCL.
        res.acc_links = 1.0
        res.acc_links_basis = "structure_presence_only"
        res.triples_matched = None    # nessun confronto vs GT: link corretti N/A
        res.n_correct_links = None    # C1/C3: EPCL non calcolabile in regime B
        res.notes.append(
            "regime B: acc_links=1.0 indica PRESENZA DI STRUTTURA, NON "
            "correttezza (diagnostico); n_correct_links=N/A perche' i causal "
            "link corretti sono definiti solo contro una ground truth"
        )
    else:
        res.acc_links = 0.0
        res.acc_links_basis = "none"
        res.n_correct_links = None    # idem: mai 0 come se fosse misurato
        res.notes.append(
            "nessuna tripla causale estraibile dalla risposta: acc_links=0.0, "
            "punteggio qualitativo interamente demandato al LLM Judge"
        )
    j_score, j_info = _run_judge(question, text, res, judge_fn)
    if j_score is None:
        res.eval_method = "llm_judge_unavailable"
        res.notes.append(
            f"LLM Judge non disponibile ({j_info.get('reason','')}): "
            f"acc_comp calcolata SOLO su acc_links, giudice dichiarato assente"
        )
    res.judge_score = j_score
    res.explanation_quality = (j_score / 5.0) if j_score is not None else NA
    # C3: n_correct_links NON sovrascritto qui: in regime B resta N/A (nessuna
    # GT -> nessun causal link "corretto" misurabile; triples_matched e' solo
    # conteggio di struttura estratta).
    # accuracy binaria primaria (1/0) determinata PRIMA di acc_comp composita
    res.is_correct = (1 if j_score >= 4.0 else 0) if j_score is not None else NA
    res.causal_accuracy = NA          # in regime B non esiste causal accuracy GT-based
    res.acc_comp = compute_acc_comp(False, res.acc_links, j_score, None,
                                    weights=(w_nogt[0], w_nogt[1]))
    res.notes.append(
        f"regime B: acc_comp={w_nogt[0]}*acc_links+{w_nogt[1]}*(judge/5) "
        f"(pesi da config); cosine_sim/semantic_similarity=N/A (nessuna ground truth)"
    )
    return res


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
