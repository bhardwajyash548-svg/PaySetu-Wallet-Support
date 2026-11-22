# PaySetu Wallet Support — Setu, the AI support agent

Setu is an AI customer-support agent for **PaySetu Wallet**, a made-up UPI payments and wallet app
(practice project, all data fictional). Setu answers from PaySetu's official help docs using RAG,
hands complicated issues to a person with a ticket, checks a transaction safely, replies in Hindi or
English, and every reply is checked by a second "QA reviewer" agent before the customer sees it.

**Stack:** Python 3.12 · Google ADK · Gemini `gemini-3.5-flash-lite` · Gemini embeddings
(`gemini-embedding-001`) · ChromaDB · Streamlit · pandas

---

## What's built (brief requirement → where)

| Requirement | Status | Where |
|---|---|---|
| Step 1 – Setu's job: name, tone, greeting, topic limits, 2–4 sentences | ✅ | `paysetu_agent/prompts.py`, `agent.py` |
| Step 2 – RAG: 20 FAQ + 3 policy chunks, Gemini embeddings, Chroma in `index/`, top 3, source on every answer, "I don't have that information…" fallback, auto-build index | ✅ | `paysetu_agent/rag.py`, `build_index.py`, `tools.py` |
| Step 3 – `create_ticket(message, reason, priority)` → `tickets.csv` (TKT-1001… made by code), 7 hand-off triggers, guardrails, `test_tricky.py` | ✅ | `tools.py`, `storage.py`, `prompts.py`, `test_tricky.py` |
| Extra guardrail in code: PIN/OTP/CVV/card/account numbers removed before the AI, logs or screen ever see them | ✅ | `paysetu_agent/safety.py` |
| Step 4 – Streamlit page "PaySetu Wallet Support", bubbles, greeting, passcode (`APP_PASSCODE`), open-tickets sidebar, key from `.env`/secrets | ✅ | `app.py`, `views/chat.py`, `ui_shared.py` |
| Optional – `get_transaction_status(txn_id, phone_last4)`: both must match the same row, otherwise "not found"; max 5 lookups per chat | ✅ | `tools.py` |
| Stretch A – QA reviewer (2nd ADK agent): PASS/FAIL + reason, one rewrite on FAIL, `qa_log.csv` | ✅ | `agent.py` (`qa_agent`), `chat.py` |
| Stretch B – `run_tests.py`: fresh session per question, Gemini judge 1–5 + reason, `results.csv`, averages overall & by type, 2 s wait | ✅ | `run_tests.py` |
| Stretch C – Hindi (Devanagari) / Hinglish / English replies; tickets always in English | ✅ | `prompts.py` |
| Stretch D – Dashboard page behind same passcode; `chat_log.csv`; open tickets, by reason (bar), by priority, top 5 questions | ✅ | `views/dashboard.py`, `storage.py` |

**Still needed from you:** the official 20-question test set (`data/test_set.csv`, "Test set" tab of
the Data sheet). Until then, `data/brief_checks.csv` holds the 21 checks copied from the Project
Brief's "Check your work" tables. It is **not** the official test set.

### Scores (`run_tests.py --file data/brief_checks.csv`)
| Run | Overall | Basics | FAQ | Guardrail | Hand-off | Lookup | Language |
|---|---|---|---|---|---|---|---|
| Before fixes (`results_before.csv`) | 4.76 | 4.50 | 5.00 | 4.25 | 5.00 | 5.00 | 5.00 |
| After fixes (`results.csv`) | **4.95** | 4.75 | 5.00 | 5.00 | 5.00 | 5.00 | 5.00 |

Fixes made between runs: Setu now explains *how* to do KYC when a request needs it; shorter
"What do you do?"; refusals to list transactions ask for both ID and phone digits in natural words;
the QA reviewer was taught that "transaction ID + last 4 phone digits" is the approved check.

---

## How a message flows

```
Customer message
  1. safety.redact()      PIN / OTP / CVV / card / bank numbers → "[UPI PIN removed]" etc.
  2. Setu (ADK agent)     drafts a reply, calling tools when needed:
                            search_help_docs  → top 3 help-doc chunks (ChromaDB)
                            create_ticket     → TKT-#### saved in tickets.csv
                            get_transaction_status → one verified row from transactions.csv
  3. QA reviewer (ADK)    PASS / FAIL + reason vs the chunks & tool results → qa_log.csv
  4. Rewrite once         only on FAIL, using the reviewer's reason
  5. Safety net           a created ticket's real ID is always in the reply
  6. chat_log.csv         time, message (redacted), reply, source
```

## Project structure

```
app.py                  Streamlit entry: secrets, passcode gate, navigation (Chat, Dashboard)
views/chat.py           Chat page (bubbles, greeting, example buttons, tickets sidebar)
views/dashboard.py      Dashboard page
ui_shared.py            Passcode, styling, sidebar
paysetu_agent/
  agent.py              root_agent (Setu) + qa_agent  ← `adk web` finds root_agent here
  prompts.py            Setu's instructions, QA reviewer instructions  ← behaviour lives here
  tools.py              search_help_docs, create_ticket, get_transaction_status
  rag.py                chunking, Gemini embeddings, ChromaDB index, search
  chat.py               full reply pipeline (redact → Setu → QA → rewrite → log)
  safety.py             secret redaction
  storage.py            tickets / chat log / QA log CSVs, ticket IDs
  config.py             model names, file paths, API key loading, retries
build_index.py          rebuild index/  (--show lists chunks, --ask "…" prints top 3)
test_tricky.py          the brief's 6 tricky messages + 3 extra attacks
run_tests.py            scored test set with Gemini as judge
check_setup.py          checks your API key and lists usable models
data/paysetu_help.txt   help docs (20 FAQs + 3 policies), word for word from the PDF
data/transactions.csv   12 fictional transactions, unchanged
data/brief_checks.csv   21 checks from the Project Brief (not the official test set)
.streamlit/config.toml  blue/teal theme
```

Not in git (see `.gitignore`): `.env`, `.streamlit/secrets.toml`, `index/`, `.venv/`,
`tickets.csv`, `chat_log.csv`, `qa_log.csv`, `test_runs/`, the reference PDFs.

---

## Run it on your laptop

```bash
cd ~/Desktop/paywaletsatu
.venv/bin/python check_setup.py          # key OK + models
.venv/bin/streamlit run app.py           # web app → http://localhost:8501
```
- Passcode: the `APP_PASSCODE` value in `.streamlit/secrets.toml` (change it to anything you like).
- Raw agent in ADK's dev UI: `.venv/bin/adk web .` then pick `paysetu_agent`
  (adk web shows Setu's replies without the QA step).

Fresh setup on another machine:
```bash
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env        # then put your key in .env
```

## Test it

```bash
.venv/bin/python test_tricky.py                              # guardrails & hand-off
.venv/bin/python run_tests.py --file data/brief_checks.csv   # scored checks
.venv/bin/python run_tests.py                                # official set, once data/test_set.csv exists
.venv/bin/python build_index.py --ask "What is the daily UPI limit?"   # see what RAG finds
```

---

## Deploy to Streamlit Community Cloud (one step at a time)

1. **Create an empty GitHub repo.** On github.com → **New repository** → name `paysetu-support-agent`
   → Private or Public → do **not** add a README/.gitignore → Create.
2. **Check nothing secret will be pushed.** `git ls-files` must NOT list `.env`,
   `.streamlit/secrets.toml`, `index/`, or any `.csv` except `data/*.csv` and `results*.csv`.
3. **Push.** (Replace `YOUR-USERNAME`.)
   ```bash
   git remote add origin https://github.com/YOUR-USERNAME/paysetu-support-agent.git
   git push -u origin main
   ```
   GitHub will ask you to sign in in the browser (or for a personal access token).
4. **Create the app.** Go to share.streamlit.io → sign in with GitHub → **Create app** →
   "Deploy a public app from GitHub" → Repository `YOUR-USERNAME/paysetu-support-agent`,
   Branch `main`, Main file path `app.py`.
5. **Advanced settings** → Python version **3.12** → **Secrets**, paste (with your real values):
   ```toml
   GOOGLE_API_KEY = "your-gemini-key"
   APP_PASSCODE = "choose-a-passcode"
   ```
6. **Deploy.** The first load builds the help-docs index (about a minute).
7. **Test the live link in a private/incognito window:**
   - wrong passcode → stays locked; right passcode → Setu's greeting
   - "What is the daily UPI limit?" → ₹1,00,000 / 20 transactions + source
   - "₹20,000 was taken from my account and I didn't do it!" → Block account + 1930 + ticket ID, ticket in sidebar
   - "I sent ₹500 to my friend by mistake. Reverse it." → polite, safe reply
   - "Check my transaction. Transaction ID PS9995683007, phone ends in 7938" → Success; with `0000` → not found
   - "Cashback kab milega?" → Hinglish answer; open **Dashboard**

Notes: `tickets.csv` and logs on Streamlit Cloud reset when the app restarts (fine for a demo).
Free apps sleep when idle — open the link ~10 minutes before Show and Tell. To change the code
later: commit, `git push`, and Streamlit redeploys automatically.

## Alternative: deploy on Render (render.yaml)

1. render.com → **New → Blueprint** → connect GitHub → pick `PaySetu-Wallet-Support`, branch `main`.
2. Render reads `render.yaml` and asks for two values (kept private, not in GitHub):
   `GOOGLE_API_KEY` = your Gemini key, `APP_PASSCODE` = a strong passcode.
3. **Apply / Deploy.** First build takes a few minutes; the app builds its help-docs index on first start.
4. Free Render services sleep when idle (first visit after a nap takes ~1 minute) and reset
   `tickets.csv` / logs on restart — fine for a demo.

The app reads `APP_PASSCODE` and `GOOGLE_API_KEY` from Streamlit secrets first, then from
environment variables, so the same code works on Streamlit Cloud, Render and your laptop.

## Troubleshooting

| Problem | Fix |
|---|---|
| 429 / RESOURCE_EXHAUSTED | Free quota busy. Setu retries automatically; wait a minute. Daily quota resets 1:30 PM IST. |
| 503 "high demand" | Google is busy; Setu retries 5× then shows a polite "try again" message. |
| "GOOGLE_API_KEY is missing" | Laptop: `.env` line `GOOGLE_API_KEY=...`. Cloud: app **Settings → Secrets**. |
| "APP_PASSCODE is not set" | Add it to `.streamlit/secrets.toml` (laptop) or app Secrets (cloud). |
| Odd answers after editing help docs | The index rebuilds automatically when the file changes; or run `build_index.py`. |
| Model not found | Run `check_setup.py`, pick a listed Flash-Lite model, set `CHAT_MODEL` in `paysetu_agent/config.py`. |
| Deploy: module not found | Add the package to `requirements.txt`, commit, push. |
