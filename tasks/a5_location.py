"""A5 - location test: is the machine weak, or is it standing in a weak spot?

Run:  python -m tasks.a5_location [--start 2025-01-01 --end 2025-06-30]
  -> outputs/a5_location.parquet       one row per machine: peer index and flags
  -> outputs/bank_scores.parquet       one row per bank: TPAH, occupancy, rank, x/y
  -> outputs/a5_game_by_zone.parquet   one row per game config x zone: same game, different spot
  -> outputs/charts/a5_floor_map.*     floor map coloured by bank TPAH

Peer index = machine TPAH / median TPAH of the OTHER machines in the same bank over the SAME days.
A machine that moved gets one peer median per bank stint, weighted by days spent there.
Starting flags (tune at Gate 1):
  location:      bank in the bottom quarter of banks AND machine within +-20% of its peers
  machine:       peer index below 0.7
  low-hold game: machine flag, BUT play volume (coin-in per available hour) is within 20% of its peers or
                 higher. People play it; the game just keeps less per bet (e.g. Royal Draw, 95% RTP).
                 Replacing it is a game-math decision, not a "nobody plays this machine" decision.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from royale.charts import COLORS, SEQUENTIAL_BLUE, save, style
from royale.cli import window_args
from royale.data import load, load_base
from royale.metrics import summarize
from royale.outputs import write_output
from royale.timeutil import to_gaming_date
from royale.util import safe_ratio
from tasks.a1_manager_list import manager_ten

PEER_BAND = 0.20           # within +-20% of peers counts as "performs like its neighbours"
MACHINE_PEER_INDEX = 0.70  # below this the machine itself is weak
THIN_PEERS = 4             # fewer peers than this: the peer median is fragile, say so


def bank_scores(base: pd.DataFrame, manager_ids: list[str]) -> pd.DataFrame:
    banks = summarize(base, ["zone_id", "bank_id"])
    banks = banks[["zone_id", "bank_id", "machines", "days_on_floor", "available_hours", "theo_usd",
                   "tpah", "occupancy", "availability", "coin_in_per_avail_hour"]]
    zones = summarize(base, "zone_id")[["zone_id", "tpah", "occupancy"]].rename(
        columns={"tpah": "zone_tpah", "occupancy": "zone_occupancy"})
    floor = load("floor_locations")
    xy = floor[floor["node_type"] == "bank"][["bank_id", "x_m", "y_m", "capacity"]]
    names = floor[floor["node_type"] == "zone"][["zone_id", "name"]].rename(columns={"name": "zone_name"})
    banks = banks.merge(zones, on="zone_id").merge(names, on="zone_id").merge(xy, on="bank_id", how="left")
    banks["bank_rank"] = banks["tpah"].rank(method="first").astype(int)          # 1 = lowest
    banks["bank_quartile"] = pd.qcut(banks["bank_rank"], 4, labels=[1, 2, 3, 4]).astype(int)  # 1 = bottom 25%
    held = base[base["machine_id"].isin(manager_ids)].groupby("bank_id")["machine_id"].nunique()
    banks["manager_10_machines"] = banks["bank_id"].map(held).fillna(0).astype(int)
    return banks.sort_values("bank_rank").reset_index(drop=True)


def peer_medians(base: pd.DataFrame) -> pd.DataFrame:
    """Per machine x bank stint: median TPAH of the other machines in that bank over the same days."""
    rows = base[["machine_id", "bank_id", "gaming_date", "theo_usd", "coin_in_usd", "available_hours"]]
    pairs = rows[["machine_id", "bank_id", "gaming_date"]].merge(
        rows.rename(columns={"machine_id": "peer_id"}), on=["bank_id", "gaming_date"])
    pairs = pairs[pairs["peer_id"] != pairs["machine_id"]]
    peer = pairs.groupby(["machine_id", "bank_id", "peer_id"])[["theo_usd", "coin_in_usd", "available_hours"]].sum()
    peer["peer_tpah"] = safe_ratio(peer["theo_usd"], peer["available_hours"])
    peer["peer_cph"] = safe_ratio(peer["coin_in_usd"], peer["available_hours"])
    stints = peer.groupby(["machine_id", "bank_id"]).agg(peer_median_tpah=("peer_tpah", "median"),
                                                         peer_median_cph=("peer_cph", "median"),
                                                         n_peers=("peer_tpah", "size"))
    days = rows.groupby(["machine_id", "bank_id"]).size().rename("days_in_bank")
    return days.to_frame().join(stints).reset_index()


def game_by_zone(base: pd.DataFrame) -> pd.DataFrame:
    """Same game, different spot: TPAH of each game config in each zone vs that game everywhere."""
    games = summarize(base, ["config_id", "theme", "zone_id"])[
        ["config_id", "theme", "zone_id", "machines", "available_hours", "theo_usd", "tpah", "occupancy"]]
    overall = summarize(base, "config_id")[["config_id", "tpah", "theo_usd", "available_hours"]].rename(
        columns={"tpah": "game_floor_tpah", "theo_usd": "_game_theo", "available_hours": "_game_hours"})
    games = games.merge(overall, on="config_id")
    games["zone_index"] = safe_ratio(games["tpah"], games["game_floor_tpah"])
    games["game_elsewhere_tpah"] = safe_ratio(games["_game_theo"] - games["theo_usd"],
                                              games["_game_hours"] - games["available_hours"])
    return games.drop(columns=["_game_theo", "_game_hours"]).sort_values(["config_id", "tpah"]).reset_index(drop=True)


def compute(base: pd.DataFrame, manager_ids: list[str] | None = None):
    """Return (a5_location, bank_scores, a5_game_by_zone) for an already-windowed base."""
    manager_ids = manager_ten() if manager_ids is None else manager_ids
    banks = bank_scores(base, manager_ids)
    games = game_by_zone(base)
    stints = peer_medians(base)

    weighted = stints.dropna(subset=["peer_median_tpah"]).assign(
        w=lambda s: s["days_in_bank"] * s["peer_median_tpah"], wc=lambda s: s["days_in_bank"] * s["peer_median_cph"])
    peer = weighted.groupby("machine_id").agg(w=("w", "sum"), wc=("wc", "sum"), d=("days_in_bank", "sum"))
    primary = stints.sort_values("days_in_bank", ascending=False).drop_duplicates("machine_id").set_index("machine_id")

    m = summarize(base, "machine_id")[["machine_id", "days_on_floor", "available_hours", "theo_usd", "tpah",
                                       "coin_in_per_avail_hour", "expected_hold", "occupancy"]]
    m = m.set_index("machine_id")
    m["bank_peer_tpah"] = peer["w"] / peer["d"]
    m["peer_index"] = safe_ratio(m["tpah"], m["bank_peer_tpah"])
    # Same comparison on play VOLUME (coin-in per available hour), which ignores the game's payout setting.
    # Low peer_index with normal volume_peer_index = people play it, but the game keeps less per bet (low hold by design).
    m["bank_peer_coin_in_per_hour"] = peer["wc"] / peer["d"]
    m["volume_peer_index"] = safe_ratio(m["coin_in_per_avail_hour"], m["bank_peer_coin_in_per_hour"])
    m["bank_id"] = primary["bank_id"]
    m["n_peers"] = primary["n_peers"]
    m["n_banks"] = stints.groupby("machine_id")["bank_id"].nunique()
    m = m.reset_index()

    attrs = base.sort_values("gaming_date").groupby("machine_id")[["config_id", "theme"]].last().reset_index()
    m = m.merge(attrs, on="machine_id")
    m = m.merge(banks[["bank_id", "zone_id", "zone_name", "tpah", "bank_rank", "bank_quartile", "zone_tpah"]]
                .rename(columns={"tpah": "bank_tpah"}), on="bank_id")
    m = m.merge(games[["config_id", "zone_id", "zone_index", "game_floor_tpah", "game_elsewhere_tpah"]]
                .rename(columns={"zone_index": "game_zone_index"}), on=["config_id", "zone_id"], how="left")
    m["floor_tpah"] = summarize(base).iloc[0]["tpah"]

    m["thin_peer_group"] = m["n_peers"] < THIN_PEERS
    m["location_flag"] = (m["bank_quartile"] == 1) & m["peer_index"].between(1 - PEER_BAND, 1 + PEER_BAND)
    m["machine_flag"] = m["peer_index"] < MACHINE_PEER_INDEX
    # The plan's machine flag compares theo, so a game that keeps less per bet (high RTP) trips it even when
    # players use it as much as its neighbours. Separate that case: weak on theo, normal on volume.
    m["low_hold_game"] = m["machine_flag"] & (m["volume_peer_index"] >= 1 - PEER_BAND)
    m["location_read"] = np.select([m["low_hold_game"], m["machine_flag"], m["location_flag"]],
                                   ["low-hold game", "machine", "location"], "")
    m["in_manager_10"] = m["machine_id"].isin(manager_ids)
    return m.sort_values("peer_index").reset_index(drop=True), banks, games


def floor_map_figure(banks: pd.DataFrame) -> go.Figure:
    floor = load("floor_locations")
    zones = floor[floor["node_type"] == "zone"].set_index("zone_id")
    entrances = floor[floor["node_type"] == "entrance"]
    walkways = load("floor_walkways")

    fig = go.Figure()
    for _, w in walkways.iterrows():
        a, b = zones.loc[w["zone_a"]], zones.loc[w["zone_b"]]
        closed = pd.notna(w["closed_from_utc"])
        fig.add_trace(go.Scatter(x=[a["x_m"], b["x_m"]], y=[a["y_m"], b["y_m"]], mode="lines", showlegend=False,
                                 line={"color": COLORS["critical"] if closed else COLORS["grid"], "width": 3 if closed else 6,
                                       "dash": "dash" if closed else "solid"}, hoverinfo="skip"))
        if closed:
            # 60% of the way along the walkway: in the gap between the zone label and the first banks.
            fig.add_annotation(x=a["x_m"] + 0.6 * (b["x_m"] - a["x_m"]), y=a["y_m"] + 0.6 * (b["y_m"] - a["y_m"]),
                               # Gaming dates, as on every other page: closed_to is exclusive, so the last closed day is the day before.
                               text=(f"⚠ walkway closed<br>{to_gaming_date(w['closed_from_utc']):%b %-d}–"
                                     f"{to_gaming_date(w['closed_to_utc']) - pd.Timedelta(days=1):%b %-d} ({w['closure_reason']})"),
                               showarrow=False, xanchor="right", xshift=-8, align="right",
                               font={"size": 12, "color": COLORS["text"]})

    ring = np.where(banks["manager_10_machines"] > 0, COLORS["series_2"], COLORS["surface"])
    width = np.where(banks["manager_10_machines"] > 0, 3, 1.5)
    fig.add_trace(go.Scatter(
        x=banks["x_m"], y=banks["y_m"], mode="markers", showlegend=False,
        marker={"size": 18, "color": banks["tpah"], "colorscale": SEQUENTIAL_BLUE, "line": {"color": ring, "width": width},
                "colorbar": {"title": {"text": "TPAH<br>$ / available h", "side": "top"}, "thickness": 12, "len": 0.6,
                             "outlinewidth": 0, "tickprefix": "$"}},
        customdata=banks[["bank_id", "zone_name", "tpah", "occupancy", "machines", "bank_rank", "manager_10_machines"]].to_numpy(),
        hovertemplate=("<b>%{customdata[0]}</b> · %{customdata[1]}<br>TPAH $%{customdata[2]:.2f} per available hour"
                       "<br>occupancy %{customdata[3]:.0%} · %{customdata[4]} machines"
                       "<br>rank %{customdata[5]} of " + str(len(banks)) + " (1 = lowest)"
                       "<br>manager's 10 here: %{customdata[6]}<extra></extra>")))
    fig.add_trace(go.Scatter(x=[None], y=[None], mode="markers", name="Bank holds one of the manager's 10",
                             marker={"size": 14, "color": COLORS["surface"], "line": {"color": COLORS["series_2"], "width": 3}}))
    fig.add_trace(go.Scatter(x=entrances["x_m"], y=entrances["y_m"], mode="markers", name="Entrance",
                             text=entrances["name"],
                             marker={"symbol": "triangle-up", "size": 13, "color": COLORS["text_secondary"]},
                             hovertemplate="%{text}<extra></extra>"))
    # Entrance labels on short leader lines; the hotel lobby sits among banks, so its label goes down-left.
    for _, e in entrances.iterrows():
        ax, ay = (-70, 42) if e["name"] == "Hotel lobby" else (0, 26)
        fig.add_annotation(x=e["x_m"], y=e["y_m"], ax=ax, ay=ay, text=e["name"], showarrow=True, arrowhead=0,
                           arrowwidth=1, arrowcolor=COLORS["neutral"], font={"size": 11, "color": COLORS["text_secondary"]})
    for zone_id, group in banks.groupby("zone_id"):
        fig.add_annotation(x=group["x_m"].mean(), y=group["y_m"].max() + 7, text=f"<b>{group['zone_name'].iloc[0]}</b>",
                           showarrow=False, font={"size": 12, "color": COLORS["text"]})

    weakest = banks[banks["bank_quartile"] == 1]
    top_zone = weakest["zone_name"].value_counts()
    style(fig, f"{top_zone.index[0]} holds {int(top_zone.iloc[0])} of the {len(weakest)} weakest banks "
               f"(bottom quarter by play value)",
          "Each dot is a bank, coloured by theo per available hour (darker = more play value). Floor coordinates in metres.",
          height=640)
    fig.update_xaxes(visible=False, range=[-12, 145])
    fig.update_yaxes(visible=False, scaleanchor="x", scaleratio=1, range=[-12, 118])
    fig.update_layout(legend={"y": -0.02, "yanchor": "top", "x": 0, "xanchor": "left"})
    return fig


def main() -> None:
    args = window_args("A5 location test")
    location, banks, games = compute(load_base(args.start, args.end))
    write_output("a5_location", location)
    write_output("bank_scores", banks)
    write_output("a5_game_by_zone", games)
    save(floor_map_figure(banks), "a5_floor_map")

    print("\nZones by TPAH:")
    zones = banks.groupby(["zone_id", "zone_name"]).agg(zone_tpah=("zone_tpah", "first"), banks=("bank_id", "size"),
                                                        bottom_quarter_banks=("bank_quartile", lambda q: int((q == 1).sum())))
    print(zones.sort_values("zone_tpah").to_string(float_format=lambda v: f"{v:,.2f}"))
    print("\nThe manager's 10:")
    cols = ["machine_id", "zone_name", "bank_id", "theme", "expected_hold", "tpah", "bank_peer_tpah", "peer_index",
            "volume_peer_index", "bank_quartile", "game_zone_index", "game_elsewhere_tpah", "location_read"]
    print(location[location["in_manager_10"]][cols].to_string(index=False, float_format=lambda v: f"{v:,.2f}"))
    reads = location["location_read"].replace("", "none").value_counts().to_dict()
    print(f"\nFloor-wide reads: {reads}. {int(location['machine_flag'].sum())} machines have peer index < "
          f"{MACHINE_PEER_INDEX}, of which {int(location['low_hold_game'].sum())} are low-hold games with normal volume; "
          f"{int(location['thin_peer_group'].sum())} with fewer than {THIN_PEERS} peers")
    print("Wrote outputs/a5_location.parquet, bank_scores.parquet, a5_game_by_zone.parquet, charts/a5_floor_map")


if __name__ == "__main__":
    main()
