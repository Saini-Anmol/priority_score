# Vector Supply Chain Intelligence System

A comprehensive manufacturing priority and deployment analysis system designed to optimize tire production planning through intelligent demand prioritization and machine deployment analysis.

## 📋 Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Installation](#installation)
- [Project Structure](#project-structure)
- [Stage 1: Demand Prioritization](#stage-1-demand-prioritization)
- [Stage 2: Machine Deployment Analysis](#stage-2-machine-deployment-analysis)
- [Configuration](#configuration)
- [Usage](#usage)
- [Output Reports](#output-reports)

## 🎯 Overview

The Vector Supply Chain Intelligence System is a two-stage analytical tool that helps manufacturing plants optimize production by:

1. **Stage 1**: Analyzing demand signals across multiple markets and locations to rank SKUs by priority
2. **Stage 2**: Comparing high-priority SKUs with current machine deployment to identify critical gaps and optimization opportunities

## ✨ Features

### Stage 1: Demand Prioritization

- 📊 Multi-factor priority scoring based on:
  - Market importance (OE, ST, EXP, RE)
  - Penetration levels
  - Requirement quantities
  - Location types (JIT, Depot, Feeder, etc.)
- 💰 Revenue potential analysis using ASP and curing cycle times
- 🎯 Dual ranking system (Demand+Inventory vs. Demand+Inventory+Price)
- 📈 Inventory criticality scoring (Red/Black stockout analysis)

### Stage 2: Machine Deployment Analysis

- 🏭 Current production status tracking
- 🔍 Critical gap identification (high-priority SKUs not in production)
- ⚠️ Excess production alerts (low-priority SKUs using many machines)
- 🔧 Mould health monitoring
- 📉 Proxy Penetration calculation (adjusts urgency based on active production)

## 🚀 Installation

### Prerequisites

- Python 3.8 or higher
- pip package manager

### Setup

1. **Clone the repository**

```bash
git clone https://github.com/Saini-Anmol/priority_score.git
cd priority_score
```

2. **Install dependencies**

```bash
pip install -r requirements.txt
```

The required packages are:

- `pandas>=2.0.0` - Data processing and analysis
- `numpy>=1.24.0` - Numerical computations
- `openpyxl>=3.0.0` - Excel file handling

3. **Prepare data directory**
   Ensure your data files are organized in the following structure:

```
data/
├── Vectordata/
│   ├── SPOR/          # Single Production Order Reports
│   ├── BOR/           # BOR Color Band Reports
│   ├── BMR/           # BM Reports
│   ├── BPR/           # Buffer Penetration Reports
│   └── Daily Mould Report/  # Mould details for Stage 2
├── DISPATCH1.csv
└── curing_cycletime.csv
```

## 📁 Project Structure

```
Vector_Project/
├── config.py                    # Stage 1 configuration parameters
├── demand_processor.py          # Stage 1 processing logic
├── app.py                       # Stage 1 standalone runner
├── config_stage2.py             # Stage 2 configuration parameters
├── deployment_processor.py      # Stage 2 processing logic
├── app_stage2.py                # Integrated Stage 1 + Stage 2 runner
├── requirements.txt             # Python dependencies
├── .gitignore                   # Git ignore rules
└── data/                        # Data directory (not in git)
```

## 📊 Stage 1: Demand Prioritization

### What It Does

Stage 1 analyzes multiple data sources to create a ranked list of SKUs based on:

- **Market Priority**: OE (highest) → ST → EXP → RE (lowest)
- **Penetration %**: How much buffer stock is depleted
- **Requirement**: Pending demand quantity
- **Top SKU Status**: Critical SKUs identified in the system
- **Inventory Status**: Red/Black stockout alerts across warehouse types
- **Revenue Potential**: ASP × Daily curing capacity

### Input Files (per date)

For a given date `DDMMYYYY`, Stage 1 requires:

- `Single_Production_Order_Report_DDMMYYYY.csv`
- `BORColorBandwiseReport__DD-MM-YYYY.csv`
- `Prod_OverAll_BMReport__DD_MM_YYYY.xlsx`
- `BufferPenetrationReport__DD-MM-YYYY.csv`
- `DISPATCH1.csv` (static)
- `curing_cycletime.csv` (static)

### Output

**File**: `combined_data_output.xlsx`

Each sheet represents one date, containing ranked SKUs with columns:

- `Rank_ConsolidatedPriorityScore` - Primary ranking (Demand + Inventory)
- `Rank_ConsolidatedPriorityScore_p` - Secondary ranking (Demand + Inventory + Price)
- All component scores and intermediate calculations

### Running Stage 1 Standalone

```bash
python app.py
```

You'll be prompted to enter:

- Start date (DD.MM.YYYY)
- End date (DD.MM.YYYY)

The system will process all dates in the range and generate a multi-sheet Excel report.

## 🏭 Stage 2: Machine Deployment Analysis

### What It Does

Stage 2 takes the output from Stage 1 and cross-references it with the Daily Mould Report to:

- Identify which high-priority SKUs are **not** in production (Critical Gaps)
- Flag low-priority SKUs consuming excessive machine capacity (Excess Production)
- Calculate **Proxy Penetration** - adjusts priority based on how many machines are already running the SKU
- Monitor mould health to prevent unexpected downtime

### Input Files (per date)

For a given date `DDMMYYYY`, Stage 2 requires:

- All Stage 1 input files (see above)
- `DDMMYYYY MouldDetails.csv` (in `data/Vectordata/Daily Mould Report/`)

### Output

**File**: `deployment_analysis_report.xlsx`

Contains all Stage 1 columns plus:

- `MachineCount` - Number of machines currently running this SKU
- `AvgMouldHealth` - Average mould life % across machines
- `ProxyPenetration` - Adjusted priority score based on production status
- `ProxyRank` - New ranking after deployment adjustment
- `CriticalGap` - Boolean flag for high-priority, not-in-production SKUs
- `ExcessProduction` - Boolean flag for low-priority SKUs with many machines
- `MouldAlert` - Boolean flag for moulds nearing end of life

### Running Stage 2 (Integrated)

```bash
python app_stage2.py
```

You'll be prompted to enter:

- Analysis date (DD.MM.YYYY)

The system will:

1. Execute Stage 1 processing
2. Execute Stage 2 deployment analysis
3. Generate a consolidated Excel report
4. Display executive summary with actionable insights

### Example Output

```
================================================================================
VECTOR SUPPLY CHAIN INTELLIGENCE SYSTEM
Stage 1: Demand Prioritization | Stage 2: Machine Deployment Analysis
================================================================================

Processing analysis for: 08-02-2026
--------------------------------------------------------------------------------

[STAGE 1] Demand Prioritization Analysis
[STAGE 1] Successfully processed 1245 SKUs

[STAGE 2] Machine Deployment Analysis
[Stage 2] Found 387 SKUs in mould report
[Stage 2] Analysis complete:
  - Critical Gaps: 12
  - Excess Production: 5
  - Mould Alerts: 3

[INSIGHTS] Executive Summary
Production Status:
  • SKUs currently in production: 387
  • SKUs NOT in production: 858

Action Required:
  • Critical Gaps (High-priority, not running): 12
  • Excess Production (Low-priority, many machines): 5
  • Mould Alerts (Nearing end of life): 3

 ATTENTION: 12 high-priority SKUs are not in production!
   Review the 'CriticalGap' column in the report.
```

## ⚙️ Configuration

### Stage 1 Configuration (`config.py`)

**Market Weights** - Higher number = Higher priority

```python
MARKET_WEIGHTS = {
    'OE': 4,   # Original Equipment
    'ST': 3,   # Stock
    'EXP': 2,  # Export
    'RE': 1    # Replacement
}
```

**Location Weights** - Warehouse importance

```python
LOCATION_WEIGHTS = {
    'JIT': 5,           # Highest priority
    'Depot': 4,
    'Depot Mobility': 3,
    'Feeder': 2,
    'PWH': 1            # Lowest priority
}
```

**Scoring Weights** - Contribution to final score

```python
SCORING_PARAMS = {
    "market_weightage": 0.25,       # 25%
    "penetration_weightage": 0.35,  # 35%
    "requirement_weightage": 0.30,  # 30%
    "top_sku_weightage": 0.10       # 10%
}
```

**Tier Weights** - Multi-tier scoring

```python
# Tier 1: Demand + Inventory
TIER1_WEIGHTS = {
    "demand_priority": 0.6,     # 60%
    "inventory_priority": 0.4   # 40%
}

# Tier 2: Demand + Inventory + Price
TIER2_WEIGHTS = {
    "demand_priority": 0.4,     # 40%
    "inventory_priority": 0.3,  # 30%
    "price_priority": 0.3       # 30%
}
```

### Stage 2 Configuration (`config_stage2.py`)

**Proxy Penetration Parameters**

```python
# Penalty per machine (5% reduction in priority per running machine)
MACHINE_COUNT_PENALTY = 0.05
```

**Gap Analysis Thresholds**

```python
# Critical Gap: SKUs with rank better than this value
CRITICAL_GAP_RANK = 50

# Excess Production: SKUs with rank worse than this value
EXCESS_PRODUCTION_RANK = 200
EXCESS_MACHINE_COUNT = 2  # Machine count threshold
```

**Mould Health Monitoring**

```python
# Alert when mould has used 90% of its target life
MOULD_LIFE_THRESHOLD = 0.9
```

## 📈 Output Reports

### Understanding Priority Scores

**ConsolidatedPriorityScore** (Tier 1)

- Combines demand factors (market, penetration, requirement) with inventory criticality
- Higher score = Higher priority
- Used for initial ranking

**ConsolidatedPriorityScore_p** (Tier 2)

- Adds revenue potential to Tier 1 score
- Balances urgency with profitability
- Used for financial optimization

**ProxyPenetration** (Stage 2)

- Adjusts priority based on current production status
- Formula: `ConsolidatedPriorityScore × (1 - MachineCount × 0.05)`
- SKUs already running get lower urgency

### Key Columns Explained

| Column                           | Description                                           |
| -------------------------------- | ----------------------------------------------------- |
| `SKUCode`                        | Unique product identifier                             |
| `Market`                         | OE, ST, EXP, or RE                                    |
| `Penetration`                    | Buffer depletion %                                    |
| `Requirement`                    | Pending demand quantity                               |
| `PriorityScore`                  | Demand-based score                                    |
| `PriorityScore_Inventory`        | Inventory criticality score                           |
| `ConsolidatedPriorityScore`      | Tier 1 final score                                    |
| `ConsolidatedPriorityScore_p`    | Tier 2 final score (with price)                       |
| `Rank_ConsolidatedPriorityScore` | Primary ranking (lower = higher priority)             |
| `MachineCount`                   | (Stage 2) Machines currently running this SKU         |
| `ProxyPenetration`               | (Stage 2) Adjusted priority score                     |
| `ProxyRank`                      | (Stage 2) Final ranking after deployment adjustment   |
| `CriticalGap`                    | (Stage 2) True if high-priority but not in production |
| `ExcessProduction`               | (Stage 2) True if low-priority with many machines     |

## 🔍 Troubleshooting

**Missing Files Error**

- Ensure all input files exist for the selected date
- Check file naming conventions match exactly
- Verify date format in filenames

**Empty Merge Results**

- This is prevented by string type casting in the code
- All SKUCode columns are automatically converted to strings

**Large Date Ranges**

- Processing many dates can be memory-intensive
- Consider processing in smaller batches

## 📝 License

This project is proprietary and confidential.

## 👤 Author

**Anmol Saini**

- GitHub: [@Saini-Anmol](https://github.com/Saini-Anmol)
- Repository: [priority_score](https://github.com/Saini-Anmol/priority_score)

---

_Built for optimizing manufacturing operations through data-driven insights._
