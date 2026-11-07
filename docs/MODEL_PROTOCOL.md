# Forecast model protocol (task M1)

Frozen before any model code was written. The git commit that adds this file is the timestamp.
Changing anything here after seeing test results would invalidate the evaluation.

## Question and target

- **Target:** daily floor coin-in in dollars, `property_day.coin_in_usd`, one value per gaming day.
- **Decision it serves:** for the 30-day budget horizon (July 1-30, 2025), which days and shifts are busiest (where an extra technician or attention matters most) and which weekend is weakest (where a promotion has the most room to add play).

## Time split (no random splits)

| Set | Gaming dates | Use |
| --- | --- | --- |
| Model selection: fit | 2025-01-01 to 2025-03-31 | Fit every candidate |
| Model selection: validate | 2025-04-01 to 2025-04-30 | Choose ONE candidate by mean absolute error (MAE) |
| Final fit | 2025-01-01 to 2025-04-30 | Refit the chosen candidate and both baselines |
| Test | 2025-05-01 to 2025-06-30 | Evaluated exactly once |

Every test-day forecast is made **as of April 30**: no May-June actual is used as an input, directly or through
lag features. The test set is used once; if the model loses to a baseline, we report that.

## Allowed inputs (known on April 30, 2025)

- Weekday of the gaming date.
- US federal holidays (`calendar_day.federal_holiday`; July 4 for the July forecast).
- Events from `events` with `announced_date <= 2025-04-30`, as two indicators fixed here in advance:
  `citywide_event` (any `local_scope = citywide` event day) and `property_promotion` (any `local_scope = property`
  event day). Event types are pooled on purpose: choosing categories after looking at uplifts (task B2 uses all six
  months) would leak test information. **Gilded Ace Locals Appreciation Week (Jun 9-15) was announced May 26, so it
  is NOT an input to the May-June forecast.** EDC (May 16-18, announced 2024) is.
- The walkway closure (Mar 3-Apr 6), a scheduled renovation, as a training-period indicator so it does not bias the
  other coefficients. It is 0 in the test period.
- A linear time trend.

## Not allowed

Tourism (LVCVA) and survey data (published later), actual weather, anything dated after April 30, test-period actuals,
and any feature computed from them.

## Candidates

- **Baseline A:** the training-period daily mean, as a constant.
- **Baseline B:** the training-period mean for each weekday.
- **Candidate 1:** Baseline B times a linear trend (multiplicative).
- **Candidate 2:** linear regression of log(coin-in) on weekday + holiday + citywide_event + property_promotion +
  closure + trend.

Choose the candidate with the lower April MAE. If a candidate does not beat Baseline B in April, Baseline B is the
model. A tie (within 1%) goes to the simpler model.

## Reporting

MAE (dollars), MAPE, and bias (mean of forecast - actual) for the model and both baselines on May-June; MAE by
weekday; a chart of actuals against forecasts with event days marked. Then refit on January-June and forecast
July 1-30 for the decision.
