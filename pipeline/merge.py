import os

TOTAL_WORKERS = 5
FINAL_RESULTS_FILE = "onpe_combined_results.jsonl"
FINAL_ERROR_FILE = "onpe_combined_errors.jsonl"

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
    merge_files("log/onpe_combined_results_worker_{}.jsonl", FINAL_RESULTS_FILE)
    merge_files("log/onpe_combined_errors_worker_{}.jsonl", FINAL_ERROR_FILE)
    print("Done! Data sets fully re-unified.")