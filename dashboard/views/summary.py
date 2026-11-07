"""W2 - Summary: the decision first, readable in 30 seconds."""
import streamlit as st

from common import kpi, evidence, money, out, page_link, pct, table


def render() -> None:
    pf = out("portfolio")
    funded = pf[pf["action_type_id"] != "A-HOLD"]
    kept = pf["kept_usd"].dropna().iloc[0]
    comp = out("a9_list_comparison")
    stays = comp[comp["status"] == "stays"]

    st.title("Don't replace the manager's 10. Inspect one, fix the spot, promote.")
    st.markdown(
        f"The general manager planned to replace the 10 machines that earned the least from January to June. "
        f"We put each one on trial for **luck, location and a leak**. Only **{len(stays)} of the 10** is a machine worth replacing; "
        f"one shows a payout pattern worth inspecting, and most are standing in the weakest part of the floor.")

    c = st.columns(4)
    kpi(c[0], "Funded from $100,000", money(funded["cost"].sum()), f"{len(funded)} action types")
    kpi(c[1], "Expected net theo (mid)", money(pf["net_mid"].sum()),
                f"low {money((funded['low'] - funded['cost']).sum())} · high {money((funded['high'] - funded['cost']).sum())}")
    kpi(c[2], "Kept", money(kept), "nothing else clears its cost")
    kpi(c[3], "Manager's 10 that are truly weak", f"{len(stays)} of 10")

    st.subheader("What we fund for July 1–30")
    for r in funded.itertuples():
        st.markdown(f"- **{r.name}** ×{r.quantity}: {money(r.cost)} → expected **{money(r.mid)}** of theo "
                    f"(range {money(r.low)} to {money(r.high)}). Targets: {r.targets}.")
    page_link("plan", "Full plan: costs, uncertainty, measurement and evidence")

    st.subheader("The manager's list vs ours")
    show = comp.rename(columns={"machine_id": "Machine", "status": "Status", "verdict": "Verdict", "why": "Why", "advice": "Advice"})
    table(show[["Machine", "Status", "Verdict", "Why", "Advice"]], height=min(38 * (len(show) + 1), 640),
          column_config={"Why": st.column_config.TextColumn(width="large"), "Advice": st.column_config.TextColumn(width="medium")})
    page_link("machines", "The machine trial: every test, every machine")

    st.subheader("Three findings that drive the decision")
    findings = [("A8-01", "Location, not the machines, is the biggest reason the manager's 10 earned less.", "machines"),
                ("A4-01", "One machine (M-1158) pays out on far more spins than its game allows: inspect it before anything else.", "machines"),
                ("B9-03", "The Back Forty lost a third of its play while its walkway was closed; access matters there.", "demand")]
    for cid, text, page in findings:
        st.markdown(f"**{text}**")
        evidence(cid)
    st.caption(f"Comp program: the May 1 rate change cut the points needed per comp dollar by more than half; whether it paid "
               f"for itself can't be told yet. Model: a weekday-average forecast, validated on May–June, sizes the promotion "
               f"benefit. Tracked players: {pct(out('d2_overview')['share_players_ahead'].iloc[0])} came out ahead.")
