import os
import sys
import time
import argparse
import subprocess
import shutil
from typing import List

SCRAPER_SCRIPT = "scraper.py"
TOTAL_WORKERS = 5
LOG_DIR = "log"
STOP_SIGNAL_FILE = os.path.join(LOG_DIR, ".stop_signal")

def check_environment() -> None:
    if not os.path.exists(SCRAPER_SCRIPT):
        print(f"Core Environment Error: Target runtime file '{SCRAPER_SCRIPT}' was not found.")
        sys.exit(1)
    os.makedirs(LOG_DIR, exist_ok=True)
    if os.path.exists(STOP_SIGNAL_FILE):
        os.remove(STOP_SIGNAL_FILE)

def get_last_log_line(worker_id: int) -> str:
    """Reads the last line of a worker's system log and strips timestamps."""
    sys_log_path = os.path.join(LOG_DIR, f"worker_{worker_id}_sys.log")
    if not os.path.exists(sys_log_path):
        return "Initializing..."
    try:
        with open(sys_log_path, "rb") as f:
            try:
                f.seek(-2, os.SEEK_END)
                while f.read(1) != b"\n":
                    f.seek(-2, os.SEEK_CUR)
            except OSError:
                f.seek(0)
            last_line = f.readline().decode("utf-8", errors="ignore").strip()
            
            if "]" in last_line:
                last_line = last_line.split("]")[-1].strip()
            return last_line if last_line else "Processing..."
    except Exception:
        return "Reading log..."

def render_dashboard(processes: List[subprocess.Popen], mode: str) -> None:
    """Renders a clean, non-wrapping dashboard using terminal control sequences."""
    # Get dynamic terminal width to handle aggressive window resizing
    terminal_columns, _ = shutil.get_terminal_size((80, 24))
    
    # 1. Reset cursor to top-left of the visual area
    sys.stdout.write("\033[H")
    
    # 2. Print Header (\033[K clears anything remaining on that specific row)
    print(f"=== ONPE CLUSTER MANAGEMENT PANEL [MODE: {mode.upper()}] ===\033[K")
    print(f"{'-' * min(terminal_columns, 90)}\033[K")
    
    running_count = 0
    for worker_id, p in enumerate(processes, 1):
        status = p.poll()
        if status is None:
            status_str = "\033[92mRUNNING\033[0m"
            running_count += 1
            latest_action = get_last_log_line(worker_id)
        elif status == 0:
            status_str = "\033[94mSUCCESS\033[0m"
            latest_action = "Finished chunk cleanly."
        else:
            status_str = f"\033[91mCRASHED ({status})\033[0m"
            latest_action = f"Check log/worker_{worker_id}_sys.log"
            
        # Calculate maximum characters allowed for the log fragment to prevent wrapping
        # 38 chars used by layout structure before log append
        max_log_len = max(10, terminal_columns - 38)
        if len(latest_action) > max_log_len:
            latest_action = latest_action[:max_log_len - 3] + "..."
            
        print(f" Worker #{worker_id} (PID: {p.pid:<5d}) | {status_str:<18} | {latest_action}\033[K")
        
    print(f"{'-' * min(terminal_columns, 90)}\033[K")
    print(f" Cluster Status: {running_count}/{TOTAL_WORKERS} Workers Running\033[K")
    print(" Action: Press \033[93mCtrl+C\033[0m to safely dump worker memory buffers and stop.\033[K")
    print("========================================================================\033[K")
    sys.stdout.flush()

def launch_parallel_workers(mode: str) -> None:
    processes: List[subprocess.Popen] = []
    log_files = []

    # Clear screen initially and hide cursor to minimize screen flicker
    sys.stdout.write("\033[2J\033[?25l")
    sys.stdout.flush()

    try:
        for worker_id in range(1, TOTAL_WORKERS + 1):
            sys_log_path = os.path.join(LOG_DIR, f"worker_{worker_id}_sys.log")
            stdout_log = open(sys_log_path, "w", encoding="utf-8")
            log_files.append(stdout_log)

            env = os.environ.copy()
            env["RUN_MODE"] = mode

            kwargs = {}
            if sys.platform == "win32":
                kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                kwargs["preexec_fn"] = os.setpgrp

            p = subprocess.Popen(
                [sys.executable, SCRAPER_SCRIPT, str(worker_id)],
                stdout=stdout_log,
                stderr=subprocess.STDOUT,
                env=env,
                **kwargs
            )
            processes.append(p)

        while True:
            render_dashboard(processes, mode)
            active_statuses = [p.poll() for p in processes]
            if sum(1 for status in active_statuses if status is None) == 0:
                break
            time.sleep(0.2)

    except KeyboardInterrupt:
        # Re-enable standard layout features and reset cursor location on drop out
        sys.stdout.write("\033[?25h\n")
        print("\n[!] Interrupt caught. Initializing data flush...")
        
        with open(STOP_SIGNAL_FILE, "w") as f:
            f.write("STOP")

        while True:
            running = sum(1 for p in processes if p.poll() is None)
            if running == 0:
                break
            sys.stdout.write(f"\rSafely parking worker engines... ({running} nodes remaining)   ")
            sys.stdout.flush()
            time.sleep(0.2)
            
        print("\nAll datasets saved successfully to log/*.jsonl records.")

    finally:
        # Guarantee cursor is returned to normal visibility even if a hard crash happens
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()
        for log_f in log_files:
            log_f.close()
        if os.path.exists(STOP_SIGNAL_FILE):
            os.remove(STOP_SIGNAL_FILE)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ONPE Cluster Process Orchestrator Hook")
    parser.add_argument(
        "--mode", 
        type=str, 
        choices=["patch", "update", "force"], 
        default="patch"
    )
    args = parser.parse_args()
    
    check_environment()
    launch_parallel_workers(args.mode)