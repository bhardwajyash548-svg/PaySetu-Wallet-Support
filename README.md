# PaySetu Wallet Support — Setu, the AI support agent (Enterprise edition)

Setu is an AI customer-support agent for **PaySetu Wallet**, a made-up UPI payments and wallet app
(practice project, all data fictional, no real payments). Setu answers from PaySetu's official help docs
using RAG, hands complicated issues to a person with a ticket, checks a transaction safely, replies in Hindi
or English, and every reply is checked by a second "QA reviewer" agent before the customer sees it.
The enterprise edition adds fraud detection, sentiment analysis, smart ticket tracking, a payment journey,
PDF receipts, hand-off summaries and an admin console.

**Stack:** Python 3.12 · Google ADK · Gemini `gemini-3.5-flash-lite` (backup `gemini-3.1-flash-lite`) ·
Gemini embeddings (`gemini-embedding-001`) · ChromaDB · Streamlit · pandas · Altair · fpdf2

---

## Features

### Original brief (all built and tested)
| Requirement | Where |
|---|---|
| Setu: name, calm tone, greeting, topic limits, 2–4 sentences | `paysetu_agent/prompts.py`, `agent.py` |
| RAG: 20 FAQ + 3 policy chunks, Gemini embeddings, Chroma in `index/`, top 3, source on every answer, "I don't have that information…" fallback, index built automatically | `rag.py`, `build_index.py`, `tools.py` |
| `create_ticket(message, reason, priority)` → `tickets.csv`, IDs TKT-1001… made by code, all 7 hand-off rules | `tools.py`, `ticket_manager.py` |
| Guardrails (PIN/OTP/CVV/card/bank numbers, other users' data, no reversal promises, prompt injection, off-topic) | `prompts.py` + code in `safety.py` |
| Streamlit page, passcode `APP_PASSCODE`, chat bubbles, greeting, tickets sidebar | `app.py`, `views/chat.py`, `ui_shared.py` |
| `get_transaction_status(txn_id, phone_last4)` — both must match the same row | `tools.py` |
| QA reviewer (2nd ADK agent), PASS/FAIL, one rewrite, `qa_log.csv` | `agent.py`, `chat.py` |
| `run_tests.py` — fresh session per question, Gemini judge 1–5, `results.csv`, averages, 2 s wait | `run_tests.py` |
| Hindi (Devanagari) / Hinglish / English replies; tickets in English | `prompts.py`, `chat.py` |
| Dashboard page + `chat_log.csv` | `views/dashboard.py` |

### Enterprise additions
| Feature | What it does | Where |
|---|---|---|
| **A. Fraud detection** | Explainable point rules → Low / Medium / High + reasons. High needs real harm (unrecognised debit, hacked account, shared OTP/PIN) and always gets a high-priority ticket + Block account + 1930, even if the AI forgets or Gemini is down. Not a trained model. | `fraud_detection.py` |
| **B. Sentiment** | Positive / Neutral / Negative / Angry + score −1…+1 (English, Hindi, Hinglish word lists, CAPS, "!!!"), tracked per conversation; angry or frustrated customers get one ticket per chat. | `sentiment_analysis.py` |
| **C. Smart tickets** | 8 categories, Open → In Progress → Resolved → Closed (re-open allowed), history and audit log, admin-only changes. | `ticket_manager.py`, `views/admin_tickets.py` |
| **D. Admin analytics** | Conversations, AI resolution rate (definition on the page), response time, tickets by status/category/priority, time to resolve, sentiment and fraud charts, QA and test scores — all from real logs. | `analytics.py`, `views/admin_analytics.py` |
| **E. Payment journey** | After a verified lookup: recorded date → actual status → what the policy says (Mon–Fri working days). Never invents bank events. Offers a ticket when a failed payment passed 3 working days or a pending one passed 48 hours. | `payment_journey.py` |
| **F. Hand-off summary** | Every new ticket gets: issue, verified transaction, steps taken, sentiment, fraud risk, escalation reason, next action. Facts from code, wording from Gemini (English), secrets/phones/emails masked, template fallback. | `conversation_summary.py` |
| **G. PDF receipt** | "Payment Receipt" for Success, "Transaction Status Statement" otherwise, DEMO / FICTIONAL watermark, re-verifies ID + phone before drawing. Setu offers to send it to the customer's email — **demo mode: only a message is shown, no real email is sent.** | `receipt_generator.py`, `emailer.py`, `tools.py` |

---

## How a message flows

```
Customer message
 1. safety          strip fake "system context", control chars, cap length; remove PIN/OTP/CVV/card/bank numbers
 2. sentiment       label + score; conversation frustration check
 3. fraud check     risk + reasons (re-checked with the verified transaction later)
 4. Setu (ADK)      tools: search_help_docs · create_ticket · get_transaction_status · send_receipt_email
                    (backup model takes over automatically if the main model's quota runs out)
 5. escalation      High fraud → high-priority ticket; angry/frustrated → ticket (one per issue per chat)
 6. QA reviewer     code checks (reply language/script, made-up sources) + AI review → one rewrite on FAIL
 7. safety nets     Block account + 1930 for High fraud; real ticket ID in the reply; fake sources removed
 8. summary         hand-off summary saved on every new ticket
 9. logs            chat_log (session, outcome, response time, sentiment, risk, model), qa_log, fraud_alerts
10. UI              reply + payment journey card + "Email me this receipt" + "Raise a ticket"
```

## Project structure

```
app.py                     Streamlit entry: passcode gate, navigation (Support + Admin sections)
ui_shared.py               passcode + admin sign-in (lockout, 30-min admin timeout), styling, sidebar
charts.py                  shared chart look for both dashboards
views/chat.py              chat page (bubbles, journey card, email/ticket buttons, 60-message cap)
views/dashboard.py         customer-safe dashboard (no customer text)
views/admin_tickets.py     ADMIN: ticket list, filters, summary, status change, history, audit log
views/admin_analytics.py   ADMIN: analytics from the logs
paysetu_agent/
  agent.py                 Setu + QA reviewer (+ backup-model copies)   ← adk web finds root_agent here
  prompts.py               Setu and QA instructions                      ← behaviour lives here
  tools.py                 search_help_docs, create_ticket, get_transaction_status, send_receipt_email
  chat.py                  the full reply pipeline above
  rag.py                   chunking, embeddings, Chroma index, search
  safety.py                secret removal, input hygiene
  sentiment_analysis.py    fraud_detection.py    payment_journey.py    conversation_summary.py
  ticket_manager.py        storage.py (CSV logs, formula-injection safe)    analytics.py    outcomes.py
  receipt_generator.py     emailer.py (demo by default)    auth.py (passcodes, lockout, admin identity)
  config.py                models, file paths, retries, backup-model switch
tests/                     175 unit tests (no API key needed)
test_tricky.py · run_tests.py · build_index.py · check_setup.py
data/paysetu_help.txt      help docs, word for word from the PDF (20 FAQs + 3 policies)
data/transactions.csv      12 fictional transactions (unchanged)
data/brief_checks.csv      21 checks copied from the Project Brief (NOT the official test set)
render.yaml                Render Blueprint
```

Not in git: `.env`, `.streamlit/secrets.toml`, `index/`, `.venv/`, `.tools/`, and every runtime log
(`tickets.csv`, `chat_log.csv`, `qa_log.csv`, `fraud_alerts.csv`, `ticket_history.csv`, `audit_log.csv`,
`email_log.csv`, `test_runs/`), plus the reference PDFs.

---

## Settings (secrets)

| Name | Needed for | Laptop | Render / Streamlit Cloud |
|---|---|---|---|
| `GOOGLE_API_KEY` | Gemini | `.env` | Environment / Secrets |
| `APP_PASSCODE` | opening the app | `.streamlit/secrets.toml` | Environment / Secrets |
| `ADMIN_PASSCODE` | admin pages (must differ from `APP_PASSCODE`) | `.streamlit/secrets.toml` | Environment / Secrets |
| `EMAIL_MODE` (optional) | leave unset = demo (message only). `send` + `SMTP_USER` + `SMTP_APP_PASSWORD` would send real Gmail | — | — |

## Run on your laptop

```bash
cd ~/Desktop/paywaletsatu
.venv/bin/python check_setup.py          # key works + model list
.venv/bin/streamlit run app.py           # http://localhost:8501
```
Admin pages: sidebar → **Admin** → sign in with your name + `ADMIN_PASSCODE`.
Fresh setup elsewhere: `python3.12 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt`, then
copy `.env.example` to `.env` and add the key.

## Tests

```bash
.venv/bin/python -m pytest tests                                   # 175 unit tests, no API key needed
.venv/bin/python test_tricky.py                                    # 9 tricky messages, live
.venv/bin/python run_tests.py --file data/brief_checks.csv         # scored, Gemini as judge
.venv/bin/python run_tests.py --file data/brief_checks.csv --retry-unscored   # re-run rate-limited ones
.venv/bin/python run_tests.py                                      # official set, once data/test_set.csv exists
```

| Scored run (brief checks) | Overall | Basics | FAQ | Guardrail | Hand-off | Lookup | Language |
|---|---|---|---|---|---|---|---|
| First run (`results_before.csv`) | 4.76 | 4.50 | 5.00 | 4.25 | 5.00 | 5.00 | 5.00 |
| After prompt fixes | 4.95 | 4.75 | 5.00 | 5.00 | 5.00 | 5.00 | 5.00 |
| Final, enterprise edition (`results.csv`) | **5.00** | 5.00 | 5.00 | 5.00 | 5.00 | 5.00 | 5.00 |

**Still needed:** the official 20-question test set (`data/test_set.csv`, the "Test set" tab of the Data sheet).

---

## Deploy

### Render (current)
1. render.com → **New → Blueprint** → repo `PaySetu-Wallet-Support`, branch `main` (reads `render.yaml`).
2. Enter `GOOGLE_API_KEY`, `APP_PASSCODE`, `ADMIN_PASSCODE` (strong values, admin ≠ app). Leave `SMTP_*` empty.
3. Deploy. Every `git push` to `main` redeploys automatically.

### Streamlit Community Cloud (alternative)
share.streamlit.io → Create app → repo, branch `main`, file `app.py` → Python 3.12 → Secrets:
```toml
GOOGLE_API_KEY = "..."
APP_PASSCODE = "..."
ADMIN_PASSCODE = "..."
```

Free hosts reset files on restart, so tickets and logs start empty after a restart (the Dashboard has a
clearly labelled "Show sample data" switch for demos). Free apps sleep when idle — open the link ~10 minutes
before a demo.

## Security notes and limits

- Secrets only in `.env` / `secrets.toml` / host settings; never committed (checked in git history).
- Customer passcode and admin passcode are separate; 5 wrong tries = 5-minute lock per browser session;
  admins are signed out after 30 minutes idle; every admin action is in `audit_log.csv`.
- Customers only see their own chat's tickets; the customer dashboard shows no customer text.
- PDFs and email offers only for transactions verified in the same chat; email addresses are masked in all logs.
- CSV logs neutralise spreadsheet formulas (`= + - @`) so they are safe to open in Excel.
- Download links Streamlit creates are random and live only while the session is open.
- This is demo-grade protection for a practice project: no regulatory certification, no production
  banking security, no real payments or emails.

## Troubleshooting

| Problem | Fix |
|---|---|
| 429 / RESOURCE_EXHAUSTED | Setu retries, then switches to the backup model for 10 minutes. Daily quota resets 1:30 PM IST. |
| Test run shows "not scored" | Rate limit during the run — `run_tests.py ... --retry-unscored`. |
| "APP_PASSCODE / ADMIN_PASSCODE is not set" | Add it to `secrets.toml` (laptop) or the host's environment. |
| "ADMIN_PASSCODE must be different" | Use a different value from `APP_PASSCODE`. |
| Odd answers after editing help docs | The index rebuilds automatically when the file changes; or run `build_index.py`. |
| Model not found | `check_setup.py`, then set `PAYSETU_MODEL` / `PAYSETU_FALLBACK_MODEL` or edit `config.py`. |
| Deploy: module not found | Add it to `requirements.txt`, commit, push. |
