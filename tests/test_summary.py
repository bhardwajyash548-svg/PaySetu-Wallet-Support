"""Hand-off summaries: required sections, verified facts only, never any secrets."""
from paysetu_agent import conversation_summary as cs
from paysetu_agent import ticket_manager as tm

TICKET = {"ticket_id": "TKT-1001", "customer_message": "Unauthorised debit", "reason": "Fraud or hacked account",
          "priority": "high", "category": "Fraud"}
MOOD = {"frustrated": True, "why": "customer is angry"}
SENT = {"label": "Angry", "score": -1.0}
RISK = {"level": "High", "reasons": ['Customer reports a payment or debit they did not make ("didn\'t do")']}
TXN = {"txn_id": "PS9995683007", "type": "Send money", "amount_inr": "860", "date": "11-Nov-2026", "status": "Success"}


def test_template_summary_has_every_section():
    turns = [("₹20,000 was taken and I didn't do it!",
              "Please tap Block account and call 1930. Your ticket ID is TKT-1001.")]
    text = cs.build_summary(turns, TICKET, MOOD, SENT, RISK, TXN, use_ai=False)
    for label in ("Issue:", "Verified transaction:", "Steps already taken:", "Customer sentiment:",
                  "Fraud risk:", "Escalation reason:", "Recommended next action:"):
        assert label in text
    assert "PS9995683007" in text and "verified" in text and "High" in text
    assert "call back promptly" in text           # upset customer
    assert "Block account and call 1930" in text  # step detected from the chat


def test_no_transaction_is_stated_honestly():
    text = cs.build_summary([("hi", "hello")], TICKET, {}, {"label": "Neutral", "score": 0}, {"level": "Low"},
                            None, use_ai=False)
    assert "None verified in this chat" in text and "Fraud risk: Low" in text


def test_summary_never_contains_secrets_even_if_ai_repeats_them(monkeypatch):
    # Worst case: the AI echoes secrets. The final redaction must still remove them.
    monkeypatch.setattr(cs, "_ai_part", lambda turns: ({
        "issue": "Customer gave UPI PIN 4821 and OTP 552311, card 4111 1111 1111 1111, call 9876543210",
        "steps": ["Asked about account number 123456789012"]}, "test-model"))
    text = cs.build_summary([("x", "y")], TICKET, MOOD, SENT, RISK, None)
    for secret in ("4821", "552311", "4111 1111", "123456789012", "9876543210"):
        assert secret not in text, secret
    assert "XXXXXX3210" in text  # phone masked to last 4


def test_falls_back_to_template_when_ai_fails(monkeypatch):
    monkeypatch.setattr(cs, "_ai_part", lambda turns: (None, ""))
    text = cs.build_summary([("hi", "Cashback is added within 24 hours. (Source: FAQ: When will I get cashback?)")],
                            {**TICKET, "category": "Cashback", "reason": "Angry or upset customer"},
                            {}, {"label": "Negative", "score": -0.3}, {"level": "Low"}, None)
    assert "Written by: template" in text and "When will I get cashback?" in text
    assert "eligible payment" in text  # cashback next action, from the help docs


def test_pipeline_saves_summary_on_ticket(fake_setu, monkeypatch):
    monkeypatch.setattr(cs, "_ai_part", lambda turns: ({"issue": "Customer reports an unauthorised debit.",
                                                        "steps": ["Gave fraud safety steps"]}, "test-model"))
    chat, _ = fake_setu(draft="Please tap Block account in Settings and call 1930.")
    out = chat.respond("My UPI PIN is 4821. ₹20,000 was taken from my account and I didn't do it!")
    t = tm.get_ticket(out["tickets"][0])
    assert t["category"] == "Fraud"
    assert "Issue: Customer reports an unauthorised debit." in t["summary"]
    assert "4821" not in t["summary"] and "Fraud risk: High" in t["summary"]
    # a second message in the same chat does not overwrite / duplicate the summary
    chat.respond("thanks")
    assert len(tm.all_tickets()) == 1


def test_phone_mask_does_not_touch_transaction_ids():
    out = cs.sanitize("PS9995683007 and +91 98765 43210 and 9876543210 and 98765-43210")
    assert out == "PS9995683007 and XXXXXX3210 and XXXXXX3210 and XXXXXX3210", out
