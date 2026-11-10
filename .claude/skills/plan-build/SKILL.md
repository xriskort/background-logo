---
name: plan-build
description: >-
  Claude talks to Claude. Runs a job through two subagents: the planner reads
  the code and writes a plan (it never edits files), the builder writes the
  code from that plan, and the planner reviews the result. The work passes back
  and forth until the planner says DONE. Use when the user says "plan and
  build", "use the planner and builder", "/plan-build <task>", or asks for
  Claude to talk to Claude on a coding task.
---

# Plan and build

The task is: $ARGUMENTS (if empty, ask the user what job to do).

Subagents cannot call each other, so you (the main session) carry every message between them. Pass each output in full - do not summarize away file paths, steps or errors.

## Loop

1. **Plan.** Call the `planner` agent in PLAN mode with the task and any useful context from the conversation.
   - If the plan has open questions only the user can answer, ask the user, then call the planner again with the answers.
2. **Build.** Call the `builder` agent with the complete plan, word for word.
3. **Review.** Call the `planner` agent in REVIEW mode with the plan and the builder's full report.
   - Verdict `DONE` -> go to step 5.
   - Verdict `NEEDS WORK`, or the builder reported `PARTIAL` / `BLOCKED` -> step 4.
4. **Revise.** Call the `builder` again with the planner's "Next steps for the builder" (and, if the planner wrote a revised plan, that plan). Then go back to step 3.
5. **Finish.** Tell the user what was built, which files changed, which checks ran and their results, and anything left open.

## Limits

- Stop after 3 build/review rounds without `DONE` and ask the user how to proceed, showing the latest review.
- Commit and push only if the user asked for it.
