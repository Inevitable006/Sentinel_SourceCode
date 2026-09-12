import multiprocessing

def stress():
    while True:
        pass

if __name__ == "__main__":
    processes = []
    # Use 8 processes to simulate heavy background load on the 12-thread CPU
    for _ in range(8):
        p = multiprocessing.Process(target=stress)
        p.start()
        processes.append(p)
        
    print(f"Started {len(processes)} CPU stress processes. Press Ctrl+C to stop.")
    try:
        for p in processes:
            p.join()
    except KeyboardInterrupt:
        print("Stopping stress processes...")
        for p in processes:
            p.terminate()
