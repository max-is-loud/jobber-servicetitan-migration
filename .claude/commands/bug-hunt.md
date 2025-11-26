---
description: Analyze a specific bug using codebase tools, then delegate deep debugging to the bug-hunter subagent.
argument-hint: "[short-description and/or error log]"
allowed-tools: Read, Glob, Grep, Bash(ls:*), Bash(git status:*), Bash(git diff:*), Bash(find:*), Bash(head:*), Bash(tail:*)
model: inherit
---

The user has provided a description of the issue and/or an error log in the text below:

$ARGUMENTS

Your job is to:

1. **Parse and restate the bug**

   * Summarize the issue in your own words.
   * Identify the key symptoms (error messages, failing commands, unexpected behavior).
   * If anything critical is unclear, ask concise clarifying questions.

2. **Initial codebase analysis using available tools**

   * Use code-exploration tools such as **Glob**, **Grep**, **Read**, and safe **Bash** commands to:
     * Locate the modules, functions, or files most likely responsible.
     * Check recent changes (e.g. `git status`, `git diff HEAD`).
     * Identify relevant types, database access layers, or API clients.
   
   * Keep this phase focused on gathering context, *not* rewriting large sections of code.

3. **Prepare a concise handoff summary**

   * Write a short summary including:
     * Your restated bug and key error text.
     * Your best hypothesis about the root cause.
     * A bullet list of **key file paths and symbols** (functions, classes) that are likely involved.
     * Any especially relevant code snippets you found.

4. **Invoke the `bug-hunter` subagent for deep debugging**

   * After initial exploration, explicitly delegate to the **`bug-hunter`** subagent.
   * Provide the handoff summary, key file paths, and crucial snippets as context.
 
5. **Stay within bug-fixing scope**

   * Focus ONLY on understanding and resolving the concrete bug described in `$ARGUMENTS`.
   * Do **not** add new features, redesign architecture, or refactor unrelated code.
   * Keep all suggestions and edits as **minimal, localized changes** unless a broader change is clearly required.

**Your overall outcome:**

* Initial message: your restated bug and exploration plan.
* Then, after invoking `bug-hunter`, return with a clear proposal for a minimal fix and how to verify it.