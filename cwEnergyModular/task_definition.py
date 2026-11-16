# -*- coding: utf-8 -*-
"""task_definition.py — Pattern dichiarativo per definire i task di benchmark energetico.

Ispirato a lm-evaluation-harness: ogni task è definito da un file YAML che
dichiara il modello, il prompt, la finestra di misura e le metriche energetiche
attese. Non serve il repository, serve il pattern.

Cosa dichiara un task YAML:
- **modello**: nome del modello Ollama da usare
- **prompt**: testo del prompt da inviare
- **few_shot_count**: numero di esempi few-shot nel prompt (metadato per
  tracciabilità energetica: un prompt con 10 few-shot costa più di uno zero-shot)
- **keep_alive**: forma numerica inviata al motore (intero, non stringa)
- **num_ctx**: contesto massimo
- **m**: numero di richieste per blocco (default 3, P3.13)
- **prompt_variants**: lista di varianti del prompt per il multi-prompt
  (Evalita-LLM: eseguire lo stesso task con N prompt diversi e aggregare
  l'energia con la stessa statistica già implementata)

Esempio di task YAML:
```yaml
task_name: qwen2.5_0.5b_italiano
model: qwen2.5:0.5b
prompt: "Qual è la capitale d'Italia?"
few_shot_count: 0
keep_alive: -1
num_ctx: 8192
m: 3
prompt_variants:
  - "Qual è la capitale d'Italia?"
  - "Indica la capitale della Repubblica Italiana."
  - "Di quale città è capitale l'Italia?"
```

Il runner v4 legge questo file e esegue il task con le varianti del prompt,
aggregando l'energia con la statistica già implementata (Wilson CI, bootstrap
a cluster).
"""
from __future__ import annotations

import yaml
from pathlib import Path
from typing import Dict, List, Optional, Any


class TaskDefinition:
    """Rappresenta un task di benchmark energetico definito in YAML.
    
    Attributi:
        task_name: nome univoco del task
        model: nome del modello Ollama
        prompt: prompt principale
        few_shot_count: numero di esempi few-shot (metadato per tracciabilità)
        keep_alive: forma numerica inviata al motore
        num_ctx: contesto massimo
        m: numero di richieste per blocco
        prompt_variants: lista di varianti del prompt per il multi-prompt
    """
    
    def __init__(
        self,
        task_name: str,
        model: str,
        prompt: str,
        few_shot_count: int = 0,
        keep_alive: int = -1,
        num_ctx: int = 8192,
        m: int = 3,
        prompt_variants: Optional[List[str]] = None,
    ):
        self.task_name = task_name
        self.model = model
        self.prompt = prompt
        self.few_shot_count = few_shot_count
        self.keep_alive = keep_alive
        self.num_ctx = num_ctx
        self.m = m
        self.prompt_variants = prompt_variants or [prompt]
    
    @classmethod
    def from_yaml(cls, path: Path) -> 'TaskDefinition':
        """Carica un task da un file YAML.
        
        Args:
            path: percorso del file YAML
            
        Returns:
            TaskDefinition istanziata
            
        Raises:
            ValueError: se il file YAML non contiene i campi obbligatori
        """
        if not path.exists():
            raise FileNotFoundError(f"File YAML non trovato: {path}")
        
        with open(path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        
        if not isinstance(data, dict):
            raise ValueError(f"File YAML non valido: {path}")
        
        task_name = data.get('task_name')
        if not task_name:
            raise ValueError(f"Campo 'task_name' obbligatorio mancante in {path}")
        
        model = data.get('model')
        if not model:
            raise ValueError(f"Campo 'model' obbligatorio mancante in {path}")
        
        prompt = data.get('prompt')
        if not prompt:
            raise ValueError(f"Campo 'prompt' obbligatorio mancante in {path}")
        
        return cls(
            task_name=task_name,
            model=model,
            prompt=prompt,
            few_shot_count=data.get('few_shot_count', 0),
            keep_alive=data.get('keep_alive', -1),
            num_ctx=data.get('num_ctx', 8192),
            m=data.get('m', 3),
            prompt_variants=data.get('prompt_variants'),
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte il task in un dizionario serializzabile.
        
        Returns:
            Dizionario con i campi del task
        """
        return {
            'task_name': self.task_name,
            'model': self.model,
            'prompt': self.prompt,
            'few_shot_count': self.few_shot_count,
            'keep_alive': self.keep_alive,
            'num_ctx': self.num_ctx,
            'm': self.m,
            'prompt_variants': self.prompt_variants,
        }
    
    def __repr__(self) -> str:
        return (
            f"TaskDefinition(task_name={self.task_name!r}, "
            f"model={self.model!r}, "
            f"prompt_variants={len(self.prompt_variants)})"
        )


def load_task_from_yaml(path: Path) -> TaskDefinition:
    """Funzione di convenienza per caricare un task da un file YAML.
    
    Args:
        path: percorso del file YAML
        
    Returns:
        TaskDefinition istanziata
    """
    return TaskDefinition.from_yaml(path)
