# Problem interview guide (20–25 minutes)

Rules: talk about their past, not your product. No pitching until the last
five minutes. Ask for specifics ("the last time…"), not opinions ("would you…").
Take notes in their words.

## Warm-up (2 min)
- What do you work on? How many people touch the backend?
- What's the stack — FastAPI? How is it deployed?

## The last painful bug (10 min)
1. Tell me about the last production bug you had to reproduce. What happened?
2. How did you find out about it? (user report, alert, logs, Sentry…)
3. What information did you have when you started? What was missing?
4. How did you reproduce it? Walk me through the steps and tools.
5. How long did that take? What was the slowest part?
6. Did you write a test for it afterwards? Why / why not?
7. Has a fixed bug ever come back? What happened?

## Current tools and spend (5 min)
8. What do you use today for errors / logs / tracing? What do you pay?
9. What do you like and dislike about it for *reproducing* (not detecting) bugs?
10. Have you tried tools that record traffic or generate tests (Keploy, GoReplay, VCR-style fixtures)? Why did/didn't they stick?

## Reaction (5 min — only now show the demo)
11. Show the 2-minute demo. "What, if anything, would this have changed in the bug you described?"
12. What would stop you from installing this? (privacy, security review, effort, cost…)
13. If this worked as shown, what would it be worth per month to your team? Who approves that?
14. Can I follow up when it's ready to try on your staging environment?

## Score after the call (fill in immediately)
| Field | Value |
|---|---|
| Recent painful repro described unprompted? | yes / no |
| Time lost on the last one | |
| Uses Sentry/Datadog/other | |
| Biggest blocker to adoption | |
| Price they named, and who pays | |
| Asked to try it on their own app? | yes / no |
| Quote worth remembering | |
