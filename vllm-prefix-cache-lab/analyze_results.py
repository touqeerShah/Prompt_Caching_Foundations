import pandas as pd

df = pd.read_csv("vllm_prefix_results.csv")

print("\nAll runs:")
print(df)

print("\nAverage by prompt kind:")
print(df.groupby("prompt_kind")[["estimated_prompt_tokens", "ttft_ms", "total_ms"]].mean().round(2))

print("\nCanonical runs only:")
print(df[df["prompt_kind"] == "canonical"][["label", "question", "ttft_ms", "total_ms"]])