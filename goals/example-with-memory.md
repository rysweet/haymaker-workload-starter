# Project Structure Analyzer

> **Memory-enabled goal.** This goal benefits from `enable_memory=true` (the default).
> On repeated runs the agent recalls previous analyses, tracks changes over time,
> and refines its recommendations based on what it learned before.

## Goal

Analyze the project structure of the current working directory. Identify code
organization patterns, dependency relationships, and potential improvements.
Produce a report summarizing findings and actionable suggestions.

## Constraints

- Read-only: do not modify any project files
- Focus on structure and organization, not individual code style
- Compare with previous analysis if memory is available

## Success Criteria

- All top-level directories and key files catalogued
- Dependency graph described (imports, config references)
- At least three actionable improvement suggestions provided
- Report written to `output/structure-report.md`
- If prior analysis exists in memory, include a "Changes Since Last Run" section
