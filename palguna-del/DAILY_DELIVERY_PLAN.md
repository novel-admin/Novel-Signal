# Palguna Daily Delivery Plan

## Monday, 24 August

- Confirm final scorecard dimensions and shared contracts with Akanksh.
- Verify Amazon Ads credentials, profiles, region and current report permissions.
- Update the Amazon Ads client/report flow with mocked tests.
- Define S11 alert models and S9 calculation interfaces without duplicating source models.

End-of-day proof:

- Amazon Ads connection verifies.
- One report request can be created or one live resource can be fetched.
- Shared payload examples are agreed with Akanksh.

## Tuesday, 25 August

- Complete Amazon Ads report polling, raw evidence storage and normalization.
- Publish search terms to Akanksh's S2 import boundary.
- Consume sponsored SERP fixtures for competitor ad presence.
- Complete S4 daily presence and daypart calculations.

End-of-day proof:

- Novel search-term performance is measured from a live report.
- Competitor sponsored presence can be derived from a published SERP capture.
- Reprocessing creates no duplicates.

## Wednesday, 26 August

- Complete review velocity, rating trajectory and topic trend calculations.
- Build the practical S8 model gate and confidence ranges.
- Implement automatic scorecard calculations for available dimensions.
- Start the S4, S7 and S9 screens.

End-of-day proof:

- One SKU battle card shows measured review and ad metrics.
- Scorecards show unknown for missing data instead of zero.
- Any estimate shows model version and confidence range.

## Thursday, 27 August

- Generate gaps from scorecards and changes.
- Add recommended playbook actions and priority ranking.
- Implement alert rules, deduplication and war-room APIs.
- Connect gaps to actions and actions to impact tracking.
- Replace the static overview with live summary APIs.

End-of-day proof:

- A real or golden published observation creates a score change, gap, action and alert.
- Every output links back to evidence.
- Duplicate processing does not duplicate alerts or open actions.

## Friday, 28 August

- Finish overview, S4, S7, S8, S9 and S11 screens.
- Integrate Akanksh's live published data.
- Run PostgreSQL migrations and all test suites.
- Run the full user acceptance path.
- Separate live, fixture-only and unavailable capabilities in the release report.
- Fix release blockers and prepare the product for users.

Final proof:

- Users can compare every configured Novel SKU with mapped competitors.
- Users can see rank, search, price, listing, review, ad and availability differences where data is available.
- Users can inspect evidence and act on important gaps.

## Daily coordination

- 10:00: review schema and API changes with Akanksh.
- 14:00: test the newest published payloads.
- 18:00: demonstrate the day's user-visible flow and report blockers plainly.

Palguna is the final integration owner, but must not silently change Akanksh-owned schemas.
