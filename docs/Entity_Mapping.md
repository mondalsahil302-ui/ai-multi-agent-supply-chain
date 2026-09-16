# Phase 1.3 — Data Lineage & Entity Mapping (MongoDB)

## Objective

Transform raw datasets into standardized MongoDB collections using unique reference IDs.

## MongoDB Collections

| Collection | Primary ID | Owner Agent |
|------------|------------|-------------|
| products | product_id | Demand Agent |
| locations | location_id | Coordinator |
| warehouses | warehouse_id | Warehouse Agent |
| suppliers | supplier_id | Supplier Agent |
| sales | sale_id | Demand Agent |
| inventory | inventory_id | Inventory Agent |
| weather | weather_id | Risk Agent |
| festivals | festival_id | Demand Agent |

## Reference Relationships

- sales → product_id → products
- sales → location_id → locations
- inventory → warehouse_id → warehouses
- inventory → product_id → products
- suppliers → product_id → products
- warehouses → location_id → locations
- weather → week_date
- festivals → week_date

## Purpose

This entity mapping acts as the reference layer before feature engineering and 30-day demand prediction.

## Architecture Diagram

![Entity Mapping](diagrams/entity_mapping.png)
