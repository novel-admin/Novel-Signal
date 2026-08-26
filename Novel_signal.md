

**NOVEL SIGNAL**

**COMPETITIVE INTELLIGENCE**

Competitive Intelligence & Performance Benchmarking Module

**Novel BOS — Module M15 | Specification v1.0**

| **Document owner** | AP, Founder — Novel Tissues Private Limited              |
| ------------------ | -------------------------------------------------------- |
| **Build lead**     | Sumukha — Technology                                     |
| **Consumers**      | Category & Brand · Digital Marketing · Channel KAMs · QA |
| **Status**         | Approved for build — handover document                   |
| **Classification** | Internal — confidential                                  |

**Contents**

**0\. OBJECTIVES**

0.1 The five questions the system must answer, on demand

0.2 Success metrics

**1\. SCOPE**

1.1 Platforms in scope

1.2 Categories in scope

1.3 Sub-modules

1.4 Where this sits in BOS

**2\. DATA SOURCING — READ THIS FIRST**

2.1 Source tiers, in order of preference

2.2 Collection conduct — binding constraints

2.3 What is measured versus what is estimated

**3\. UNIVERSE & COMPETITOR SETUP — S1**

3.1 Competitor master

3.2 Tracked entity registry

3.3 Battle cards — the SKU-to-SKU mapping

3.4 Auto-discovery

3.5 Tracking tiers — control the cost

**4\. KEYWORD INTELLIGENCE — S2**

4.1 Building the keyword universe

4.2 Keyword attributes

4.3 Clustering by intent

4.4 Share of Voice

4.5 Keyword gap analysis

**5\. RANK & VISIBILITY TRACKING — S3**

5.1 Hourly SERP capture

5.2 Geo matters

5.3 Derived visibility metrics

5.4 Our own rank, from the same capture

**6\. AD INTELLIGENCE — S4**

6.1 What we can actually see

6.2 Ad presence tracking

6.3 Daypart and budget-behaviour inference

6.4 Creative capture

6.5 Ad spend estimation — with honesty built in

6.6 Our own ad performance, side by side

**7\. LISTING & CONTENT INTELLIGENCE — S5**

7.1 Snapshot and diff engine

7.2 Why the diff log is the most underrated feature here

7.3 Content quality scoring

7.4 Claim and compliance watch

**8\. PRICE, PROMO & OFFER INTELLIGENCE — S6**

8.1 Captured hourly

8.2 Derived

8.3 Availability tracking

**9\. REVIEW & VOICE-OF-CUSTOMER — S7**

9.1 Captured

9.2 Derived

9.3 Two outputs that matter

**10\. SALES & SHARE ESTIMATION — S8**

10.1 The calibration advantage

10.2 Outputs

**11\. THE BENCHMARKING SCORECARD — S9**

11.1 Structure

11.2 The seven dimensions

11.3 The four views AP should be able to open at any hour

11.4 Revenue at stake — the ranking mechanism

11.5 Trend, not snapshot

**12\. GAP & ACTION ENGINE — S10**

12.1 Gap generation

12.2 Root cause classification

12.3 Recommended actions

12.4 Action lifecycle

12.5 Governance

**13\. ALERTING & WAR ROOM — S11**

13.1 Threat alerts

13.2 Opportunity alerts

13.3 Delivery

13.4 War room board

**14\. DASHBOARDS**

**15\. TECHNICAL ARCHITECTURE — S12**

15.1 Layers

15.2 Collection specifics

15.3 Parser resilience — the real maintenance cost

15.4 Storage sizing — do the arithmetic before building

15.5 Data quality framework

**16\. CORE DATA MODEL (indicative)**

**17\. PHASED DELIVERY**

**18\. ACCEPTANCE CRITERIA**

**19\. RISKS**

**20\. WHAT I NEED FROM THE TEAM**

**21\. ONE HONEST RECOMMENDATION**

### **Purpose in one line**

An internal Helium 10 — but built for us, wired into our own first-party data, and pointed at one question every hour of every day: **where do we stand against the competition right now, what are we losing, why, and what do we do about it today.**

Commercial tools tell you what a market looks like. They cannot tell you where _you_ are lacking, because they do not have your cost, margin, inventory, ad spend or conversion data. Novel Signal does, because it sits inside BOS next to the SCM module. That is the entire reason to build rather than buy.

## **0\. OBJECTIVES**

### **0.1 The five questions the system must answer, on demand**

1. **What are they doing?** Every competitor SKU we care about — price, content, offers, badges, stock, ratings, new launches — captured continuously with a full change history.
2. **How are they doing it?** Which keywords they rank on organically, which they buy, how aggressively, at what hours, with what creative, and how their content and pricing differ from ours.
3. **How long have they been advertising?** Continuous ad-presence days per competitor per keyword per platform, plus off-platform ad run dates from public ad libraries.
4. **Where do we stand?** An hourly scorecard per SKU, per keyword, per platform — our position versus theirs, on visibility, price, content, reviews, availability and ad presence.
5. **What do we do about it?** Every gap converted into a ranked, owned, dated action with the revenue at stake attached, tracked to closure, with before/after impact measured.

### **0.2 Success metrics**

| **Metric**                                                     | **Target**                              |
| -------------------------------------------------------------- | --------------------------------------- |
| Tracked keyword coverage of category search volume             | ≥ 80%                                   |
| SERP capture success rate (scheduled vs successfully captured) | ≥ 98%                                   |
| Data freshness for Tier-1 keywords                             | ≤ 60 minutes                            |
| Competitor price-change detection latency                      | ≤ 2 hours                               |
| Competitor new-SKU detection latency                           | ≤ 24 hours                              |
| Share of Voice on Tier-1 keywords (Novel brands)               | Baseline now, +X% at 6 months           |
| Keyword gaps closed per month                                  | Tracked, trending up                    |
| Actions generated → actions closed                             | ≥ 70% closure within SLA                |
| Measured rank improvement on actioned keywords                 | ≥ 60% of actions show positive movement |
| Time from "competitor went out of stock" to our response       | < 4 hours                               |

## **1\. SCOPE**

### **1.1 Platforms in scope**

Amazon.in (priority 1), Flipkart, Meesho, Blinkit, Zepto, Swiggy Instamart, BigBasket, Tata 1mg, FirstCry, and our own Shopify D2C. Off-platform: Meta (Facebook/Instagram), Google/YouTube, and organic social.

### **1.2 Categories in scope**

Baby care (diapers, pants, wipes, bath and skincare), adult personal care, incontinence, perfumes/fragrance. Structured so a new category is a configuration change, not a code change.

### **1.3 Sub-modules**

| **Code** | **Sub-module**                        | **What it owns**                                                                                    |
| -------- | ------------------------------------- | --------------------------------------------------------------------------------------------------- |
| S1       | **Universe & Competitor Setup**       | Competitor master, SKU battle-card mapping, category tree, tracked-entity registry                  |
| S2       | **Keyword Intelligence**              | Keyword universe, volume, clustering, reverse-ASIN, gap analysis                                    |
| S3       | **Rank & Visibility Tracking**        | Hourly SERP capture, organic rank, BSR, badges, Share of Voice                                      |
| S4       | **Ad Intelligence**                   | Sponsored placement capture, ad-presence days, daypart patterns, creative capture, spend estimation |
| S5       | **Listing & Content Intelligence**    | Full listing snapshots, diff engine, content-quality scoring                                        |
| S6       | **Price, Promo & Offer Intelligence** | Price/MRP/discount/coupon/deal history, promo calendar reconstruction                               |
| S7       | **Review & Voice-of-Customer**        | Review velocity, rating trajectory, complaint and praise topic mining                               |
| S8       | **Sales & Share Estimation**          | BSR-to-units model, category sizing, market share                                                   |
| S9       | **Benchmarking Scorecard**            | Where we stand — us versus them, every dimension, every hour                                        |
| S10      | **Gap & Action Engine**               | Gaps quantified and ranked, actions assigned, closure and impact tracking                           |
| S11      | **Alerting & War Room**               | Threat and opportunity alerts, escalation, live response board                                      |
| S12      | **Collection Infrastructure**         | Scheduler, browser farm, proxies, parsers, dedup, data-quality monitoring                           |

### **1.4 Where this sits in BOS**

Novel Signal is a BOS module and reads from the same platform layer as SCM: shared auth, roles, audit trail, alerting and notification engine. It **consumes** SCM data (our stock position, our landed cost, our margin) and **feeds** SCM (demand signals, competitor stock-out windows that spike our demand, NPD opportunities). The existing rank-tracking automation is absorbed into S3 — it becomes the seed, not a parallel system.

## **2\. DATA SOURCING — READ THIS FIRST**

This section governs the whole build. Get it wrong and we build something that breaks weekly, or that creates legal exposure.

### **2.1 Source tiers, in order of preference**

**Tier 1 — First-party APIs (our own data, full fidelity, always use where available)**

| **Source**                    | **Gives us**                                                                                                                                                                                    |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Amazon SP-API                 | Our orders, inventory, pricing, listings, fees, returns                                                                                                                                         |
| **Amazon Ads API**            | Our campaigns, keywords, bids, spend, impressions, clicks, ACOS, search-term reports                                                                                                            |
| **Amazon Brand Analytics**    | Search Query Performance, Top Search Terms with share data, Market Basket, Repeat Purchase — _the single richest legitimate keyword dataset available to us, and most competitors under-use it_ |
| Flipkart / Meesho seller APIs | Our sales, listings, ads                                                                                                                                                                        |
| Shopify Admin API + GA4       | D2C traffic, conversion, search terms                                                                                                                                                           |
| Meta / Google Ads APIs        | Our off-platform spend and performance                                                                                                                                                          |

**Tier 2 — Licensed third-party data (buy, don't build)**

| **Source**                            | **Gives us**                                                                                                                                                              |
| ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Helium 10 / Jungle Scout / Keepa APIs | Keyword volume estimates, historical BSR and price, reverse-ASIN                                                                                                          |
| **Meta Ad Library API**               | Competitor ad creative, format, and **exact run start/stop dates** — public, official, free. This is how we answer "how many days are they advertising" without guessing. |
| **Google Ads Transparency Center**    | Competitor Google/YouTube ad creative and run dates                                                                                                                       |
| SimilarWeb / Semrush                  | Competitor site traffic, D2C search visibility                                                                                                                            |
| GST / e-way bill public data          | B2B movement (we have already proven this approach on distributor targeting)                                                                                              |

**Tier 3 — Public page collection (build carefully, use last)**

Public, logged-out marketplace pages: search results, product detail pages, category bestseller pages, brand stores. This is where SERP rank, sponsored placements, live price and stock come from — no API provides them.

### **2.2 Collection conduct — binding constraints**

These are design constraints, not preferences. Build them into the collector:

1. **Official API first, always.** Never collect by page what an API will give us.
2. **Public, logged-out pages only.** Never collect from behind a login, never use another party's account, never touch personal data of reviewers beyond the public display name.
3. **Never bypass CAPTCHA or bot-detection.** If a platform challenges us, the collector backs off and reports a collection failure. It does not solve the challenge. A system built on evasion breaks constantly and creates exposure we do not need.
4. **Respect rate limits and robots directives.** Conservative request rates, exponential backoff, off-peak scheduling. Our own listings are on these platforms; do not create a reason for anyone to look at us.
5. **Store only what we use.** No personal data. Reviewer names hashed. Retention policy per data type.
6. **Legal sign-off before go-live** on the Tier-3 scope, and re-review annually. Marketplace terms change.

**Honest note on this:** Tier-3 collection is standard practice across the industry and is how every competitor tool works, but it sits on terms-of-service ground that shifts. Budget for it to break periodically and for maintenance, and keep as much as possible on Tiers 1 and 2, which are stable.

### **2.3 What is measured versus what is estimated**

The system must never blur these. Every number carries a confidence label.

| **Data point**                                                     | **Status**                                                                       |
| ------------------------------------------------------------------ | -------------------------------------------------------------------------------- |
| Competitor price, title, images, rating, review count, BSR, badges | **Measured** — high confidence                                                   |
| Competitor organic rank on a keyword                               | **Measured** at our sampling geo and time                                        |
| Competitor sponsored placement on a keyword                        | **Measured** — we saw the ad slot                                                |
| Competitor ad-presence days (on-platform)                          | **Derived** from continuous observation — high confidence if sampling is dense   |
| Competitor off-platform ad run dates                               | **Measured** — from the public ad library                                        |
| Competitor keyword bid, budget, ACOS                               | **Not observable. Estimated only.**                                              |
| Competitor ad spend                                                | **Modelled estimate with a confidence band** (Section 6.5)                       |
| Competitor units sold and revenue                                  | **Modelled estimate**, calibrated against our own BSR-to-units curve (Section 9) |

**Rule: no estimated figure is ever displayed without its confidence band.** False precision in a competitor dashboard leads to bad decisions made with total conviction, and it is the most common failure of tools in this category.

## **3\. UNIVERSE & COMPETITOR SETUP — S1**

### **3.1 Competitor master**

Per competitor: brand name, parent company, brand store URLs per platform, seller IDs, category presence, positioning tier (premium / mid / value), our threat rating (1–5), and the analyst who owns them.

Sample structure for baby care: national leaders, challenger D2C brands, marketplace private labels, and regional price players — each tracked differently, because a private label needs price watching while a D2C challenger needs ad and content watching.

### **3.2 Tracked entity registry**

Every ASIN / FSN / platform SKU we track, with: brand, competitor, our mapped SKU, category node, tracking tier, and start date. Entities are added by rule (auto-discovery, Section 3.4) or manually.

### **3.3 Battle cards — the SKU-to-SKU mapping**

This is the backbone of "where do we stand". Every Novel SKU is mapped to its 3–8 direct competitor SKUs, with the comparison basis recorded: same pack size, same price band, same category node, same use case.

Each battle card holds, side by side and refreshed hourly: price and price-per-unit, rating and review count, review velocity, BSR, content score, ad presence, availability, and our own margin (from SCM — which no external tool can see). **Price-per-unit, not price** — a 72-pack versus a 62-pack at the same price is not the same offer, and this is where category managers most often deceive themselves.

### **3.4 Auto-discovery**

Weekly job: scan category bestseller lists, top search results for Tier-1 keywords, and "compared with similar items" modules. Any brand or SKU appearing repeatedly above a threshold that is not in the registry is proposed for tracking, with evidence. Analyst accepts or rejects. **New entrants are found by the system, not by someone noticing.**

### **3.5 Tracking tiers — control the cost**

Hourly tracking of everything is expensive and unnecessary. Three tiers:

| **Tier** | **Scope**                                                                                   | **Frequency** |
| -------- | ------------------------------------------------------------------------------------------- | ------------- |
| **T1**   | Top ~200 keywords + top ~150 SKUs (ours + direct competitors) driving most category revenue | **Hourly**    |
| **T2**   | Next ~800 keywords, ~400 SKUs                                                               | Every 4 hours |
| **T3**   | Long tail, watchlist, adjacent categories                                                   | Daily         |

Tiers are reviewed monthly and are data-driven — a keyword's tier follows its revenue contribution and volatility, not someone's opinion.

## **4\. KEYWORD INTELLIGENCE — S2**

### **4.1 Building the keyword universe**

Sources combined and deduplicated:

- **Amazon Brand Analytics Top Search Terms** — actual ranked search terms with click and conversion share by ASIN. Start here; it is real data, not an estimate.
- **Our Amazon Ads search-term reports** — every query that has ever converted for us, with its ACOS
- Platform autocomplete and suggestion scraping across seed prefixes
- **Reverse-ASIN**: every keyword a given competitor ASIN ranks or advertises on (built from our own SERP capture over time, supplemented by licensed data)
- Google Keyword Planner and Search Console for D2C and off-platform intent
- Review mining — the words customers actually use ("rash free", "overnight", "leak proof")
- Regional and vernacular variants, and common misspellings

### **4.2 Keyword attributes**

Volume estimate and trend, seasonality index, competition density, average price of top 10 results, our best rank, our best sponsored position, competitor presence count, conversion rate where known, and **revenue-at-stake** (estimated volume × category conversion × our average selling price).

### **4.3 Clustering by intent**

Every keyword classified: **generic category** ("baby diapers") | **attribute/long-tail** ("diaper pants xl 62 count") | **problem/benefit** ("rash free diaper") | **our brand** | **competitor brand** | **adjacent** ("baby wipes sensitive"). Each cluster has a different strategy — you defend brand terms cheaply, you buy problem terms for conversion, you fight generic terms only where margin allows.

### **4.4 Share of Voice**

For each keyword, at each capture:

Organic SOV(brand) = Σ position-weighted organic slots held by brand ÷ total weighted organic slots (page 1)

Paid SOV(brand) = Σ position-weighted sponsored slots held by brand ÷ total weighted sponsored slots

Total SOV(brand) = weighted blend, weights configurable (default 60% organic, 40% paid)

Position weighting uses a click-through decay curve (position 1 counts far more than position 20). SOV is trended by brand, by keyword cluster, by platform, daily and weekly. **This single chart — our SOV versus each competitor's, over time, per cluster — is the headline number of the whole module.**

### **4.5 Keyword gap analysis**

Four gap types, each with revenue-at-stake attached and each auto-generating an action:

1. **Organic gap** — they rank page 1, we do not rank page 1
2. **Paid gap** — they advertise on it, we do not
3. **Coverage gap** — the keyword is relevant to our SKU but appears in neither our listing nor our campaigns
4. **Efficiency gap** — we both advertise, but our position is worse or our cost per click is materially higher

## **5\. RANK & VISIBILITY TRACKING — S3**

### **5.1 Hourly SERP capture**

For every tracked keyword × platform × geo, at each scheduled run, capture the full page-1 result set (and page 2 for T1 keywords), recording per result:

- Position (absolute and within-type), platform SKU ID, brand
- **Placement type:** Organic | Sponsored Product | Sponsored Brand | Sponsored Brand Video | Sponsored Display | Editorial/Deal module
- Badge: Best Seller, Amazon's Choice (and the term it is awarded for), Deal, Limited Time Deal, New Arrival, Sponsored label
- Displayed price, MRP, discount %, coupon, delivery promise, rating, review count
- Thumbnail hash (to detect main-image changes without storing every image)
- Capture timestamp, geo/pincode, device profile (mobile and desktop differ materially — track both for T1)

### **5.2 Geo matters**

Quick-commerce and delivery-promise results vary by pincode. Capture from a defined set of pincodes covering our priority cities. A brand can be invisible in Bengaluru and dominant in Delhi, and a single-geo tracker will never show it.

### **5.3 Derived visibility metrics**

- Rank history and rank volatility per SKU per keyword
- **Time-in-top-3 / top-10 percentage** — a far better measure than a spot rank reading
- Page-1 presence count per brand (how many slots one brand holds — total shelf dominance)
- Category BSR captured hourly for tracked SKUs, with BSR velocity
- Badge acquisition and loss events, timestamped
- New-entrant detection: any SKU appearing on page 1 for the first time

### **5.4 Our own rank, from the same capture**

Our SKUs are tracked in the identical run, from the identical page. This matters — comparing our rank from one source against theirs from another produces nonsense. **One capture, both sides, same second.**

## **6\. AD INTELLIGENCE — S4**

This is the section that answers _"how many days are they running ads, what ads, on what keywords."_

### **6.1 What we can actually see**

On a marketplace search page, sponsored slots are labelled. Every capture therefore tells us, factually: **this brand was buying this keyword at this hour, in this slot type, at this position.** Repeat that hourly across a large keyword set and a very detailed picture of a competitor's ad strategy emerges from observation alone. We never see their bid, budget or ACOS — and we do not pretend to.

### **6.2 Ad presence tracking**

Per competitor × keyword × platform × slot type:

- **First seen** and **last seen** advertising
- **Continuous ad-presence days** — consecutive days with at least one sponsored appearance (this is the "how many days" number)
- **Total ad days** in period, and **ad-day coverage %** (days advertising ÷ days in period)
- **Keyword ad breadth** — how many of our tracked keywords they bid on, trended weekly
- **Ad intensity** — average sponsored position and share of sponsored slots held

### **6.3 Daypart and budget-behaviour inference**

Because we capture hourly, we can see patterns that daily tools cannot:

- **Daypart pattern** — the hours of day a competitor's ads appear. Heat map by hour × day of week.
- **Budget exhaustion signal** — present at 09:00, absent from 17:00, back at 09:00 the next day. That is a daily budget capping out. **This is one of the most commercially useful signals in the system:** it tells us exactly which hours a competitor's ads go dark on a keyword we care about, and those are the cheapest, least contested hours for us to buy.
- **Weekend and payday patterns**, festive ramp-up timing, and how many days _before_ a sale event they turn spend on — which lets us predict the next event's ramp.
- **Launch signature** — heavy ad presence on a brand-new SKU with low review count means a funded launch. Flag it within 24 hours.

### **6.4 Creative capture**

- **Sponsored Brand headlines** — headline copy, brand logo, the SKUs featured, landing destination (store page vs listing). Full text and image archived with first-seen and last-seen dates.
- **Sponsored Brand Video** — thumbnail, duration, and a stored copy of the creative for review
- **Off-platform, from public ad libraries:** Meta Ad Library gives competitor ad creative, format, placement and **official start and stop dates** — the cleanest possible answer to "how many days have they been running this." Google Ads Transparency Center does the same for Google and YouTube. Both are public and official; use them heavily.
- **Creative diff log** — when a competitor changes creative, we know the date, and we can correlate it against their rank and review-velocity movement afterwards

### **6.5 Ad spend estimation — with honesty built in**

Estimated impressions(competitor, keyword, day)

\= keyword daily search volume

× share of sponsored slot-time held by competitor (from hourly capture)

× slot-type impression weighting

Estimated clicks = estimated impressions × CTR benchmark for that slot type and position

(calibrated from OUR OWN Amazon Ads data — our biggest advantage)

Estimated spend = estimated clicks × estimated CPC

(calibrated from OUR OWN CPC on the same keyword, same platform, same week)

Confidence band = ± f(sampling density, keyword volume confidence, our own data volume on that keyword)

**We can calibrate this far better than any external tool can, because we hold ground truth on one side of the market.** We know exactly what our impressions, clicks and CPC were on that keyword that day. Anchoring the model to our real numbers turns a wild guess into a usable estimate.

Display rule: always as a range with the confidence band, never as a single rupee figure. Monthly back-test of the model against our own actuals, with the error published.

### **6.6 Our own ad performance, side by side**

Pulled from the Amazon Ads API and equivalents: our impressions, clicks, CTR, CPC, spend, ACOS/TACOS, conversion, and impression share per keyword — shown against the competitor picture on the same screen. **Their estimated aggression next to our actual efficiency** is the view the marketing team should be running the week from.

## **7\. LISTING & CONTENT INTELLIGENCE — S5**

### **7.1 Snapshot and diff engine**

Full listing capture for every tracked SKU at T1/T2/T3 frequency: title, all bullets, description, A+ / Enhanced Brand Content blocks, image set (count, hashes, order), video presence and count, variation family structure, category node, brand store link, Q&A count.

**Every field is diffed against the previous snapshot.** Any change writes a change event with timestamp, old value, new value, and a rendered before/after view.

### **7.2 Why the diff log is the most underrated feature here**

Competitors do not announce strategy. They change a title, swap a main image, add a claim, restructure a variation family. The diff log turns those into a dated, searchable record — and because it sits next to rank history, we can see what happened _after_ the change. Over six months this becomes a library of what works in our category, learned from other people's experiments.

### **7.3 Content quality scoring**

Scored per SKU and compared across the battle card:

- Title: length, keyword coverage against the SKU's target keyword cluster, readability
- Bullets: count, length, benefit vs feature ratio, keyword coverage
- Images: count, presence of lifestyle/infographic/size-chart/comparison images, main-image compliance
- Video present, A+ present, A+ Premium present, brand store linked
- Rating, review count, Q&A depth
- **Composite content score** with our gap to the category leader shown explicitly, per attribute

### **7.4 Claim and compliance watch**

Track claims competitors make on pack and listing (dermatologically tested, hypoallergenic, X-hour absorption, pH balanced). Two uses: it shows where the category's claim bar is moving, and it flags claims we would need substantiation for before matching — which routes to QA, not to marketing. **This links directly to the QC module: a claim we cannot substantiate is a claim we do not make.**

## **8\. PRICE, PROMO & OFFER INTELLIGENCE — S6**

### **8.1 Captured hourly**

Selling price, MRP, discount %, price-per-unit (per piece, per 100ml, per wipe — normalised), coupon value, Subscribe & Save rate, bank/card offer, deal type and deal window, bundle and combo construction, and Buy Box holder where visible.

### **8.2 Derived**

- Price history per SKU with change events, and **price-change frequency** (a proxy for how algorithmic their pricing is)
- **Price ladder** for the category: every tracked SKU by price-per-unit, showing exactly where each Novel SKU sits and where the white space is
- **Their price move → their BSR move**, over the following 24–72 hours. Repeated across many observations, this gives an observed elasticity for the category that no survey will give us.
- Promo calendar reconstruction — who discounts, when, how deep, for how long, and how far ahead of an event they start
- **Our price versus battle-card competitors, with our margin from SCM attached.** The system should refuse to recommend a price match that takes a SKU below its margin floor, and should say so explicitly.

### **8.3 Availability tracking**

Competitor out-of-stock and low-stock signals per platform and pincode. **A competitor stock-out on a keyword we both rank for is the single highest-value short-term opportunity in the system** — it should fire a real-time alert to the KAM with the recommended response (raise bids on that keyword, ensure our stock at that node, hold price) and the window should be tracked until they return.

## **9\. REVIEW & VOICE-OF-CUSTOMER — S7**

### **9.1 Captured**

Rating distribution, total review count, and new reviews per day per tracked SKU, with text, date, rating, verified flag and variant. Reviewer identity is hashed; we store no personal data.

### **9.2 Derived**

- **Review velocity** — new reviews per day. This is the best publicly observable proxy for sales velocity, and it is more stable than BSR. Trend it per SKU and per brand.
- Rating trajectory and inflection detection — a rating that starts falling usually means a formulation, supplier or batch change, and it is worth knowing about a competitor's within days
- **Topic mining** on competitor reviews: cluster complaints and praise into themes (leakage, rash, absorbency, smell, tape strength, packaging damage, price, delivery). Trend each theme by brand over time.
- Suspicious-pattern flags: sudden review spikes, unverified clusters — useful context, held internally, never published

### **9.3 Two outputs that matter**

1. **Opportunity feed to NPD** — the top complaint themes about competitor products in our categories, ranked by frequency and severity. This is a free, continuously updated product brief.
2. **Early warning on ourselves** — our own review themes trending negative on a SKU routes straight into the QC module's complaint and CAPA workflow with the batch context attached. Market feedback becomes a quality input within days instead of months.

## **10\. SALES & SHARE ESTIMATION — S8**

### **10.1 The calibration advantage**

Every external tool estimates units from BSR using a generic curve. **We know our exact daily units and our exact BSR, hourly, for hundreds of our own SKUs across every node in our categories.** That gives us a category-specific, size-specific, season-specific BSR-to-units curve that is materially more accurate than anything purchasable.

Fit: units_per_day = f(BSR, category_node, price_band, season)

trained and re-fitted monthly on OUR OWN (BSR, units) observations

Apply: estimated competitor units = f(their observed BSR, same node, their price band, same period)

Cross-check: estimated units vs their observed review velocity ÷ category review rate

Two independent estimates that agree raise confidence; two that diverge lower it, and the system says so.

### **10.2 Outputs**

Estimated units and revenue per competitor SKU and brand; category size; **market share by brand, trended**; share by sub-segment (pack size, price band, variant); and our share gap to the leader, with the specific SKUs driving the gap.

## **11\. THE BENCHMARKING SCORECARD — S9**

_"Where do we stand, where are we, what are we lacking behind, what are we good at."_ This sub-module is the answer, and everything above exists to feed it.

### **11.1 Structure**

A scorecard exists at four levels, each refreshed on the tracking tier's cadence:

1. **SKU × keyword** — the atomic unit
2. **SKU** — rolled up across its keyword cluster
3. **Brand** (Babio, ALMA, Novel Cosmetics, Medibath) — rolled up across SKUs
4. **Category** — total Novel position versus the market

### **11.2 The seven dimensions**

| **#** | **Dimension**             | **Measured by**                                                     | **Where the data comes from** |
| ----- | ------------------------- | ------------------------------------------------------------------- | ----------------------------- |
| 1     | **Visibility**            | Organic rank, time-in-top-10, page-1 slot share, BSR                | S3                            |
| 2     | **Paid presence**         | Paid SOV, keyword coverage, ad position, impression share           | S4 + our Ads API              |
| 3     | **Price competitiveness** | Price-per-unit index vs battle card, discount depth, offer strength | S6 + SCM margin               |
| 4     | **Content**               | Composite content score vs category leader, attribute by attribute  | S5                            |
| 5     | **Social proof**          | Rating, review count, review velocity, Q&A depth                    | S7                            |
| 6     | **Availability**          | In-stock %, node coverage, delivery promise                         | S6 + SCM stock                |
| 7     | **Conversion**            | Our actual conversion vs category benchmark; sessions to units      | First-party                   |

Each dimension is scored 0–100 against the battle-card set, colour-banded: **Leading** (top of set) | **Competitive** (within tolerance of the leader) | **Lagging** (materially behind) | **Critical** (bottom of set, or a hard failure such as out of stock).

### **11.3 The four views AP should be able to open at any hour**

**"Where we stand"** — one screen, every Novel SKU, seven dimensions, colour-banded, sortable by revenue. The whole business at a glance.

**"What we're good at"** — every dimension where we are Leading, with the size of our lead and how long we have held it. **This view is not vanity — it is a defence list.** A lead you are not aware of is a lead you will lose without noticing. Each entry carries a defence action and a monitoring threshold.

**"Where we're lagging"** — every Lagging and Critical cell, ranked by **revenue at stake**, not by how far behind we are. Being 40% behind on a keyword worth very little is not a problem; being 8% behind on the keyword that carries the category is.

**"What we need to do"** — the action queue from S10.

### **11.4 Revenue at stake — the ranking mechanism**

Revenue at stake (SKU × keyword)

\= keyword volume

× achievable click share at target position − current click share at current position

× category conversion rate

× our average selling price

× our contribution margin % ← from SCM, which no external tool has

Everything in the system is prioritised by this number. It is what stops the module becoming an interesting dashboard nobody acts on.

### **11.5 Trend, not snapshot**

Every scorecard cell carries direction and velocity — improving, flat, deteriorating, and how fast. **A "Competitive" cell that has been deteriorating for three weeks is more urgent than a "Lagging" cell that is recovering**, and the interface must make that obvious.

## **12\. GAP & ACTION ENGINE — S10**

A dashboard that reports problems without producing owned actions gets looked at for three weeks and then ignored. This sub-module is what prevents that.

### **12.1 Gap generation**

Every Lagging or Critical scorecard cell auto-generates a **gap record**: dimension, SKU, keyword or cluster, competitor benchmark, our value, the size of the gap, revenue at stake, and detected root cause.

### **12.2 Root cause classification**

The engine classifies each gap before proposing anything, because the same symptom has very different fixes:

| **Symptom**       | **Candidate causes the engine tests**                                                                                                                 |
| ----------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| Rank dropped      | Out of stock during the period · price increase · content change on our side · competitor ad surge · rating fall · review velocity fall · seasonality |
| Low paid position | Bid below market · budget exhausted before peak hours · low relevance score · keyword not in any campaign                                             |
| Low conversion    | Price uncompetitive per unit · weak main image · thin content · low rating · slow delivery promise · wrong pack size for the query                    |
| Low content score | Specific missing attributes, named                                                                                                                    |
| Availability gap  | Node-level stock-out — **pulled live from the SCM module, with the reason**                                                                           |

### **12.3 Recommended actions**

Each gap maps to a recommended action from a maintained playbook, with the expected effect and the effort. Examples of the shape: raise bid on keyword K to reach position P during hours 18:00–23:00 when competitor C's budget goes dark; add attribute A to the title of SKU S; add a comparison infographic to SKU S, which trails the battle card by three images; push stock to node N where we have been out of stock 18% of the last 30 days.

**Guardrails:** any action with a commercial consequence is checked against SCM before it is proposed. A price action that breaches the margin floor is not proposed — it is shown as blocked, with the margin reason stated. A stock action that we cannot supply is flagged as infeasible with the shortage detail.

### **12.4 Action lifecycle**

Gap detected → Action proposed (with revenue at stake and expected effect)

→ Reviewed by owner (accept / modify / reject with reason)

→ Assigned: owner, due date, SLA by priority

→ Executed → marked done

→ IMPACT MEASURED: the affected metric is tracked for 7/14/30 days after closure

→ Outcome recorded: improved / no change / worsened

→ Playbook updated — actions that repeatedly fail get demoted

**The impact-measurement loop is what makes this compound.** After six months the playbook contains what actually works in _our_ categories, not general best practice.

### **12.5 Governance**

Weekly review with the digital marketing team (Jeevan and Ragvendra) and the KAMs: new gaps, action closure rate, impact of last month's closed actions, and the SOV trend. Monthly to AP: SOV by cluster, share estimate, competitive threats, and the top ten revenue-at-stake gaps still open.

## **13\. ALERTING & WAR ROOM — S11**

### **13.1 Threat alerts**

| **Trigger**                                                | **Priority** | **Route to**                                          |
| ---------------------------------------------------------- | ------------ | ----------------------------------------------------- |
| Competitor starts advertising on a **Novel brand keyword** | Critical     | Marketing + AP                                        |
| Our rank on a T1 keyword drops more than N positions       | High         | KAM + Marketing                                       |
| We lose Buy Box or a badge (Best Seller, Amazon's Choice)  | High         | KAM                                                   |
| Competitor drops price more than X% on a battle-card SKU   | High         | KAM + Category                                        |
| Competitor launches a new SKU in our sub-category          | High         | Category + NPD + AP                                   |
| Competitor ad breadth expands sharply (funded push)        | Medium       | Marketing                                             |
| Our rating on a SKU falls below threshold                  | High         | QA + Category (routes into the QC complaint workflow) |
| Competitor claim appears that we cannot substantiate       | Medium       | QA + Marketing                                        |

### **13.2 Opportunity alerts**

| **Trigger**                                                | **Priority** | **Recommended response**                                                                  |
| ---------------------------------------------------------- | ------------ | ----------------------------------------------------------------------------------------- |
| **Competitor out of stock** on a shared keyword            | Critical     | Raise bids, confirm our stock at that node, hold price. Window tracked until they return. |
| **Competitor ads go dark** (budget exhausted) in a daypart | High         | Buy those hours — cheapest contested inventory in the category                            |
| Competitor rating falls sharply                            | Medium       | Content and ad emphasis on the attribute they are being criticised for                    |
| Keyword volume rising with low competition                 | Medium       | Content and campaign coverage before the category notices                                 |
| Competitor delists or discontinues a SKU                   | High         | Capture the demand — stock, rank, bid                                                     |

### **13.3 Delivery**

Reuses the BOS alerting engine: in-app, email, WhatsApp. Every alert carries the evidence (the captured SERP row or the diff), the recommended action, an owner and an SLA. Daily caps and digest batching for anything below High — **an alert stream that cannot be kept up with is the same as no alert stream at all.**

### **13.4 War room board**

A live board for event periods (Big Billion Days, Great Indian Festival, Dasara, Prime Day): every T1 keyword, our position versus each competitor, refreshed continuously, with the open action queue beside it. This is the screen the team runs the sale from.

## **14\. DASHBOARDS**

**AP / Founder** — daily 07:00 digest and a live screen: SOV by brand and cluster with trend | estimated market share | the "where we stand" grid | top 10 open gaps by revenue at stake | competitor moves in the last 24 hours | active opportunities | action closure rate.

**Category / Brand manager** — battle cards, price ladder, content gaps, review themes, NPD opportunity feed.

**Marketing (Jeevan, Ragvendra)** — keyword-level paid and organic view, our efficiency against their estimated aggression, daypart heat maps, creative library and diffs, action queue.

**KAM (channel)** — their platform only: rank, buy box, availability, competitor stock-outs, deal calendar, alerts.

**Analyst** — collection health, data-quality flags, model back-test accuracy, universe management.

## **15\. TECHNICAL ARCHITECTURE — S12**

### **15.1 Layers**

COLLECTION Scheduler → job queue → collector workers (API clients + headless browser pool)

→ raw response store (immutable, compressed, hash-addressed)

PARSING Versioned parsers per platform per page type → normalised records

→ schema validation → quarantine on parse failure

STORAGE Time-series store for observations (partitioned by day)

Relational store for masters, scorecards, gaps, actions

Object store for creatives, screenshots, raw HTML

PROCESSING Nightly + intraday jobs: SOV, ad-presence, diffs, scores, models, gaps

INTELLIGENCE NLP for review topics, BSR-to-units model, spend model, anomaly detection

SERVING API → BOS UI, alerts, exports

### **15.2 Collection specifics**

- Job scheduler with per-platform concurrency caps and politeness delays
- Headless browser pool for JS-rendered pages; plain HTTP where sufficient (much cheaper — use it wherever the page allows)
- Rotating egress with a legitimate commercial proxy provider; realistic device and geo profiles for pincode-specific capture
- **Backoff-and-report on any challenge or block. Never solve a challenge.** A blocked capture is logged as a collection failure, not worked around.
- Retry with jitter; dead-letter queue; every failure alerted if the failure rate breaches threshold

### **15.3 Parser resilience — the real maintenance cost**

Marketplace HTML changes without notice, and a silently broken parser is worse than a dead one because it fills the database with wrong data that people then act on. Mitigations, all mandatory:

- **Parsers are versioned and independently deployable** — a layout change means shipping a parser, not the platform
- **Golden-file tests** per platform per page type, run on every deploy
- **Statistical canaries:** if today's parse yields a field-fill rate, row count or value distribution materially different from the trailing 7-day norm, the run is quarantined and an alert fires _before_ the data reaches the scorecards
- Raw responses retained so any historical period can be re-parsed after a parser fix — **this is why we store raw, and it will save the project at least twice**

### **15.4 Storage sizing — do the arithmetic before building**

Order of magnitude for planning: roughly 200 T1 keywords hourly + 800 T2 keywords 6× daily + T3 daily, across 4 primary platforms, at ~40–60 result rows per capture, is on the order of **1–2 million observation rows per day**, plus raw HTML.

Implications to design for from day one: partition by day, compress raw responses, define a retention policy per data type (raw HTML 90 days, parsed observations 3 years, daily aggregates indefinitely), and pre-aggregate for the dashboards rather than querying raw. **Retro-fitting partitioning onto a live time-series table is painful — do it at the start.**

### **15.5 Data quality framework**

Freshness (is every tier within SLA), completeness (captures attempted vs succeeded), consistency (do our own captured numbers match our first-party API numbers — a free and continuous accuracy check), and model back-tests published monthly. **Data-quality status is shown on every dashboard.** A user must always be able to see whether the number they are looking at is fresh and trustworthy.

## **16\. CORE DATA MODEL (indicative)**

\-- Universe

competitor, tracked_entity, sku_battle_card, battle_card_line,

category_node, tracking_tier, geo_profile

\-- Keywords

keyword, keyword_attribute, keyword_cluster, keyword_source,

keyword_volume_history, reverse_asin_map

\-- Observations (time-series, partitioned by day)

serp_capture, serp_result_row, listing_snapshot, listing_diff_event,

price_observation, offer_observation, availability_observation,

bsr_observation, review_observation, badge_event

\-- Ads

ad_observation, ad_presence_daily, ad_daypart_profile,

ad_creative, ad_creative_diff, external_ad_record,

spend_estimate, own_ad_performance

\-- Intelligence

sov_daily, content_score, review_topic, review_topic_trend,

units_model_fit, units_estimate, market_share_daily

\-- Benchmarking & action

scorecard_cell, scorecard_history, gap, gap_root_cause,

action, action_impact, playbook_entry

\-- Alerts & ops

alert_rule, alert_event, collection_job, collection_failure,

parser_version, data_quality_check, model_backtest

## **17\. PHASED DELIVERY**

| **Phase**                                      | **Weeks** | **Scope**                                                                                                                                                                 | **Definition of done**                                                                                           |
| ---------------------------------------------- | --------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| **0 — Foundation**                             | 1–3       | Competitor master, battle cards for top 30 Novel SKUs, keyword universe v1 from Brand Analytics + our search-term reports, tier definitions, legal review of Tier-3 scope | Battle cards signed off by category; keyword universe covers ≥ 70% of category volume                            |
| **1 — Collection core**                        | 2–8       | Scheduler, collectors, parsers for Amazon + Flipkart, raw store, SERP capture, data-quality canaries. Absorb the existing rank-tracking automation.                       | ≥ 98% capture success for 2 straight weeks; parser canaries proven by catching a seeded layout change            |
| **2 — Rank, price, listing**                   | 6–13      | S3, S5, S6 — rank history, listing diff engine, price and offer tracking, availability                                                                                    | Diff log demonstrably catching real competitor changes; price ladder live                                        |
| **3 — Ad intelligence**                        | 11–18     | S4 — sponsored capture, ad-presence days, daypart heat maps, creative capture, Meta and Google ad-library integration, spend model v1                                     | Ad-presence days and daypart map produced for top 5 competitors; spend model back-tested against our own actuals |
| **4 — Scorecard & action engine**              | 15–23     | S9 + S10 — seven-dimension scorecard, revenue-at-stake ranking, gap generation, action lifecycle                                                                          | AP can open "where we stand" and "where we're lagging"; first 50 actions assigned and closed                     |
| **5 — Reviews, share, alerts**                 | 20–28     | S7, S8, S11 — review mining, BSR-to-units model, market share, full alerting and war room                                                                                 | Share estimate cross-validated two ways; alerts running with acknowledged SLAs                                   |
| **6 — Meesho, quick commerce, D2C, hardening** | 26–34     | Remaining platforms, pincode-level quick-commerce tracking, D2C and off-platform, performance tuning                                                                      | All priority platforms live; war room used through one full sale event                                           |

**Sequencing note:** Phase 3 (ads) is the headline ask, but it is worthless without Phase 1 running at high capture reliability — ad-presence days computed from a feed with gaps in it are simply wrong. Do not pull Phase 3 forward.

## **18\. ACCEPTANCE CRITERIA**

1. For any tracked keyword, the system shows page-1 organic and sponsored results, hourly, for the last 90 days, with our SKUs and competitor SKUs from the same capture.
2. For any competitor, the system reports continuous ad-presence days, total ad days, keyword ad breadth, and a daypart heat map, per platform, with the underlying observations viewable.
3. For any competitor Meta or Google campaign in the public ad libraries, the system shows the creative and the official run dates.
4. Any listing change by a tracked competitor is captured within its tier SLA and shown as a before/after diff.
5. A competitor stock-out on a shared T1 keyword fires an alert within 2 hours, with a recommended response.
6. The "where we stand" scorecard renders all Novel SKUs across seven dimensions, and every Lagging cell has a gap record with revenue at stake.
7. Every gap produces an action with an owner and a due date; closed actions have measured 7/14/30-day impact.
8. Every estimated figure displays a confidence band; the spend and units models publish a monthly back-test against our own actuals.
9. A seeded parser break is caught by the canary before bad data reaches any dashboard.
10. The collector demonstrably backs off and reports rather than attempting to bypass any bot challenge.
11. Data-quality status (freshness, completeness) is visible on every dashboard.

## **19\. RISKS**

| **Risk**                                       | **Impact**                                                             | **Mitigation**                                                                                                                                |
| ---------------------------------------------- | ---------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| **Silent parser breakage**                     | Wrong data acted on with confidence — the worst outcome in this system | Golden-file tests, statistical canaries, quarantine before publish, raw retention for re-parse                                                |
| Platform blocking or ToS change                | Collection stops                                                       | Maximise Tier-1 and Tier-2 sources; conservative rates; never evade challenges; legal review; accept periodic breakage and budget maintenance |
| **False precision on estimates**               | Confident bad decisions                                                | Confidence bands mandatory, monthly back-tests published, measured vs estimated always labelled                                               |
| Dashboard nobody acts on                       | Wasted build                                                           | The action engine with owners, SLAs and impact measurement is core scope, not a later phase                                                   |
| Alert fatigue                                  | Alerts ignored, real threats missed                                    | Priority tiers, daily caps, digest batching, quarterly rule review                                                                            |
| Scope creep into a general BI tool             | Never ships                                                            | Scope is competitive intelligence and benchmarking only; general reporting stays in the BOS control tower                                     |
| Storage and compute cost drift                 | Budget surprise                                                        | Tiering enforced, retention policy from day one, monthly cost review against capture volume                                                   |
| **Team bandwidth collides with the SCM build** | Both slip                                                              | These are two large builds. Sequence them or resource them separately — see Section 20.                                                       |

## **20\. WHAT I NEED FROM THE TEAM**

1. **Sumukha** — an honest read on running this alongside the SCM and QC platform. These are two substantial builds and the same team cannot do both well at once. Options to come back to me on: sequence them (SCM first, Signal from month 4), split the team, or bring in additional resource. Also: confirm the collection stack, proxy provider and storage plan, and give a phase estimate against Section 17.
2. **Category / Brand** — the competitor list, the threat ratings, and battle-card mapping for the top 30 Novel SKUs. This is a business input, not a technical one, and Phase 0 cannot start without it.
3. **Marketing (Jeevan, Ragvendra)** — export our full Amazon Ads search-term history and Brand Analytics Top Search Terms. This is the seed of the entire keyword universe and it costs nothing to produce.
4. **KAMs** — the keywords that actually matter per platform, and the pincodes we should be tracking from.
5. **Legal** — review of the Tier-3 collection scope in Section 2 before Phase 1 ships.
6. **All** — baseline the metrics in Section 0.2. We cannot demonstrate improvement without a starting number.

## **21\. ONE HONEST RECOMMENDATION**

Everything above is buildable and most of it is high value. But two things are worth saying plainly:

**First, the highest-return work is not the hardest work.** Brand Analytics, our own ads search-term data, the Meta Ad Library and a reliable hourly SERP capture on 200 keywords would deliver perhaps 70% of the commercial value of this entire specification, and Phases 0–2 get there. The sophisticated parts — spend modelling, units estimation, review NLP — are genuinely useful but they sit on top of that foundation and add less than people expect.

**Second, buying is not defeat.** A Helium 10 or Jungle Scout subscription costs a fraction of a developer-month and gives keyword volume and historical BSR immediately. The case for building is not to replicate those tools — it is the parts they can never do: our margin, our stock, our real ad efficiency, the battle cards, the scorecard, and the action loop. My recommendation is to **licence the commodity data and build only the differentiated layer.** That halves the build and gets the scorecard in front of you months earlier.

_Novel Group — Novel BOS Module M15. Build baseline v1.0. Changes to be raised as versioned change requests against this document._

**— AP**