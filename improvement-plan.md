# Critics - Improvement Plan

1 parsing defect(s) across 1 job(s). 4 field(s) were consistent.

## Findings

### Staff Software Engineer (`4380826388`) - salary

- **Stored value:** $212,500.00 - $287,500.00
- **Evidence (from description):** > $205,600 - $257,000 CAD in Toronto, Ontario, Canada
- **Suggested fix:** The stored salary range ($212,500 - $287,500) does not match the ground truth. Source the salary from the description body under the 'Salary / Benefits' section, which states '$205,600 - $257,000 CAD in Toronto, Ontario, Canada'. Note the currency is CAD, and both the low and high ends differ from what was stored.
