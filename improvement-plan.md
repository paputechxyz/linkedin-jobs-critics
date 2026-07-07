# Critics - Improvement Plan

1 parsing defect(s) across 1 job(s). 4 field(s) were consistent.

## Findings

### Member of Technical Staff, Post-Training (`4259504707`) - salary

- **Stored value:** $225,000.00 - $550,000.00
- **Evidence (from description):** > 
- **Suggested fix:** The salary range '$225,000.00 - $550,000.00' does not appear anywhere in the full description body. The description only mentions stipends and benefits (e.g., '$75/£75 weekly lunch stipend', '$500 home office stipend'). This value likely originates from the LinkedIn page's rounded card band element, not the description text. If the card band is unavailable or unreliable, salary should be set to null since no salary information exists in the ground-truth description.
