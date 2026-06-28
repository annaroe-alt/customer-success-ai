import json
from dataclasses import dataclass, field, asdict
from typing import List, Dict

# Pricing per 1M tokens (USD) — matches Pricing Reference tab
PRICING = {
    "claude-haiku-4-5-20251001": {"input": 1.00, "output": 5.00},
    "claude-sonnet-4-6":         {"input": 3.00, "output": 15.00},
    "claude-opus-4-8":           {"input": 5.00, "output": 25.00},
    # OpenAI (simulated for embeddings / prioritization)
    "gpt-5-4-mini":              {"input": 0.75, "output": 4.50},
    "text-embedding-3-small":    {"input": 0.02, "output": 0.00},
}

BUDGET_ANNUAL = 50_000.00


@dataclass
class TokenRecord:
    stage: str
    model: str
    run_index: int
    input_tokens: int
    output_tokens: int
    input_cost: float
    output_cost: float
    total_cost: float


class TokenLogger:
    def __init__(self):
        self.records: List[TokenRecord] = []

    def log(self, stage: str, model: str, run_index: int,
            input_tokens: int, output_tokens: int) -> TokenRecord:
        p = PRICING.get(model, {"input": 1.00, "output": 5.00})
        input_cost  = input_tokens  / 1_000_000 * p["input"]
        output_cost = output_tokens / 1_000_000 * p["output"]
        r = TokenRecord(
            stage=stage, model=model, run_index=run_index,
            input_tokens=input_tokens, output_tokens=output_tokens,
            input_cost=input_cost, output_cost=output_cost,
            total_cost=input_cost + output_cost,
        )
        self.records.append(r)
        return r

    def summary(self) -> Dict:
        by_stage: Dict = {}
        for r in self.records:
            s = by_stage.setdefault(r.stage, {
                "model": r.model, "runs": 0,
                "total_input_tokens": 0, "total_output_tokens": 0,
                "total_cost": 0.0,
            })
            s["runs"]                += 1
            s["total_input_tokens"]  += r.input_tokens
            s["total_output_tokens"] += r.output_tokens
            s["total_cost"]          += r.total_cost
        return by_stage

    def print_summary(self):
        summary = self.summary()
        grand_total = sum(v["total_cost"] for v in summary.values())
        print("\n" + "="*70)
        print("TOKEN USAGE REPORT — Customer Success AI")
        print("="*70)
        fmt = "{:<35} {:>6}  {:>10}  {:>10}  {:>10}"
        print(fmt.format("Stage", "Runs", "Input Tok", "Output Tok", "Cost ($)"))
        print("-"*70)
        for stage, v in summary.items():
            print(fmt.format(
                stage[:35], v["runs"],
                f"{v['total_input_tokens']:,}",
                f"{v['total_output_tokens']:,}",
                f"${v['total_cost']:.4f}",
            ))
        print("-"*70)
        print(f"{'TOTAL':35}  {'':>6}  {'':>10}  {'':>10}  ${grand_total:.4f}")
        pct = grand_total / BUDGET_ANNUAL * 100
        print(f"\nSample run cost: ${grand_total:.4f}")
        print(f"Annual budget:   ${BUDGET_ANNUAL:,.2f}")
        print(f"(Per-run costs annualize to full-scale in the Token Math Sheet)")
        print("="*70 + "\n")

    def save(self, path="token_usage_report.json"):
        summary = self.summary()
        grand_total = sum(v["total_cost"] for v in summary.values())
        with open(path, "w") as f:
            json.dump({
                "sample_run_total_cost": grand_total,
                "annual_budget": BUDGET_ANNUAL,
                "summary_by_stage": summary,
                "records": [asdict(r) for r in self.records],
            }, f, indent=2)
        print(f"Token usage report saved to {path}")
