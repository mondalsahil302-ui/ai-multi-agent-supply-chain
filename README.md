# AI Multi-Agent Supply Chain

This repository contains the foundational raw datasets for the AI Multi-Agent Supply Chain system.

## Project Status

The codebase has been reset to retain only the raw source datasets. All previous work (documentation, entity schemas, data dictionary, preprocessing notebooks, and scripts) is permanently preserved and can be restored at any time.

### How to Restore Previous Work

To access or restore everything as it was prior to this cleanup:

- **Switch to backup branch**:
  ```bash
  git checkout backup/pre-cleanup-all
  ```
- **Or checkout the backup tag**:
  ```bash
  git checkout v0-pre-cleanup
  ```
- **Or restore specific files/folders into your current branch**:
  ```bash
  git checkout backup/pre-cleanup-all -- docs/ notebooks/ scripts/
  ```

---

## Raw Datasets (`Datasets/raw/`)

The raw datasets are organized across six operational domains:

### 1. Demand (`Datasets/raw/demand/`)
- `Demand of last 2 years.xlsx`: Historical order and demand transaction records.
- `final_demand_agent_training_2_years_kolkata (1).xlsx`: Regional demand dataset for Kolkata.
- `sales_history.xlsx`: Historical sales data.

### 2. External Factors (`Datasets/raw/external/`)
- `festival_calendar.csv`: Major holiday and festive season dates.
- `weather_weekly.csv`: Weekly weather metrics (temperature, precipitation, etc.).

### 3. Inventory (`Datasets/raw/inventory/`)
- `inventory_stock.xlsx`: Stock levels across SKUs and storage locations.
- `inventory_transactions.xlsx`: Inbound, outbound, and adjustment transactions.

### 4. Master Data (`Datasets/raw/master/`)
- `Final product list.xlsx` / `products.csv`: Product SKU attributes, categories, and units.
- `locations.csv.csv`: Geospatial/regional delivery locations.

### 5. Supplier Data (`Datasets/raw/supplier/`)
- `supplier_inventory.xlsx`: Vendor capacity, lead times, and catalogue availability.

### 6. Warehouse Data (`Datasets/raw/warehouse/`)
- `warehouses.xlsx` / `final_warehouse_dataset_kolkata.xlsx`: Warehouse facility specs, capacities, and operational constraints.
