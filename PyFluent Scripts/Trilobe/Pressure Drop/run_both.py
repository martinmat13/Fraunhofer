import subprocess
import datetime
import os

# Function to generate timestamped log file names
def get_log_path(script_path):
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    script_name = os.path.splitext(os.path.basename(script_path))[0]
    log_dir = os.path.join(os.path.dirname(script_path), "logs")
    os.makedirs(log_dir, exist_ok=True)
    return os.path.join(log_dir, f"{script_name}_{timestamp}.log")

# Absolute paths to your scripts
script1 = r"Y:\Projekte\02_Aktuell\ANSYS_Rocky\Fixed Bed Project\Case Files\Case_3_ParticleBed75mm_Trilobe_Pellet\Simulation\Mesh Study\automationScript.py"
script2 = r"Y:\Projekte\02_Aktuell\ANSYS_Rocky\Fixed Bed Project\Case Files\Case_3_ParticleBed75mm_Trilobe_Pellet\Simulation\Pressure Drop Study\automationScript.py"

# Generate log file paths
log1 = get_log_path(script1)
log2 = get_log_path(script2)

# Run first script
print(f"Running script1: {script1}")
with open(log1, 'w') as f1:
    result1 = subprocess.run(["python", script1], stdout=f1, stderr=subprocess.STDOUT)
    if result1.returncode == 0:
        print(f"Script1 completed successfully. Log saved to: {log1}")
    else:
        print(f"Script1 failed. Check log: {log1}")

# Run second script
print(f"Running script2: {script2}")
with open(log2, 'w') as f2:
    result2 = subprocess.run(["python", script2], stdout=f2, stderr=subprocess.STDOUT)
    if result2.returncode == 0:
        print(f"Script2 completed successfully. Log saved to: {log2}")
    else:
        print(f"Script2 failed. Check log: {log2}")

print("Both scripts executed sequentially.")
