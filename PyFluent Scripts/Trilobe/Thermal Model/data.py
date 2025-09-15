import os
import glob
import pandas as pd
import matplotlib.pyplot as plt

# Root folder where all massflow_* folders are stored
ROOT_DIR = r"Y:\Projekte\02_Aktuell\ANSYS_Rocky\Fixed Bed Project\Case Files\Case_3_ParticleBed75mm_Trilobe_Pellet\Simulation\Thermal Modelling\Double Precision"
MASTER_CSV = "master_results.csv"

all_data = []

# Loop through each massflow folder
for massflow_dir in glob.glob(os.path.join(ROOT_DIR, "massflow_*")):
    massflow_str = os.path.basename(massflow_dir).replace("massflow_", "")
    # Remove '_kgps' if present
    massflow_str = massflow_str.replace("_kgps", "")
    massflow_float = float(massflow_str)  # for legend in scientific notation
    print(f"\n🔍 Checking massflow: {massflow_dir}")

    # Find timestamped folders
    subfolders = glob.glob(os.path.join(massflow_dir, "fluentMsh9_*"))
    if not subfolders:
        print("  ⚠️ No timestamped subfolders found")
        continue

    latest_folder = max(subfolders, key=os.path.getmtime)
    print(f"  ✔ Using latest folder: {latest_folder}")

    # File paths
    temp_file = os.path.join(latest_folder, "axial_temperature_profile.csv")
    dens_file = os.path.join(latest_folder, "density_data.csv")
    flux_file = os.path.join(latest_folder, "iso_clip_heat_flux_profile.csv")

    # --- Temperature data ---
    if os.path.exists(temp_file):
        df_temp = pd.read_csv(temp_file)
        df_temp = df_temp.melt(id_vars=[df_temp.columns[0]], var_name="Metric", value_name="Value")
        df_temp = df_temp.rename(columns={df_temp.columns[0]: "Axial Length (m)"})
        df_temp["Massflow"] = massflow_float
        df_temp["Type"] = "Temperature"
        all_data.append(df_temp)
        print(f"    ✔ Loaded {temp_file}")

    # --- Density data ---
    if os.path.exists(dens_file):
        df_dens = pd.read_csv(dens_file)
        df_dens = df_dens.melt(id_vars=[df_dens.columns[0]], var_name="Metric", value_name="Value")
        df_dens = df_dens.rename(columns={df_dens.columns[0]: "Axial Length (m)"})
        df_dens["Massflow"] = massflow_float
        df_dens["Type"] = "Density"
        all_data.append(df_dens)
        print(f"    ✔ Loaded {dens_file}")

    # --- Heat flux data ---
    if os.path.exists(flux_file):
        df_flux = pd.read_csv(flux_file)
        df_flux = df_flux[["Z_mid_m", "HeatFlux_W_clipped"]]
        df_flux = df_flux.rename(columns={
            "Z_mid_m": "Axial Length (m)",
            "HeatFlux_W_clipped": "Value"
        })
        df_flux["Massflow"] = massflow_float
        df_flux["Type"] = "Heat Flux"
        all_data.append(df_flux)
        print(f"    ✔ Loaded {flux_file}")

# Combine into one master dataframe
if all_data:
    master_df = pd.concat(all_data, ignore_index=True)
    master_df.to_csv(MASTER_CSV, index=False)
    print(f"\n✅ Master CSV saved: {MASTER_CSV}")
else:
    print("\n❌ No CSV data collected! Check folder structure or filenames.")
    exit()

# ----------------- Plotting -----------------
colors = plt.cm.tab10.colors  # consistent color cycle

def make_plot(data_type, ylabel, title, filename, logy=False, x_margin_ratio=0.02, y_margin_ratio=0.05):
    plt.figure(figsize=(8,6))
    x_min, x_max = float('inf'), float('-inf')
    y_min, y_max = float('inf'), float('-inf')

    for i, massflow in enumerate(sorted(master_df["Massflow"].unique())):
        subset = master_df[(master_df["Massflow"] == massflow) & (master_df["Type"] == data_type)]
        if not subset.empty:
            x = subset["Axial Length (m)"]
            y = subset["Value"]
            plt.plot(x, y, marker="o", linestyle='-', color=colors[i % len(colors)],
                     label=f"{massflow:.2e} kg/s")
            x_min, x_max = min(x_min, x.min()), max(x_max, x.max())
            y_min, y_max = min(y_min, y.min()), max(y_max, y.max())

    # Add setbacks/margins
    x_range = x_max - x_min
    y_range = y_max - y_min
    plt.xlim(x_min - x_margin_ratio*x_range, x_max + x_margin_ratio*x_range)
    if logy:
        plt.yscale("log")
        plt.ylim(max(y_min, 1e-12), y_max*1.05)
        # No ticklabel_format on log scale
    else:
        plt.ylim(y_min - y_margin_ratio*y_range, y_max + y_margin_ratio*y_range)
        plt.ticklabel_format(style='plain', axis='both')  # Only for linear axes

    plt.xlabel("Axial Length (m)")
    plt.ylabel(ylabel)
    plt.title(title)
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(filename, dpi=300)
    print(f"✅ Saved {filename}")



# Make the three plots
make_plot("Temperature", "Mass-weighted average Temperature (K)", "Axial Temperature Profiles", "temperature_profiles.png")
make_plot("Density", "Mass-weighted average Density (kg/m³)", "Axial Density Profiles", "density_profiles.png")
make_plot("Heat Flux", "Heat Flux Integral (W)", "Axial Heat Flux Profiles", "heatflux_profiles.png", logy=True)
