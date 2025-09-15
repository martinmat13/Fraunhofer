import os
from pathlib import Path
from datetime import datetime, timedelta
import time
from time import sleep

# --- USER PARAMETERS ---
INIT_ITERATIONS = 10
CALCULATION_ITERATIONS = 100

# --- Setup Fluent environment ---
if not os.getenv('FLUENT_PROD_DIR'):
    import ansys.fluent.core as pyfluent
    flglobals = pyfluent.setup_for_fluent(product_version="24.2.0", mode="solver", version="3d", precision="double", processor_count=8)
    globals().update(flglobals)

# --- Working directory and mesh files ---
script_dir = Path(__file__).resolve().parent
mesh_files = list(script_dir.glob("*.msh"))
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

while True:
    mass_flow_rate = None

    for mesh_path in mesh_files:
        start_time = time.time()
        mesh_name = mesh_path.stem
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log(f"Running mesh study for: {mesh_name}")

        # --- Read mesh ---
        solver.settings.file.read_mesh(file_name=str(mesh_path))
        solver.settings.mesh.check()
        log("Mesh read.")

        solver.settings.setup.models.viscous.model = "laminar"
        log("Laminar model assigned.")

        # --- Set fluid material (Nitrogen example) ---
        nitrogen = solver.settings.setup.materials.fluid.create("nitrogen")
        nitrogen.density.value.set_state(1.1508)
        nitrogen.viscosity.value.set_state(17.594e-6)
        solver.settings.setup.cell_zone_conditions.fluid['fluid'].general.material = "nitrogen"
        log("Nitrogen material assigned.")

        # --- Set inlet zone type ---
        solver.settings.setup.boundary_conditions.set_zone_type(zone_list=["inlet"], new_type="mass-flow-inlet")
        log("Inlet zone type set to mass-flow-inlet.")
        sleep(2)

        # --- Input mass flow rate (ask every time) ---
        while True:
            user_input = input("Enter mass flow rate in kg/s for the 'inlet' zone (or 'q' to quit): ").strip()
            if user_input.lower() == 'q':
                log("User requested to quit the batch process.")
                solver.exit()
                exit()
            try:
                mass_flow_rate = float(user_input)
                break
            except ValueError:
                print("Invalid input. Please enter a valid number or 'q' to quit.")

        # --- Apply inlet mass flow ---
        try:
            inlet_zone = solver.settings.setup.boundary_conditions.mass_flow_inlet["inlet"]
            inlet_zone.momentum.mass_flow_rate.value = mass_flow_rate
            log(f"Mass flow rate set: {mass_flow_rate} kg/s")
        except Exception as e:
            log(f"ERROR: Failed to assign mass flow rate — {str(e)}")
            solver.exit()
            raise

        # --- Output directory ---
        flow_str = f"{mass_flow_rate:.6f}".replace('.', 'p')
        output_dir = script_dir / f"massflow_{flow_str}_kgps" / f"{mesh_name}_{timestamp}"
        output_dir.mkdir(parents=True, exist_ok=True)

        # --- Other boundary conditions ---
        for wall in ['particle_bed', 'reactor_wall', 'thermocouple_wall']:
            solver.settings.setup.boundary_conditions.wall[wall].momentum.wall_motion = "Stationary Wall"
            solver.settings.setup.boundary_conditions.wall[wall].momentum.shear_condition = "No Slip"

        solver.settings.setup.boundary_conditions.pressure_outlet['outlet'].momentum.backflow_reference_frame = "Absolute"
        solver.settings.setup.boundary_conditions.pressure_outlet['outlet'].momentum.gauge_pressure.value = 0
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
        for eq in ['continuity', 'x-velocity', 'y-velocity', 'z-velocity']:
            solver.solution.monitor.residual.equations[eq].check_convergence = False
            solver.solution.run_calculation.iter_count = CALCULATION_ITERATIONS
            solver.solution.run_calculation.calculate()
        log("Calculation finished.")

        # --- Save pressure drop ---
        pressure_drop_val = solver.solution.report_definitions.compute(report_defs=["pressure_drop"])
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
        log(f"Duration for {mesh_name} at {mass_flow_rate} kg/s: {str(elapsed_td)}")
        log_divider()

    # Ask to repeat for another mass flow
    repeat = input("Do you want to run another batch with a different mass flow rate? (y/n): ").strip().lower()
    if repeat != 'y':
        log("User finished all batches. Exiting.")
        break
    else:
        reuse_mass_flow = False  # reset flag for next batch

solver.exit()
