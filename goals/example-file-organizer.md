# File Organization Agent

## Goal
Scan the current working directory for files, classify them by type
(code, docs, config, data, other), and produce a summary report.

## Constraints
- Read-only: do not move or delete any files
- Classify by file extension
- Output report to `output/file-report.md`

## Success Criteria
- All files in the directory scanned
- Each file classified into a category
- Markdown report generated with counts per category
