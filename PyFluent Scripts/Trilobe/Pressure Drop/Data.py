import os
import re
import matplotlib.pyplot as plt
from collections import defaultdict

# === CONSTANTS ===
DENSITY = 1.1508  # kg/m³ at 20°C

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

def massflow_to_NmLmin(mass_flow_kg_s, density=1.1508, temp_C=20.0):
    """Convert mass flow (kg/s) to normalized mL/min (NmL/min)."""
    return (mass_flow_kg_s * 273.15 / ((temp_C + 273.15) * density)) * 60 * 1e6

def plot_pressure_vs_volumetric_flow(grouped_data, output_dir, trn_filename):
    if not grouped_data:
        print("⚠ No data to plot.")
        return

    for mesh_case, entries in grouped_data.items():
        entries.sort(key=lambda x: x['mass_flow'])
        vol_flows = [massflow_to_NmLmin(e['mass_flow']) for e in entries]
        pressures_pa = [e['pressure_drop'] for e in entries]

        fig, ax1 = plt.subplots(figsize=(10, 6))

        # Left y-axis (Pa)
        ax1.plot(vol_flows, pressures_pa, marker='o', linestyle='-')
        ax1.set_xlabel("Volumetric Flow Rate (NmL/min)")
        ax1.set_ylabel("Pressure Drop (Pa)", color='black')
        ax1.tick_params(axis='y', labelcolor='black')

        # Right y-axis (mbar), same data but converted
        ax2 = ax1.twinx()
        pressures_mbar = [p / 100 for p in pressures_pa]
        ax2.set_ylabel("Pressure Drop (mbar)", color='black')
        ax2.tick_params(axis='y', labelcolor='black')

        # Sync the y-limits so right axis matches left axis scaled by 1/100 (Pa to mbar)
        y1_min, y1_max = ax1.get_ylim()
        ax2.set_ylim(y1_min / 100, y1_max / 100)

        # Title and grid
        plt.title(f"Pressure Drop vs Volumetric Flow Rate\nMesh Case = {mesh_case}")
        fig.tight_layout()
        ax1.grid(True)

        # Save figure
        fig_name = f"{os.path.splitext(trn_filename)[0]}_{mesh_case}_pressure_vs_volflow.png"
        fig_path = os.path.join(output_dir, fig_name)
        plt.savefig(fig_path, dpi=600)
        print(f"💾 Saved figure: {fig_path}")
        plt.close()


def write_summary_file(grouped_data, output_dir, trn_filename):
    summary_path = os.path.join(output_dir, f"{os.path.splitext(trn_filename)[0]}_summary.txt")
    with open(summary_path, 'w') as f:
        f.write("Summary of Pressure Drop vs Volumetric Flow Rate\n")
        f.write("=" * 60 + "\n\n")
        if not grouped_data:
            f.write("No matching data found.\n")
        else:
            for mesh_case, entries in grouped_data.items():
                f.write(f"Mesh Case = {mesh_case}\n")
                f.write("-" * 70 + "\n")
                f.write(f"| {'Vol. Flow Rate (NmL/min)':^28} | {'Pressure Drop (Pa)':^18} |\n")
                f.write("-" * 70 + "\n")
                for e in sorted(entries, key=lambda x: x['mass_flow']):
                    f.write(f"| {massflow_to_NmLmin(e['mass_flow']):^28.3f} | {e['pressure_drop']:^18.4f} |\n")
                f.write("-" * 70 + "\n\n")
    print(f"💾 Summary written to: {summary_path}")

# ===== Run script =====
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
        grouped_data = group_by_mesh_case(parsed_data)
        plot_pressure_vs_volumetric_flow(grouped_data, trn_dir, trn_file)
        write_summary_file(grouped_data, trn_dir, trn_file)
