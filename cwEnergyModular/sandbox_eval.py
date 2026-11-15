"""Sandbox evaluation for generated code using epicbox.

This module integrates epicbox Docker sandbox with CasualWatt evaluation framework
for pass@k assessment of coding tasks. It provides:

- Code execution in isolated containers with resource limits
- Test suite evaluation for pass/fail determination
- pass@k unbiased estimation (Chen et al.)
- Integration with evaluation_schema.py for structured output
- Energy attribution via existing CasualWatt measurement pipeline
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import epicbox

from evaluation_schema import (
    EVALUATION_RESULT_COLUMNS,
    EVALUATION_SUMMARY_COLUMNS,
    compute_pass_at_k_unbiased,
    export_evaluation_results,
    export_evaluation_summary,
    export_task_definitions,
    load_task_definitions,
    TASK_DEFINITION_COLUMNS,
)
from evaluation_runner import (
    record_verdict,
    _task_id,
    notes_with_task_id,
    final_verdict,
    summarize_records,
)


# Default sandbox profiles for different languages
DEFAULT_PROFILES = {
    "python": epicbox.Profile("python", "python:3.11-slim"),
    "node": epicbox.Profile("node", "node:20-slim"),
    "javascript": epicbox.Profile("node", "node:20-slim"),
    "typescript": epicbox.Profile("node", "node:20-slim"),
    "cpp": epicbox.Profile("cpp", "gcc:latest"),
    "rust": epicbox.Profile("rust", "rust:latest"),
    "go": epicbox.Profile("go", "golang:latest"),
    "java": epicbox.Profile("java", "openjdk:21-slim"),
}

# Default resource limits
DEFAULT_LIMITS = {
    "cputime": 10,      # CPU seconds
    "realtime": 30,     # Wall-clock seconds
    "memory": 256,      # MB
    "processes": 64,    # Max processes
}


@dataclass
class TestCase:
    """A single test case for coding evaluation."""
    input_data: Any
    expected_output: Any
    description: str = ""
    hidden: bool = False  # Hidden tests not shown to model


@dataclass
class CodingTask:
    """A coding task definition with test cases."""
    task_id: str
    prompt: str
    tests: List[TestCase]
    ground_truth: str = ""  # Reference solution (optional)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_type": "coding",
            "description": self.metadata.get("description", ""),
            "prompt": self.prompt,
            "ground_truth": self.ground_truth,
            "tests": [
                {
                    "input": tc.input_data,
                    "expected": tc.expected_output,
                    "description": tc.description,
                    "hidden": tc.hidden,
                }
                for tc in self.tests
            ],
            "metadata": self.metadata,
        }


@dataclass
class ExecutionResult:
    """Result of executing generated code against test cases."""
    task_id: str
    candidate_id: str  # Which candidate solution (for pass@k)
    attempt: int       # Attempt number (0-indexed)
    passed: bool
    tests_total: int
    tests_passed: int
    compile_error: Optional[str] = None
    runtime_error: Optional[str] = None
    stdout: str = ""
    stderr: str = ""
    duration_s: float = 0.0
    exit_code: int = 0
    energy_j: Optional[float] = None  # Filled by energy measurement pipeline


@dataclass
class SandboxConfig:
    """Configuration for sandbox execution."""
    language: str = "python"
    profile: Optional[epicbox.Profile] = None
    limits: Dict[str, Any] = field(default_factory=lambda: DEFAULT_LIMITS.copy())
    timeout_s: float = 30.0
    max_attempts: int = 1  # For pass@k, how many candidates to evaluate


class CodeSandbox:
    """Epicbox-based sandbox for executing generated code."""
    
    def __init__(self, config: SandboxConfig):
        self.config = config
        self._profiles = DEFAULT_PROFILES.copy()
        if config.profile:
            self._profiles[config.language] = config.profile
        self._configured = False
    
    def _ensure_configured(self):
        if not self._configured:
            profiles_list = list(self._profiles.values())
            epicbox.configure(profiles=profiles_list)
            self._configured = True
    
    def _get_profile_name(self) -> str:
        """Map language to profile name."""
        mapping = {
            "python": "python",
            "javascript": "node",
            "typescript": "node",
            "node": "node",
            "cpp": "cpp",
            "rust": "rust",
            "go": "go",
            "java": "java",
        }
        return mapping.get(self.config.language, self.config.language)
    
    def run_code(
        self,
        code: str,
        test_cases: List[TestCase],
        stdin: str = "",
    ) -> ExecutionResult:
        """Execute code with test cases and return result."""
        self._ensure_configured()
        
        # Build test harness
        test_code = self._build_test_harness(code, test_cases)
        
        # Prepare command based on language
        cmd = self._get_command(test_code)
        
        start_time = time.time()
        try:
            result = epicbox.run(
                self._get_profile_name(),
                cmd,
                stdin=stdin.encode() if stdin else None,
                limits=self.config.limits,
            )
            duration = time.time() - start_time
            
            return self._parse_result(result, duration, test_cases)
        except epicbox.exceptions.DockerError as e:
            return ExecutionResult(
                task_id="",
                candidate_id="",
                attempt=0,
                passed=False,
                tests_total=len(test_cases),
                tests_passed=0,
                compile_error=None,
                runtime_error=str(e),
                duration_s=time.time() - start_time,
            )
    
    def _build_test_harness(self, code: str, test_cases: List[TestCase]) -> str:
        """Build test harness for the given language."""
        if self.config.language == "python":
            return self._build_python_harness(code, test_cases)
        elif self.config.language in ("node", "javascript", "typescript"):
            return self._build_js_harness(code, test_cases)
        elif self.config.language == "cpp":
            return self._build_cpp_harness(code, test_cases)
        else:
            raise ValueError(f"Unsupported language: {self.config.language}")
    
    def _build_python_harness(self, code: str, test_cases: List[TestCase]) -> str:
        """Build Python test harness."""
        test_code = code + "\n\n"
        test_code += "import sys\nimport json\n\n"
        test_code += "def run_tests():\n"
        test_code += "    results = []\n"
        
        for i, tc in enumerate(test_cases):
            # Convert input to Python literal
            input_repr = json.dumps(tc.input_data)
            expected_repr = json.dumps(tc.expected_output)
            test_code += f"    # Test {i}: {tc.description}\n"
            test_code += f"    try:\n"
            test_code += f"        input_data = {input_repr}\n"
            test_code += f"        expected = {expected_repr}\n"
            
            # Handle different input types
            if isinstance(tc.input_data, dict):
                test_code += f"        result = solution(**input_data)\n"
            elif isinstance(tc.input_data, list):
                test_code += f"        result = solution(*input_data)\n"
            else:
                test_code += f"        result = solution(input_data)\n"
            
            test_code += f"        passed = (result == expected)\n"
            test_code += f"        results.append({{'test': {i}, 'passed': passed, 'got': result, 'expected': expected}})\n"
            test_code += f"    except Exception as e:\n"
            test_code += f"        results.append({{'test': {i}, 'passed': False, 'error': str(e)}})\n"
        
        test_code += "    return results\n\n"
        test_code += "if __name__ == '__main__':\n"
        test_code += "    results = run_tests()\n"
        test_code += "    passed = sum(1 for r in results if r.get('passed'))\n"
        test_code += "    total = len(results)\n"
        test_code += "    print(f'PASSED:{passed}/{total}')\n"
        test_code += "    for r in results:\n"
        test_code += "        if r.get('passed'):\n"
        test_code += "            print(f'  PASS test {r[\"test\"]}')\n"
        test_code += "        else:\n"
        test_code += "            err = r.get('error', f'got {r.get(\"got\")}, expected {r.get(\"expected\")}')\n"
        test_code += "            print(f'  FAIL test {r[\"test\"]}: {err}')\n"
        test_code += "    sys.exit(0 if passed == total else 1)\n"
        
        return test_code
    
    def _build_js_harness(self, code: str, test_cases: List[TestCase]) -> str:
        """Build JavaScript/TypeScript test harness."""
        test_code = code + "\n\n"
        test_code += "const testCases = " + json.dumps([
            {"input": tc.input_data, "expected": tc.expected_output, "description": tc.description}
            for tc in test_cases
        ]) + ";\n\n"
        
        test_code += "function runTests() {\n"
        test_code += "    const results = [];\n"
        test_code += "    for (let i = 0; i < testCases.length; i++) {\n"
        test_code += "        const tc = testCases[i];\n"
        test_code += "        try {\n"
        test_code += "            let result;\n"
        test_code += "            if (typeof tc.input === 'object' && tc.input !== null) {\n"
        test_code += "                if (Array.isArray(tc.input)) {\n"
        test_code += "                    result = solution(...tc.input);\n"
        test_code += "                } else {\n"
        test_code += "                    result = solution(tc.input);\n"
        test_code += "                }\n"
        test_code += "            } else {\n"
        test_code += "                result = solution(tc.input);\n"
        test_code += "            }\n"
        test_code += "            const passed = JSON.stringify(result) === JSON.stringify(tc.expected);\n"
        test_code += "            results.push({test: i, passed, got: result, expected: tc.expected});\n"
        test_code += "        } catch (e) {\n"
        test_code += "            results.push({test: i, passed: false, error: e.message});\n"
        test_code += "        }\n"
        test_code += "    }\n"
        test_code += "    return results;\n"
        test_code += "}\n\n"
        test_code += "const results = runTests();\n"
        test_code += "const passed = results.filter(r => r.passed).length;\n"
        test_code += "const total = results.length;\n"
        test_code += "console.log(`PASSED:${passed}/${total}`);\n"
        test_code += "results.forEach(r => {\n"
        test_code += "    if (r.passed) console.log(`  PASS test ${r.test}`);\n"
        test_code += "    else console.log(`  FAIL test ${r.test}: ${r.error || `got ${JSON.stringify(r.got)}, expected ${JSON.stringify(r.expected)}`}`);\n"
        test_code += "});\n"
        test_code += "process.exit(passed === total ? 0 : 1);\n"
        
        return test_code
    
    def _build_cpp_harness(self, code: str, test_cases: List[TestCase]) -> str:
        """Build C++ test harness - simplified for demonstration."""
        # For C++, we'd need a more complex setup with compilation
        # This is a placeholder
        return code
    
    def _get_command(self, test_code: str) -> List[str]:
        """Get execution command for the language."""
        if self.config.language == "python":
            return ["python", "-c", test_code]
        elif self.config.language in ("javascript", "typescript"):
            return ["node", "-e", test_code]
        elif self.config.language == "cpp":
            return ["sh", "-c", f'echo "{test_code}" > test.cpp && g++ test.cpp -o test && ./test']
        else:
            return ["sh", "-c", test_code]
    
    def _parse_result(self, result: Dict, duration: float, test_cases: List[TestCase]) -> ExecutionResult:
        """Parse epicbox result into ExecutionResult."""
        stdout = result.get("stdout", b"").decode("utf-8", errors="replace")
        stderr = result.get("stderr", b"").decode("utf-8", errors="replace")
        exit_code = result.get("exit_code", -1)
        
        # Parse test results from stdout
        tests_passed = 0
        tests_total = len(test_cases)
        compile_error = None
        runtime_error = None
        
        for line in stdout.splitlines():
            if line.startswith("PASSED:"):
                try:
                    parts = line.split(":")[1].split("/")
                    tests_passed = int(parts[0])
                    tests_total = int(parts[1])
                except (IndexError, ValueError):
                    pass
            elif "error" in line.lower() and "compile" in stderr.lower():
                compile_error = stderr
            elif exit_code != 0 and not compile_error:
                runtime_error = stderr
        
        passed = (tests_passed == tests_total and tests_total > 0)
        
        return ExecutionResult(
            task_id="",  # Filled by caller
            candidate_id="",  # Filled by caller
            attempt=0,  # Filled by caller
            passed=passed,
            tests_total=tests_total,
            tests_passed=tests_passed,
            compile_error=compile_error,
            runtime_error=runtime_error,
            stdout=stdout,
            stderr=stderr,
            duration_s=duration,
            exit_code=exit_code,
        )


class PassAtKEvaluator:
    """Evaluates pass@k for coding tasks using sandbox execution."""
    
    def __init__(
        self,
        sandbox: CodeSandbox,
        k_values: List[int] = None,
        max_attempts: int = 10,
    ):
        self.sandbox = sandbox
        self.k_values = k_values or [1, 3, 5, 10]
        self.max_attempts = max_attempts
    
    def evaluate_task(
        self,
        task: CodingTask,
        candidates: List[str],  # List of generated code candidates
        run_id: str,
        session_id: str = "",
        model_name: str = "",
        model_label: str = "",
        provider: str = "ollama",
        seed: int = 42,
    ) -> Tuple[List[Dict], Dict]:
        """
        Evaluate multiple candidates for a task (pass@k).
        
        Returns:
            - List of evaluation result records (for EVALUATION_RESULT_COLUMNS)
            - Summary dict (for EVALUATION_SUMMARY_COLUMNS)
        """
        task_id = task.task_id
        all_results = []
        
        for attempt_idx, candidate_code in enumerate(candidates[:self.max_attempts]):
            candidate_id = f"{task_id}_attempt_{attempt_idx}"
            
            exec_result = self.sandbox.run_code(candidate_code, task.tests)
            exec_result.task_id = task_id
            exec_result.candidate_id = candidate_id
            exec_result.attempt = attempt_idx
            
            # Build evaluation record
            eval_record = self._build_eval_record(
                task=task,
                exec_result=exec_result,
                run_id=run_id,
                session_id=session_id,
                model_name=model_name,
                model_label=model_label,
                provider=provider,
                seed=seed,
            )
            all_results.append(eval_record)
        
        # Compute pass@k metrics
        passed_attempts = [r for r in all_results if r["passed"]]
        n_samples = len(all_results)
        
        # pass@1: first attempt correct
        pass_at_1 = 1 if all_results and all_results[0]["passed"] else 0
        
        # pass@k for each k
        pass_at_k_results = {}
        for k in self.k_values:
            if k <= n_samples:
                n_correct = len(passed_attempts)
                pass_at_k_results[f"pass_at_{k}"] = compute_pass_at_k_unbiased(n_samples, n_correct, k)
            else:
                pass_at_k_results[f"pass_at_{k}"] = None
        
        # Build summary
        summary = {
            "run_id": run_id,
            "model_name": model_name,
            "model_label": model_label,
            "task_type": "coding",
            "n_tasks": 1,
            "n_tasks_evaluated": 1,
            "pass_at_1_mean": pass_at_1,
            "pass_at_k_mean": pass_at_k_results.get(f"pass_at_{self.k_values[0]}") if self.k_values else None,
            "pass_at_k_unbiased_mean": pass_at_k_results.get(f"pass_at_{self.k_values[-1]}") if self.k_values else None,
            "compile_rate_mean": sum(1 for r in all_results if not r.get("compile_error")) / n_samples if n_samples else 0,
            "runtime_success_rate_mean": sum(1 for r in all_results if not r.get("runtime_error")) / n_samples if n_samples else 0,
            "accuracy_mean": len(passed_attempts) / n_samples if n_samples else 0,
            "n_effective_tasks": 1,
            "notes": f"pass@k evaluation: candidates={n_samples}, k_values={self.k_values}",
        }
        
        # Add pass@k values to summary
        for k, v in pass_at_k_results.items():
            summary[k] = v
        
        return all_results, summary
    
    def _build_eval_record(
        self,
        task: CodingTask,
        exec_result: ExecutionResult,
        run_id: str,
        session_id: str,
        model_name: str,
        model_label: str,
        provider: str,
        seed: int,
    ) -> Dict:
        """Build evaluation record matching EVALUATION_RESULT_COLUMNS."""
        from datetime import datetime
        
        passed = exec_result.passed
        verdict = "correct" if passed else "incorrect"
        
        return {
            "run_id": run_id,
            "session_id": session_id,
            "batch_id": "",
            "point_id": "",
            "task_id": exec_result.task_id,
            "task_type": "coding",
            "prompt_id": task.metadata.get("prompt_id", ""),
            "model_name": model_name,
            "model_label": model_label,
            "provider": provider,
            "prompt": task.prompt,
            "ground_truth": task.ground_truth,
            "model_response": exec_result.stdout,
            "extracted_answer": exec_result.stdout,
            "tests_total": exec_result.tests_total,
            "tests_passed": exec_result.tests_passed,
            "passed": passed,  # Add this for pass@k computation
            "pass_rate": exec_result.tests_passed / exec_result.tests_total if exec_result.tests_total else 0,
            "pass_at_1": 1 if (exec_result.attempt == 0 and passed) else 0,
            "pass_at_k": 1 if passed else 0,
            "k_value": max(self.k_values) if self.k_values else 1,
            "pass_at_k_unbiased": 1.0 if passed else 0.0,
            "compile_rate": 0.0 if exec_result.compile_error else 1.0,
            "runtime_success_rate": 0.0 if exec_result.runtime_error else 1.0,
            "factual_claims": 0,
            "factual_correct": 0,
            "factual_incorrect": 0,
            "factual_unverifiable": 0,
            "factual_accuracy": 0.0,
            "factual_precision": 0.0,
            "factual_recall": 0.0,
            "factual_f1": 0.0,
            "human_score": "",
            "human_score_raw": "",
            "llm_judge_score": "",
            "llm_judge_model": "",
            "rubric_scores": "",
            "rubric_schema": "",
            "wilson_ci_lower": "",
            "wilson_ci_upper": "",
            "bootstrap_ci_lower": "",
            "bootstrap_ci_upper": "",
            "n_effective_tasks": 1,
            "mcnemar_p_exact": "",
            "mcnemar_ci_lower": "",
            "mcnemar_ci_upper": "",
            "mcnemar_verdict": "",
            "energy_scope": "attributed",
            "energy_per_task_j": exec_result.energy_j if exec_result.energy_j is not None else "",
            "energy_per_token_j": "",
            "latency_ms": round(exec_result.duration_s * 1000),
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "run_mode": "pass_at_k",
            "seed": seed,
            "notes": f"sandbox: epicbox; language: {self.sandbox.config.language}; attempt: {exec_result.attempt}",
            "eval_method": "auto_test",
            "eval_version": "sandbox_v1",
            "ground_truth_source": "dataset",
        }


def create_coding_task_from_dict(data: Dict[str, Any]) -> CodingTask:
    """Create CodingTask from dictionary (e.g., loaded from tasks.json)."""
    tests = []
    for tc in data.get("tests", []):
        tests.append(TestCase(
            input_data=tc.get("input"),
            expected_output=tc.get("expected"),
            description=tc.get("description", ""),
            hidden=tc.get("hidden", False),
        ))
    return CodingTask(
        task_id=data["task_id"],
        prompt=data["prompt"],
        tests=tests,
        ground_truth=data.get("ground_truth", ""),
        metadata=data.get("metadata", {}),
    )


def load_coding_tasks(path: Path) -> List[CodingTask]:
    """Load coding tasks from tasks.json."""
    tasks_data = load_task_definitions(path)
    return [create_coding_task_from_dict(t) for t in tasks_data if t.get("task_type") == "coding"]


def evaluate_coding_tasks(
    tasks: List[CodingTask],
    candidates_by_task: Dict[str, List[str]],
    run_id: str,
    output_dir: Path,
    sandbox_config: Optional[SandboxConfig] = None,
    k_values: List[int] = None,
    model_name: str = "",
    model_label: str = "",
    provider: str = "ollama",
    seed: int = 42,
) -> Tuple[List[Dict], List[Dict]]:
    """
    Evaluate multiple coding tasks with pass@k.
    
    Args:
        tasks: List of CodingTask objects
        candidates_by_task: Dict mapping task_id -> list of candidate code strings
        run_id: Unique run identifier
        output_dir: Directory to write evaluation CSVs
        sandbox_config: Sandbox configuration
        k_values: k values for pass@k
        model_name: Model name
        model_label: Model label
        provider: Provider name
        seed: Random seed
    
    Returns:
        - All evaluation result records
        - All summary records
    """
    sandbox_config = sandbox_config or SandboxConfig()
    sandbox = CodeSandbox(sandbox_config)
    evaluator = PassAtKEvaluator(sandbox, k_values=k_values)
    
    all_results = []
    all_summaries = []
    
    for task in tasks:
        candidates = candidates_by_task.get(task.task_id, [])
        if not candidates:
            continue
        
        results, summary = evaluator.evaluate_task(
            task=task,
            candidates=candidates,
            run_id=run_id,
            model_name=model_name,
            model_label=model_label,
            provider=provider,
            seed=seed,
        )
        all_results.extend(results)
        all_summaries.append(summary)
    
    # Write CSVs
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    results_path = output_dir / f"{run_id}_evaluation.csv"
    summary_path = output_dir / f"{run_id}_summary.csv"
    
    export_evaluation_results(all_results, results_path)
    export_evaluation_summary(all_summaries, summary_path)
    
    return all_results, all_summaries


# Convenience function for quick testing
def quick_test_sandbox(language: str = "python") -> bool:
    """Quick test that sandbox is working."""
    config = SandboxConfig(language=language)
    sandbox = CodeSandbox(config)
    
    if language == "python":
        code = "def solution(x): return x * 2"
        tests = [
            TestCase(input_data=5, expected_output=10),
            TestCase(input_data=0, expected_output=0),
            TestCase(input_data=-3, expected_output=-6),
        ]
    elif language in ("node", "javascript", "typescript"):
        code = "function solution(x) { return x * 2; }"
        tests = [
            TestCase(input_data=5, expected_output=10),
            TestCase(input_data=0, expected_output=0),
            TestCase(input_data=-3, expected_output=-6),
        ]
    else:
        raise ValueError(f"Unsupported language for quick test: {language}")
    
    result = sandbox.run_code(code, tests)
    return result.passed


if __name__ == "__main__":
    # Quick test
    print("Testing Python sandbox...")
    ok = quick_test_sandbox("python")
    print(f"Python: {'OK' if ok else 'FAILED'}")
    
    print("Testing JavaScript sandbox...")
    ok = quick_test_sandbox("javascript")
    print(f"JavaScript: {'OK' if ok else 'FAILED'}")
    
    # Test pass@k evaluation
    print("\nTesting pass@k evaluation...")
    task = CodingTask(
        task_id="test_factorial",
        prompt="Write a function factorial(n) that returns n!",
        tests=[
            TestCase(input_data=0, expected_output=1),
            TestCase(input_data=1, expected_output=1),
            TestCase(input_data=5, expected_output=120),
            TestCase(input_data=10, expected_output=3628800),
        ],
    )
    
    candidates = [
        # Correct recursive
        "def solution(n):\n    if n <= 1: return 1\n    return n * solution(n-1)",
        # Correct iterative
        "def solution(n):\n    result = 1\n    for i in range(2, n+1):\n        result *= i\n    return result",
        # Buggy (off by one)
        "def solution(n):\n    result = 1\n    for i in range(1, n):\n        result *= i\n    return result",
    ]
    
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        results, summaries = evaluate_coding_tasks(
            tasks=[task],
            candidates_by_task={task.task_id: candidates},
            run_id="test_run_001",
            output_dir=tmpdir,
            model_name="test-model",
            k_values=[1, 3],
        )
        
        print(f"Results: {len(results)}")
        print(f"Summaries: {len(summaries)}")
        for r in results:
            print(f"  Attempt {r['attempt']}: passed={r['passed']}, tests={r['tests_passed']}/{r['tests_total']}")
        print(f"pass@1: {summaries[0].get('pass_at_1')}")
        print(f"pass@3: {summaries[0].get('pass_at_3')}")