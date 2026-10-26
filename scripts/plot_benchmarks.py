import os
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

results_dir = "results"
scale_factors = [1, 2, 4, 8]

files = {
    1: os.path.join(results_dir, "pt_sf=1_full_combined_sf1.txt"),
    2: os.path.join(results_dir, "pt_sf=2_full_combined_sf2.txt"),
    4: os.path.join(results_dir, "pt_sf=4_full_combined_sf4.txt"),
    8: os.path.join(results_dir, "pt_sf=8_full_combined_sf8.txt"),
}

data = {}
for sf, path in files.items():
    if not os.path.exists(path):
        continue
    query_vals = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.lower().startswith("total"):
                continue
            try:
                query_vals.append(float(line))
            except ValueError:
                continue
    data[sf] = {q_idx + 1: val for q_idx, val in enumerate(query_vals[:99])}

df = pd.DataFrame(data)
df.index.name = "Query"
df.columns = [f"SF{col}" for col in df.columns]

# Compute Multipliers (Ratio of Growth)
# Theoretical linear scaling is 2.0x when data doubles
df["Ratio_SF2_SF1"] = df["SF2"] / df["SF1"].replace(0, np.nan)
df["Ratio_SF4_SF2"] = df["SF4"] / df["SF2"].replace(0, np.nan)
df["Ratio_SF8_SF4"] = df["SF8"] / df["SF4"].replace(0, np.nan)
df["Total_Growth_SF8_SF1"] = df["SF8"] / df["SF1"].replace(0, np.nan)

# Absolute difference in seconds from SF1 to SF8
df["Absolute_Diff_SF8_SF1"] = df["SF8"] - df["SF1"]

print("\n" + "="*80)
print("TOP 10 QUERIES WITH HIGHEST MULTIPLIER GROWTH (SF1 -> SF8, Ideal = 8.0x)")
print("="*80)
top_relative = df.sort_values(by="Total_Growth_SF8_SF1", ascending=False)[
    ["SF1", "SF2", "SF4", "SF8", "Total_Growth_SF8_SF1"]
].head(10)
print(top_relative.to_string(formatters={
    "SF1": "{:.3f}s".format,
    "SF2": "{:.3f}s".format,
    "SF4": "{:.3f}s".format,
    "SF8": "{:.3f}s".format,
    "Total_Growth_SF8_SF1": "{:.1f}x".format
}))

print("\n" + "="*80)
print("TOP 10 QUERIES WITH HIGHEST ABSOLUTE TIME SPIKE (Seconds Added on SF8 vs SF1)")
print("="*80)
top_absolute = df.sort_values(by="Absolute_Diff_SF8_SF1", ascending=False)[
    ["SF1", "SF4", "SF8", "Absolute_Diff_SF8_SF1"]
].head(10)
print(top_absolute.to_string(formatters={
    "SF1": "{:.2f}s".format,
    "SF4": "{:.2f}s".format,
    "SF8": "{:.2f}s".format,
    "Absolute_Diff_SF8_SF1": "+{:.2f}s".format
}))

# Save complete metrics table to CSV for report appendix
metrics_csv = os.path.join(results_dir, "scaling_metrics_summary.csv")
df.to_csv(metrics_csv)
print(f"\nSaved raw analytical metrics to: {metrics_csv}")

# -------------------------------------------------------------
# PLOT 1: Top 15 Bottleneck Outliers (Multiplier Jump from SF1 -> SF8)
# -------------------------------------------------------------
plt.figure(figsize=(10, 6))
top_15_ratio = df.sort_values(by="Total_Growth_SF8_SF1", ascending=True).tail(15)
bars = plt.barh([f"Query {q}" for q in top_15_ratio.index], top_15_ratio["Total_Growth_SF8_SF1"], color="#C44E52")
plt.axvline(x=8.0, color="black", linestyle="--", linewidth=1.5, label="Linear Baseline (8.0x)")
plt.xlabel("Growth Factor Multiplier (SF8 Time / SF1 Time)")
plt.title("Top 15 Most Severe Query Degradations (SF1 -> SF8)")
plt.grid(axis="x", linestyle="--", alpha=0.7)
plt.legend()

for bar in bars:
    w = bar.get_width()
    plt.text(w + 1, bar.get_y() + bar.get_height()/2.0, f"{w:.1f}x", va="center", ha="left", fontsize=9)

plt.tight_layout()
p1 = os.path.join(results_dir, "top_15_scaling_degradations.png")
plt.savefig(p1, dpi=300)
plt.close()
print(f"Saved: {p1}")

# -------------------------------------------------------------
# PLOT 2: Step-by-Step Step-Doubling Growth Heatmap / Bar Distribution
# -------------------------------------------------------------
fig, ax = plt.subplots(figsize=(18, 7))
queries = df.index
bar_width = 0.28
x = np.arange(len(queries))

r1 = ax.bar(x - bar_width, df["Ratio_SF2_SF1"], width=bar_width, label="SF1 -> SF2 (Ideal 2x)", color="#4C72B0")
r2 = ax.bar(x, df["Ratio_SF4_SF2"], width=bar_width, label="SF2 -> SF4 (Ideal 2x)", color="#55A868")
r3 = ax.bar(x + bar_width, df["Ratio_SF8_SF4"], width=bar_width, label="SF4 -> SF8 (Ideal 2x)", color="#E1812C")

ax.axhline(y=2.0, color="red", linestyle="--", linewidth=1.2, label="Linear Doubling (2.0x)")
ax.set_ylabel("Execution Time Multiplier (Ratio)")
ax.set_xlabel("TPC-DS Query Number")
ax.set_title("Step-by-Step Scaling Multipliers Across All 99 Queries (Threshold Spike Detection)")
ax.set_xticks(x[::2])  # Tick every 2nd query
ax.set_xticklabels(queries[::2], fontsize=8, rotation=90)
ax.set_ylim(0, max(25, min(df[["Ratio_SF2_SF1", "Ratio_SF4_SF2", "Ratio_SF8_SF4"]].max().max(), 60)))
ax.grid(axis="y", linestyle="--", alpha=0.5)
ax.legend()

plt.tight_layout()
p2 = os.path.join(results_dir, "step_scaling_ratios_all_queries.png")
plt.savefig(p2, dpi=300)
plt.close()
print(f"Saved: {p2}")

# -------------------------------------------------------------
# PLOT 3: Absolute Time Contributors on SF8
# -------------------------------------------------------------
plt.figure(figsize=(10, 6))
top_15_abs = df.sort_values(by="SF8", ascending=True).tail(15)
bars = plt.barh([f"Query {q}" for q in top_15_abs.index], top_15_abs["SF8"], color="#8172B3")
plt.xlabel("Execution Time on SF8 (seconds)")
plt.title("Top 15 Absolute Heaviest Queries on Scale Factor 8")
plt.grid(axis="x", linestyle="--", alpha=0.7)

for bar in bars:
    w = bar.get_width()
    plt.text(w + (top_15_abs["SF8"].max() * 0.01), bar.get_y() + bar.get_height()/2.0, f"{w:.1f}s", va="center", ha="left", fontsize=9)

plt.tight_layout()
p3 = os.path.join(results_dir, "top_15_heaviest_sf8.png")
plt.savefig(p3, dpi=300)
plt.close()
print(f"Saved: {p3}")
