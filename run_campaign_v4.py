"""Campaign runner for P6 main campaign (39 blocks + 12 gate).
Uses benchmark_v4.run_v4_benchmark with generated prompts.
Estimated time: ~2.5 hours
"""
import sys
import os
import time
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "cwEnergyModular"))

PROJECT = os.path.dirname(os.path.abspath(__file__))
CW = os.path.join(PROJECT, "cwEnergyModular")

from test_source import make_prompt_items
from benchmark_v4 import run_v4_benchmark

BASE_TEXT = "The quick brown fox jumps over the lazy dog. Energy efficiency in computing is important for sustainable AI. "

def make_prompt_of_length(target_words):
    words = BASE_TEXT.split()
    result = []
    while len(result) < target_words:
        result.extend(words)
    return " ".join(result[:target_words])

DESIGN_POINTS = [
    (32, 32), (32, 128), (32, 256),
    (128, 32), (128, 128), (128, 256),
    (512, 32), (512, 128), (512, 256),
    (128, 128), (128, 128), (128, 128),
    (128, 128), (128, 128), (128, 128),
    (8, 4),
    (12, 32),
    (256, 192),
]

MODELS = ["qwen2.5:0.5b", "gemma2:2b"]

def main():
    print(f"Campaign started at {datetime.now()}")
    total_blocks = len(DESIGN_POINTS) * 3 * len(MODELS)
    print(f"Total blocks: {total_blocks}")

    block_num = 0
    for model in MODELS:
        for (inp_words, out_tokens) in DESIGN_POINTS:
            prompt_text = make_prompt_of_length(inp_words)
            items = make_prompt_items([(prompt_text, None, "free_text")], "campaign", "c")

            for rep in range(3):
                block_num += 1
                print(f"\n=== Block {block_num}/{total_blocks}: {model} ({inp_words}w/{out_tokens}tok) rep {rep+1} ===")
                try:
                    summary = run_v4_benchmark(
                        local_models=[model],
                        prompts=items,
                        m=1,
                        blocks_per_point=1,
                        num_predict=out_tokens,
                        temperature=0.0,
                        timeout_s=120.0,
                        max_invalidated_blocks=2,
                        substitution_seed="campaign-20261106",
                        on_log=lambda m: print(m, flush=True),
                    )
                    print(f"  records={summary.get('records', 0)} errors={summary.get('errors', 0)}")
                except Exception as e:
                    print(f"  ERROR: {e}")
                time.sleep(3)

    print(f"\nCampaign completed at {datetime.now()}")
    print(f"Total blocks executed: {block_num}")

if __name__ == "__main__":
    main()
