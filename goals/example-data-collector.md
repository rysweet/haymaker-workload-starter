# Data Collection Agent

## Goal
Collect system metrics (CPU, memory, disk usage) from the local machine
every 30 seconds and write them to a JSON log file.

## Constraints
- Use only Python standard library (psutil not required)
- Write output to `output/metrics.json`
- Append, do not overwrite previous entries
- Complete after collecting 10 samples

## Success Criteria
- 10 metric samples collected
- Output file contains valid JSON array
- Each sample includes timestamp, cpu_percent, memory_percent, disk_percent
