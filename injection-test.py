import time
import requests
import random
import datetime

# Target configuration
HOST_IP = "127.0.0.1"  # Replace with the IP of the computer running Dash
PORT = "8050"
ENDPOINT = f"http://{HOST_IP}:{PORT}/api/telemetry"

def generate_string(current_drw):
    """Generates a mock string matching the cRIO output format."""
    # Abk: 32 ints
    abk = [random.randint(0, 10) for _ in range(32)]
    abk_str = ";".join(map(str, abk))
    
    # Cnd: 4 floats
    cnd = [random.uniform(0.001, 0.003) for _ in range(4)]
    cnd_str = ";".join([f"{x:.4f}" for x in cnd])
    
    # Flw: 1 float
    flw = random.uniform(-5.1, -4.9)
    flw_str = f"{flw:.6f}"
    
    # Drw: 1 float (decreasing positive value for Core Height)
    drw_str = f"{current_drw:.0f}"
    
    # Pmp: 1 float (RPM), 1 int (State)
    pmp_rpm = random.uniform(11.5, 12.0)
    pmp_state = 1
    pmp_str = f"{pmp_rpm:.6f};{pmp_state}"
    
    return f"AbkStr;{abk_str};AbkEnd;CndStr;{cnd_str};CndEnd;FlwStr;{flw_str};FlwEnd;DrwStr;{drw_str};DrwEnd;PmpStr;{pmp_str};PmpEnd;"

if __name__ == "__main__":
    print(f"Starting Data Injection to {ENDPOINT}")
    current_drw = 100.0  # Initialize core height to a realistic upper threshold
    
    while True:
        payload = {"data": generate_string(current_drw)}
        try:
            response = requests.post(ENDPOINT, json=payload, timeout=2)
            if response.status_code == 200:
                print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Sent telemetry successfully (DRW: {current_drw:.0f}cm).")
            else:
                print(f"Server responded with code {response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"Connection failed: {e}")
            
        # Progressively decrease the core height
        current_drw -= random.uniform(0.5, 1.5)
        # Reset if it hits the lower threshold (simulate loading a new core)
        if current_drw <= 15.0:
            current_drw = 100.0
            
        time.sleep(1) # 1Hz refresh rate