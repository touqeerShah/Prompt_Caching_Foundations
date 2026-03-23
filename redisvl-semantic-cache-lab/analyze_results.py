import pandas as pd

df = pd.read_csv("semantic_cache_results.csv")

print("\nAll runs:")
print(df)

print("\nHit rate:")
print(df["semantic_cache_hit"].mean())

print("\nAverage by hit:")
print(df.groupby("semantic_cache_hit")[["distance", "model_ms", "total_ms"]].mean().round(3))

print("\nDistances for hits:")
print(df[df["semantic_cache_hit"] == True][["label", "distance", "total_ms"]])