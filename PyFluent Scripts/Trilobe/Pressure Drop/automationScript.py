import os
from pathlib import Path
from datetime import datetime, timedelta
import time
from time import sleep
import tkinter as tk
from tkinter import simpledialog
import sys


# --- Create a class that writes to both terminal and a file ---
class Tee:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, message):
        for stream in self.streams:
            stream.write(message)
            stream.flush()  # ensure real-time output

    def flush(self):
        for stream in self.streams:
            stream.flush()

# --- Setup paths ---
script_dir = Path(__file__).resolve().parent
log_file_path = script_dir / "terminal_output_log.txt"
log_file = open(log_file_path, "w", encoding="utf-8")

# --- Redirect stdout and stderr to both terminal and log file ---
tee = Tee(sys.__stdout__, log_file)
sys.stdout = sys.stderr = tee

# --- USER PARAMETERS ---
MASS_FLOW_RATES = [
    1.23506e-05,
    2.05843e-05,
    4.11685e-05,
    1.02921e-04,
    2.05843e-04,
    4.11685e-04,
    6.17528e-04
]  # Mass flow rates in kg/s

INIT_ITERATIONS = 10                         # Hybrid init iterations
CALCULATION_ITERATIONS = 100                 # Solver iterations

# --- Setup Fluent environment ---
if not os.getenv('FLUENT_PROD_DIR'):
    import ansys.fluent.core as pyfluent
    flglobals = pyfluent.setup_for_fluent(product_version="25.1.0",
                                          mode="solver", dimension=3,
                                          precision="single", processor_count=8,
                                          graphics_driver="dx11")
    globals().update(flglobals)

# --- Working directory and mesh file setup ---
script_dir = Path(__file__).resolve().parent
mesh_files = list(script_dir.glob("*.msh"))  # Find all .msh files
log_file = script_dir / "simulation_log.txt"

def log(msg: str):
    timestamp = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
    with open(log_file, "a", encoding="utf-8") as logf:
        logf.write(f"{timestamp} {msg}\n")
    print(f"{timestamp} {msg}")

def log_divider():
    with open(log_file, "a", encoding="utf-8") as logf:
        logf.write("=" * 60 + "\n")
    print("=" * 60)

log("\n--- Starting mesh study batch for multiple mass flow rates ---")

for mass_flow_rate in MASS_FLOW_RATES:
    # Folder named by mass flow rate, dots replaced with 'p' for safe folder names
    flow_str = f"{mass_flow_rate:.6f}"
    flow_dir = script_dir / f"massflow_{flow_str}_kgps"
    flow_dir.mkdir(exist_ok=True)

    log(f"\n--- Processing mass flow rate: {mass_flow_rate} kg/s ---")

    for mesh_path in mesh_files:
        start_time = time.time()
        mesh_name = mesh_path.stem
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = flow_dir / f"{mesh_name}_{timestamp}"
        output_dir.mkdir(exist_ok=True)

        log(f"Running mesh study for: {mesh_name} at mass flow rate {mass_flow_rate} kg/s")

        # --- Read mesh ---
        solver.settings.file.read_mesh(file_name=str(mesh_path))
        solver.settings.mesh.check()
        log("Mesh read.")
        # --- Boundary conditions ---
        solver.settings.setup.boundary_conditions.set_zone_type(zone_list = ["inlet"], new_type = "mass-flow-inlet")    
        log("Inlet zone type set to mass-flow-inlet.")
        #solver.settings.setup.boundary_conditions.mass_flow_inlet["inlet"].momentum.mass_flow_rate.value = 0.0  # Initialize to zero
        sleep(2)  # short delay helps in PyFluent context

        # Access the newly updated inlet zone dictionary (ensures correct type)
        try:
            inlet_zone = solver.settings.setup.boundary_conditions.mass_flow_inlet["inlet"]
            inlet_zone.momentum.mass_flow_rate.value = mass_flow_rate
        except Exception as e:
            log(f"ERROR: Failed to assign mass flow rate — {str(e)}")
            solver.exit()
            raise     
        solver.settings.setup.models.viscous.model = "laminar"
        log("Laminar model assigned.")
        # --- Set fluid material (Nitrogen example) ---
        nitrogen = solver.settings.setup.materials.fluid.create("nitrogen")
        nitrogen.density.value.set_state(1.1508)
        nitrogen.viscosity.value.set_state(17.594e-6)
        solver.settings.setup.cell_zone_conditions.fluid['body'].general.material = "nitrogen"
        log("Nitrogen material assigned.")
                
        solver.settings.setup.boundary_conditions.wall['particle_bed'].momentum.wall_motion = "Stationary Wall"
        solver.settings.setup.boundary_conditions.wall['reactor_wall'].momentum.wall_motion = "Stationary Wall"
        solver.settings.setup.boundary_conditions.wall['thermocouple_wall'].momentum.wall_motion = "Stationary Wall"

        solver.settings.setup.boundary_conditions.wall['particle_bed'].momentum.shear_condition = "No Slip"
        solver.settings.setup.boundary_conditions.wall['reactor_wall'].momentum.shear_condition = "No Slip"
        solver.settings.setup.boundary_conditions.wall['thermocouple_wall'].momentum.shear_condition = "No Slip"
        
        # Outlet BC
        solver.settings.setup.boundary_conditions.pressure_outlet['outlet'].momentum.backflow_reference_frame = "Absolute"
        solver.settings.setup.boundary_conditions.pressure_outlet['outlet'].momentum.gauge_pressure.value = 0

        log("Boundary conditions set.")
      
        # --- Report definitions ---
        solver.settings.solution.report_definitions.surface["report-inlet"] = {"report_type": "surface-areaavg"}
        solver.settings.solution.report_definitions.surface["report-inlet"].surface_names = ["inlet"]

        solver.settings.solution.report_definitions.surface["report-outlet"] = {"report_type": "surface-areaavg"}
        solver.settings.solution.report_definitions.surface["report-outlet"].surface_names = ["outlet"]

        solver.settings.solution.report_definitions.single_valued_expression["pressure_drop"] = {
            "definition": "{report-inlet} - {report-outlet}"
        }

        log("Report definitions set.")

        # --- Initialization ---
        solver.settings.solution.initialization.initialization_type = "hybrid"
        solver.settings.solution.initialization.hybrid_init_options.general_settings.iter_count = INIT_ITERATIONS
        solver.settings.solution.initialization.initialize()
        log("Initialization complete.")

        # --- Run calculation ---
        solver.settings.solution.monitor.residual.equations['continuity'].check_convergence = False
        solver.settings.solution.monitor.residual.equations['x-velocity'].check_convergence = False
        solver.settings.solution.monitor.residual.equations['y-velocity'].check_convergence = False
        solver.settings.solution.monitor.residual.equations['z-velocity'].check_convergence = False
        solver.settings.solution.run_calculation.iter_count = CALCULATION_ITERATIONS
        solver.settings.solution.run_calculation.calculate()
        log("Calculation finished.")

        # --- Save pressure drop ---
        pressure_drop_val = solver.settings.solution.report_definitions.compute(report_defs=["pressure_drop"])
        with open(output_dir / "pressure_drop.txt", "w", encoding="utf-8") as f:
            f.write(f"Pressure Drop: {pressure_drop_val}\n")
        log(f"Pressure drop computed: {pressure_drop_val}")

        # --- Save residual plot ---
        res_plot_path = str(output_dir / "Residual_Plot.png")
        solver.settings.solution.monitor.residual.plot()
        solver.settings.results.graphics.picture.save_picture(file_name=res_plot_path)
        log(f"Residual plot saved: {res_plot_path}")

        # --- Save case and data ---
        solver.file.write_case_data(file_name=str(output_dir / f"{mesh_name}.cas.h5"))
        log("Case and data written.")

        # --- Duration logging ---
        elapsed = time.time() - start_time
        elapsed_td = timedelta(seconds=int(elapsed))
        log(f"Duration for {mesh_name} at mass flow rate {mass_flow_rate} kg/s: {str(elapsed_td)}")
        log_divider()

log("\nAll mesh cases completed for all mass flow rates.")
solver.exit()

