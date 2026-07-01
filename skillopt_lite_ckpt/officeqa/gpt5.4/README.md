# Best skill — gpt-5.4 (officeqa, SkillOpt loop 2026-06-21/22)

`skill.md` here is the **canonical best** produced by the 8-round loop
targeting `gpt-5.4`. Sourced from the loop's GOLDEN snapshot
(`workspaces/gpt-5.4/.skillopt/history/loop12_round0__GOLDEN__initial.md`,
md5 `7860f806ea4946f071012ddd78182f9e`, 14 lines).

> Note: this is **not** the same byte content as the live
> `skills/initial.md` or `workspaces/gpt-5.4/skill.md` on disk today —
> both of those have been modified by subsequent work. The file here is
> the exact best skill from that run.

## Eval numbers on the best skill (msra/shared, reasoning=medium)

| split | n   | hard   | soft   | n_429 |
|-------|----:|-------:|-------:|------:|
| val   | 49  | 0.5918 | 0.6293 | 0     |
| test  | 148 | 0.4527 | 0.4907 | 0     |

(Test eval dir: `workspaces/gpt-5.4/.skillopt/_eval_run/20260622_004159/`.)

## Loop outcome

8 rounds ran; the loop stopped early on `regression_streak ≥ 5`. Every
prescriptive patch the optimizer proposed scored ≤ baseline on the full
val split (49 items), so the rollback path kept the original baseline
as best. **Net improvement over baseline = 0.**

## Reference: best non-rejected candidate (round 3)

`round3_18line_variant.md` adds an `## Answering Discipline` block
requiring `<answer>VALUE</answer>` etc. Went FLAT on val (0.5918 ==
baseline) so was not adopted as best. On test it scored hard=0.4595 /
soft=0.4666 with 11/148 items rate-limited by TRAPI — within ~10pp 429
noise of baseline, no real signal.

## Takeaway

On gpt-5.4 + officeqa, the bare 14-line baseline is plausibly optimal:
every addition tried by the loop degraded performance on clean
(no-429) runs by 4–12pp. Opposite of the gpt-5.5 pattern documented in
`.github/copilot-instructions.md` where heavy prescription helps.
