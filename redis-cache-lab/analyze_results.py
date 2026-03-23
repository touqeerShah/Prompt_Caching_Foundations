import pandas as pd

df = pd.read_csv("exact_cache_results.csv")

print("\nAll runs:")
print(df)

print("\nAverage by cache hit:")
print(df.groupby("cache_hit")[["model_ms", "total_ms", "cache_lookup_ms"]].mean().round(2))

print("\nAverage by use_cache:")
print(df.groupby("use_cache")[["model_ms", "total_ms"]].mean().round(2))