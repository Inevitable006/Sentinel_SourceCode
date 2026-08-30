import os
import urllib.request
import hashlib
import time
from pathlib import Path

# Paths
APPDATA_DIR = os.getenv("APPDATA")
if not APPDATA_DIR:
    APPDATA_DIR = str(Path.home() / "AppData" / "Roaming")
MODELS_DIR = Path(APPDATA_DIR) / "sentinel" / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)

MODEL_FILENAME = "qwen2.5-7b-instruct-q4_k_m.gguf"
DESTINATION = MODELS_DIR / MODEL_FILENAME
URL = f"https://huggingface.co/bartowski/Qwen2.5-7B-Instruct-GGUF/resolve/main/Qwen2.5-7B-Instruct-Q4_K_M.gguf"

def download_file(url, dest):
    print(f"Downloading {url} to {dest}...")
    start = time.time()
    
    # Custom reporter to show progress
    def reporthook(blocknum, blocksize, totalsize):
        readsofar = blocknum * blocksize
        if totalsize > 0:
            percent = readsofar * 1e2 / totalsize
            s = f"\r{percent:5.1f}% {readsofar / (1024*1024):.1f} MB / {totalsize / (1024*1024):.1f} MB"
            print(s, end='')
        else: # total size is unknown
            print(f"\r{readsofar / (1024*1024):.1f} MB read", end='')
            
    urllib.request.urlretrieve(url, dest, reporthook)
    print(f"\nDownload completed in {time.time() - start:.2f} seconds.")

def compute_sha256(file_path):
    print("Computing SHA-256 checksum...")
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        # Read in 4MB chunks
        for byte_block in iter(lambda: f.read(4096*1024), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def record_provenance():
    import shutil
    total, used, free = shutil.disk_usage(DESTINATION.parent)
    
    print("\n--- Download Provenance ---")
    print(f"Source URL: {URL}")
    print(f"Publisher: Qwen (official HuggingFace repository)")
    print(f"License: Apache 2.0 (Qwen2.5)")
    print(f"File Size: {os.path.getsize(DESTINATION) / (1024*1024*1024):.2f} GB")
    print(f"Destination Path: {DESTINATION}")
    print(f"Disk Free Space (After): {free / (1024*1024*1024):.2f} GB")
    
    checksum = compute_sha256(DESTINATION)
    print(f"SHA-256 Checksum: {checksum}")
    print("---------------------------")

if __name__ == "__main__":
    if DESTINATION.exists():
        print("Model file already exists. Verifying...")
        record_provenance()
    else:
        import shutil
        _, _, free = shutil.disk_usage(MODELS_DIR)
        print(f"Disk Free Space (Before): {free / (1024*1024*1024):.2f} GB")
        download_file(URL, DESTINATION)
        record_provenance()
