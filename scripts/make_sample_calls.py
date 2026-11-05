"""Write practice support calls for the simulator. The calls are made up, no real customer data.

    python -m scripts.make_sample_calls
"""
import json
from pathlib import Path

from openai import OpenAI

from app.config import settings

COMPANY = "Northwind Telecom, an internet and phone provider"

SCENARIOS = [
    ("strong-billing", "Billing question handled well", "Maya",
     "A customer was charged twice this month. The agent greets properly, is warm, checks the customer's identity "
     "(name and last four digits of the account number), finds the duplicate charge, explains the refund takes "
     "5 to 7 days, summarises, asks if anything else is needed and thanks them."),
    ("rude-agent", "Rude agent, slow internet", "Dan",
     "A customer's internet is slow. The agent is short and impatient, sighs, blames the customer's router, "
     "interrupts, uses slang, gives a half answer, and ends the call abruptly without a goodbye."),
    ("compliance-failure", "Account details shared without checking identity", "Leo",
     "Someone calls asking for the address and card ending digits on an account. The agent never verifies "
     "identity, reads out the full address and last four card digits, and also promises a guaranteed refund of "
     "200 dollars without checking eligibility. Otherwise the agent is friendly."),
    ("calm-after-anger", "Angry customer, agent de-escalates", "Priya",
     "A very angry customer lost service for two days. The agent stays calm, apologises sincerely, verifies "
     "identity, books a technician for tomorrow morning, offers a fair bill credit within policy, and closes well."),
    ("vague-no-fix", "Friendly but no resolution", "Tom",
     "A customer cannot connect their new router. The agent is polite and greets well but gives vague advice "
     "('maybe try restarting things'), never asks which lights are on, never finds the cause, and ends with no "
     "clear next step."),
    ("good-no-closing", "Good fix, weak ending", "Ana",
     "A customer wants to change their plan. The agent is clear, verifies identity, explains two options with "
     "prices correctly, makes the change, but then just says 'ok, done' and hangs up with no summary, no "
     "'anything else' and no thanks."),
]

PROMPT = """Write a realistic phone call transcript between a support agent and a customer at {company}.
Scenario: {scenario}
The agent is called {agent}. Write 14 to 20 lines, starting with the agent's greeting. Natural spoken language, no stage directions.
Reply with JSON only: {{"lines": [{{"speaker": "agent" or "customer", "text": "..."}}]}}"""


def main():
    client = OpenAI(api_key=settings.openai_api_key)
    samples = []
    for sample_id, title, agent, scenario in SCENARIOS:
        resp = client.chat.completions.create(
            model="gpt-4o", temperature=0.8, response_format={"type": "json_object"},
            messages=[{"role": "user", "content": PROMPT.format(company=COMPANY, scenario=scenario, agent=agent)}],
        )
        lines = json.loads(resp.choices[0].message.content)["lines"]
        lines = [{"speaker": ln["speaker"], "text": ln["text"].strip()} for ln in lines
                 if ln["speaker"] in ("agent", "customer") and ln["text"].strip()]
        samples.append({"id": sample_id, "title": title, "agent_name": agent, "lines": lines})
        print(f"{sample_id}: {len(lines)} lines")
    Path("data/sample_calls.json").write_text(json.dumps(samples, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
