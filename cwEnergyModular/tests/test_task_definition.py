# -*- coding: utf-8 -*-
"""test_task_definition.py — Test per il modulo task_definition.

Verifica che:
- TaskDefinition carichi correttamente da un file YAML
- I campi obbligatori siano validati
- Le varianti del prompt siano gestite correttamente
- La serializzazione in dizionario funzioni
"""
import pytest
import tempfile
from pathlib import Path

from task_definition import TaskDefinition, load_task_from_yaml


class TestTaskDefinitionFromYaml:
    """Test per il caricamento da YAML."""
    
    def test_carica_task_da_yaml_valido(self):
        """Un file YAML valido viene caricato correttamente."""
        yaml_content = """
task_name: test_task
model: qwen2.5:0.5b
prompt: "Qual e la capitale d'Italia?"
few_shot_count: 0
keep_alive: -1
num_ctx: 8192
m: 3
prompt_variants:
  - "Qual e la capitale d'Italia?"
  - "Indica la capitale della Repubblica Italiana."
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            path = Path(f.name)
        
        try:
            task = TaskDefinition.from_yaml(path)
            assert task.task_name == "test_task"
            assert task.model == "qwen2.5:0.5b"
            assert task.prompt == "Qual e la capitale d'Italia?"
            assert task.few_shot_count == 0
            assert task.keep_alive == -1
            assert task.num_ctx == 8192
            assert task.m == 3
            assert len(task.prompt_variants) == 2
        finally:
            path.unlink()
    
    def test_campi_obbligatori_mancanti(self):
        """Un file YAML senza campi obbligatori solleva ValueError."""
        yaml_content = """
model: qwen2.5:0.5b
prompt: "Qual e la capitale d'Italia?"
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            path = Path(f.name)
        
        try:
            with pytest.raises(ValueError, match="task_name"):
                TaskDefinition.from_yaml(path)
        finally:
            path.unlink()
    
    def test_file_yaml_non_esistente(self):
        """Un file YAML non esistente solleva FileNotFoundError."""
        path = Path("/non/esistente/task.yaml")
        with pytest.raises(FileNotFoundError):
            TaskDefinition.from_yaml(path)
    
    def test_prompt_variants_assenti_usano_prompt_principale(self):
        """Se prompt_variants è assente, viene usato il prompt principale."""
        yaml_content = """
task_name: test_task
model: qwen2.5:0.5b
prompt: "Qual e la capitale d'Italia?"
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            path = Path(f.name)
        
        try:
            task = TaskDefinition.from_yaml(path)
            assert task.prompt_variants == ["Qual e la capitale d'Italia?"]
        finally:
            path.unlink()


class TestTaskDefinitionToDict:
    """Test per la serializzazione in dizionario."""
    
    def test_to_dict_inclutti_tutti_i_campi(self):
        """to_dict() restituisce tutti i campi del task."""
        task = TaskDefinition(
            task_name="test_task",
            model="qwen2.5:0.5b",
            prompt="Qual e la capitale d'Italia?",
            few_shot_count=0,
            keep_alive=-1,
            num_ctx=8192,
            m=3,
            prompt_variants=["Qual e la capitale d'Italia?", "Indica la capitale."],
        )
        
        d = task.to_dict()
        assert d['task_name'] == "test_task"
        assert d['model'] == "qwen2.5:0.5b"
        assert d['prompt'] == "Qual e la capitale d'Italia?"
        assert d['few_shot_count'] == 0
        assert d['keep_alive'] == -1
        assert d['num_ctx'] == 8192
        assert d['m'] == 3
        assert len(d['prompt_variants']) == 2


class TestLoadTaskFromYaml:
    """Test per la funzione di convenienza."""
    
    def test_load_task_from_yaml_carica_correttamente(self):
        """load_task_from_yaml() carica un task da un file YAML."""
        yaml_content = """
task_name: test_task
model: qwen2.5:0.5b
prompt: "Qual e la capitale d'Italia?"
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            path = Path(f.name)
        
        try:
            task = load_task_from_yaml(path)
            assert isinstance(task, TaskDefinition)
            assert task.task_name == "test_task"
        finally:
            path.unlink()
