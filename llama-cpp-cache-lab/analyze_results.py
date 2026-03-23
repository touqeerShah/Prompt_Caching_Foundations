import pandas as pd

df = pd.read_csv("llama_cpp_cache_results.csv")

print("\nAll runs:")
print(df)

print("\nAverage by cache flag:")
print(df.groupby("use_cache")[["estimated_prompt_tokens", "ttft_ms", "total_ms"]].mean().round(2))

print("\nCache-enabled runs:")
print(df[df["use_cache"] == True][["label", "prompt_kind", "ttft_ms", "total_ms"]])