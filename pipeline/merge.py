import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paths import LOG_DIR, COMBINED_RESULTS, COMBINED_ERRORS

TOTAL_WORKERS = 5

def merge_files(pattern: str, output_path: str) -> None:
    print(f"Merging files matching pattern into {output_path}...")
    with open(output_path, "w", encoding="utf-8") as outfile:
        for i in range(1, TOTAL_WORKERS + 1):
            file_part = pattern.format(i)
            if os.path.exists(file_part):
                print(f" -> Consuming {file_part}")
                with open(file_part, "r", encoding="utf-8") as infile:
                    for line in infile:
                        if line.strip():
                            outfile.write(line)
            else:
                print(f" -> Skip: {file_part} (File not found)")

if __name__ == "__main__":
    results_pattern = str(LOG_DIR / "onpe_combined_results_worker_{}.jsonl")
    errors_pattern  = str(LOG_DIR / "onpe_combined_errors_worker_{}.jsonl")
    merge_files(results_pattern, str(COMBINED_RESULTS))
    merge_files(errors_pattern,  str(COMBINED_ERRORS))
    print("Done! Data sets fully re-unified.")
