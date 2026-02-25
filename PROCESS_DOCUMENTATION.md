# Demand Prioritization, Plan Generation, KPI Calculation, and Scenario Analysis

## Complete Process Documentation

---

## Overview

This system automates production priority ranking across **three progressive stages**, each building on the previous:

| Stage       | Name                        | Purpose                                                                         |
| ----------- | --------------------------- | ------------------------------------------------------------------------------- |
| **Stage 1** | Demand Scoring              | Combine Vector reports (BMR, BOR, BPR, SPOR) into a ranked demand list          |
| **Stage 2** | Machine Deployment Analysis | Overlay live mould/dispatch data on Stage 1 to assess production readiness      |
| **Stage 3** | Manual Strategic Override   | Inject CPT (Central Planning Team) manual demands at the top of the ranked list |

---

## Stage 1: Demand Scoring (Priority Score Calculation)

### 1.1 Input Sources

Stage 1 pulls data from **four Vector daily report files**, all stored under `./data/Vectordata/`:

| Report                                    | File Pattern                                       | Key Columns                                                                       |
| ----------------------------------------- | -------------------------------------------------- | --------------------------------------------------------------------------------- |
| **SPOR** — Single Production Order Report | `SPOR/Single_Production_Order_Report_DDMMYYYY.csv` | Production summary, BU stock levels                                               |
| **BOR** — BOR Color Bandwise Report       | `BOR/BORColorBandwiseReport__DD-MM-YYYY.csv`       | Location Code, SKUCode, Virtual Norm, Stock, Norm                                 |
| **BMR** — Prod Overall BM Report          | `BMR/Prod_OverAll_BMReport__DD_MM_YYYY.xlsx`       | Plant Code, Item Code (SKUCode), Pending CCR Qty (Requirement), BPP (Penetration) |
| **BPR** — Buffer Penetration Report       | `BPR/BufferPenetrationReport__DD-MM-YYYY.csv`      | SKUCode, Location Type, On hand Inv. Color, Top SKU                               |

> **Market Source Mapping:** BOR Location Codes are parsed into market categories:  
> `FG10 → RE` | `OE10 → OE` | `ST10 → ST` | `OTR10 → OTR` | BMR rows → `EXP`

---

### 1.2 Configuration Parameters (Stage 1)

All Stage 1 parameters are configurable via `config_input.xlsx` → `Stage1_Config` sheet:

#### Market Weights (Higher = Higher Priority)

| Parameter            | Default | Description                        |
| -------------------- | ------- | ---------------------------------- |
| `MARKET_WEIGHTS_OE`  | 4       | Original Equipment market weight   |
| `MARKET_WEIGHTS_ST`  | 3       | Strategic market weight            |
| `MARKET_WEIGHTS_EXP` | 2       | Export market weight               |
| `MARKET_WEIGHTS_OTR` | 2       | Off-The-Road tyre market weight    |
| `MARKET_WEIGHTS_RE`  | 1       | Replacement / Retail market weight |

#### Location Weights (for Inventory Scoring)

| Parameter                         | Default | Description                      |
| --------------------------------- | ------- | -------------------------------- |
| `LOCATION_WEIGHTS_JIT`            | 5       | Just-In-Time (highest urgency)   |
| `LOCATION_WEIGHTS_Depot`          | 4       | Regular depot                    |
| `LOCATION_WEIGHTS_Depot_Mobility` | 3       | Mobile depot                     |
| `LOCATION_WEIGHTS_Feeder`         | 2       | Feeder warehouse                 |
| `LOCATION_WEIGHTS_PWH`            | 1       | Plant Warehouse (lowest urgency) |

#### Scoring Component Weights (PriorityScore)

| Parameter                       | Default | Description                             |
| ------------------------------- | ------- | --------------------------------------- |
| `SCORING_market_weightage`      | 0.25    | Weight of MarketWeight in PriorityScore |
| `SCORING_penetration_weightage` | 0.35    | Weight of Normalized Penetration        |
| `SCORING_requirement_weightage` | 0.30    | Weight of Normalized Requirement        |
| `SCORING_top_sku_weightage`     | 0.10    | Weight of Top SKU flag                  |

#### Inventory Score Factors

| Parameter                | Default | Description                                     |
| ------------------------ | ------- | ----------------------------------------------- |
| `INVENTORY_BLACK_FACTOR` | 1.0     | Multiplier for Black (fully depleted) stockouts |
| `INVENTORY_RED_FACTOR`   | 0.5     | Multiplier for Red (low stock) stockouts        |

#### Consolidated Score Weights

| Parameter                          | Default | Description                              |
| ---------------------------------- | ------- | ---------------------------------------- |
| `CONSOLIDATED_demand_priority`     | 0.35    | Weight of PriorityScore (demand signals) |
| `CONSOLIDATED_inventory_priority`  | 0.25    | Weight of Inventory score                |
| `CONSOLIDATED_price_priority`      | 0.25    | Weight of Revenue/Price score            |
| `CONSOLIDATED_history_penetration` | 0.15    | Weight of History Penetration streak     |

#### Market Norm Multipliers

| Parameter             | Default | Description                                              |
| --------------------- | ------- | -------------------------------------------------------- |
| `RE_NORM_MULTIPLIER`  | 1.0     | Fraction of Virtual Norm used as Adjusted Target for RE  |
| `OE_NORM_MULTIPLIER`  | 1.0     | Fraction of Virtual Norm used as Adjusted Target for OE  |
| `ST_NORM_MULTIPLIER`  | 1.0     | Fraction of Virtual Norm used as Adjusted Target for ST  |
| `OTR_NORM_MULTIPLIER` | 1.0     | Fraction of Virtual Norm used as Adjusted Target for OTR |

#### History Penetration Parameters

| Parameter                   | Default | Description                                            |
| --------------------------- | ------- | ------------------------------------------------------ |
| `HISTORY_PENETRATION_N`     | 10      | Lookback window (days); also the maximum history score |
| `HISTORY_PENETRATION_BLACK` | 100     | Minimum penetration % for a day to count as "black"    |

#### Yield Factors (Quality Adjustment — used in Stage 3)

| Parameter          | Default | Description                                       |
| ------------------ | ------- | ------------------------------------------------- |
| `YIELD_FACTOR_OE`  | 0.95    | Fraction of OE output meeting quality spec (95%)  |
| `YIELD_FACTOR_EXP` | 0.95    | Fraction of EXP output meeting quality spec (95%) |
| `YIELD_K_OE`       | 0       | Extra safety buffer units for OE                  |
| `YIELD_K_EXP`      | 0       | Extra safety buffer units for EXP                 |

#### Production Constants

| Parameter           | Default | Description                                                    |
| ------------------- | ------- | -------------------------------------------------------------- |
| `EFFICIENCY_FACTOR` | 0.9     | Machine efficiency — fraction of theoretical output achieved   |
| `DEFAULT_ASP`       | 3000    | Default Average Selling Price (₹) when no dispatch data exists |
| `DEFAULT_CURE_TIME` | 15      | Default curing cycle time (minutes) when not in curing CSV     |

---

### 1.3 Calculated Attributes and Formulas

#### Step A — Inventory Scoring (from BPR)

For each SKU, Black/Red stockout counts are aggregated per location type and combined with location weights:

```
PriorityScore_Inventory =
    Σ (Black_Count_[Loc] × Location_Weight_[Loc] × INVENTORY_BLACK_FACTOR) +
    Σ (Red_Count_[Loc]   × Location_Weight_[Loc] × INVENTORY_RED_FACTOR)
```

Where `[Loc]` iterates over: JIT, Depot, Depot Mobility, Feeder, PWH.

#### Step B — Demand Signals (from BOR & BMR)

**BOR (RE/OE/ST/OTR markets):**

| Derived Column    | Formula                                       |
| ----------------- | --------------------------------------------- |
| `Adjusted_Target` | `Virtual Norm × NORM_MULTIPLIER[Market]`      |
| `Requirement`     | `max(0, Adjusted_Target − Stock)`             |
| `Penetration`     | `(Virtual Norm − Stock) / Virtual Norm × 100` |

> Note: Penetration always uses 100% of Virtual Norm regardless of `NORM_MULTIPLIER`. This ensures a true buffer-depletion reading.

**BMR (EXP market):**

- `Requirement` = `Pending CCR Qty` (directly from report)
- `Penetration` = `BPP` (directly from report)
- `Adjusted_Target` = Not applicable (BMR has no Virtual Norm)

#### Step C — Revenue & Efficiency (from DISPATCH & curing CSV)

| Derived Column   | Formula                                                                                                          |
| ---------------- | ---------------------------------------------------------------------------------------------------------------- |
| `ASP`            | `Amt.in loc.cur. / Quantity` per SKU (from DISPATCH1.csv, plant=1300 only); defaults to `DEFAULT_ASP` if missing |
| `Cure Time`      | From `curing_cycletime.csv`; defaults to `DEFAULT_CURE_TIME + 2.5`                                               |
| `daily_cure`     | `ceil((1440 / Cure_Time) × EFFICIENCY_FACTOR)`                                                                   |
| `rev_pot`        | `ASP × daily_cure` (daily revenue potential)                                                                     |
| `price_priority` | `rev_pot / max(rev_pot)` (normalized to [0, 1])                                                                  |

#### Step D — History Penetration Score (from historical BOR files)

A streak-based score tracking consecutive "black" (fully depleted) days:

| Condition                                                        | Score                             |
| ---------------------------------------------------------------- | --------------------------------- |
| Today's Penetration < `HISTORY_PENETRATION_BLACK` (Red/in-stock) | 0                                 |
| Black today only                                                 | 1                                 |
| Black today + yesterday                                          | 2                                 |
| …                                                                | …                                 |
| Black for N consecutive days                                     | N (max = `HISTORY_PENETRATION_N`) |

```
HistoryPenetrationScore = count of consecutive days where
    Penetration = (Virtual Norm − Stock) / Virtual Norm × 100 ≥ HISTORY_PENETRATION_BLACK

NormHistoryPenetrationScore = HistoryPenetrationScore / HISTORY_PENETRATION_N
```

> Missing BOR files (weekends/holidays) are skipped — the streak remains intact.

#### Step E — PriorityScore (Demand-Only Score)

Normalizations:

```
NormPenetration  = Penetration  / max(Penetration)
NormRequirement  = Requirement  / max(Requirement)
```

```
PriorityScore =
    MarketWeight        × SCORING_market_weightage       +
    NormPenetration     × SCORING_penetration_weightage  +
    NormRequirement     × SCORING_requirement_weightage  +
    TopSKUFlag          × SCORING_top_sku_weightage
```

#### Step F — ConsolidatedPriorityScore (Final Stage 1 Score)

```
NormInventoryScore = PriorityScore_Inventory / max(PriorityScore_Inventory)

ConsolidatedPriorityScore =
    PriorityScore               × CONSOLIDATED_demand_priority       +
    NormInventoryScore          × CONSOLIDATED_inventory_priority     +
    price_priority              × CONSOLIDATED_price_priority         +
    NormHistoryPenetrationScore × CONSOLIDATED_history_penetration
```

---

### 1.4 Stage 1 Output Columns

The output is saved to `combined_data_output.xlsx`, one tab per processing date. Columns are organized in the following logical groups:

| Group                        | Columns                                                                        |
| ---------------------------- | ------------------------------------------------------------------------------ |
| **1 — Identification**       | `SKUCode`, `SKU Description`, `size`                                           |
| **2 — Targets**              | `Market`, `Norm`, `Virtual Norm`, `Adjusted_Target`                            |
| **3 — Demand Signals**       | `Stock`, `Requirement`, `Penetration`, `NormPenetration`, `NormRequirement`    |
| **4 — SKU Attributes**       | `Top SKU`, `TopSKUFlag`, `MarketWeight`, `priority`                            |
| **5 — Inventory Signals**    | `PriorityScore_Inventory`, `NormInventoryScore`                                |
| **6 — Revenue & Efficiency** | `ASP`, `Cure Time`, `daily_cure`, `rev_pot`, `price_priority`                  |
| **7 — History Penetration**  | `HistoryPenetrationScore`, `NormHistoryPenetrationScore`                       |
| **8 — Scoring & Ranking**    | `PriorityScore`, `ConsolidatedPriorityScore`, `Rank_ConsolidatedPriorityScore` |

---

## Stage 2: Machine Deployment Analysis

### 2.1 Input Sources

Stage 2 takes the **Stage 1 output** plus additional live production data:

| Source                 | File Pattern                                              | Key Columns                                                  |
| ---------------------- | --------------------------------------------------------- | ------------------------------------------------------------ |
| **Stage 1 Output**     | `combined_data_output.xlsx`                               | All Stage 1 columns                                          |
| **Daily Mould Report** | `Vectordata/Daily Mould Report/DDMMYYYY MouldDetails.csv` | Sapcode (SKUCode), WCNAME (machine), Mould life, Target life |

---

### 2.2 Configuration Parameters (Stage 2)

All Stage 2 parameters are in `config_input.xlsx` → `Stage2_Config` sheet:

| Parameter                | Default | Description                                                                            |
| ------------------------ | ------- | -------------------------------------------------------------------------------------- |
| `MOULD_LIFE_THRESHOLD`   | 0.9     | Mould health ratio above which a `MouldAlert` is raised (90%)                          |
| `MACHINE_COUNT_PENALTY`  | 0.05    | Priority reduction per machine already running this SKU (5% per machine)               |
| `CRITICAL_GAP_RANK`      | 50      | Stage 1 Rank threshold below which a 0-machine SKU is flagged as a Critical Gap        |
| `EXCESS_PRODUCTION_RANK` | 200     | Stage 1 Rank threshold above which multi-machine SKUs are flagged as Excess Production |
| `EXCESS_MACHINE_COUNT`   | 2       | Minimum machine count to qualify for Excess Production flag                            |

---

### 2.3 Calculated Attributes and Formulas

#### Step A — Mould Report Cleaning

For each SKU (grouped by `Sapcode = SKUCode`):

| Derived Column   | Formula                                                               |
| ---------------- | --------------------------------------------------------------------- |
| `MachineCount`   | `count(unique WCNAME)` — number of distinct machines running this SKU |
| `AvgMouldHealth` | `mean(Mould life / Target life)` across all machines                  |

#### Step B — Ghost SKU Detection

SKUs present in the Mould Report but **absent from Stage 1 demand** are called **Ghost SKUs** — production is running but there is no Vector demand signal. They receive:

| Attribute                            | Value                                                         |
| ------------------------------------ | ------------------------------------------------------------- |
| `Requirement` / `Vector_Requirement` | 0 (no active demand)                                          |
| `Penetration`                        | 0                                                             |
| `Market`                             | `GHOST_SKU_MARKET` (default: `RE`)                            |
| `Cure Time`                          | `GHOST_SKU_CURE_TIME` (default: 20 min)                       |
| `ConsolidatedPriorityScore`          | `min(existing scores) × 0.5` — guaranteed below all real SKUs |
| `IsGhostSKU`                         | `True`                                                        |

#### Step C — Proxy Penetration (Production-Adjusted Priority)

Reduces a SKU's priority if it is already running on multiple machines (less urgent to schedule more):

```
penalty_factor = max(0,  1 − (MachineCount × MACHINE_COUNT_PENALTY))

ProxyPenetration = ConsolidatedPriorityScore × penalty_factor

ProxyRank = rank(ProxyPenetration, descending)
```

**Example:** A SKU with `ConsolidatedPriorityScore = 0.8` running on 4 machines:  
`penalty_factor = 1 − (4 × 0.05) = 0.80`  
`ProxyPenetration = 0.8 × 0.80 = 0.64`

#### Step D — Gap Analysis Flags

| Flag               | Condition                                                               | Meaning                                                                       |
| ------------------ | ----------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| `CriticalGap`      | `Rank ≤ CRITICAL_GAP_RANK AND MachineCount == 0`                        | High-priority SKU with **no machines assigned** — immediate scheduling needed |
| `ExcessProduction` | `Rank > EXCESS_PRODUCTION_RANK AND MachineCount > EXCESS_MACHINE_COUNT` | Low-priority SKU consuming too many machines — review for reallocation        |
| `MouldAlert`       | `AvgMouldHealth > MOULD_LIFE_THRESHOLD`                                 | Mould nearing end-of-life — maintenance action required                       |

---

### 2.4 Stage 2 Output Columns

Output saved to `deployment_analysis_report.xlsx`, one tab per date:

| Group                              | Columns                                                                                                                          |
| ---------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| **1 — Identification**             | `SKUCode`, `SKU Description`, `size`                                                                                             |
| **2 — Targets**                    | `Market`, `Norm`, `Virtual Norm`, `Adjusted_Target`                                                                              |
| **3 — Demand Signals**             | `Stock`, `Requirement`, `Penetration`, `NormPenetration`, `NormRequirement`                                                      |
| **4 — SKU Attributes**             | `Top SKU`, `TopSKUFlag`, `MarketWeight`, `priority`                                                                              |
| **5 — Inventory Signals**          | `PriorityScore_Inventory`, `NormInventoryScore`                                                                                  |
| **5b — History Penetration**       | `HistoryPenetrationScore`, `NormHistoryPenetrationScore`                                                                         |
| **6 — Deployment Metrics & Flags** | `MachineCount`, `AvgMouldHealth`, `ProxyPenetration`, `ProxyRank`, `CriticalGap`, `ExcessProduction`, `MouldAlert`, `IsGhostSKU` |
| **7 — Revenue & Efficiency**       | `ASP`, `Cure Time`, `daily_cure`, `rev_pot`, `price_priority`                                                                    |
| **8 — Scoring & Ranking**          | `PriorityScore`, `ConsolidatedPriorityScore`, `Rank_ConsolidatedPriorityScore`                                                   |

---

## Stage 3: Manual Strategic Override (CPT Input)

### 3.1 Input Sources

Stage 3 takes the **Stage 2 output** plus a manually maintained Excel file:

| Source                 | File                               | Key Columns                                                   |
| ---------------------- | ---------------------------------- | ------------------------------------------------------------- |
| **Stage 2 Output**     | `deployment_analysis_report.xlsx`  | All Stage 2 columns                                           |
| **Manual Demand File** | `data/manual_frontend_demand.xlsx` | SKU Code, SKU Description, Market, Quantity, Highest Priority |

### 3.2 Manual Demand File Format

CPT planners fill this Excel file directly:

| Column             | Description                                       |
| ------------------ | ------------------------------------------------- |
| `SKU Code`         | SKU identifier (string)                           |
| `SKU Description`  | SKU name/description                              |
| `Market`           | Market category (OE, RE, EXP, ST, OTR, etc.)      |
| `Quantity`         | Required production quantity (`CPT_Requirement`)  |
| `Highest Priority` | Flag: `1` = highest priority, `0` = normal manual |

---

### 3.3 Calculated Attributes and Formulas

#### Step A — Super-Boost Priority Score

Manual entries are assigned a score guaranteed to exceed any automated score (automated scores are bounded by [0, 1]):

```
ManualPriorityScore = BOOST_BASE + (HighestPriority × BOOST_MULTIPLIER)
```

Where:

- `BOOST_BASE = 10.0` — floor score for any manual entry
- `BOOST_MULTIPLIER = 1.0` — extra score for entries flagged `Highest Priority = 1`

| Entry Type                               | ManualPriorityScore |
| ---------------------------------------- | ------------------- |
| Normal manual (`HighestPriority = 0`)    | 10.0                |
| Highest Priority (`HighestPriority = 1`) | 11.0                |
| Automated (best case)                    | ≤ 1.0               |

#### Step B — Multi-Source Requirement Transparency

For any SKU appearing in both manual and automated demand:

| Column               | Source                     | Purpose                                       |
| -------------------- | -------------------------- | --------------------------------------------- |
| `Vector_Requirement` | Stage 1/2 calculated value | What automated analysis demanded              |
| `CPT_Requirement`    | Manual input `Quantity`    | What the planner specified (takes precedence) |
| `Requirement`        | = `CPT_Requirement`        | Used for all downstream calculations          |

#### Step C — Updated Requirement (Yield Adjustment)

For **OE** and **EXP** markets only, the final production quantity is inflated to account for quality yield:

```
Updated_Requirement = ceil(Requirement / yield_factor + k)
```

Where:

- `yield_factor` = `YIELD_FACTOR_OE` or `YIELD_FACTOR_EXP` (e.g., 0.95 = 95% top quality)
- `k` = `YIELD_K_OE` or `YIELD_K_EXP` (extra safety buffer units)

For **RE, ST, OTR** markets: `Updated_Requirement = Requirement` (no adjustment).

#### Step D — Strategic Priority Score (Unified Score)

A single score covering all rows (manual + automated):

```
StrategicPriorityScore =
    ManualPriorityScore          if Source == "Manual"
    ConsolidatedPriorityScore    if Source == "Automated"
```

#### Step E — Final Rank

All rows are sorted by `StrategicPriorityScore` descending:

```
Final Rank = sequential rank (1, 2, 3, …) after sorting
```

Manual entries (score 10–11) always appear before automated entries (score ≤ 1).

---

### 3.4 Stage 3 Output Columns

Final output saved to `final_hybrid_deployment_report.xlsx`, one tab per date:

| Group                               | Columns                                                                                                                                     |
| ----------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| **0 — Primary Production Sequence** | `Final Rank`                                                                                                                                |
| **1 — Identification**              | `SKUCode`, `SKU Description`, `size`                                                                                                        |
| **2 — Source & Override**           | `Source`, `HighestPriority`, `ManualPriorityScore`, `ManualRank`                                                                            |
| **3 — Strategic Score**             | `StrategicPriorityScore`                                                                                                                    |
| **4 — Targets**                     | `Market`, `Norm`, `Virtual Norm`, `Adjusted_Target`                                                                                         |
| **5 — Demand Signals**              | `Stock`, `Vector_Requirement`, `CPT_Requirement`, `Requirement`, `Updated_Requirement`, `Penetration`, `NormPenetration`, `NormRequirement` |
| **6 — SKU Attributes**              | `Top SKU`, `TopSKUFlag`, `MarketWeight`, `priority`                                                                                         |
| **7 — Inventory Signals**           | `PriorityScore_Inventory`, `NormInventoryScore`                                                                                             |
| **7b — History Penetration**        | `HistoryPenetrationScore`, `NormHistoryPenetrationScore`                                                                                    |
| **8 — Deployment Metrics & Flags**  | `MachineCount`, `AvgMouldHealth`, `ProxyPenetration`, `ProxyRank`, `CriticalGap`, `ExcessProduction`, `MouldAlert`, `IsGhostSKU`            |
| **9 — Revenue & Efficiency**        | `ASP`, `Cure Time`, `daily_cure`, `rev_pot`, `price_priority`                                                                               |
| **10 — Detailed Scoring**           | `PriorityScore`, `ConsolidatedPriorityScore`, `Rank_ConsolidatedPriorityScore`                                                              |

---

## End-to-End Data Flow

```
Vector Daily Reports              Manual Input (CPT)
 ┌──────────┐                      ┌──────────────────────────┐
 │   SPOR   │                      │  manual_frontend_demand   │
 │   BOR    │──────┐               │  .xlsx                   │
 │   BMR    │      ▼               └─────────────┬────────────┘
 │   BPR    │  [Stage 1]                         │
 └──────────┘  demand_processor.py               │
                    │                            │
                    ▼                            │
            combined_data_output.xlsx            │
                    │                            │
                    ▼                            │
 ┌────────────────────────────────┐              │
 │  Daily Mould Report (.csv)     │              │
 └─────────────────┬──────────────┘              │
                   │                             │
                   ▼                             │
               [Stage 2]                         │
         deployment_processor.py                 │
                   │                             │
                   ▼                             │
       deployment_analysis_report.xlsx           │
                   │                             │
                   └───────────────┬─────────────┘
                                   ▼
                               [Stage 3]
                    manual_integration_processor.py
                                   │
                                   ▼
                  final_hybrid_deployment_report.xlsx
```

---

## Column Reference Glossary

| Column                           | Definition                                                                   |
| -------------------------------- | ---------------------------------------------------------------------------- |
| `SKUCode`                        | Alpha-numeric product identifier (SAP material code)                         |
| `SKU Description`                | Product name                                                                 |
| `size`                           | Rim size extracted from SKUCode characters [8:10]                            |
| `Market`                         | Market category: OE, RE, EXP, ST, OTR                                        |
| `Norm`                           | Target stock level (from BOR)                                                |
| `Virtual Norm`                   | Adjusted/virtual target stock level (from BOR)                               |
| `Adjusted_Target`                | `Virtual Norm × NORM_MULTIPLIER[Market]` — effective replenishment target    |
| `Stock`                          | Current available stock                                                      |
| `Requirement`                    | Units needed to reach the Adjusted Target; `max(0, Adjusted_Target − Stock)` |
| `Penetration`                    | `(Virtual Norm − Stock) / Virtual Norm × 100` — buffer depletion %           |
| `NormPenetration`                | Penetration normalized to [0, 1] within date's SKU set                       |
| `NormRequirement`                | Requirement normalized to [0, 1] within date's SKU set                       |
| `Top SKU`                        | "T" if flagged as a priority SKU, otherwise blank                            |
| `TopSKUFlag`                     | 1 for Top SKU, 0 otherwise                                                   |
| `MarketWeight`                   | Configured market importance score (OE=4, ST=3, EXP=2, OTR=2, RE=1)          |
| `priority`                       | Tuple `(−MarketWeight, −Penetration, −Requirement, −TopSKUFlag)` — sort key  |
| `PriorityScore_Inventory`        | Weighted sum of Black/Red stockout counts across location types              |
| `NormInventoryScore`             | `PriorityScore_Inventory / max(PriorityScore_Inventory)`                     |
| `ASP`                            | Average Selling Price (₹) derived from dispatch data                         |
| `Cure Time`                      | Tyre curing cycle time (minutes)                                             |
| `daily_cure`                     | `ceil((1440 / Cure_Time) × EFFICIENCY_FACTOR)` — units producible per day    |
| `rev_pot`                        | `ASP × daily_cure` — daily revenue potential per SKU                         |
| `price_priority`                 | `rev_pot / max(rev_pot)` — normalized revenue score                          |
| `HistoryPenetrationScore`        | Consecutive "black" day streak (integer 0–N)                                 |
| `NormHistoryPenetrationScore`    | `HistoryPenetrationScore / HISTORY_PENETRATION_N`                            |
| `PriorityScore`                  | Demand-only composite score (Market + Penetration + Requirement + TopSKU)    |
| `ConsolidatedPriorityScore`      | Final Stage 1/2 score (Demand + Inventory + Price + History)                 |
| `Rank_ConsolidatedPriorityScore` | Rank on ConsolidatedPriorityScore (1 = highest priority)                     |
| `MachineCount`                   | Number of unique machines currently producing this SKU                       |
| `AvgMouldHealth`                 | Average `Mould life / Target life` ratio across machines                     |
| `ProxyPenetration`               | `ConsolidatedPriorityScore × (1 − MachineCount × MACHINE_COUNT_PENALTY)`     |
| `ProxyRank`                      | Rank based on ProxyPenetration                                               |
| `CriticalGap`                    | True if high-rank SKU has no machines assigned                               |
| `ExcessProduction`               | True if low-rank SKU is over-machined                                        |
| `MouldAlert`                     | True if `AvgMouldHealth > MOULD_LIFE_THRESHOLD`                              |
| `IsGhostSKU`                     | True if SKU is in mould report but absent from Vector demand                 |
| `Source`                         | "Manual" or "Automated"                                                      |
| `HighestPriority`                | 1 if CPT flagged as absolute priority override, 0 otherwise                  |
| `ManualPriorityScore`            | Super-boost score: `10 + HighestPriority`                                    |
| `ManualRank`                     | Rank within the manual-only block                                            |
| `Vector_Requirement`             | Requirement calculated by automated Stage 1/2 pipeline                       |
| `CPT_Requirement`                | Quantity entered by CPT planner (overrides Vector)                           |
| `Updated_Requirement`            | Yield-adjusted final requirement for OE/EXP markets                          |
| `StrategicPriorityScore`         | Unified score: ManualPriorityScore OR ConsolidatedPriorityScore              |
| `Final Rank`                     | Absolute production sequence rank across all Stage 3 rows                    |
