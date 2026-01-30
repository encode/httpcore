import httpcore
import socket
import threading
import time

# --- Same Server Setup as before ---
TIMEOUT = 2.0
HANG_TIME = 20

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
            time.sleep(HANG_TIME) # Hang the handshake
            client.close()
        except socket.timeout: continue
        except: break
    server.close()

# --- The Test ---
def run_test():
    proxy_port = get_free_port()
    stop_event = threading.Event()
    t = threading.Thread(target=blackhole_proxy_server, args=(proxy_port, stop_event))
    t.start()
    time.sleep(0.5)

    print(f"[*] Testing httpcore SOCKSProxy with {TIMEOUT}s timeout...")
    start_time = time.time()
    
    # We use the low-level SOCKSProxy directly
    with httpcore.SOCKSProxy(
        proxy_url=f"socks5://127.0.0.1:{proxy_port}"
    ) as pool:
        try:
            # We assume httpcore 1.0+ style request
            pool.request(
                "GET", 
                "http://example.com", 
                extensions={'timeout': {'connect': TIMEOUT, 'read': TIMEOUT}}
            )
        except httpcore.TimeoutException:
            print("[SUCCESS] Caught timeout correctly!")
        except Exception as e:
            print(f"[ERROR] {e}")
        finally:
            duration = time.time() - start_time
            print(f"[*] Duration: {duration:.2f}s")
            stop_event.set()
            t.join()

if __name__ == "__main__":
    run_test()