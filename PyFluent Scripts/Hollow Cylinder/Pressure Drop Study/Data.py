import os
import re
import matplotlib.pyplot as plt
from collections import defaultdict

def parse_trn_file(filepath):
    mesh_cases = []
    with open(filepath, 'r') as file:
        lines = file.readlines()

    current_case = {}
    for line in lines:
        match_case = re.search(r'Running mesh study for:\s*(\S+)', line)
        if match_case:
            if current_case:
                mesh_cases.append(current_case)
                current_case = {}
            current_case['mesh_case'] = match_case.group(1)

        match_cells = re.search(r'(\d+)\s+tetrahedral cells', line)
        if match_cells:
            current_case['cells'] = int(match_cells.group(1))

        match_flow = re.search(r'Mass flow rate set:\s*([0-9.eE+-]+)', line)
        if match_flow:
            current_case['mass_flow'] = float(match_flow.group(1))

        match_pressure = re.search(
            r'Pressure drop computed:\s*\[\{\s*\'pressure_drop\'\s*:\s*\[\s*([0-9.eE+-]+),\s*0\s*\]\s*\}\]',
            line
        )
        if match_pressure:
            current_case['pressure_drop'] = float(match_pressure.group(1))

    if current_case:
        mesh_cases.append(current_case)

    return [case for case in mesh_cases if all(k in case for k in ['mesh_case', 'cells', 'mass_flow', 'pressure_drop'])]

def group_by_mass_flow(data):
    grouped = defaultdict(list)
    for entry in data:
        grouped[entry['mass_flow']].append(entry)
    return grouped

def format_mass_flow(mf):
    return f"{mf:.2e}".replace('.', 'p').replace('+0', '').replace('+', '').replace('-', 'm')

def plot_grouped_results(grouped_data, output_dir, trn_filename):
    for mass_flow, entries in grouped_data.items():
        entries.sort(key=lambda x: x['cells'])
        cells_millions = [e['cells'] / 1e6 for e in entries]
        pressure = [e['pressure_drop'] for e in entries]
        labels = [e['mesh_case'] for e in entries]

        plt.figure(figsize=(10, 6))
        plt.plot(cells_millions, pressure, marker='o', linestyle='-')
        #for i, label in enumerate(labels):
           # plt.annotate(label, (cells_millions[i], pressure[i]), textcoords="offset points", xytext=(0, 10), ha='center')
        plt.title(f"Pressure Drop vs Number of Cells\nMass Flow Rate = {mass_flow:.2e} kg/s")
        plt.xlabel("Number of Cells (Millions)")
        plt.ylabel("Pressure Drop (Pa)")
        plt.grid(True)
        plt.tight_layout()

        # Save figure
        formatted_mf = format_mass_flow(mass_flow)
        fig_name = f"{os.path.splitext(trn_filename)[0]}_massflow_{formatted_mf}.png"
        fig_path = os.path.join(output_dir, fig_name)
        plt.savefig(fig_path, dpi=300)
        print(f"Saved figure: {fig_path}")
        plt.close()

def write_summary_file(grouped_data, output_dir, trn_filename):
    summary_path = os.path.join(output_dir, f"{os.path.splitext(trn_filename)[0]}_summary.txt")
    with open(summary_path, 'w') as f:
        f.write("Summary of Mesh Study Results\n")
        f.write("=" * 30 + "\n\n")

        for mass_flow, entries in grouped_data.items():
            f.write(f"Mass Flow Rate = {mass_flow:.5e} kg/s\n")
            f.write("-" * 60 + "\n")
            f.write(f"| {'Mesh Case':<18} | {'# Cells (Million)':^18} | {'Pressure Drop (Pa)':^18} |\n")
            f.write("-" * 60 + "\n")
            for e in entries:
                f.write(f"| {e['mesh_case']:<18} | {e['cells']/1e6:^18.3f} | {e['pressure_drop']:^18.4f} |\n")
            f.write("-" * 60 + "\n\n")

    print(f"Summary written to: {summary_path}")


# ===== Run script =====
if __name__ == "__main__":
    trn_dir = os.path.dirname(os.path.abspath(__file__))
    trn_files = [f for f in os.listdir(trn_dir) if f.endswith('.trn')]

    if not trn_files:
        print("[!] No .trn files found in the directory.")
    for trn_file in trn_files:
        print(f"\nProcessing {trn_file}...")
        full_path = os.path.join(trn_dir, trn_file)
        parsed_data = parse_trn_file(full_path)
        grouped_data = group_by_mass_flow(parsed_data)
        plot_grouped_results(grouped_data, trn_dir, trn_file)
        write_summary_file(grouped_data, trn_dir, trn_file)
