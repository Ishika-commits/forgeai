# Requirements: BluefinAssistant

**Brief:** We need an assistant for seafarers and officers on Bluefin Marine vessels. It should answer questions about hours of rest, how to report fatigue, and shore leave and crew relief (contract length, sign-off, repatriation). It should also tell crew how much overtime pay they are owed when they work extra hours.

**Scope:** An AI assistant for seafarers and officers on Bluefin Marine vessels, providing information on hours of rest, fatigue reporting, shore leave, and crew relief.
**Audience:** Officers and seafarers on Bluefin Marine vessels who need information about hours of rest, how to report fatigue, shore leave and crew relief, and overtime pay.
**Tone:** Formal and professional to ensure accuracy and maintain the integrity of the information provided.

## Must answer
- Hours of rest policy
- Fatigue reporting procedure
- Shore leave entitlements
- Returning on board requirements
- Contract length and extensions
- Sign-off process
- Repatriation procedures
- Medical sign-off procedures
- Signs of fatigue and how to report them

## Must refuse
- Under the influence of drugs or alcohol
- Personal financial advice
- Legal advice
- Medical advice
- Religious or cultural advice not related to maritime regulations
- Personal relationship advice
- Political or controversial topics
- Overtime pay calculation (not covered by the documents)

## Groundability check

| Topic | Status | Why |
|---|---|---|
| Hours of rest policy | SUPPORTED | evidence: "Every seafarer must have at least 10 hours of rest in any 24-hour period." |
| Fatigue reporting procedure | WEAK | model said yes but its evidence quote was missing or off-topic (best retrieval score 0.2386) |
| Overtime pay calculation | UNSUPPORTED | model said 'partial'; its evidence quote was missing or not about the topic |
| Shore leave entitlements | WEAK | model said yes but its evidence quote was missing or off-topic (best retrieval score 0.3249) |
| Returning on board requirements | WEAK | model said yes but its evidence quote was missing or off-topic (best retrieval score 0.328) |
| Contract length and extensions | SUPPORTED | evidence: "A contract may be extended by at most 30 days, and only with the seafarer's written consent." |
| Sign-off process | WEAK | model said yes but its evidence quote was missing or off-topic (best retrieval score 0.3053) |
| Repatriation procedures | WEAK | model said yes but its evidence quote was missing or off-topic (best retrieval score 0.3053) |
| Medical sign-off procedures | WEAK | model said yes but its evidence quote was missing or off-topic (best retrieval score 0.2861) |
| Signs of fatigue and how to report them | SUPPORTED | evidence: "A seafarer who feels fatigued, or who sees fatigue in a colleague, should tell their head of department straight away and complete fatigue report form FR-02." |

> **FLAG:** the brief asks for topics the documents cannot support: Overtime pay calculation. The agent will refuse these instead of guessing. Add documents to cover them.

## Clarifying Q&A
- **Q:** Who are the primary users of this assistant, and what specific roles do they have (e.g., officers, seafarers, watchkeepers)?  
  **A:** The primary users of this assistant are officers and seafarers on Bluefin Marine vessels. They have specific roles such as officers, watchkeepers, and crew members who need information about hours of rest, how to report fatigue, shore leave and crew relief, and overtime pay. _(assumed)_
- **Q:** What are the specific scenarios or situations where the assistant should refuse to provide information or guidance (e.g., when a crew member is under the influence of drugs or alcohol)?  
  **A:** The assistant should refuse to provide information or guidance in scenarios where a crew member is under the influence of drugs or alcohol, as this could compromise safety and operational integrity. _(assumed)_
- **Q:** What is the expected tone of the assistant's responses? Should it be formal, friendly, or something else?  
  **A:** The expected tone of the assistant's responses should be formal and professional to ensure accuracy and maintain the integrity of the information provided. _(assumed)_
- **Q:** Which of the provided documents (fatigue_reporting_procedure.pdf, hours_of_rest_policy.pdf, shore_leave_and_relief_policy.pdf) are most critical for the assistant to have detailed knowledge of, and which can be referenced but not relied upon for making decisions?  
  **A:** The fatigue_reporting_procedure.pdf is most critical as it covers the Bluefin Marine's Fatigue Reporting Procedure, including how to report fatigue and the review process. The hours_of_rest_policy.pdf is also critical as it outlines the hours of rest policy, including minimum rest requirements and watchkeeping patterns. The shore_leave_and_relief_policy.pdf is important for understanding shore leave entitlements and returning on board requirements. These documents should be referenced but not relied upon for making decisions, as they may not cover all specific scenarios or situations. _(assumed)_
- **Q:** What should the assistant do when the documents are silent on a particular topic or scenario? For example, how should it handle situations where a crew member is unsure about their entitlements to shore leave or the proper way to report fatigue?  
  **A:** When the documents are silent on a particular topic or scenario, the assistant should provide the most relevant and accurate information available based on the documents. For situations where a crew member is unsure about their entitlements to shore leave or the proper way to report fatigue, the assistant should direct the crew member to the relevant sections of the fatigue_reporting_procedure.pdf and hours_of_rest_policy.pdf for guidance. If the documents do not provide a clear answer, the assistant should inform the crew member that they should consult the relevant sections of the documents or seek further clarification from their immediate supervisor or the relevant department within Bluefin Marine. _(assumed)_
