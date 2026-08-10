# The $58k That Wasn't

*Second post in a series about ercot-rtcb-bench, an open benchmark I'm building for battery bidding in the Texas power market. The [first post](#) introduced the benchmark. This one covers what happened when I tried to cash in its two biggest findings.*

## Some quick background

Texas runs its power grid through a market called ERCOT. In December 2025, ERCOT switched to a new market design (RTC+B) that changes how batteries buy and sell. A battery in this market earns money two ways: energy arbitrage (charge when power is cheap, discharge when it's expensive) and ancillary services, or "AS" (getting paid to hold capacity in reserve for grid emergencies). Every five minutes, prices update, and a bidding strategy has to decide what to do with limited battery capacity.

My benchmark tests bidding strategies on real market data. The strategy at the center of this post is a stochastic optimizer: it takes price forecasts, considers many possible price scenarios, and picks the bid plan with the best expected revenue. On my test week (April 20 to 26, 2026), it earned $238,376.

To see how much better it could do, I also ran a version with perfect knowledge of future prices. That version earned $351,612. The gap between the two, about $113,000, is what a perfect forecaster would be worth for that week. The question driving this post: how much of that gap can a realistic forecast improvement actually capture?

## Two promising targets

In an earlier phase of the project I broke that $113k gap into pieces, by swapping in true prices one component at a time and measuring the change. Two pieces stood out:

- **AS price errors: $36,393.** The forecasts of ancillary service prices were off, and fixing only those recovered $36k.
- **An evening price bias: $21,479.** The energy price forecast ran about $48/MWh too low during the 7 to 8pm peak on the test week.

Together, about $58k of measured forecast error with dollar values attached. If you run batteries for a living, you know how tempting that looks.

One caveat was attached from the start. These numbers are ceilings. They measure the value of replacing the forecast with the truth. A real forecaster only gets part of the way there. The work described below was an attempt to find out how big that part is.

## The first fix: worked once, then didn't

I started with the bigger target, the $36k of AS price error.

Digging into the code revealed something surprising: the system had no real AS price forecaster. It simply took the day-ahead market's own AS prices as its prediction and added some historical noise. Measuring the errors showed a clear pattern. The day-ahead prices ran too high, and almost all of the overshoot happened in a small number of tight, high-demand hours. Ordinary hours were fine.

So I built a small correction: when day-ahead AS prices spike above their normal range, shrink them toward it. Four fitted parameters total, chosen to cancel the measured overshoot on training data.

On the test week, this correction earned an extra **$18,271. Half the theoretical ceiling, from four parameters.**

I almost shipped that result. It had everything: a measured target, a simple fix, a mechanism that made sense. What stopped me was a rule I had written down earlier, before seeing any of these numbers: the gain came almost entirely from one day (April 25, a scarcity day worth +$18.7k on its own), the same week had two losing days, and my own decision log said no claims until the result repeats on new data.

So I tested it on three more weeks, chosen by a rule fixed in advance (the week with the most scarcity, the week with the least, and one more high-scarcity week), with the correction frozen exactly as fitted:

| Week | Result of the correction |
|---|---:|
| Apr 20–26 (original test week) | +$18,270 |
| Apr 27–May 3 (high scarcity) | +$6,303 |
| Jun 1–7 (highest scarcity) | **−$4,765** |
| May 4–10 (calm) | **−$10,619** |

Two of the three new weeks lost money. Worse, the week with the *most* scarcity lost money, and that is exactly where a genuine fix should have helped most.

The reason became clear in the details. The day-ahead market's high AS prices are a prediction that scarcity is coming. Sometimes scarcity arrives and those prices are justified. Sometimes it doesn't and they were too high. My correction assumed they were always too high. In weeks where scarcity failed to materialize, that assumption paid off. In weeks where scarcity showed up for real, the correction made the battery hold back exactly when reserves were most valuable. It was never a fix. It was a bet, and it wins or loses depending on the week.

I retired it.

## The second fix: killed before it was built

Next in line was the evening price bias, the $21.5k target. It had the same shape as the first one: a measured error, concentrated in a few hours, inviting a simple correction.

This time I ran a cheap check first. I now had seven weeks of clean data, so before building anything, I measured the evening bias on every week separately.

It flipped sign. Four weeks the forecast was too low, three weeks too high. Averaged across weeks, the bias was $0.82/MWh, essentially zero. The scary −$48/MWh figure came from one day on the original test week. That day was April 25. The same scarcity day that had propped up the first fix.

One afternoon of measurement, and the second correction was dead before I wrote a line of it.

## What was actually going on

Both fixes failed the same way, and the common cause is worth spelling out.

My original test week contained one severe scarcity day. On that day, forecasts of every kind missed badly, because the forecasts didn't know scarcity was coming. When I decomposed the $113k gap, that single day's misses showed up in the arithmetic as large, specific-looking "biases": AS prices too high, evening energy prices too low. The decomposition was correct, but what it measured wasn't a steady error you can subtract out. It was mostly the value of knowing, in advance, whether a scarcity event will happen. That knowledge has a name in decision theory, the expected value of perfect information, and no after-the-fact price adjustment can buy it.

This changed the project's direction. The forecaster roadmap used to be a list of bias corrections. Now it is one harder question: can you predict, from information available ahead of time, how likely scarcity is to actually materialize?

## Why this matters beyond my benchmark

Battery revenue in ERCOT concentrates on scarcity days. Scarcity days are rare and irregular. Put those together and any single backtest window is heavily shaped by its scarcity luck, which means a bidding improvement measured on one window is partly, sometimes mostly, an artifact of that window. My correction recovered 50% of a measured ceiling on one week and lost money over four.

Nothing that caught this was clever. The replication requirement was written into my decision log before the test result existed. The extra test weeks were picked by a fixed rule, so I couldn't choose flattering ones. The correction was frozen before retesting. The pass/fail criteria were written down in advance. This is ordinary scientific hygiene, and it is still uncommon in how bidding strategies get evaluated. If a vendor shows you an improvement measured on one favorable window, this post is the reason to ask for the other windows.

## Honest limits

All of this rests on seven weeks of data from April to June 2026, the first months of the new market design. Summer scarcity in Texas is a different beast, and whether these findings hold there is an open question I plan to test now that summer data exists.

Everything is reproducible: code and decision records are in the [GitHub repo](https://github.com/karthikmattu06-hue/ercot-rtcb-bench), and the exact dataset behind every number here is archived at Zenodo ([10.5281/zenodo.21178739](https://doi.org/10.5281/zenodo.21178739)).

*Baseline figures: stochastic bidder $238,376 on the April test week, later restated to $238,378.80 after a data rebuild documented in the repo; perfect-foresight bound $351,612.*
