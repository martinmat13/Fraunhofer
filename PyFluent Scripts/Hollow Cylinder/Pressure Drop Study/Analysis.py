import numpy as np
import matplotlib.pyplot as plt
import pandas as pd

# === Data from image ===
data = {
    "V_NmL_min": [20, 250, 1000],
    "u_in_m_per_s": [0.0019, 0.0241, 0.0963],
    "mass_flow_kg_per_s": [4.11685e-7, 5.14607e-6, 2.05843e-5],
    "dp_exp_Pa": [0.5, 2.5, 17.5],
    "dp_sim_Pa": [0.076, 0.962, 4.4],
    "dp_ana_Pa": [0.041339, 0.560797, 2.817815]
}

# Create DataFrame
df = pd.DataFrame(data)

# === Relative Error Functions ===
def relative_error(true, predicted):
    return np.abs((true - predicted) / true) * 100

df["err_sim_vs_exp_%"] = relative_error(df["dp_exp_Pa"], df["dp_sim_Pa"])
df["err_ana_vs_exp_%"] = relative_error(df["dp_exp_Pa"], df["dp_ana_Pa"])

# === Print comparison summary ===
print("\n==== Pressure Drop Comparison Table ====")
print(df[["V_NmL_min", "dp_exp_Pa", "dp_sim_Pa", "dp_ana_Pa", "err_sim_vs_exp_%", "err_ana_vs_exp_%"]])

# === Plotting ===
plt.figure(figsize=(10, 6))
plt.plot(df["V_NmL_min"], df["dp_exp_Pa"], 'o-', label="Experimental", linewidth=2)
plt.plot(df["V_NmL_min"], df["dp_sim_Pa"], 's--', label="Simulation", linewidth=2)
plt.plot(df["V_NmL_min"], df["dp_ana_Pa"], 'd-.', label="Analytical using Ergun Equation", linewidth=2)
plt.xlabel("Volumetric Flow Rate (NmL/min)")
plt.ylabel("Pressure Drop (Pa)")
plt.title("Pressure Drop Comparison")
plt.grid(True)
plt.legend()
plt.tight_layout()
plt.show()

# === Error Plot ===
plt.figure(figsize=(10, 5))
plt.plot(df["V_NmL_min"], df["err_sim_vs_exp_%"], 's--', label="Simulation vs Experimental", linewidth=2)
plt.plot(df["V_NmL_min"], df["err_ana_vs_exp_%"], 'd-.', label="Analytical vs Experimental", linewidth=2)
plt.xlabel("Volumetric Flow Rate (NmL/min)")
plt.ylabel("Relative Error (%)")
plt.title("Relative Error in Pressure Drop Estimates")
plt.grid(True)
plt.legend()
plt.tight_layout()
plt.show()
