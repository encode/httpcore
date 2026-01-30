import httpcore
import socket
import threading
import time
import asyncio

# --- Server Setup (Same as before) ---
HANG_TIME = 20
TIMEOUT = 2.0

def get_free_port():
    with socket.socket() as s:
        s.bind(('', 0))
        return s.getsockname()[1]

def blackhole_proxy_server(port, stop_event):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('127.0.0.1', port))
    server.listen(1)
    server.settimeout(1.0)
    
    while not stop_event.is_set():
        try:
            client, _ = server.accept()
            # print("[Server] Accepted connection, sleeping...")
            time.sleep(HANG_TIME) 
            client.close()
        except socket.timeout: continue
        except: break
    server.close()

# --- Async Test ---
async def run_async_test(port):
    print(f"[*] Testing ASYNC httpcore SOCKSProxy with {TIMEOUT}s timeout...")
    start_time = time.time()
    
    async with httpcore.AsyncSOCKSProxy(
        proxy_url=f"socks5://127.0.0.1:{port}"
    ) as pool:
        try:
            await pool.request(
                "GET", 
                "http://example.com", 
                extensions={'timeout': {'connect': TIMEOUT, 'read': TIMEOUT}}
            )
        except httpcore.TimeoutException:
            print("[SUCCESS] Caught timeout correctly!")
        except Exception as e:
            print(f"[ERROR] {type(e).__name__}: {e}")
        finally:
            duration = time.time() - start_time
            print(f"[*] Duration: {duration:.2f}s")

def main():
    port = get_free_port()
    stop_event = threading.Event()
    t = threading.Thread(target=blackhole_proxy_server, args=(port, stop_event))
    t.start()
    time.sleep(0.5)

    try:
        asyncio.run(run_async_test(port))
    finally:
        stop_event.set()
        t.join()

if __name__ == "__main__":
    main()