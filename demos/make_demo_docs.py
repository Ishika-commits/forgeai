"""Builds the demo PDFs from the text below. Run: python demos/make_demo_docs.py"""
import os

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

HERE = os.path.dirname(os.path.abspath(__file__))

DOCS = {
"crew_rest/docs/hours_of_rest_policy.pdf": """
# Bluefin Marine - Hours of Rest Policy (BM-HR-01, Rev 4)
## 1. Purpose
This policy makes sure every seafarer on a Bluefin Marine vessel gets enough rest to work safely, and that rest is recorded honestly. It applies to the Master, officers and ratings on all managed vessels.
## 2. Minimum hours of rest
Every seafarer must have at least 10 hours of rest in any 24-hour period. Every seafarer must have at least 77 hours of rest in any 7-day period.
## 3. Splitting rest
The hours of rest in any 24-hour period may be divided into no more than two periods. One of these periods must be at least 6 hours long. The interval between two consecutive periods of rest must not exceed 14 hours.
## 4. Watchkeeping
Navigating and engineering officers normally keep a 4-on, 8-off watch pattern. Any other pattern must be approved by the Master and shown on the table of shipboard working arrangements posted in the mess room.
## 5. Drills and musters
Musters, fire drills, lifeboat drills and drills required by law must be held in a way that disturbs rest periods as little as possible. A seafarer whose rest period is interrupted by a drill or a call-out must be given an adequate compensatory rest period as soon as possible.
## 6. Unmanned machinery space call-outs
An engineer on call for an unmanned machinery space who is called out during a rest period must receive compensatory rest equal to the time lost.
## 7. Records
Each seafarer records their own hours of rest daily on form HR-03. The head of department checks the records weekly. The Master signs the records at the end of each month, and the seafarer receives a signed copy. Records are kept on board for 3 years.
## 8. Non-conformities
If the records show a breach of the minimum hours, the head of department must report it to the Master within 24 hours. The Master records the cause and the corrective action and reports breaches to the office in the monthly report.
## 9. Emergencies
The Master may suspend the hours of rest schedule when it is needed for the immediate safety of the ship, persons on board or cargo, or to help other ships or persons in distress at sea. As soon as the situation is over, the Master must make sure that every seafarer who worked during a scheduled rest period gets an adequate period of rest.
""",
"crew_rest/docs/fatigue_reporting_procedure.pdf": """
# Bluefin Marine - Fatigue Reporting Procedure (BM-FR-02, Rev 2)
## 1. Why we report fatigue
Fatigue causes mistakes. Reporting it early is a safety action, not a complaint. Bluefin Marine operates a no-blame policy: no seafarer will be disciplined or lose pay for reporting that they or a colleague are fatigued.
## 2. Signs of fatigue
Common signs include difficulty concentrating, slow reactions, nodding off on watch, irritability, headaches and forgetting routine steps.
## 3. How to report
A seafarer who feels fatigued, or who sees fatigue in a colleague, should tell their head of department straight away and complete fatigue report form FR-02. The completed form goes to the Master within 24 hours.
## 4. Master's actions
The Master reviews each FR-02 and decides on immediate measures, such as a rest period, changing the watch, or adding a second person on the bridge. The Master must send a copy of every FR-02 to the Designated Person Ashore (DPA) within 48 hours of receiving it.
## 5. Standing down from watch
Officers use the Karolinska Sleepiness Scale (KSS), from 1 (extremely alert) to 9 (very sleepy, fighting sleep). Anyone who rates themselves at 7 or higher must not stand a navigational or engine-room watch alone until they have rested.
## 6. Anonymous reporting
A seafarer who does not want to report through the ship can report anonymously to the safety department by email at fatigue@bluefinmarine.example. Anonymous reports are investigated in the same way.
## 7. Review
The safety department reviews all fatigue reports every quarter and shares trends with vessels in the quarterly safety bulletin.
""",
"crew_rest/docs/shore_leave_and_relief_policy.pdf": """
# Bluefin Marine - Shore Leave and Crew Relief Policy (BM-CR-05, Rev 3)
## 1. Shore leave
Seafarers are entitled to shore leave when the ship is in port, subject to operational needs, port security rules and local immigration requirements. The Master decides who may go ashore and when.
## 2. Returning on board
Seafarers on shore leave must return on board at least 2 hours before the ship's scheduled departure time. Anyone who expects to be late must call the ship or the local agent immediately.
## 3. Contract length
The normal contract length is 4 months for officers and 6 months for ratings.
## 4. Extensions
A contract may be extended by at most 30 days, and only with the seafarer's written consent. Extensions beyond 30 days are not allowed.
## 5. Requesting sign-off
A seafarer who wants to sign off at the end of their contract must give at least 60 days notice to the Master, who passes it to the crewing department.
## 6. Repatriation
Repatriation at the end of the contract is at the company's cost, including travel to the seafarer's home airport and accommodation while waiting for a flight. If a seafarer asks to leave before the contract ends for personal reasons, repatriation costs may be recovered from them, except in cases of family emergency.
## 7. Medical sign-off
A seafarer who is declared unfit by a doctor in port will be signed off and repatriated at the company's cost, and keeps their sick pay entitlement under their employment agreement.
""",
"port_costs/docs/agency_terms.pdf": """
# Bluefin Marine - Standard Port Agency Terms (2026)
## 1. Agency fee
The agent's fee is USD 1,450 per port call, regardless of port or vessel size. The fee covers clearance, husbandry coordination and preparing the disbursement account.
## 2. Pilotage overtime
Pilotage carried out outside normal hours (0800 to 1700 local time) is charged with a 25% surcharge on the pilotage tariff.
## 3. Weekend and public holiday towage
Towage on Saturdays, Sundays and local public holidays is charged with a 50% surcharge on the towage tariff.
## 4. Advance payment
The owner pays 50% of the proforma disbursement account in advance, before the vessel's arrival. The agent may refuse to arrange services if the advance has not been received.
## 5. Balance
The balance is due within 30 days of the agent issuing the final disbursement account.
## 6. Disputes
Any dispute about an item in the final disbursement account must be raised in writing within 14 days of receiving it. Undisputed items must be paid on time.
## 7. Cancellation
If a call is cancelled less than 48 hours before the vessel's ETA, a cancellation fee of 30% of the agency fee is charged.
## 8. Currency
All tariffs and fees are in US dollars. Local currency charges are converted at the exchange rate on the day of the vessel's arrival.
""",
"port_costs/docs/port_notes.pdf": """
# Bluefin Marine - Port Notes for Operations (2026)
## Singapore
Pilotage is compulsory for vessels of 300 GT and above. The pre-arrival notification must be sent at least 24 hours before arrival.
## Rotterdam
Vessels with a draft over 17.4 metres must use the Eurogeul approach channel and book a slot with the harbour master in advance.
## Mumbai
Vessels longer than 200 metres LOA may not navigate the main channel at night. Plan arrival for daylight.
## Jebel Ali
A port security declaration must be submitted 48 hours before arrival. Crew changes need an approved agent request.
## Santos
The channel is subject to tidal windows. Vessels over 13 metres draft can only enter at high water.
## Busan
A ballast water reporting form must be submitted before arrival. Bunkering at anchorage needs a separate permit.
""",
}


def build(path, text):
    styles = getSampleStyleSheet()
    story = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if line.startswith("# "):
            story += [Paragraph(line[2:], styles["Title"]), Spacer(1, 8)]
        elif line.startswith("## "):
            story += [Paragraph(line[3:], styles["Heading2"])]
        elif line:
            story += [Paragraph(line, styles["BodyText"]), Spacer(1, 4)]
    SimpleDocTemplate(path, pagesize=A4).build(story)


if __name__ == "__main__":
    for rel, text in DOCS.items():
        build(os.path.join(HERE, rel), text)
        print("wrote", rel)
