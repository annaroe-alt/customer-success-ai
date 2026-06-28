"""
Stage 5 — Quality Review
Evaluates each junior output against its tagged QS standards via Claude.
Produces pass/fail per standard plus a rewrite suggestion for failures.
Writes quality_reviews.json to outputs/.
"""
from models.schemas import AccountContext, JuniorOutput, QualityStandard, QualityReviewResult
from pipeline.utils import get_logger, call_claude, save_json, load_prompt

logger = get_logger("05_quality_review")


def _format_standards(standards: dict[str, QualityStandard], ids: list[str]) -> str:
    lines = []
    for sid in ids:
        if sid in standards:
            s = standards[sid]
            lines.append(f"  {s.standard_id} — {s.standard_name}: {s.description}")
    return "\n".join(lines)


def _build_account_snapshot(ctx: AccountContext) -> str:
    a = ctx.account
    call_line = (
        f"Last call ({ctx.call_note.call_date}): {ctx.call_note.summary}. "
        f"Blocker: {ctx.call_note.risk_or_blocker}. "
        f"Follow-up committed: {ctx.call_note.follow_up_items}."
        if ctx.call_note else "No recent call note."
    )
    return (
        f"{a.account_name} ({a.account_id}) | Renewal: {a.renewal_date} | "
        f"Health: {a.current_health_score} (trend: {a.product_usage_trend}) | "
        f"NPS: {a.nps_score}\n{call_line}"
    )


def review_output(
    output: JuniorOutput,
    ctx: AccountContext,
    standards: dict[str, QualityStandard],
) -> QualityReviewResult:
    try:
        template = load_prompt("quality_review")
        standards_block = _format_standards(standards, output.quality_standard_ids)
        prompt = template.format(
            account_snapshot=_build_account_snapshot(ctx),
            output_type=output.output_type,
            intended_action=output.intended_customer_action,
            draft_text=output.draft_text,
            standards_block=standards_block,
            standard_ids=", ".join(output.quality_standard_ids),
        )
        response = call_claude(prompt)
        return _parse_review_response(output, response)
    except Exception as e:
        logger.error(f"Quality review failed for {output.output_id}: {e}")
        return QualityReviewResult(
            output_id=output.output_id,
            account_id=output.account_id,
            output_type=output.output_type,
            standard_results={sid: {"passed": False, "reason": f"Error: {e}"} for sid in output.quality_standard_ids},
            overall_passed=False,
            rewrite_suggestion=f"Review could not be completed: {e}",
        )


def _parse_review_response(output: JuniorOutput, response: str) -> QualityReviewResult:
    """
    Expects Claude to respond with sections like:
      QS001: PASS — reason
      QS002: FAIL — reason
      ...
      REWRITE: <improved draft>
    """
    standard_results: dict[str, dict] = {}
    rewrite_lines: list[str] = []
    in_rewrite = False

    for line in response.splitlines():
        stripped = line.strip()
        if not stripped:
            if in_rewrite:
                rewrite_lines.append("")
            continue

        if stripped.upper().startswith("REWRITE:"):
            in_rewrite = True
            after = stripped.split(":", 1)[1].strip()
            if after:
                rewrite_lines.append(after)
            continue

        if in_rewrite:
            rewrite_lines.append(stripped)
            continue

        # Try to match "QSxxx: PASS/FAIL — reason"
        for sid in output.quality_standard_ids:
            if stripped.upper().startswith(sid.upper()):
                rest = stripped[len(sid):].lstrip(":").strip()
                passed = rest.upper().startswith("PASS")
                reason = rest.split("—", 1)[1].strip() if "—" in rest else rest
                standard_results[sid] = {"passed": passed, "reason": reason}
                break

    # Fill in any standards not parsed
    for sid in output.quality_standard_ids:
        if sid not in standard_results:
            standard_results[sid] = {"passed": False, "reason": "Not evaluated in response."}

    overall_passed = all(v["passed"] for v in standard_results.values())
    rewrite_suggestion = "\n".join(rewrite_lines).strip() or "No rewrite provided."

    return QualityReviewResult(
        output_id=output.output_id,
        account_id=output.account_id,
        output_type=output.output_type,
        standard_results=standard_results,
        overall_passed=overall_passed,
        rewrite_suggestion=rewrite_suggestion,
    )


def review_all_outputs(
    contexts: list[AccountContext],
    standards: dict[str, QualityStandard],
) -> list[QualityReviewResult]:
    results = []
    for ctx in contexts:
        for output in ctx.junior_outputs:
            logger.info(f"Reviewing {output.output_id} ({output.output_type}) for {ctx.account_id}...")
            result = review_output(output, ctx, standards)
            results.append(result)
            status = "PASSED" if result.overall_passed else "FAILED"
            logger.info(f"  {output.output_id}: {status}")

    serialised = [
        {
            "output_id": r.output_id,
            "account_id": r.account_id,
            "output_type": r.output_type,
            "overall_passed": r.overall_passed,
            "standard_results": r.standard_results,
            "rewrite_suggestion": r.rewrite_suggestion,
        }
        for r in results
    ]
    save_json(serialised, "quality_reviews.json")
    logger.info(f"Reviewed {len(results)} outputs. Saved quality_reviews.json.")
    return results
