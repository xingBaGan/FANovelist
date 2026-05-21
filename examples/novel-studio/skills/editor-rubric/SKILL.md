---
name: editor-rubric
description: JSON schema for executive editor chapter reviews
---

# Editor Review JSON

Write to `studio/reviews/chNN.json`. **JSON only.**

```json
{
  "chapter": "ch01",
  "verdict": "PASS",
  "scores": {
    "theme_alignment": 8,
    "premise_alignment": 9,
    "pacing": 7,
    "voice_consistency": 8,
    "prose_quality": 8
  },
  "continuity_issues": [],
  "pov_issues": [],
  "character_issues": [],
  "structure_issues": [],
  "required_revisions": [],
  "summary": "One paragraph for the human author."
}
```

## Verdict values

- `PASS` — human may run approve-chapter
- `REVISE` — Ghostwriter must address `required_revisions`
- `REJECT` — Showrunner must replan; cite whitepaper section

## required_revisions items

```json
{
  "location": "paragraph or line hint",
  "problem": "what is wrong",
  "fix": "concrete instruction"
}
```
