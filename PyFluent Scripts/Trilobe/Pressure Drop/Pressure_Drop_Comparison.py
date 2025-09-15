import os
import re
import math
import matplotlib.pyplot as plt
from collections import defaultdict

# === CONSTANTS ===
DENSITY_Nitrogen = 1.1508  # kg/m³ at 20°C
MU_Nitrogen = 17.594e-6    # Pa.s (dynamic viscosity)
EPSILON = 0.4890          # Bed porosity (example, adjust as needed)

# Reactor dimensions (convert cm to m)
L_BED = 10.0 * 1e-2        # Bed length in meters
R_OUTER = 0.7855 * 1e-2    # Outer radius in meters
R_INNER = 0.15875 * 1e-2   # Inner radius in meters

# Cross-sectional flow area of annular packed bed
A_CROSS = math.pi * (R_OUTER**2 - R_INNER**2)

# === Pellet data ===
# Length (mm), Volume (cm³), Surface Area (cm²), Mass Flow Rate (g/s)
pellet_data = [
    {'length_mm': 2, 'volume_cm3': 0.00405, 'surface_area_cm2': 0.17037, 'mass_flow_g_s': 1.35977},
    {'length_mm': 3, 'volume_cm3': 0.00607, 'surface_area_cm2': 0.23524, 'mass_flow_g_s': 2.50944},
    {'length_mm': 4, 'volume_cm3': 0.00810, 'surface_area_cm2': 0.30016, 'mass_flow_g_s': 3.34689},
    {'length_mm': 5, 'volume_cm3': 0.01012, 'surface_area_cm2': 0.36507, 'mass_flow_g_s': 1.77801},
    {'length_mm': 6, 'volume_cm3': 0.01215, 'surface_area_cm2': 0.42999, 'mass_flow_g_s': 0.73241},
]

# Convert pellet volumes and surface areas to SI units (m³, m²) and mass flow to kg/s
for pellet in pellet_data:
    pellet['volume_m3'] = pellet['volume_cm3'] * 1e-6
    pellet['surface_area_m2'] = pellet['surface_area_cm2'] * 1e-4
    pellet['mass_flow_kg_s'] = pellet['mass_flow_g_s'] * 1e-3

def calculate_sauter_mean_diameter(pellets):
    total_mass_flow = sum(p['mass_flow_kg_s'] for p in pellets)
    # Unweighted sums:
    vol_weighted = sum(p['volume_m3'] for p in pellets)
    surf_weighted = sum(p['surface_area_m2'] for p in pellets)

    # Weighted sums (commented out as requested)
    # vol_weighted = sum(p['volume_m3'] * (p['mass_flow_kg_s'] / total_mass_flow) for p in pellets)
    # surf_weighted = sum(p['surface_area_m2'] * (p['mass_flow_kg_s'] / total_mass_flow) for p in pellets)

    d_p = 6 * vol_weighted / surf_weighted
    return d_p

# === Ergun Equation ===
def ergun_pressure_drop(mu, rho, epsilon, dp, L_bed, v):
    term1 = (150 * mu * (1 - epsilon)**2) / (dp**2 * epsilon**3) * L_bed * v
    term2 = (1.75 * rho * (1 - epsilon)) / (dp * epsilon**3) * L_bed * v**2
    return term1 + term2

# === Parsing simulation log ===
def parse_trn_file(filepath):
    mesh_cases = []
    with open(filepath, 'r') as file:
        lines = file.readlines()

    current_case = {}
    for line in lines:
        match_case = re.search(
            r'Running mesh study for:\s*(\S+)\s+at mass flow rate\s+([0-9.eE+-]+)',
            line
        )
        if match_case:
            if current_case:
                mesh_cases.append(current_case)
                current_case = {}
            current_case['mesh_case'] = match_case.group(1)
            current_case['mass_flow'] = float(match_case.group(2))

        match_cells = re.search(r'(\d+)\s+tetrahedral cells', line)
        if match_cells:
            current_case['cells'] = int(match_cells.group(1))

        match_pressure = re.search(
            r'Pressure drop computed:\s*\[\{\s*\'pressure_drop\'\s*:\s*\[\s*([0-9.eE+-]+),\s*0\s*\]\s*\}\]',
            line
        )
        if match_pressure:
            current_case['pressure_drop'] = float(match_pressure.group(1))

    if current_case:
        mesh_cases.append(current_case)

    valid_cases = [case for case in mesh_cases if all(k in case for k in ['mesh_case', 'cells', 'mass_flow', 'pressure_drop'])]
    print(f"✅ Parsed {len(valid_cases)} valid cases from {os.path.basename(filepath)}")
    return valid_cases

def group_by_mesh_case(data):
    grouped = defaultdict(list)
    for entry in data:
        grouped[entry['mesh_case']].append(entry)
    return grouped

def massflow_to_NmLmin(mass_flow_kg_s, density=DENSITY_Nitrogen, temp_C=20.0):
    """Convert mass flow (kg/s) to normalized mL/min (NmL/min)."""
    return (mass_flow_kg_s * 273.15 / ((temp_C + 273.15) * density)) * 60 * 1e6

# === Experimental data provided by user ===
# Columns: Volumetric Flow (NmL/min), Pressure Drop (mbar)
experimental_data = [
    (0, 0),
    (600, 0.425),
    (1000, 0.725),
    (2000, 1.575),
    (5000, 5.3),
    (10000, 16.375),
    (20000, 58.4),
    (30000, 116.125),
]

def plot_pressure_vs_volumetric_flow(grouped_data, output_dir, trn_filename, dp_sauter):
    if not grouped_data:
        print("⚠ No data to plot.")
        return

    for mesh_case, entries in grouped_data.items():
        entries.sort(key=lambda x: x['mass_flow'])
        vol_flows = [massflow_to_NmLmin(e['mass_flow']) for e in entries]
        pressures_pa = [e['pressure_drop'] for e in entries]

        # Calculate Ergun predicted pressure drop for each mass flow rate
        pressures_ergun_pa = []
        for e in entries:
            mfr = e['mass_flow']  # kg/s
            Q = mfr / DENSITY_Nitrogen  # m³/s volumetric flow
            v = Q / A_CROSS       # m/s superficial velocity
            delta_p = ergun_pressure_drop(MU_Nitrogen, DENSITY_Nitrogen, EPSILON, dp_sauter, L_BED, v)
            pressures_ergun_pa.append(delta_p)

        # Prepare experimental data converted to Pa and normalized flow rates
        exp_vol_flows = [pt[0] for pt in experimental_data]  # NmL/min
        exp_pressures_pa = [p * 100 for _, p in experimental_data]  # mbar to Pa

        fig, ax1 = plt.subplots(figsize=(10, 6))

        # Plot simulation data with blue circles and connecting lines
        ax1.plot(vol_flows, pressures_pa, marker='o', linestyle='-', color='blue',
                 markersize=7, linewidth=2, label='Simulation')

        # Plot experimental data as red squares with connecting line
        ax1.plot(exp_vol_flows, exp_pressures_pa, marker='s', linestyle='-',
                 color='red', markersize=8, linewidth=2, label='Experimental')

        # Plot Ergun prediction with green dashed line and circle markers
        ax1.plot(vol_flows, pressures_ergun_pa, linestyle='--', marker='o',
                 color='green', markersize=6, linewidth=2, label='Ergun Prediction')

        ax1.set_xlabel("Volumetric Flow Rate (NmL/min)", fontsize=14)
        ax1.set_ylabel("Pressure Drop (Pa)", fontsize=14)
        ax1.tick_params(axis='both', which='major', labelsize=12)
        ax1.grid(True, linestyle='--', alpha=0.6)

        # Secondary y-axis (mbar)
        ax2 = ax1.twinx()
        y1_min, y1_max = ax1.get_ylim()
        ax2.set_ylim(y1_min / 100, y1_max / 100)
        ax2.set_ylabel("Pressure Drop (mbar)", fontsize=14)
        ax2.tick_params(axis='both', which='major', labelsize=12)

        # Title with mesh case and particle diameter
        plt.title(f"Pressure Drop vs Volumetric Flow Rate\n"
                  f"Mesh Case = {mesh_case}, Sauter Diameter = {dp_sauter*1000:.3f} mm",
                  fontsize=16)

        # Legend with larger font
        ax1.legend(fontsize=12, loc='upper left', frameon=True)

        plt.tight_layout()

        # Save figure
        fig_name = f"{os.path.splitext(trn_filename)[0]}_{mesh_case}_pressure_vs_volflow.png"
        fig_path = os.path.join(output_dir, fig_name)
        plt.savefig(fig_path, dpi=600)
        print(f"💾 Saved figure: {fig_path}")
        plt.close()

def write_summary_file(grouped_data, output_dir, trn_filename, dp_sauter):
    summary_path = os.path.join(output_dir, f"{os.path.splitext(trn_filename)[0]}_summary.txt")
    with open(summary_path, 'w', encoding='utf-8') as f:
        # Header
        f.write("Summary Report: Pressure Drop Analysis in Fixed Bed Reactor\n")
        f.write("="*80 + "\n\n")

        # Reactor Geometry Section
        f.write("1. Reactor Geometry:\n")
        f.write("-" * 80 + "\n")
        f.write(f"Bed Length (L)                  : {L_BED:.4f} m\n")
        f.write(f"Inner Radius (r_inner)          : {R_INNER:.5f} m\n")
        f.write(f"Outer Radius (r_outer)          : {R_OUTER:.5f} m\n")
        f.write(f"Cross-sectional Flow Area (A)   : {A_CROSS:.6e} m²\n\n")

        # Pellet Data Section
        f.write("2. Pellet Properties and Sauter Mean Diameter:\n")
        f.write("-" * 80 + "\n")
        f.write(f"{'Length (mm)':>12} | {'Volume (cm³)':>12} | {'Surface Area (cm²)':>18} | {'Mass Flow Rate (g/s)':>22}\n")
        f.write("-" * 80 + "\n")
        for pellet in pellet_data:
            f.write(f"{pellet['length_mm']:12d} | "
                    f"{pellet['volume_cm3']:12.5f} | "
                    f"{pellet['surface_area_cm2']:18.5f} | "
                    f"{pellet['mass_flow_g_s']:22.5f}\n")
        f.write("-" * 80 + "\n")
        f.write(f"Sauter Mean Diameter (d_p) calculated as unweighted volume-surface area mean:\n")
        f.write(f"  d_p = 6 * (Σ volume_i) / (Σ surface_area_i)\n")
        f.write(f"  Computed d_p = {dp_sauter:.6e} m ({dp_sauter*1000:.3f} mm)\n\n")

        f.write(f"  Computed d_p = {dp_sauter:.6e} m ({dp_sauter*1000:.3f} mm)\n\n")

        # Simulation and Ergun Results Section
        f.write("3. Simulation Results vs. Ergun Equation Predictions:\n")
        f.write("-" * 80 + "\n")
        f.write(f"{'Mesh Case':<15} | {'Vol. Flow Rate (NmL/min)':>25} | {'Sim Pressure Drop (Pa)':>22} | {'Ergun Predicted (Pa)':>22}\n")
        f.write("-" * 80 + "\n")
        for mesh_case, entries in grouped_data.items():
            for e in sorted(entries, key=lambda x: x['mass_flow']):
                vol_flow = massflow_to_NmLmin(e['mass_flow'])
                Q = e['mass_flow'] / DENSITY_Nitrogen
                v = Q / A_CROSS
                p_ergun = ergun_pressure_drop(MU_Nitrogen, DENSITY_Nitrogen, EPSILON, dp_sauter, L_BED, v)

                f.write(f"{mesh_case:<15} | "
                        f"{vol_flow:25.3f} | "
                        f"{e['pressure_drop']:22.4f} | "
                        f"{p_ergun:22.4f}\n")
        f.write("-" * 80 + "\n\n")

        # Experimental Data Section
        f.write("4. Experimental Data:\n")
        f.write("-" * 40 + "\n")
        f.write(f"{'Vol. Flow Rate (NmL/min)':>25} | {'Pressure Drop (Pa)':>20}\n")
        f.write("-" * 40 + "\n")
        for vol, pres_mbar in experimental_data:
            pres_pa = pres_mbar * 100
            f.write(f"{vol:25d} | {pres_pa:20.2f}\n")
        f.write("-" * 40 + "\n\n")

        # Notes and Explanation
        f.write("5. Notes and Explanation:\n")
        f.write("-" * 80 + "\n")
        f.write(" - Pressure drops include simulation results, experimental measurements, and Ergun equation predictions.\n")
        f.write(" - Ergun equation parameters:\n")
        f.write(f"    Dynamic viscosity (μ) = {MU_Nitrogen:.2e} Pa.s\n")
        f.write(f"    Fluid density (ρ) = {DENSITY_Nitrogen:.4f} kg/m³\n")
        f.write(f"    Bed porosity (ε) = {EPSILON:.4f} (assumed/estimated)\n")
        f.write(f"    Bed length (L) = {L_BED:.4f} m\n")
        f.write(f"    Particle diameter (d_p) = {dp_sauter:.6e} m\n")
        f.write(" - Sauter mean diameter is volume to surface area weighted mean based on pellet mass flow distribution,\n")
        f.write("   providing a representative particle diameter for the mixed-size bed.\n")
        f.write(" - Cross-sectional flow area accounts for the annular geometry of the fixed bed reactor.\n")
        f.write(" - All volumetric flow rates are normalized to standard conditions (20°C, 1 atm) as NmL/min.\n")
        f.write(" - Experimental data were provided for validation of the simulation and analytical predictions.\n")

    print(f"💾 Summary written to: {summary_path}")


# === Main execution ===
if __name__ == "__main__":
    trn_dir = os.path.dirname(os.path.abspath(__file__))
    trn_file = "terminal_output_log.txt"
    trn_path = os.path.join(trn_dir, trn_file)

    if not os.path.exists(trn_path):
        print(f"[!] {trn_file} not found in {trn_dir}")
    else:
        print(f"\n📂 Processing {trn_file}...")
        parsed_data = parse_trn_file(trn_path)
        if not parsed_data:
            print("⚠ No valid data found in file — check your patterns or log format.")
        else:
            grouped_data = group_by_mesh_case(parsed_data)
            # Calculate Sauter mean diameter from pellet data
            dp_sauter = calculate_sauter_mean_diameter(pellet_data)
            print(f"Sauter mean diameter: {dp_sauter*1000:.3f} mm")

            plot_pressure_vs_volumetric_flow(grouped_data, trn_dir, trn_file, dp_sauter)
            write_summary_file(grouped_data, trn_dir, trn_file, dp_sauter)
            print("✅ Analysis complete.")
