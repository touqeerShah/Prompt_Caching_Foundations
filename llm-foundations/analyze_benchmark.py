import pandas as pd

df = pd.read_csv("benchmark_results.csv")

print("\nAll rows:")
print(df[[
    "label",
    "use_retrieval",
    "total_tokens",
    "ttft_ms",
    "model_total_ms",
    "total_ms",
    "count_method",
]])

print("\nAverages by retrieval flag:")
print(
    df.groupby("use_retrieval")[["total_tokens", "ttft_ms", "model_total_ms", "total_ms"]]
    .mean()
    .round(2)
)

print("\nRepeated prompt comparison:")
print(df[df["label"].str.contains("repeat_same")][[
    "label", "total_tokens", "ttft_ms", "model_total_ms", "total_ms"
]])