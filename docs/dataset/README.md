# Raw Dataset README

## 1. Overview

This directory contains the **raw source datasets** used for the Kolkata supply-chain project.

The datasets are documented here exactly as source datasets. This README covers only:

- Dataset name
- Source file
- Purpose
- Record count
- Row-level meaning (grain)
- Keys
- Important fields
- Data coverage
- Source/provenance
- Dataset-specific notes

This README does **not** describe preprocessing, staging, standardization, feature engineering, machine learning, agents, routing, optimization, or system architecture.

---

## 2. Raw Dataset Inventory

| # | Dataset | Source File | Approx. Records | Grain | Primary / Business Key |
|---|---|---|---:|---|---|
| 1 | Product Master | `product_master.csv` / `Final product list.xlsx` | 200 | 1 row = 1 product | `product_id` |
| 2 | Location / Region Master | `location_regions.csv` | 40 | 1 row = 1 location/region | `location_id` |
| 3 | Sales History | `sales_history_source.xlsx` / `SELL of past 2 years.xlsx` | ~1,112,000 | 1 row = 1 location × product × week | `region_product_week_key` |
| 4 | Demand Agent Training Dataset | `demand_agent_training.csv` / `final_demand_agent_training_Jan2024_Aug2026_CORRECTED.xlsx` | 27,800 | 1 row = 1 location × selected product × week | `demand_id` |
| 5 | Festival Calendar | `festival_calendar.csv` | 36 | 1 row = 1 festival/holiday event | Festival/date fields |
| 6 | Weekly Weather | `weather_weekly.csv` | 105 | 1 row = 1 week | `week_id` / week date |
| 7 | Warehouse Master | `warehouse_master.csv` / `Kolkata_Warehouse_Master_FINAL.xlsx` | 15 | 1 row = 1 warehouse | `warehouse_id` |
| 8 | Inventory Position | `inventory_position.csv` | 3,000 | 1 row = 1 warehouse × product | Warehouse-product combination |
| 9 | Shelf Master | `shelf_master.csv` | 600 | 1 row = 1 shelf | `shelf_id` |
| 10 | Product-Shelf Assignment | `product_shelf_assignment.csv` | 3,000 | 1 row = 1 warehouse × product storage assignment | Warehouse-product combination |
| 11 | Supplier Master | `supplier_master.csv` | 200 | 1 row = 1 supplier | `supplier_id` |
| 12 | Supplier Area Options | `supplier_area_options.csv` | 200 | 1 row = 1 supplier × location option | Supplier-location combination |
| 13 | Supplier Product Catalog | `supplier_product_catalog.csv` | 8,000 | 1 row = 1 supplier × product | Supplier-product combination |

> **Note:** Where both CSV and original Excel names are shown, the Excel file is the original source file and the CSV name represents the corresponding raw dataset used in the project data directory.

---

# 3. Dataset Details

## 3.1 Product Master

**Source file:** `Final product list.xlsx`  
**Dataset file:** `product_master.csv`  
**Record count:** 200  
**Grain:** One row represents one product.  
**Key:** `product_id`

### Purpose

Contains the master catalog of products used across the supply-chain data.

### Important fields

- `product_id`
- `category_code`
- `category_name`
- `product_name`
- `brand`
- `quality_level`
- `unit_type`
- Product size / unit-size information
- Cost price fields
- Selling price fields

### Data characteristics

- 200 products
- Multiple product categories
- Product-level commercial and descriptive attributes
- Multiple size/cost/selling-price groups are represented in the source workbook

### Notes

`product_id` is the main product identifier used to refer to a product in other raw datasets.

---

## 3.2 Location / Region Master

**Source file:** `location_regions.csv`  
**Record count:** 40  
**Grain:** One row represents one Kolkata region/location.  
**Key:** `location_id`

### Purpose

Defines the geographical areas represented in the raw supply-chain datasets.

### Important fields

- `location_id`
- Region/location name
- Geographic/location attributes available in the source

### Data characteristics

The dataset contains 40 Kolkata locations/regions, including areas such as Lake Gardens, Tollygunge, Ballygunge, Jadavpur, Garia and other mapped locations.

### Notes

`location_id` is the main identifier for a region/location.

---

## 3.3 Sales History

**Source file:** `SELL of past 2 years.xlsx`  
**Dataset file:** `sales_history_source.xlsx`  
**Record count:** Approximately 1,112,000 rows  
**Grain:** One row represents one location × product × week.  
**Key:** `region_product_week_key`

### Purpose

Contains historical weekly sales observations across locations and products.

### Important fields

- Location/region identifier
- Product identifier
- Week/date information
- `region_week_key`
- `region_product_week_key`
- Weekly units sold / demand quantity
- Price-related fields available in the source
- Inventory-related fields where present
- Ranking / demand-position fields where present

### Data coverage

- 139 weekly sheets
- Weekly Sunday-Saturday periods
- Historical coverage spanning approximately two years and the project-defined weekly period

### Data characteristics

- Approximately 8,000 rows per weekly sheet
- Zero-demand records are retained where present in the source structure
- The source contains historical location-product-week observations

### Notes

The workbook is organized into separate weekly sheets. `region_product_week_key` is intended to uniquely identify a location-product-week observation.

---

## 3.4 Demand Agent Training Dataset

**Source file:** `final_demand_agent_training_Jan2024_Aug2026_CORRECTED.xlsx`  
**Dataset file:** `demand_agent_training.csv`  
**Record count:** 27,800  
**Grain:** One row represents one location × selected product × week.  
**Key:** `demand_id`

### Purpose

Provides weekly demand observations for a selected set of products across the defined Kolkata locations, together with contextual variables available in the source dataset.

### Important fields

- `demand_id`
- `location_id`
- `region`
- `demand_rank`
- `product_id`
- `product_name`
- `unit_size`
- Week/date fields
- Weekday/weekend demand information
- `units_sold`
- Average price
- Promotion / discount information
- Holiday / festival information
- Season information
- Weather information
- `stockout_flag`
- Forecast period start/end fields
- `next_week_demand_target_units`
- `data_source`

### Data coverage

- 139 weekly windows
- 40 locations
- 5 selected products per location-week
- Date range: January 2024 to August 2026

### Notes

The dataset contains the field `next_week_demand_target_units` as part of the supplied source dataset. This README records the field as supplied and does not describe how it is generated or used.

---

## 3.5 Festival Calendar

**Source file:** `festival_calendar.csv`  
**Record count:** 36  
**Grain:** One row represents one festival or holiday event/date.

### Purpose

Contains festival and holiday calendar information relevant to the Kolkata demand context.

### Important fields

- Festival name
- Festival date
- Holiday indicator where present
- Other event/date descriptors available in the source

### Data characteristics

The dataset contains 36 festival/holiday records.

### Notes

Festival dates are stored independently from sales and demand observations so that an event can be associated with the relevant calendar period.

---

## 3.6 Weekly Weather

**Source file:** `weather_weekly.csv`  
**Record count:** 105  
**Grain:** One row represents one week.  
**Key:** Weekly date / `week_id`

### Purpose

Contains weekly weather observations for the project time period.

### Important fields

- Week/date identifier
- Temperature
- Humidity
- Rainfall
- Other weather attributes available in the source

### Data coverage

The raw file contains 105 weekly weather records.

### Notes

Weather observations are represented at weekly granularity in the supplied dataset.

---

## 3.7 Warehouse Master

**Source file:** `Kolkata_Warehouse_Master_FINAL.xlsx`  
**Dataset file:** `warehouse_master.csv`  
**Record count:** 15  
**Grain:** One row represents one warehouse.  
**Key:** `warehouse_id`

### Purpose

Contains the master information for the warehouses used in the Kolkata supply-chain dataset.

### Important fields

- `warehouse_id`
- Warehouse / area name
- Latitude
- Longitude
- Storage capacity
- Operating hours
- Dispatch capacity
- Service radius
- Vehicle-type availability/count information

### Data characteristics

- 15 warehouses
- Warehouse identifiers follow the `WH-KOL-001` to `WH-KOL-015` pattern in the current master
- Geographic coordinates are provided for warehouse locations

### Notes

`warehouse_id` is the authoritative warehouse identifier in the supplied warehouse master.

---

## 3.8 Inventory Position

**Source file:** `Complete dataset for inventory.xlsx`  
**Dataset file:** `inventory_position.csv`  
**Record count:** 3,000  
**Grain:** One row represents one warehouse × product inventory position.

### Purpose

Contains the current/snapshot inventory position of products held by warehouses.

### Important fields

- `warehouse_id`
- `product_id`
- Stock quantity fields
- Reserved stock fields where present
- Safety stock fields where present
- Inbound stock fields where present
- Other inventory-position attributes supplied in the source

### Data characteristics

- 15 warehouses
- 200 products
- 3,000 warehouse-product combinations

### Notes

The dataset represents warehouse-level product inventory rather than individual customer orders.

---

## 3.9 Shelf Master

**Source file:** `Complete dataset for inventory.xlsx`  
**Dataset file:** `shelf_master.csv`  
**Record count:** 600  
**Grain:** One row represents one warehouse shelf.  
**Key:** `shelf_id`

### Purpose

Defines shelf/storage locations within warehouses.

### Important fields

- `shelf_id`
- `warehouse_id`
- Shelf/location attributes
- Capacity or storage attributes where supplied
- Storage characteristics where supplied

### Data characteristics

- 600 shelves
- Shelves are associated with the warehouse in which they are located

---

## 3.10 Product-Shelf Assignment

**Source file:** `Complete dataset for inventory.xlsx`  
**Dataset file:** `product_shelf_assignment.csv`  
**Record count:** 3,000  
**Grain:** One row represents one warehouse × product storage assignment.

### Purpose

Maps products to the warehouse storage locations/shelves defined in the inventory source workbook.

### Important fields

- `warehouse_id`
- `product_id`
- `shelf_id`
- Assignment/location information

### Data characteristics

- 3,000 assignments
- Links products to physical storage locations within warehouses

---

## 3.11 Supplier Master

**Source file:** Supplier source workbook (`supplier...xlsx`)  
**Dataset file:** `supplier_master.csv`  
**Record count:** 200  
**Grain:** One row represents one supplier.  
**Key:** `supplier_id`

### Purpose

Contains the master information for suppliers participating in the supply-chain data.

### Important fields

- `supplier_id`
- Supplier name/identity
- Supplier location
- Latitude
- Longitude
- Supplier attributes supplied in the source

### Data characteristics

- 200 suppliers
- Supplier locations are represented geographically where coordinates are available

---

## 3.12 Supplier Area Options

**Source file:** Supplier source workbook (`supplier...xlsx`)  
**Dataset file:** `supplier_area_options.csv`  
**Record count:** 200  
**Grain:** One row represents one supplier × location service/coverage option.

### Purpose

Defines the locations/areas that suppliers can serve according to the supplied source data.

### Important fields

- `supplier_id`
- `location_id`
- Area/service information

### Data characteristics

- 200 supplier-area records
- Associates suppliers with supported locations/areas

---

## 3.13 Supplier Product Catalog

**Source file:** Supplier source workbook (`supplier...xlsx`)  
**Dataset file:** `supplier_product_catalog.csv`  
**Record count:** 8,000  
**Grain:** One row represents one supplier × product relationship.

### Purpose

Defines the products that individual suppliers can provide and the associated supplier-product information.

### Important fields

- `supplier_id`
- `product_id`
- Supply cost
- Available quantity/capacity fields where supplied
- Vehicle assignment/availability information where supplied
- Minimum order quantity where supplied
- Maximum shipment quantity where supplied
- Other supplier-product commercial attributes

### Data characteristics

- 200 suppliers
- 200 products
- 8,000 supplier-product records

---

# 4. Raw Dataset Relationships

The raw datasets contain the following main identifiers and relationships:

| Identifier | Dataset(s) containing the identifier |
|---|---|
| `product_id` | Product Master, Sales History, Demand Dataset, Inventory Position, Product-Shelf Assignment, Supplier Product Catalog |
| `location_id` | Location / Region Master, Demand Dataset, Supplier Area Options |
| `warehouse_id` | Warehouse Master, Inventory Position, Shelf Master, Product-Shelf Assignment |
| `supplier_id` | Supplier Master, Supplier Area Options, Supplier Product Catalog |
| `shelf_id` | Shelf Master, Product-Shelf Assignment |
| `week_id` / week date | Weather and time-based source datasets |
| `region_product_week_key` | Sales History |
| `demand_id` | Demand Agent Training Dataset |

These identifiers describe relationships among the raw records without applying any additional transformation logic.

---

# 5. Raw Dataset Classification

## Master datasets

- Product Master
- Location / Region Master
- Warehouse Master
- Shelf Master
- Supplier Master

## Historical / operational datasets

- Sales History
- Demand Agent Training Dataset
- Inventory Position
- Product-Shelf Assignment
- Supplier Product Catalog
- Supplier Area Options

## External calendar / environmental datasets

- Festival Calendar
- Weekly Weather

---

# 6. Raw Data Provenance

The raw datasets originate from the source files maintained for the project. Original source files are preserved separately from their corresponding dataset representations.

### Source workbook groups

- `Final product list.xlsx` — product catalog
- `SELL of past 2 years.xlsx` — historical sales
- `Complete dataset for inventory.xlsx` — inventory, shelf and product-storage information
- `Kolkata_Warehouse_Master_FINAL.xlsx` — warehouse master
- Supplier source workbook(s) — supplier master, supplier-product and supplier-area information
- Demand training workbook — demand observations and contextual variables
- CSV files — raw datasets supplied directly in CSV form

---

# 7. Important Raw Data Notes

1. The raw source files are treated as the original data sources.
2. Record counts are the project-record counts documented for the supplied datasets and may be approximate where the source workbook is large or represented in multiple forms.
3. Grain describes what a single raw row represents; it is not a processing step.
4. Keys shown in this README are the identifiers supplied or defined for the corresponding raw dataset.
5. Dataset-specific fields may contain additional columns beyond the important fields listed here.
6. No derived reference tables or synthetic support datasets are documented in this README.

---

# 8. Excluded from This Raw Dataset README

The following are intentionally **not** documented here:

- Derived reference datasets
- Reconstructed or synthetic datasets
- Calendar lookup tables created from other data
- Product variant reference tables
- Warehouse-location mapping tables created separately
- Warehouse-picker mapping tables
- Vehicle reference tables created separately
- Distance matrices
- Inventory transaction reconstruction datasets
- Delivery-demand proxy datasets
- Preprocessed datasets
- Feature-engineered datasets
- Validation outputs
- Machine-learning outputs
- Agent inputs/outputs
- Workflow and architecture documentation

---

## 9. Summary

This README documents only the **raw source data layer** for the project: products, locations, sales, demand, festivals, weather, warehouses, inventory, shelves, and suppliers. It is intended to serve as the dataset-level reference for understanding the original source files and the meaning of their records.
