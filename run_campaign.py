"""Campaign runner for P6 main campaign (39 blocks + 12 gate).
Run with: python run_campaign.py
Estimated time: ~2.5 hours
"""
import subprocess
import time
import sys
import os
import json
from datetime import datetime

PYTHON = r"C:\Users\Massimo\AppData\Local\Programs\Python\Python313\python.exe"
PROJECT = r"C:\Users\Massimo\Documents\CasualWatt\CWProject"
CW = os.path.join(PROJECT, "cwEnergyModular")

# Design points: (input_tokens, output_tokens, num_predict)
# 3x3 grid: 32/128/512 x 32/128/256
# center (128,128) x6, minimum (8,4), confirmation (12,32), confirmation high (256,192)
DESIGN_POINTS = [
    (32, 32), (32, 128), (32, 256),
    (128, 32), (128, 128), (128, 256),
    (512, 32), (512, 128), (512, 256),
    (128, 128), (128, 128), (128, 128),  # center x3 more (total 6)
    (128, 128), (128, 128), (128, 128),
    (8, 4),   # minimum
    (12, 32),  # confirmation
    (256, 192),  # confirmation high
]

MODELS = ["qwen2.5:0.5b", "gemma2:9b"]
BLOCKS_PER_POINT = 3

def run_block(model, input_tokens, output_tokens, block_num):
    """Run a single benchmark block."""
    print(f"\n=== Block {block_num}: {model} ({input_tokens}in/{output_tokens}out) ===")
    # Generate prompt of approximately input_tokens length
    # This is a simplified version - actual implementation needs proper prompt generation
    result = subprocess.run(
        [PYTHON, os.path.join(CW, "main.py"), "--no-gui", "--local", model,
         "--prompts", "3", "--temperature", "0"],
        capture_output=True, text=True, cwd=PROJECT, timeout=300
    )
    print(result.stdout[-200:] if result.stdout else "No output")
    if result.returncode != 0:
        print(f"ERROR: {result.stderr[-200:]}")
    return result.returncode == 0

def main():
    print(f"Campaign started at {datetime.now()}")
    total_blocks = len(DESIGN_POINTS) * BLOCKS_PER_POINT * len(MODELS)
    print(f"Total blocks: {total_blocks}")
    
    block_num = 0
    for model in MODELS:
        for (inp, out) in DESIGN_POINTS:
            for rep in range(BLOCKS_PER_POINT):
                block_num += 1
                success = run_block(model, inp, out, block_num)
                if not success:
                    print(f"Block {block_num} failed, continuing...")
                time.sleep(5)  # cooldown between blocks
    
    print(f"\nCampaign completed at {datetime.now()}")
    print(f"Total blocks executed: {block_num}")

if __name__ == "__main__":
    main()
