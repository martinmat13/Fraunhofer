import os
from pathlib import Path
from datetime import datetime, timedelta
import time

# --- USER PARAMETERS ---
INLET_VELOCITY = 1.0                    	# m/s
INIT_ITERATIONS = 10                   		# Hybrid init iterations
CALCULATION_ITERATIONS = 100            	# Run calculation iterations

# --- Setup Fluent environment if not already running ---
if not os.getenv('FLUENT_PROD_DIR'):
    import ansys.fluent.core as pyfluent
    flglobals = pyfluent.setup_for_fluent(product_version="24.2.0", mode="solver", version="3d", precision="double", processor_count=8)
    globals().update(flglobals)

# --- Set up working directory and log file ---
script_dir = Path(__file__).resolve().parent
mesh_files = list(script_dir.glob("*.msh"))  # All .msh files in the script folder
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

log("\n--- Starting mesh study batch ---")

for mesh_path in mesh_files:
    start_time = time.time()
    mesh_name = mesh_path.stem
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = script_dir / f"{mesh_name}_{timestamp}"
    output_dir.mkdir(exist_ok=True)

    log(f"Running mesh study for: {mesh_name}")

    # --- Read mesh file ---
    solver.file.read_mesh(file_name=str(mesh_path))
    solver.mesh.check()
    log("Mesh read.")

    # --- Boundary conditions setup ---
    solver.setup.boundary_conditions.velocity_inlet['inlet'].momentum.velocity.value = INLET_VELOCITY
    solver.setup.boundary_conditions.wall['particle_bed'].momentum.wall_motion = "Stationary Wall"
    solver.setup.boundary_conditions.wall['particle_bed'].momentum.shear_condition = "No Slip"
    solver.setup.boundary_conditions.pressure_outlet['outlet'].momentum.backflow_reference_frame = "Absolute"
    solver.setup.boundary_conditions.pressure_outlet['outlet'].momentum.gauge_pressure.value = 0
    log("Boundary conditions set.")

    # --- Report definitions ---
    solver.solution.report_definitions.surface["report-inlet"] = {"report_type": "surface-areaavg"}
    solver.solution.report_definitions.surface["report-inlet"].surface_names = ["inlet"]

    solver.solution.report_definitions.surface["report-outlet"] = {"report_type": "surface-areaavg"}
    solver.solution.report_definitions.surface["report-outlet"].surface_names = ["outlet"]

    solver.solution.report_definitions.single_valued_expression["pressure_drop"] = {
        "definition": "{report-inlet} - {report-outlet}"
    }

    log("Report definitions set.")

    # --- Initialization ---
    solver.solution.initialization.initialization_type = "hybrid"
    solver.solution.initialization.hybrid_init_options.general_settings.iter_count = INIT_ITERATIONS
    solver.solution.initialization.initialize()
    log("Initialization complete.")

    # --- Run calculation ---
    solver.solution.monitor.residual.equations['continuity'].check_convergence = False
    solver.solution.monitor.residual.equations['x-velocity'].check_convergence = False
    solver.solution.monitor.residual.equations['y-velocity'].check_convergence = False
    solver.solution.monitor.residual.equations['z-velocity'].check_convergence = False
    solver.solution.run_calculation.iter_count = CALCULATION_ITERATIONS
    solver.solution.run_calculation.calculate()
    log("Calculation finished.")

    # --- Compute and save pressure drop ---
    pressure_drop_val = solver.solution.report_definitions.compute(report_defs=["pressure_drop"])
    with open(output_dir / "pressure_drop.txt", "w", encoding="utf-8") as f:
        f.write(f"Pressure Drop: {pressure_drop_val}\n")
    log(f"Pressure drop computed: {pressure_drop_val}")

    # --- Create line surface and velocity plot ---
    solver.results.surfaces.line_surface["line-1"] = {}
    solver.results.surfaces.line_surface['line-1'].p0 = [0, 0, -0.01]
    solver.results.surfaces.line_surface['line-1'].p1 = [0, 0, 0.02]

    solver.results.plot.xy_plot['velocity-xy'] = {
        "name": "velocity-xy",
        "options": {
            "position_on_y_axis": False,
            "position_on_x_axis": True,
            "node_values": True
        },
        "plot_direction": {
            "option": "direction-vector",
            "direction_vector": {
                "x_component": 0,
                "y_component": 0,
                "z_component": 1
            }
        },
        "surfaces_list": ["line-1"],
        "uid": "uid-1",
        "x_axis_function": "Direction Vector",
        "y_axis_function": "velocity-magnitude"
    }

    solver.results.plot.xy_plot['velocity-xy'].write_to_file(filename=str(output_dir / "velocityXY"))
    log("Velocity data saved.")

    # --- Save case and data ---
    solver.file.write_case_data(file_name=str(output_dir / f"{mesh_name}.cas.h5"))
    log("Case and data written.")

    # --- Log duration ---
    elapsed = time.time() - start_time
    elapsed_td = timedelta(seconds=int(elapsed))
    log(f"Duration for {mesh_name}: {str(elapsed_td)}")
    log_divider()

log("\nAll mesh cases completed.")

solver.exit()
