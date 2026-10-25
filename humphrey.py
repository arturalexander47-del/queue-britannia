"""Sir Humphrey and the tabloids. Jokes punch at the system and politicians only,
never at defendants, victims or witnesses.

Optional: set ANTHROPIC_API_KEY to have Claude write fresh lines from the numbers.
"""
import os
import random

COURAGEOUS = [
    "A very courageous decision, Minister.",
    "Bold, Minister. Some might even say... brave.",
    "I'm sure the Treasury will be thrilled, Minister.",
]
APPROVING = [
    "Masterly inactivity, Minister. The finest tradition of the Department.",
    "An excellent decision, Minister. Nobody will notice anything at all.",
]
WORRIED = [
    "Minister, the prisons are full. Again. I've taken the liberty of drafting your resignation letter. Just in case.",
    "The good news, Minister, is that the backlog is no longer growing. The bad news is that it's because there's nowhere left to put anyone.",
]
FASTER_COURTS_FULLER_PRISONS = [
    "Congratulations, Minister. You've sped up the courts so much that the prisons are now full sooner. Joined-up government at last.",
]

HEADLINES = {
    "overbooking": ["COURTS GO RYANAIR: Trials now 'overbooked' like budget flights",
                    "JUSTICE, NOW WITH SPEEDY BOARDING"],
    "early_release": ["DOORS OPEN: Minister says 'see you later' to lags",
                      "EARLY RELEASE: Minister insists it's 'just a long weekend'"],
    "nightingale": ["POP-UP COURTS: Justice served in a conference centre near you",
                    "NIGHTINGALE COURTS RETURN: 'Like the Bake Off tent, but for burglary'"],
    "sitting_days": ["JUDGES TOLD: Cancel the golf",
                     "WIGS ON OVERTIME: Minister orders more sitting days"],
    "fixes": ["BARRISTERS FOUND: Minister locates lawyers down back of sofa",
              "TRIAL BY ZOOM: 'You're on mute, m'lud'"],
    "prisons": ["CONCRETE PLANS: Minister orders prisons, hopes they'll be ready by Christmas",
                "BUILD BABY BUILD: Cranes spotted near Wormwood Scrubs"],
    "nothing": ["MINISTER DOES NOTHING, BACKLOG GROWS: Experts 'not surprised'",
                "STATUS QUO: Still the Department's favourite policy"],
}

EVENT_HEADLINES = {
    "Barrister strike": "WIGS DOWN! Barristers walk out, trials grind to halt",
    "Police charging surge": "COPPERS ON A ROLL: Charging surge floods the courts",
    "Tough new sentencing law": "LOCK 'EM UP LONGER: MPs pass tough new law, forget to build prisons",
    "Crumbling prison wing closed": "CRUMBLING CRISIS: Prison wing closed after ceiling 'makes a run for it'",
    "Treasury windfall": "KERCHING! Treasury finds cash down the back of the Whitehall sofa",
    "Juror shortage": "WHERE ARE THE TWELVE? Nation suddenly 'very busy' on jury day",
}
LOSS_HEADLINES = {
    "Prisons full": "NO ROOM AT THE INN: Prisons full, Minister out",
    "Sacked in the reshuffle": "YOU'RE FIRED: PM wields axe in late-night reshuffle",
}


def front_page(action, events, lost_reason=""):
    """(headline, deck) for the newspaper shown between quarters."""
    if lost_reason:
        return LOSS_HEADLINES.get(lost_reason, lost_reason.upper()), "Sources close to the Minister say they 'saw it coming'."
    keys = []
    if action.early_release:
        keys.append("early_release")
    if action.overbook:
        keys.append("overbooking")
    if action.rooms:
        keys.append("nightingale")
    if action.funds:
        keys.append("fixes")
    if action.places:
        keys.append("prisons")
    mine = random.choice(HEADLINES[random.choice(keys) if keys else "nothing"])
    if events:
        return EVENT_HEADLINES.get(events[0], events[0].upper()), "Also inside: " + mine
    head, _, deck = mine.partition(": ")
    return head, deck or "Whitehall sources 'deeply relaxed'."


def _llm_line(summary):
    try:
        import anthropic
        client = anthropic.Anthropic()
        msg = client.messages.create(
            model="claude-sonnet-5-5",
            max_tokens=120,
            messages=[{"role": "user", "content": (
                "You are Sir Humphrey Appleby from Yes, Minister, advising the UK Justice Secretary. "
                "In one or two dry, witty sentences, react to these simulation results. "
                "Mock the system and politicians, never defendants, victims or witnesses.\n\n" + summary)}],
        )
        return msg.content[0].text.strip()
    except Exception:
        return None


def react(levers, base_weeks_to_full, new_weeks_to_full, backlog_change_pct):
    changed = []
    if levers.overbooking_uplift > 0:
        changed.append("overbooking")
    if levers.release_point < 0.5:
        changed.append("early_release")
    if levers.nightingale_rooms > 0:
        changed.append("nightingale")
    if levers.sitting_days_pct > 0:
        changed.append("sitting_days")
    if getattr(levers, "fix_uplift", 0) > 0:
        changed.append("fixes")
    headline = random.choice(HEADLINES[random.choice(changed) if changed else "nothing"])

    if os.environ.get("ANTHROPIC_API_KEY"):
        summary = (f"Policies: {', '.join(changed) or 'none'}. Backlog change after 3 years: {backlog_change_pct:+.0f}%. "
                   f"Weeks until prisons full: before {base_weeks_to_full}, after {new_weeks_to_full}.")
        line = _llm_line(summary)
        if line:
            return line, headline

    if not changed:
        line = random.choice(APPROVING)
    elif (new_weeks_to_full is not None and base_weeks_to_full is not None
          and new_weeks_to_full < base_weeks_to_full and backlog_change_pct < 0):
        line = random.choice(FASTER_COURTS_FULLER_PRISONS)
    elif new_weeks_to_full is not None and new_weeks_to_full < 8:
        line = random.choice(WORRIED)
    else:
        line = random.choice(COURAGEOUS)
    return line, headline


def career_survival(backlog_change_pct, weeks_to_full, cost_gbp):
    """0-100 'chance you survive the next reshuffle'. Pure satire."""
    score = 60 - 0.8 * backlog_change_pct
    if weeks_to_full is not None:
        score -= max(0, 26 - weeks_to_full)
    score -= cost_gbp / 5e7
    return int(max(0, min(100, score)))


def react_quarter(action, backlog_change, occupancy):
    """Sir Humphrey's line for the morning paper after a game quarter. Returns (line, None)."""
    if occupancy > 0.985:
        return random.choice(WORRIED), None
    if action.cost() == 0 and not action.early_release and not action.overbook:
        return random.choice(APPROVING), None
    if backlog_change < 0 and occupancy > 0.96:
        return random.choice(FASTER_COURTS_FULLER_PRISONS), None
    return random.choice(COURAGEOUS), None
