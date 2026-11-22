"""Admin: Ticket management. Signed-in admins only; every change goes to history and the audit log."""
import html

import pandas as pd
import streamlit as st

from paysetu_agent import config, storage, ticket_manager as tm
from paysetu_agent.auth import admin_actor
from ui_shared import hero, require_admin

ADMIN_CSS = """
<style>
.block-container { max-width: 1180px !important; }
.ps-stat { background:#fff; border:1px solid #DCE6EF; border-radius:14px; padding:10px 14px;
  box-shadow:0 4px 14px rgba(11,37,64,.05); }
.ps-stat .l { color:#52606D; font-size:.8rem; } .ps-stat .v { font-size:1.6rem; font-weight:800; color:#0B2540; }
.ps-pill { font-size:.74rem; font-weight:700; padding:2px 9px; border-radius:999px; display:inline-block; }
.ps-open { background:#E0F2FE; color:#075985; } .ps-in_progress { background:#FFF4DB; color:#8A5A00; }
.ps-resolved { background:#E3F5EC; color:#0f8a5f; } .ps-closed { background:#EEF1F4; color:#52606D; }
.ps-high { background:#FDE8E8; color:#B42318; } .ps-normal { background:#E0F2FE; color:#075985; }
.ps-summary { white-space:pre-wrap; font-size:.86rem; background:#F8FAFC; border:1px solid #DCE6EF;
  border-radius:12px; padding:10px 12px; color:#0B2540; }
.ps-tl { display:grid; grid-template-columns:12px minmax(0,1fr); gap:8px; font-size:.86rem; margin-bottom:8px; }
.ps-tl .dot { width:10px; height:10px; border-radius:50%; background:#0E8C8C; margin-top:5px; }
.ps-tl .when { color:#8394A5; font-size:.76rem; }
</style>
"""

admin = require_admin()  # stops here unless an admin is signed in
st.markdown(ADMIN_CSS, unsafe_allow_html=True)
hero("Ticket management", "Admin only · every change is saved to ticket history and the audit log")
e = html.escape

tickets = tm.all_tickets()
counts = {s: sum(1 for t in tickets if t["status"] == s) for s in tm.STATUSES}
cols = st.columns(4)
for col, s in zip(cols, tm.STATUSES):
    col.markdown(f'<div class="ps-stat"><div class="l">{tm.STATUS_LABELS[s]}</div><div class="v">{counts[s]}</div></div>',
                 unsafe_allow_html=True)

if not tickets:
    st.info("No tickets yet. Tickets appear here when Setu hands a customer to a person.")
    st.stop()

# ---------- filters ----------
f1, f2, f3, f4 = st.columns([1.2, 1.2, 1, 1.4])
status_f = f1.multiselect("Status", [tm.STATUS_LABELS[s] for s in tm.STATUSES],
                          default=["Open", "In Progress"], key="f_status")
cat_f = f2.multiselect("Category", tm.CATEGORIES, key="f_cat")
prio_f = f3.multiselect("Priority", ["high", "normal"], key="f_prio")
search = f4.text_input("Search ID or text", key="f_search", max_chars=60).strip().lower()

rows = [t for t in tickets
        if (not status_f or tm.STATUS_LABELS.get(t["status"], t["status"]) in status_f)
        and (not cat_f or t["category"] in cat_f)
        and (not prio_f or t["priority"] in prio_f)
        and (not search or search in t["ticket_id"].lower() or search in t["customer_message"].lower()
             or search in t["reason"].lower())]
rows = list(reversed(rows))  # newest first

df = pd.DataFrame([{"Ticket": t["ticket_id"], "Created": t["time"], "Category": t["category"],
                    "Priority": t["priority"], "Fraud risk": t["fraud_risk"] or "-",
                    "Status": tm.STATUS_LABELS.get(t["status"], t["status"]), "Reason": t["reason"],
                    "Updated": t["updated_at"]} for t in rows])
st.caption(f"{len(rows)} of {len(tickets)} tickets")
if df.empty:
    st.info("No tickets match these filters.")
    st.stop()
st.dataframe(df, hide_index=True, use_container_width=True, height=min(420, 38 + 35 * len(df)))

# ---------- one ticket ----------
ids = [t["ticket_id"] for t in rows]
chosen = st.selectbox("Open a ticket", ids, key="f_ticket")
t = tm.get_ticket(chosen)
left, right = st.columns([1.3, 1], gap="medium")

with left:
    box = st.container(border=True)
    box.markdown(
        f'<p style="margin:0 0 6px"><b style="font-size:1.1rem">{e(t["ticket_id"])}</b> &nbsp;'
        f'<span class="ps-pill ps-{e(t["status"])}">{e(tm.STATUS_LABELS.get(t["status"], t["status"]))}</span> '
        f'<span class="ps-pill ps-{e(t["priority"])}">{e(t["priority"])}</span> '
        f'<span class="ps-pill ps-closed">{e(t["category"])}</span></p>'
        f'<p style="margin:0;color:#52606D;font-size:.85rem">Created {e(t["time"])} · updated {e(t["updated_at"])} · '
        f'sentiment {e(t["sentiment"] or "-")} · fraud risk {e(t["fraud_risk"] or "-")}</p>'
        f'<p style="margin:8px 0 4px"><b>Reason:</b> {e(t["reason"])}</p>'
        f'<p style="margin:0 0 8px"><b>Customer message (English summary):</b> {e(t["customer_message"])}</p>',
        unsafe_allow_html=True)
    box.markdown("**Hand-off summary**")
    box.markdown(f'<div class="ps-summary">{e(t["summary"] or "No summary saved for this ticket.")}</div>',
                 unsafe_allow_html=True)

with right:
    box = st.container(border=True)
    box.markdown("**Change status**")
    allowed = sorted(tm.TRANSITIONS.get(t["status"] or "open", set()), key=tm.STATUSES.index)
    with box.form(f"status_{t['ticket_id']}", clear_on_submit=True):
        new = st.selectbox("New status", [tm.STATUS_LABELS[s] for s in allowed])
        note = st.text_area("Note (optional)", max_chars=300, height=80)
        save = st.form_submit_button("Save status", type="primary")
    if save:
        try:
            tm.change_status(t["ticket_id"], new, admin_actor(st.session_state), note.strip())
            st.toast(f"{t['ticket_id']} moved to {new}")
            st.rerun()
        except (tm.TicketError, PermissionError) as exc:
            box.error(str(exc))

    box = st.container(border=True)
    box.markdown("**History**")
    hist = tm.history(t["ticket_id"])
    if not hist:
        box.caption("No history recorded (ticket created before tracking started).")
    for h in hist:
        frm = tm.STATUS_LABELS.get(h["from_status"], "Created") if h["from_status"] else "Created"
        to = tm.STATUS_LABELS.get(h["to_status"], h["to_status"])
        note = f' · "{e(h["note"])}"' if h["note"] else ""
        box.markdown(f'<div class="ps-tl"><span class="dot"></span><div><b>{e(frm)} → {e(to)}</b> by '
                     f'{e(h["changed_by"])}{note}<div class="when">{e(h["time"])}</div></div></div>',
                     unsafe_allow_html=True)

with st.expander("Audit log (latest 50 admin actions)"):
    audit = storage.read_rows(config.AUDIT_LOG_FILE)[-50:][::-1]
    if audit:
        st.dataframe(pd.DataFrame(audit), hide_index=True, use_container_width=True)
    else:
        st.caption("No admin actions recorded yet.")
