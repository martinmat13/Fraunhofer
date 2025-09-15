import os
import sys
import time
from time import sleep
from datetime import datetime, timedelta
from pathlib import Path
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")  # non-GUI backend

# -------------------------------------------------------------------
# Tee class to duplicate stdout to both console and log file
# -------------------------------------------------------------------
class Tee:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, message):
        for stream in self.streams:
            stream.write(message)
            stream.flush()

    def flush(self):
        for stream in self.streams:
            stream.flush()

# -------------------------------------------------------------------
# Setup paths and logging
# -------------------------------------------------------------------
script_dir = Path(__file__).resolve().parent
log_file_path = script_dir / "terminal_output_log.txt"
log_file = open(log_file_path, "w", encoding="utf-8")
tee = Tee(sys.__stdout__, log_file)
sys.stdout = sys.stderr = tee

def log(msg: str):
    timestamp = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
    with open(script_dir / "simulation_log.txt", "a", encoding="utf-8") as logf:
        logf.write(f"{timestamp} {msg}\n")
    print(f"{timestamp} {msg}")

def log_divider():
    with open(script_dir / "simulation_log.txt", "a", encoding="utf-8") as logf:
        logf.write("=" * 60 + "\n")
    print("=" * 60)

# -------------------------------------------------------------------
# USER PARAMETERS
# -------------------------------------------------------------------
MASS_FLOW_RATES = [6.17528e-04,4.11685e-04,2.05843e-04,1.02921e-04,4.11685e-05,2.05843e-05,1.23506e-05]
#MASS_FLOW_RATES = [6.17528e-04] #For Test
INIT_ITERATIONS = 10
CALCULATION_ITERATIONS = 100
REACTOR_LENGTH = 0.075        # [m]
N_PLANES = 10                # axial planes
N_ISO_CLIPS = 10             # iso-clips for heat flux
INLET_TEMPERATURE = 300      # K
PARTICLE_TEMPERATURE = 1300  # K
# -------------------------------------------------------------------
# Fluent Environment Setup
# -------------------------------------------------------------------
if not os.getenv("FLUENT_PROD_DIR"):
    import ansys.fluent.core as pyfluent
    flglobals = pyfluent.setup_for_fluent(
        product_version="25.1.0",
        mode="solver",
        dimension=3,
        precision="double",
        processor_count=8,
        ui_mode="no_gui",
        graphics_driver="dx11"
    )
    globals().update(flglobals)

# -------------------------------------------------------------------
# Mesh Setup and Loop
# -------------------------------------------------------------------
mesh_files = list(script_dir.glob("*.msh"))
log("\n--- Starting batch for multiple mass flow rates ---")

for mass_flow_rate in MASS_FLOW_RATES:
    flow_str = f"{mass_flow_rate:.6f}"
    flow_dir = script_dir / f"massflow_{flow_str}_kgps"
    flow_dir.mkdir(exist_ok=True)
    log(f"\n--- Processing mass flow rate: {mass_flow_rate} kg/s ---")

    for mesh_path in mesh_files:
        start_time = time.time()
        mesh_name = mesh_path.stem
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = flow_dir / f"{mesh_name}_{timestamp}"
        plots_dir = output_dir / "plots"
        contours_dir = output_dir / "contours"
        for d in [output_dir, plots_dir, contours_dir]:
            d.mkdir(exist_ok=True)

        # ---------------------- Read Mesh ------------
        solver.settings.file.read_mesh(file_name=str(mesh_path))
        solver.settings.mesh.check()
        log(f"Mesh {mesh_name} read.")

        # ----------------- Boundary Conditions -----------------
        solver.settings.setup.boundary_conditions.set_zone_type(
            zone_list=["inlet"], new_type="mass-flow-inlet"
        )
        sleep(1)
        inlet_zone = solver.settings.setup.boundary_conditions.mass_flow_inlet["inlet"]
        inlet_zone.momentum.mass_flow_rate.value = mass_flow_rate
        log("Mass flow rate set at inlet.")

        solver.settings.setup.models.viscous.model = "laminar"
        solver.settings.setup.models.energy.enabled = True
        log("Models assigned: Laminar + Energy.")

        # Materials
        nitrogen = solver.settings.setup.materials.fluid.create("nitrogen")
        #nitrogen.density.value.set_state(1.1508) #Constant Density
        nitrogen.density = {"option" : "ideal-gas"}
        nitrogen.viscosity.value = 17.594e-6
        #nitrogen.specific_heat.value = 1006.43
        #nitrogen.thermal_conductivity.value = 0.0242
        #nitrogen.molecular_weight.value = 28.966

        solver.settings.setup.cell_zone_conditions.fluid["fluid"].general.material = "nitrogen"
        log("Nitrogen material assigned.")

        # Walls and outlet
        for wall in ["particle_bed", "reactor_wall", "thermocouple_wall"]:
            solver.settings.setup.boundary_conditions.wall[wall].momentum.wall_motion = "Stationary Wall"
            solver.settings.setup.boundary_conditions.wall[wall].momentum.shear_condition = "No Slip"
        solver.settings.setup.boundary_conditions.pressure_outlet["outlet"].momentum.gauge_pressure.value = 0
        solver.settings.setup.boundary_conditions.pressure_outlet["outlet"].thermal.backflow_total_temperature = PARTICLE_TEMPERATURE

        # Thermal BCs
        solver.settings.setup.boundary_conditions.mass_flow_inlet["inlet"].thermal.total_temperature.value = INLET_TEMPERATURE
        solver.settings.setup.boundary_conditions.wall["particle_bed"].thermal.thermal_condition = "Temperature"
        solver.settings.setup.boundary_conditions.wall["particle_bed"].thermal.temperature.value = PARTICLE_TEMPERATURE
        solver.settings.setup.boundary_conditions.wall["reactor_wall"].thermal.heat_flux.value = 0
        solver.settings.setup.boundary_conditions.wall["thermocouple_wall"].thermal.heat_flux.value = 0
        log("Thermal boundary conditions set.")

        # ----------------- Initialization -----------------
        solver.settings.solution.initialization.initialization_type = "hybrid"
        solver.settings.solution.initialization.hybrid_init_options.general_settings.iter_count = INIT_ITERATIONS
        solver.settings.solution.initialization.initialize()
        log("Hybrid initialization complete.")

        # ----------------- Axial Planes -----------------
        z_positions = np.linspace(0, REACTOR_LENGTH, N_PLANES + 1)
        plane_names = []
        for i, z in enumerate(z_positions):
            pname = f"plane_{i+1}"
            solver.settings.results.surfaces.plane_surface.create(name=pname)
            solver.settings.results.surfaces.plane_surface[pname].method = "xy-plane"
            solver.settings.results.surfaces.plane_surface[pname].z = float(z)
            plane_names.append(pname)
        log(f"Created {N_PLANES} axial planes.")

        # ----------------- Temperature Reports -----------------
        temp_reports = []
        for i, (pname, z_pos) in enumerate(zip(plane_names, z_positions), start=1):
            # Create mass-weighted temperature report
            rname = f"Temp_Mass_Avg_{pname}"
            solver.settings.solution.report_definitions.surface[rname] = {
                "report_type": "surface-massavg",
                "field": "temperature",
                "surface_names": [pname],
                "output_parameter": True
            }
            temp_reports.append(rname)

            # Create monitor plot using default internal name
            T_plot_name = f"temperature-report-plot-{i}"  # default generated name
            solver.settings.solution.monitor.report_plots.create(T_plot_name)  # automatically creates "report-plot-N"

            solver.settings.solution.monitor.report_plots[T_plot_name].report_defs = [rname]
            solver.settings.solution.monitor.report_plots[T_plot_name].print = False
            solver.settings.solution.monitor.report_plots[T_plot_name].plot_instantaneous_values = True
        log("Temperature mass-avg report definitions created.")

        density_reports = []
        for i, (pname, z_pos) in enumerate(zip(plane_names, z_positions), start=1):
            # Create mass-weighted desnity report
            rname = f"Density_Mass_Avg_{pname}"
            solver.settings.solution.report_definitions.surface[rname] = {
                "report_type": "surface-massavg",
                "field": "density",
                "surface_names": [pname],
                "output_parameter": True
            }
            density_reports.append(rname)

            # Create monitor plot using default internal name
            rho_plot_name = f"density-report-plot-{i}"  # default generated name
            solver.settings.solution.monitor.report_plots.create(rho_plot_name)  # automatically creates "report-plot-N"

            solver.settings.solution.monitor.report_plots[rho_plot_name].report_defs = [rname]
            solver.settings.solution.monitor.report_plots[rho_plot_name].print = False
            solver.settings.solution.monitor.report_plots[rho_plot_name].plot_instantaneous_values = True
        log("Density mass-avg report definitions created.")

        # ----------------- ISO-CLIPS & Heat Flux Reports -----------------
        iso_clip_names = []
        z_positions_iso = np.linspace(0, REACTOR_LENGTH, N_ISO_CLIPS + 1)

        for i in range(N_ISO_CLIPS):
            z_min = z_positions_iso[i]
            z_max = z_positions_iso[i+1]
            clip_name = f"iso_clip_{i+1}"
            iso_clip_names.append(clip_name)

            # Create iso clip AFTER initialization
            solver.settings.results.surfaces.iso_clip.create(name=clip_name)
            solver.settings.results.surfaces.iso_clip[clip_name].field = "z-coordinate"
            solver.settings.results.surfaces.iso_clip[clip_name].surfaces = ["particle_bed"]
            solver.settings.results.surfaces.iso_clip[clip_name].range.minimum = float(z_min)
            solver.settings.results.surfaces.iso_clip[clip_name].range.maximum = float(z_max)

            # Create area-averaged heat-flux report
            report_name = f"HF_AreaAvg_{i+1}"
            solver.settings.solution.report_definitions.surface.create(name=report_name)
            solver.settings.solution.report_definitions.surface[report_name].report_type = "surface-integral"
            solver.settings.solution.report_definitions.surface[report_name].field = "heat-flux"
            solver.settings.solution.report_definitions.surface[report_name].surface_names = [clip_name]
            solver.settings.solution.report_definitions.surface[report_name].output_parameter = True

        # ----------------- Pressure Drop -----------------
        solver.settings.solution.report_definitions.surface["report-inlet"] = {"report_type": "surface-areaavg"}
        solver.settings.solution.report_definitions.surface["report-inlet"].surface_names = ["inlet"]
        solver.settings.solution.report_definitions.surface["report-outlet"] = {"report_type": "surface-areaavg"}
        solver.settings.solution.report_definitions.surface["report-outlet"].surface_names = ["outlet"]
        solver.settings.solution.report_definitions.single_valued_expression["pressure_drop"] = {
            "definition": "{report-inlet} - {report-outlet}"
        }

        # ----------------- Calculation -----------------
        solver.settings.solution.monitor.residual.equations['continuity'].check_convergence = False
        solver.settings.solution.monitor.residual.equations['x-velocity'].check_convergence = False
        solver.settings.solution.monitor.residual.equations['y-velocity'].check_convergence = False
        solver.settings.solution.monitor.residual.equations['z-velocity'].check_convergence = False
        solver.settings.solution.monitor.residual.equations['energy'].check_convergence = False
        solver.settings.solution.run_calculation.iter_count = CALCULATION_ITERATIONS
        solver.settings.solution.run_calculation.calculate()
        log("Solver run complete.")

        # ----------------- Extract Pressure Drop -----------------
        pressure_drop_val = solver.settings.solution.report_definitions.compute(report_defs=["pressure_drop"])
        with open(output_dir / "pressure_drop.txt", "w", encoding="utf-8") as f:
            f.write(f"Pressure Drop: {pressure_drop_val}\n")
        log(f"Pressure drop computed: {pressure_drop_val}")

        # ----------------- Residual Plot -----------------
        res_plot_path = str(plots_dir / "Residual_Plot.png")
        solver.settings.solution.monitor.residual.plot()
        solver.settings.results.graphics.picture.save_picture(file_name=res_plot_path)
        log(f"Residual plot saved: {res_plot_path}")

        # ----------------- Plot Monitor Reports & Save Pictures -----------------
        for i in range(1, len(temp_reports) + 1):
            T_plot_name = f"temperature-report-plot-{i}"  # default plot names
            solver.settings.solution.monitor.report_plots[T_plot_name].plot()
            
            # Save picture with meaningful name
            pic_name = f"temperature_plane_{i}.png" if i < len(temp_reports) else "temperature_outlet.png"
            solver.settings.results.graphics.picture.save_picture(file_name=str(plots_dir / pic_name))
            log(f"Saved temperature monitor plot picture: {pic_name}")

        for i in range(1, len(density_reports) + 1):
            rho_plot_name  = f"density-report-plot-{i}"  # default plot names
            solver.settings.solution.monitor.report_plots[rho_plot_name].plot()
            
            # Save picture with meaningful name
            pic_name = f"density_plane_{i}.png" if i < len(density_reports) else "density_outlet.png"
            solver.settings.results.graphics.picture.save_picture(file_name=str(plots_dir / pic_name))
            log(f"Saved density monitor plot picture: {pic_name}")

        # ----------------- Temperature Profile CSV & Plot -----------------
        temp_data = {}
        for pname, rname in zip(plane_names, temp_reports):
            result = solver.settings.solution.report_definitions.compute(report_defs=[rname])
            temp_data[pname] = float(result[0][rname][0])
        df = pd.DataFrame({
            "Axial_Position_m": z_positions,
            "Temperature_K": [temp_data[p] for p in plane_names]
        })
        df.to_csv(output_dir / "axial_temperature_profile.csv", index=False)
        plt.figure(figsize=(7,5))
        plt.plot(df["Axial_Position_m"], df["Temperature_K"], marker="o", color="tab:red")
        plt.xlabel("Axial Position [m]")
        plt.ylabel("Mass-Weighted Avg Temp [K]")
        plt.title(f"Axial Temperature Profile: {mass_flow_rate} kg/s, Mesh: {mesh_name}")
        plt.grid(True)
        plt.savefig(plots_dir / "axial_temperature_profile.png", dpi=600)
        plt.close()
        log("Axial temperature profile saved.")

        # ----------------- Density CSV & Plot -----------------
        density_data = {}
        for pname, rname in zip(plane_names, density_reports):
            result = solver.settings.solution.report_definitions.compute(report_defs=[rname])
            density_data[pname] = float(result[0][rname][0])
        df = pd.DataFrame({
            "Axial_Position_m": z_positions,
            "Density_kg/m^3": [density_data[p] for p in plane_names]
        })
        df.to_csv(output_dir / "density_data.csv", index=False)
        plt.figure(figsize=(7,5))
        plt.plot(df["Axial_Position_m"], df["Density_kg/m^3"], marker="o", color="tab:red")
        plt.xlabel("Axial Position [m]")
        plt.ylabel("Mass-Weighted Avg Density [kg/m^3]")
        plt.title(f"Axial Density Profile: {mass_flow_rate} kg/s, Mesh: {mesh_name}")
        plt.grid(True)
        plt.savefig(plots_dir / "axial_density_profile.png", dpi=600)
        plt.close()
        log("Axial density profile saved.")

        # ----------------- Area-Averaged Heat Flux CSV & Plot -----------------
        heat_flux_data = {}
        for i in range(N_ISO_CLIPS):
            report_name = f"HF_AreaAvg_{i+1}"
            result = solver.settings.solution.report_definitions.compute(report_defs=[report_name])
            heat_flux_data[f"iso_clip_{i+1}"] = float(result[0][report_name][0])

        # Original values before thresholding
        original_hf_values = [heat_flux_data[f"iso_clip_{i+1}"] for i in range(N_ISO_CLIPS)]

        # Midpoints
        z_mid = (z_positions_iso[:-1] + z_positions_iso[1:]) / 2

        # Build dataframe
        df_hf = pd.DataFrame({
            "Z_min_m": z_positions_iso[:-1],
            "Z_max_m": z_positions_iso[1:],
            "Z_mid_m": z_mid,
            "HeatFlux_W_raw": original_hf_values,
            "HeatFlux_W_clipped": np.clip(original_hf_values, 1e-3, None)
        })

        # Save CSV
        df_hf.to_csv(output_dir / "iso_clip_heat_flux_profile.csv", index=False)

        # Use clipped values for plotting
        hf_values = df_hf["HeatFlux_W_clipped"].tolist()

        # Plot
        plt.figure(figsize=(7, 5))
        plt.plot(z_mid, hf_values, marker="o", color="tab:blue")
        plt.xlabel("Axial Position [m]")
        plt.ylabel("Heat Flux Integral [W]")
        plt.title(f"Iso-Clip Heat Flux Profile: {mass_flow_rate} kg/s, Mesh: {mesh_name}")
        plt.yscale("log")
        plt.grid(True)
        plt.tight_layout()
        plt.savefig(plots_dir / "iso_clip_heat_flux_profile.png", dpi=600)
        plt.close()


        log("Iso-clip heat flux CSV & plot saved.")

        # ----------------- Contours & Scenes -----------------
        solver.settings.results.graphics.contour.create("temperature_contour")
        solver.settings.results.graphics.contour["temperature_contour"].field = "temperature"
        solver.settings.results.graphics.contour["temperature_contour"].surfaces_list = plane_names
        solver.settings.results.graphics.contour["temperature_contour"].range_options.global_range = False
        solver.settings.results.graphics.contour["temperature_contour"].range_options.auto_range = False
        solver.settings.results.graphics.contour["temperature_contour"].range_options.minimum = 300
        solver.settings.results.graphics.contour["temperature_contour"].range_options.maximum = 1300

        solver.settings.results.graphics.contour.create("heat_flux_contour")
        solver.settings.results.graphics.contour["heat_flux_contour"].field = "heat-flux"
        solver.settings.results.graphics.contour["heat_flux_contour"].surfaces_list = ["particle_bed"]
        solver.settings.results.graphics.contour["heat_flux_contour"].range_options.global_range = True
        solver.settings.results.graphics.contour["heat_flux_contour"].range_options.auto_range = True
        #solver.settings.results.graphics.contour["heat_flux_contour"].range_options.minimum = 0
        #solver.settings.results.graphics.contour["heat_flux_contour"].range_options.maximum = 50

        solver.settings.results.scene.create("temperature_scene")
        solver.settings.results.scene["temperature_scene"].graphics_objects.add(name="temperature_contour")
        solver.settings.results.scene["temperature_scene"].display()
        solver.settings.results.graphics.picture.save_picture(file_name=str(contours_dir / "temperature_scene.png"))

        solver.settings.results.scene.create("heat_flux_scene")
        solver.settings.results.scene["heat_flux_scene"].graphics_objects.add(name="heat_flux_contour")
        solver.settings.results.scene["heat_flux_scene"].display()
        solver.settings.results.graphics.picture.save_picture(file_name=str(contours_dir / "heat_flux_scene.png"))
        log("Contour and scene images saved.")

        # ----------------- Save Case/Data -----------------
        solver.settings.file.write_case_data(file_name=str(output_dir / f"{mesh_name}.cas.h5"))
        log("Case and data written.")

        elapsed = time.time() - start_time
        log(f"Elapsed time for {mesh_name} at {mass_flow_rate} kg/s: {timedelta(seconds=int(elapsed))}")
        log_divider()

log("All simulations completed successfully.")
solver.exit()
