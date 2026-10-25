"""Model assumptions. Every value marked PLACEHOLDER must be replaced with a
figure from an MoJ/HMCTS publication before the demo (and cited on screen 4)."""

# Courts
NIGHTINGALE_DISPOSALS_PER_ROOM = 220  # PLACEHOLDER: case disposals a year one extra courtroom adds
                                      # (~220 sitting days x ~1 disposal per sitting day; check HMCTS figures)
BUMP_PENALTY = 1.5                # cost of bumping one trial, in "trial slots" (minister sets risk appetite)

# Prisons
AVG_CUSTODY_WEEKS = 52.0          # PLACEHOLDER: average weeks served by sentenced prisoners (at 50% release)
BASE_RELEASE_POINT = 0.50         # standard automatic release point for the model's baseline

# Costs (all PLACEHOLDERS: set from published MoJ unit costs)
COST_PER_SITTING_DAY_GBP = 0
COST_PER_NIGHTINGALE_ROOM_YEAR_GBP = 0
COST_PER_PRISON_PLACE_YEAR_GBP = 0

# Simulation
HORIZON_WEEKS = 156               # 3 years
N_RUNS = 300
RECEIPTS_NOISE_SD = 0.08          # weekly log-noise on receipts
SEED = 7

# Fixes aimed at the recorded reasons trials don't go ahead (MoJ trial effectiveness reasons).
# "reduction" = share of those ineffective trials the fix would prevent: an ASSUMPTION the
# minister can change. Costs are PLACEHOLDERS until sourced.
FIXES = {
    "More barristers": dict(
        patterns=["advocate failed to attend", "advocate engaged in"],
        reduction=0.5, cost_per_year_gbp=0,
        note="More criminal barristers available, so trials don't collapse for lack of an advocate"),
    "Video links": dict(
        patterns=["not produced by prisoner escort", "witness absent"],
        reduction=0.3, cost_per_year_gbp=0,
        note="Defendants and witnesses can appear by video when transport or travel fails"),
    "Better case preparation": dict(
        patterns=["not ready", "failed to disclose", "late notice of additional evidence"],
        reduction=0.3, cost_per_year_gbp=0,
        note="Funding for CPS and legal aid so both sides are ready on the day"),
}
