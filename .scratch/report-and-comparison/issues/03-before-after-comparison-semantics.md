# Define honest before-and-after comparison semantics

Type: grilling
Status: resolved

Part of: [Report and Comparison](../map.md)

## Question

How should the product interpret and explain the original-versus-agent-updated comparison while preserving uncertainty?

Settle the user-visible comparison rules for the original site and the later agent-produced version, using identical assessment settings. The comparison must make clear:

- the overall score and each metric for each version, plus meaningful changes between them;
- the coverage and evidence differences between the two versions;
- any repeated barrier, failed goal, or incomplete assessment in either version;
- the evidence-backed proposed fix carried from the run evidence; and
- every inconsistent or inconclusive result, without hiding it or turning the demonstration into an unsupported general accessibility claim.

Define what the report should say when coverage, evidence, or metric values are insufficient or differ across versions, and decide what repeated-run protocol is needed for a meaningful comparison. Use the Journey and Evidence map's eventual evidence vocabulary as an input; do not invent browser facts or a second assessment model in this ticket.

## Answer

The comparison uses a developer-configured consistency level, separate from agent reasoning:

- Low: one assessment per version.
- Medium: two assessments per version.
- High: three assessments per version.

Low is the default. The same level and all other assessment settings apply to both the original site and the agent-updated site.

The comparison leads with the original score, updated score, score change, each metric before and after, and coverage before and after. It also keeps every individual run visible, alongside an average score and score range for each version. Inconclusive and agent-failed runs remain visible rather than being hidden from the comparison.

If some metrics improve while others worsen, the comparison says `mixed result` and shows both directions. It must show meaningful evidence differences, repeated barriers, failed goals, incomplete assessments, and evidence-backed proposed fixes without turning the result into an unsupported general accessibility claim.

The ticket is resolved.
