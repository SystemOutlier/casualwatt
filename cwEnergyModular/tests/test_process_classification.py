# -*- coding: utf-8 -*-
"""Test per la classificazione dei processi in machine_state.py.

Verifica che classify_process() distingua correttamente TARGET_WORKLOAD,
BACKGROUND e SYSTEM_UNATTRIBUTED basandosi su PID, nome e albero dei processi.
"""
import pytest
from unittest.mock import patch, MagicMock

from machine_state import (
    classify_process,
    _get_process_tree,
    _find_descendants,
    CLASS_TARGET_WORKLOAD,
    CLASS_BACKGROUND,
    CLASS_SYSTEM_UNATTRIBUTED,
    TARGET_WORKLOAD_NAMES,
)


class TestClassifyProcess:
    """Test per classify_process()."""

    def _make_tree(self, processes):
        """Costruisce un albero di processi finto per i test."""
        tree = {}
        for pid, name, ppid, create_time in processes:
            tree[pid] = {
                "pid": pid,
                "name": name,
                "ppid": ppid,
                "create_time": create_time,
            }
        return tree

    def test_ollama_by_name(self):
        """Ollama classificato come TARGET_WORKLOAD per nome."""
        tree = self._make_tree([
            (1234, "ollama", 100, 1000.0),
        ])
        result = classify_process(1234, target_pids=None, process_tree=tree)
        assert result == CLASS_TARGET_WORKLOAD

    def test_ollama_by_pid(self):
        """PID esplicito nel set target → TARGET_WORKLOAD."""
        tree = self._make_tree([
            (1234, "ollama", 100, 1000.0),
        ])
        result = classify_process(1234, target_pids={1234}, process_tree=tree)
        assert result == CLASS_TARGET_WORKLOAD

    def test_child_of_ollama(self):
        """Figlio di Ollama classificato come TARGET_WORKLOAD."""
        tree = self._make_tree([
            (1234, "ollama", 100, 1000.0),
            (5678, "python", 1234, 1001.0),  # figlio di ollama
        ])
        result = classify_process(
            5678, target_pids={1234}, process_tree=tree)
        assert result == CLASS_TARGET_WORKLOAD

    def test_grandchild_of_ollama(self):
        """Nipote di Ollama classificato come TARGET_WORKLOAD."""
        tree = self._make_tree([
            (1234, "ollama", 100, 1000.0),
            (5678, "python", 1234, 1001.0),
            (9999, "subprocess", 5678, 1002.0),  # nipote
        ])
        result = classify_process(
            9999, target_pids={1234}, process_tree=tree)
        assert result == CLASS_TARGET_WORKLOAD

    def test_chrome_is_background(self):
        """Chrome classificato come BACKGROUND."""
        tree = self._make_tree([
            (2222, "chrome.exe", 100, 1000.0),
        ])
        result = classify_process(2222, target_pids={1234}, process_tree=tree)
        assert result == CLASS_BACKGROUND

    def test_vscode_is_background(self):
        """Visual Studio Code classificato come BACKGROUND."""
        tree = self._make_tree([
            (3333, "Code.exe", 100, 1000.0),
        ])
        result = classify_process(3333, target_pids={1234}, process_tree=tree)
        assert result == CLASS_BACKGROUND

    def test_svchost_is_system(self):
        """svchost.exe classificato come SYSTEM_UNATTRIBUTED."""
        tree = self._make_tree([
            (444, "svchost.exe", 4, 500.0),
        ])
        result = classify_process(444, target_pids={1234}, process_tree=tree)
        assert result == CLASS_SYSTEM_UNATTRIBUTED

    def test_low_pid_is_system(self):
        """PID < 100 classificato come SYSTEM_UNATTRIBUTED."""
        tree = self._make_tree([
            (50, "system_helper", 4, 500.0),
        ])
        result = classify_process(50, target_pids={1234}, process_tree=tree)
        assert result == CLASS_SYSTEM_UNATTRIBUTED

    def test_unknown_process_is_background(self):
        """Processo sconosciuto classificato come BACKGROUND."""
        tree = self._make_tree([
            (7777, "unknown_app.exe", 100, 1000.0),
        ])
        result = classify_process(7777, target_pids={1234}, process_tree=tree)
        assert result == CLASS_BACKGROUND

    def test_no_tree_falls_back(self):
        """Senza albero, il processo viene classificato per nome."""
        result = classify_process(1234, target_pids=None)
        # Senza albero, il processo non è trovato → BACKGROUND
        assert result == CLASS_BACKGROUND

    def test_ollama_case_insensitive(self):
        """Classificazione case-insensitive: OLLAMA → TARGET_WORKLOAD."""
        tree = self._make_tree([
            (1234, "OLLAMA", 100, 1000.0),
        ])
        result = classify_process(1234, target_pids=None, process_tree=tree)
        assert result == CLASS_TARGET_WORKLOAD

    def test_ollama_with_suffix(self):
        """Ollama con suffisso: ollama_app → TARGET_WORKLOAD."""
        tree = self._make_tree([
            (1234, "ollama_app", 100, 1000.0),
        ])
        result = classify_process(1234, target_pids=None, process_tree=tree)
        assert result == CLASS_TARGET_WORKLOAD

    def test_not_ollama_similar_name(self):
        """Nome simile ma non Ollama: not_ollama → BACKGROUND."""
        tree = self._make_tree([
            (1234, "not_ollama", 100, 1000.0),
        ])
        result = classify_process(1234, target_pids=None, process_tree=tree)
        assert result == CLASS_BACKGROUND

    def test_system_names_list(self):
        """Processi di sistema riconosciuti."""
        system_names = ["smss.exe", "csrss.exe", "services.exe",
                        "lsass.exe", "wininit.exe"]
        tree = {}
        for i, name in enumerate(system_names):
            tree[i + 10] = {
                "pid": i + 10,
                "name": name,
                "ppid": 4,
                "create_time": 500.0,
            }
        for pid in tree:
            result = classify_process(pid, target_pids={9999}, process_tree=tree)
            assert result == CLASS_SYSTEM_UNATTRIBUTED, (
                f"{tree[pid]['name']} non classificato come SYSTEM_UNATTRIBUTED")

    def test_target_names_override(self):
        """target_names personalizzato sovrascrive il default."""
        tree = self._make_tree([
            (1234, "custom_app", 100, 1000.0),
        ])
        result = classify_process(
            1234,
            target_pids=None,
            target_names=("custom_app",),
            process_tree=tree,
        )
        assert result == CLASS_TARGET_WORKLOAD


class TestFindDescendants:
    """Test per _find_descendants()."""

    def test_no_descendants(self):
        """Processo senza figli."""
        tree = {
            100: {"pid": 100, "name": "a", "ppid": 0, "create_time": 0},
        }
        result = _find_descendants(100, tree)
        assert result == set()

    def test_single_child(self):
        """Processo con un figlio."""
        tree = {
            100: {"pid": 100, "name": "a", "ppid": 0, "create_time": 0},
            200: {"pid": 200, "name": "b", "ppid": 100, "create_time": 1},
        }
        result = _find_descendants(100, tree)
        assert result == {200}

    def test_deep_tree(self):
        """Albero profondo: 3 livelli."""
        tree = {
            100: {"pid": 100, "name": "a", "ppid": 0, "create_time": 0},
            200: {"pid": 200, "name": "b", "ppid": 100, "create_time": 1},
            300: {"pid": 300, "name": "c", "ppid": 200, "create_time": 2},
        }
        result = _find_descendants(100, tree)
        assert result == {200, 300}

    def test_multiple_children(self):
        """Processo con più figli."""
        tree = {
            100: {"pid": 100, "name": "a", "ppid": 0, "create_time": 0},
            200: {"pid": 200, "name": "b", "ppid": 100, "create_time": 1},
            300: {"pid": 300, "name": "c", "ppid": 100, "create_time": 2},
        }
        result = _find_descendants(100, tree)
        assert result == {200, 300}

    def test_empty_tree(self):
        """Albero vuoto."""
        result = _find_descendants(100, {})
        assert result == set()
