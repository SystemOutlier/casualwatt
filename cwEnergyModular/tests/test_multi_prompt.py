# -*- coding: utf-8 -*-
"""test_multi_prompt.py — Test per il modulo multi_prompt.

Verifica che:
- aggregate_prompt_energy() calcoli correttamente le statistiche
- calculate_energy_prompt_sensitivity() restituisca la deviazione standard
- I casi limite (meno di 2 campioni, energie nulle) siano gestiti
"""
import pytest

from multi_prompt import (
    aggregate_prompt_energy,
    calculate_energy_prompt_sensitivity,
)


class TestAggregatePromptEnergy:
    """Test per l'aggregazione dell'energia delle varianti del prompt."""
    
    def test_aggrega_energie_attive(self):
        """Le energie attive vengono aggregate correttamente."""
        prompt_results = [
            {
                'prompt_variant_index': 0,
                'prompt': "Qual è la capitale d'Italia?",
                'task_name': 'test_task',
                'model': 'qwen2.5:0.5b',
                'active_energy_j': 1.0,
            },
            {
                'prompt_variant_index': 1,
                'prompt': "Indica la capitale.",
                'task_name': 'test_task',
                'model': 'qwen2.5:0.5b',
                'active_energy_j': 2.0,
            },
            {
                'prompt_variant_index': 2,
                'prompt': "Di quale città è capitale l'Italia?",
                'task_name': 'test_task',
                'model': 'qwen2.5:0.5b',
                'active_energy_j': 3.0,
            },
        ]
        
        result = aggregate_prompt_energy(prompt_results)
        
        assert result['task_name'] == 'test_task'
        assert result['model'] == 'qwen2.5:0.5b'
        assert result['prompt_variant_count'] == 3
        assert result['mean_active_energy_j'] == 2.0
        assert result['min_active_energy_j'] == 1.0
        assert result['max_active_energy_j'] == 3.0
        # stdev([1.0, 2.0, 3.0]) = 1.0
        # sensitivity è ora un dizionario con 3 metriche
        assert abs(result['energy_prompt_sensitivity']['std_energy_j'] - 1.0) < 1e-9
        # CV = std/mean = 1.0/2.0 = 0.5
        assert abs(result['energy_prompt_sensitivity']['cv'] - 0.5) < 1e-9
        # Max/Min = 3.0/1.0 = 3.0
        assert abs(result['energy_prompt_sensitivity']['max_min_ratio'] - 3.0) < 1e-9
    
    def test_energie_nulle_restituiscono_none(self):
        """Se le energie sono tutte None, le metriche sono None."""
        prompt_results = [
            {
                'prompt_variant_index': 0,
                'prompt': "Qual è la capitale d'Italia?",
                'task_name': 'test_task',
                'model': 'qwen2.5:0.5b',
                'active_energy_j': None,
            },
        ]
        
        result = aggregate_prompt_energy(prompt_results)
        
        assert result['mean_active_energy_j'] is None
        assert result['energy_prompt_sensitivity']['std_energy_j'] is None
        assert result['energy_prompt_sensitivity']['cv'] is None
        assert result['energy_prompt_sensitivity']['max_min_ratio'] is None
    
    def test_una_sola_variante_sensibilita_non_calcolabile(self):
        """Una sola variante non permette di calcolare la sensibilità.
        
        La sensibilità richiede almeno 2 campioni per stimare la variabilità.
        Con un solo prompt, l'energia misurata è legata a quella formulazione,
        non al modello: le metriche di sensibilità sono None.
        """
        prompt_results = [
            {
                'prompt_variant_index': 0,
                'prompt': "Qual è la capitale d'Italia?",
                'task_name': 'test_task',
                'model': 'qwen2.5:0.5b',
                'active_energy_j': 1.5,
            },
        ]
        
        result = aggregate_prompt_energy(prompt_results)
        
        assert result['mean_active_energy_j'] == 1.5
        # Con un solo campione, la sensibilità non è calcolabile
        assert result['energy_prompt_sensitivity']['std_energy_j'] is None
        assert result['energy_prompt_sensitivity']['cv'] is None
        assert result['energy_prompt_sensitivity']['max_min_ratio'] is None


class TestCalculateEnergyPromptSensitivity:
    """Test per il calcolo della sensibilità energetica al prompt."""
    
    def test_calcola_tre_metriche(self):
        """Le tre metriche vengono calcolate correttamente."""
        energies = [1.0, 2.0, 3.0]
        sensitivity = calculate_energy_prompt_sensitivity(energies)
        # std = 1.0, mean = 2.0, CV = 0.5, Max/Min = 3.0
        assert abs(sensitivity['std_energy_j'] - 1.0) < 1e-9
        assert abs(sensitivity['cv'] - 0.5) < 1e-9
        assert abs(sensitivity['max_min_ratio'] - 3.0) < 1e-9
    
    def test_meno_di_due_campioni_restituisce_none(self):
        """Meno di due campioni restituisce None per tutte le metriche."""
        assert calculate_energy_prompt_sensitivity([1.0]) == {
            'std_energy_j': None, 'cv': None, 'max_min_ratio': None
        }
        assert calculate_energy_prompt_sensitivity([]) == {
            'std_energy_j': None, 'cv': None, 'max_min_ratio': None
        }
    
    def test_due_campioni_uguali_danno_zero(self):
        """Due campioni uguali danno std zero, CV zero, Max/Min 1.0."""
        sensitivity = calculate_energy_prompt_sensitivity([1.5, 1.5])
        assert sensitivity['std_energy_j'] == 0.0
        assert sensitivity['cv'] == 0.0
        assert sensitivity['max_min_ratio'] == 1.0
    
    def test_due_campioni_diversi_danno_valore_positivo(self):
        """Due campioni diversi danno valori positivi per tutte le metriche."""
        sensitivity = calculate_energy_prompt_sensitivity([1.0, 3.0])
        assert sensitivity['std_energy_j'] > 0
        assert sensitivity['cv'] > 0
        assert sensitivity['max_min_ratio'] > 1.0
        # stdev([1.0, 3.0]) = 1.414...
        assert abs(sensitivity['std_energy_j'] - 1.4142135623730951) < 1e-9
        # CV = 1.414.../2.0 = 0.707...
        assert abs(sensitivity['cv'] - 0.7071067811865476) < 1e-9
        # Max/Min = 3.0/1.0 = 3.0
        assert abs(sensitivity['max_min_ratio'] - 3.0) < 1e-9
    
    def test_cv_permette_confronto_cross_modello(self):
        """CV normalizza la sensibilità, permettendo il confronto cross-modello.
        
        Un SLM con energie [1.0, 1.2, 0.8] ha std = 0.2, CV = 0.2/1.0 = 0.2
        Un LLM con energie [100.0, 120.0, 80.0] ha std = 20.0, CV = 20.0/100.0 = 0.2
        Le due CV sono uguali: la sensibilità relativa è la stessa.
        """
        slm_energies = [1.0, 1.2, 0.8]
        llm_energies = [100.0, 120.0, 80.0]
        
        slm_sensitivity = calculate_energy_prompt_sensitivity(slm_energies)
        llm_sensitivity = calculate_energy_prompt_sensitivity(llm_energies)
        
        # std assoluto: LLM >> SLM
        assert llm_sensitivity['std_energy_j'] > slm_sensitivity['std_energy_j']
        # CV: uguale perché la variabilità relativa è la stessa
        assert abs(slm_sensitivity['cv'] - llm_sensitivity['cv']) < 1e-9
        # Max/Min: uguale perché il rapporto è lo stesso
        assert abs(slm_sensitivity['max_min_ratio'] - llm_sensitivity['max_min_ratio']) < 1e-9
    
    def test_cv_undefined_per_media_zero(self):
        """CV è None se la media è zero (caso patologico)."""
        # Energie che si sommano a zero (impossibili nella pratica, ma test del contratto)
        energies = [-1.0, 1.0]
        sensitivity = calculate_energy_prompt_sensitivity(energies)
        assert sensitivity['std_energy_j'] is not None
        assert sensitivity['cv'] is None  # mean = 0.0
        assert sensitivity['max_min_ratio'] is None  # min < 0
    
    def test_max_min_ratio_sensibile_all_ampiezza(self):
        """Max/Min ratio misura l'ampiezza conservativa della variabilità."""
        # Variabilità bassa: [1.0, 1.1, 0.9]
        low_var = calculate_energy_prompt_sensitivity([1.0, 1.1, 0.9])
        # Variabilità alta: [1.0, 2.0, 0.5]
        high_var = calculate_energy_prompt_sensitivity([1.0, 2.0, 0.5])
        
        assert high_var['max_min_ratio'] > low_var['max_min_ratio']
        # 2.0/0.5 = 4.0 > 1.1/0.9 ≈ 1.22
        assert high_var['max_min_ratio'] == 4.0
