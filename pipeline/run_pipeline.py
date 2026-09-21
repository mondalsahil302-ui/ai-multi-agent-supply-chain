"""
Master runner — executes all 6 pipeline stages sequentially.
"""
import subprocess, sys, os

stages = [
    "pipeline\\stage_01_setup_and_raw.py",
    "pipeline\\stage_02_profiling.py",
    "pipeline\\stage_03_standardize.py",
    "pipeline\\stage_03b_integrate_updates.py",
    "pipeline\\stage_04_features.py",
    "pipeline\\stage_05_validation.py",
    "pipeline\\stage_06_mapping_docs.py",
    "pipeline\\stage_07_data_dictionary.py",
]

env = os.environ.copy()
env["PYTHONIOENCODING"] = "utf-8"

for stage in stages:
    print(f"\n{'='*60}")
    print(f"RUNNING: {stage}")
    print('='*60)
    result = subprocess.run(
        [sys.executable, stage],
        cwd=r"D:\ai-multi-agent-supply-chain",
        env=env,
        capture_output=False,
    )
    if result.returncode != 0:
        print(f"ERROR in {stage} — exit code {result.returncode}")
        sys.exit(result.returncode)
    print(f"DONE: {stage}")

print("\n" + "="*60)
print("ALL PIPELINE STAGES COMPLETE")
print("="*60)

