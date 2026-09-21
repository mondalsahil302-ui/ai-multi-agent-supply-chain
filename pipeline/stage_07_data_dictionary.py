"""
Stage 07: Generate comprehensive DATA_DICTIONARY.md and DATA_DICTIONARY.csv
covering every canonical entity, fact, bridge, and feature table.
"""

import pandas as pd
from pathlib import Path
from datetime import datetime, timezone

BASE = Path(r"D:\ai-multi-agent-supply-chain")
DOC  = BASE / "data" / "10_documentation"
CUR  = BASE / "data" / "06_curated"
FEAT = BASE / "data" / "07_features"
NOW  = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

# ─── Master field definitions ─────────────────────────────────────────────────
# Format: (table, field, data_type, nullable, pk_fk, description, example, agent_consumer)

DEFINITIONS = [

    # ═══════════════════════════════════════════════════════
    # DIM_PRODUCT
    # ═══════════════════════════════════════════════════════
    ("DIM_PRODUCT","product_id","STRING","NO","PK","Unique product identifier. Format: <CATEGORY_CODE>-<NNN>. e.g. ICE-001, BEV-005.","ICE-001","All agents"),
    ("DIM_PRODUCT","category_code","STRING","NO","FK→category","Short category code. 2–4 uppercase letters. e.g. ICE, BEV, DAI.","ICE","All agents"),
    ("DIM_PRODUCT","category_name","STRING","NO","","Full human-readable category name.","Ice Cream & Frozen Desserts","All agents"),
    ("DIM_PRODUCT","product_name","STRING","NO","","Full commercial product name including brand prefix.","Amul Vanilla Ice Cream","All agents"),
    ("DIM_PRODUCT","brand","STRING","NO","","Brand name of the product. Used for grouping and supplier matching.","Amul","Supply Agent"),
    ("DIM_PRODUCT","quality_level","STRING","NO","","Product tier: Standard or Premium.","Standard","Demand Agent, Supply Agent"),
    ("DIM_PRODUCT","unit_type","STRING","NO","","Physical unit dimension: ml (volume) or g (mass). Never mix across dimensions.","ml","Inventory Agent"),
    ("DIM_PRODUCT","canonical_source","STRING","NO","","Source file chosen as canonical: products.csv (reconciled against Final product list.xlsx).","products.csv","Lineage"),
    ("DIM_PRODUCT","source_file","STRING","NO","","Provenance: source file(s) this record was built from.","products.csv (reconciled against Final product list.xlsx)","Lineage"),
    ("DIM_PRODUCT","pipeline_timestamp","TIMESTAMP","NO","","UTC timestamp when this record was written by the pipeline.","2026-09-21T13:24:00Z","Lineage"),

    # ═══════════════════════════════════════════════════════
    # DIM_PRODUCT_VARIANT
    # ═══════════════════════════════════════════════════════
    ("DIM_PRODUCT_VARIANT","product_variant_id","STRING","NO","PK","Deterministic variant key. Format: <product_id>-<SIZE><UNIT>. e.g. ICE-001-80ML.","ICE-001-80ML","Inventory Agent, Supply Agent"),
    ("DIM_PRODUCT_VARIANT","product_id","STRING","NO","FK→DIM_PRODUCT","Parent product identifier. Joins to DIM_PRODUCT.product_id.","ICE-001","All agents"),
    ("DIM_PRODUCT_VARIANT","variant_index","INTEGER","NO","","Ordinal position of this variant within the product (1–5). 1 = smallest size.","1","Inventory Agent"),
    ("DIM_PRODUCT_VARIANT","unit_size_raw","STRING","NO","","Original size string exactly as supplied in source. e.g. '80 ml', '500 g', '1 L'.","80 ml","Inventory Agent"),
    ("DIM_PRODUCT_VARIANT","unit_size_value","FLOAT","YES","","Numeric part of the unit size. e.g. 80 for '80 ml'.","80","Inventory Agent"),
    ("DIM_PRODUCT_VARIANT","unit_size_unit","STRING","YES","","Unit string extracted from size. ml, l, g, kg, piece, dozen.","ml","Inventory Agent"),
    ("DIM_PRODUCT_VARIANT","normalized_quantity_value","FLOAT","YES","","Canonical quantity in base unit. ml→ml, l→ml×1000, kg→g×1000.","80","Inventory Agent"),
    ("DIM_PRODUCT_VARIANT","normalized_quantity_unit","STRING","YES","","Base unit after normalization: ml or g. Never cross-converts volume↔mass.","ml","Inventory Agent"),
    ("DIM_PRODUCT_VARIANT","cost_price_rs","FLOAT","YES","","Cost price (INR) for this specific variant size.","36","Supply Agent"),
    ("DIM_PRODUCT_VARIANT","selling_price_rs","FLOAT","YES","","Selling price (INR) for this specific variant size.","41","Demand Agent"),
    ("DIM_PRODUCT_VARIANT","source_file","STRING","NO","","Provenance.","products.csv","Lineage"),
    ("DIM_PRODUCT_VARIANT","source_record","STRING","NO","","Row-level provenance including product_id and column name.","product_id=ICE-001, unit_size_1","Lineage"),
    ("DIM_PRODUCT_VARIANT","pipeline_timestamp","TIMESTAMP","NO","","UTC pipeline write timestamp.","2026-09-21T13:24:00Z","Lineage"),

    # ═══════════════════════════════════════════════════════
    # DIM_LOCATION
    # ═══════════════════════════════════════════════════════
    ("DIM_LOCATION","location_id","STRING","NO","PK","Canonical Kolkata region identifier. Format: KOL-LOC-<NNN>.","KOL-LOC-001","All agents"),
    ("DIM_LOCATION","region_of_kolkata","STRING","NO","","Human-readable neighbourhood/area name within Kolkata.","Lake Gardens","All agents"),
    ("DIM_LOCATION","city","STRING","YES","","City name. All records = 'Kolkata'.","Kolkata","Routing Agent"),
    ("DIM_LOCATION","latitude","FLOAT","YES","","WGS-84 latitude of the approximate area centroid. Range: 22.3–22.7.","22.5065","Routing Agent"),
    ("DIM_LOCATION","longitude","FLOAT","YES","","WGS-84 longitude of the approximate area centroid. Range: 88.2–88.5.","88.3554","Routing Agent"),
    ("DIM_LOCATION","location_name","STRING","NO","","Alias for region_of_kolkata. Same value.","Lake Gardens","All agents"),
    ("DIM_LOCATION","source_file","STRING","NO","","Provenance: primary + enrichment source.","locations.csv.csv + supplier_inventory.xlsx/Area_Master","Lineage"),
    ("DIM_LOCATION","pipeline_timestamp","TIMESTAMP","NO","","UTC pipeline write timestamp.","2026-09-21T13:24:00Z","Lineage"),

    # ═══════════════════════════════════════════════════════
    # DIM_WAREHOUSE
    # ═══════════════════════════════════════════════════════
    ("DIM_WAREHOUSE","warehouse_id","STRING","NO","PK","Unique warehouse identifier. Format: WH-KOL-<NNN>.","WH-KOL-001","All agents"),
    ("DIM_WAREHOUSE","warehouse_name","STRING","NO","","Full descriptive warehouse name.","South City Mall Warehouse","All agents"),
    ("DIM_WAREHOUSE","area","STRING","NO","","Kolkata neighbourhood where the warehouse is located.","Jadavpur","Routing Agent"),
    ("DIM_WAREHOUSE","city","STRING","NO","","City. All records = 'Kolkata'.","Kolkata","Routing Agent"),
    ("DIM_WAREHOUSE","latitude","FLOAT","NO","","WGS-84 latitude of warehouse. Range: 22.3–22.7.","22.5014","Routing Agent"),
    ("DIM_WAREHOUSE","longitude","FLOAT","NO","","WGS-84 longitude of warehouse. Range: 88.2–88.5.","88.36175","Routing Agent"),
    ("DIM_WAREHOUSE","capacity_units","INTEGER","NO","","Maximum total stock units the warehouse can hold.","20000","Warehouse Agent"),
    ("DIM_WAREHOUSE","weekday_open_time","STRING","NO","","Opening time on weekdays. Format: HH:MM (24h).","08:00","Warehouse Agent"),
    ("DIM_WAREHOUSE","weekday_close_time","STRING","NO","","Closing time on weekdays. Format: HH:MM (24h).","22:00","Warehouse Agent"),
    ("DIM_WAREHOUSE","weekend_open_time","STRING","NO","","Opening time on weekends. Format: HH:MM (24h).","09:00","Warehouse Agent"),
    ("DIM_WAREHOUSE","weekend_close_time","STRING","NO","","Closing time on weekends. Format: HH:MM (24h).","22:00","Warehouse Agent"),
    ("DIM_WAREHOUSE","daily_dispatch_capacity_units","INTEGER","NO","","Maximum units that can be dispatched from this warehouse per day.","7000","Warehouse Agent, Routing Agent"),
    ("DIM_WAREHOUSE","service_radius_km","FLOAT","NO","","Geographic radius (km) within which this warehouse can serve locations. Used to derive BRIDGE_WAREHOUSE_LOCATION.","18","Routing Agent"),
    ("DIM_WAREHOUSE","cycle_count","INTEGER","YES","","Number of cycle vehicles available for local delivery.","8","Routing Agent"),
    ("DIM_WAREHOUSE","bike_count","INTEGER","YES","","Number of motorbikes available for delivery.","14","Routing Agent"),
    ("DIM_WAREHOUSE","scooter_count","INTEGER","YES","","Number of scooters available for delivery.","10","Routing Agent"),
    ("DIM_WAREHOUSE","electric_scooter_count","INTEGER","YES","","Number of electric scooters available.","6","Routing Agent"),
    ("DIM_WAREHOUSE","auto_count","INTEGER","YES","","Number of auto-rickshaws available for delivery.","4","Routing Agent"),
    ("DIM_WAREHOUSE","total_vehicle_count","INTEGER","NO","","Sum of all vehicle types at this warehouse.","42","Routing Agent"),
    ("DIM_WAREHOUSE","storage_type","STRING","YES","","Storage category: Mixed, Cold, Dry, etc. From final_warehouse_dataset_kolkata.xlsx.","Mixed","Inventory Agent"),
    ("DIM_WAREHOUSE","x_coordinate","FLOAT","YES","","X coordinate (same as longitude in source). Retained for completeness.","88.36175","Routing Agent"),
    ("DIM_WAREHOUSE","y_coordinate","FLOAT","YES","","Y coordinate (same as latitude in source). Retained for completeness.","22.5014","Routing Agent"),
    ("DIM_WAREHOUSE","status","STRING","YES","","Operational status: Active or Inactive. From final_warehouse_dataset_kolkata.xlsx.","Active","Warehouse Agent"),
    ("DIM_WAREHOUSE","source_file","STRING","NO","","Merged from two warehouse sources.","warehouses.xlsx + final_warehouse_dataset_kolkata.xlsx","Lineage"),
    ("DIM_WAREHOUSE","pipeline_timestamp","TIMESTAMP","NO","","UTC pipeline write timestamp.","2026-09-21T13:24:00Z","Lineage"),

    # ═══════════════════════════════════════════════════════
    # DIM_SUPPLIER
    # ═══════════════════════════════════════════════════════
    ("DIM_SUPPLIER","supplier_id","STRING","NO","PK","Unique supplier identifier. Format: SUP-KOL-<LOC_NUM>-<SUPPLIER_NUM>.","SUP-KOL-001-01","Supply Agent"),
    ("DIM_SUPPLIER","supplier_name","STRING","NO","","Full legal/trade name of the supplier.","Lake Gardens Fresh Produce & Chilled Market","Supply Agent"),
    ("DIM_SUPPLIER","supplier_type_id","STRING","NO","","Supplier type code. e.g. SUP-T01.","SUP-T01","Supply Agent"),
    ("DIM_SUPPLIER","supplier_type_name","STRING","NO","","Human-readable supplier type. e.g. 'Fresh Produce & Chilled'.","Fresh Produce & Chilled","Supply Agent"),
    ("DIM_SUPPLIER","location_id","STRING","NO","FK→DIM_LOCATION","Location (area) where this supplier is based.","KOL-LOC-001","Supply Agent, Routing Agent"),
    ("DIM_SUPPLIER","location_name","STRING","NO","","Area name corresponding to location_id.","Lake Gardens","Supply Agent"),
    ("DIM_SUPPLIER","city","STRING","NO","","City. All records = 'Kolkata'.","Kolkata","Supply Agent"),
    ("DIM_SUPPLIER","supplier_latitude","FLOAT","NO","","WGS-84 latitude of the supplier's approximate location.","22.5051","Routing Agent"),
    ("DIM_SUPPLIER","supplier_longitude","FLOAT","NO","","WGS-84 longitude of the supplier's approximate location.","88.3542","Routing Agent"),
    ("DIM_SUPPLIER","product_category_scope","STRING","NO","","Semicolon-separated list of product categories this supplier stocks.","Fresh Fruits; Dairy & Milk Products; Ice Cream","Supply Agent"),
    ("DIM_SUPPLIER","minimum_order_qty_units","INTEGER","NO","","Minimum Order Quantity (MOQ) in units. Must be <= max_order_qty_units.","90","Supply Agent"),
    ("DIM_SUPPLIER","max_order_qty_units","INTEGER","NO","","Maximum single order quantity in units.","1900","Supply Agent"),
    ("DIM_SUPPLIER","max_ship_qty_at_once_units","INTEGER","NO","","Maximum units that can be shipped in a single shipment.","750","Supply Agent, Routing Agent"),
    ("DIM_SUPPLIER","supplier_storage_capacity_units","INTEGER","NO","","Total storage capacity of the supplier's facility in units.","2300","Supply Agent, Risk Agent"),
    ("DIM_SUPPLIER","vehicle_type","STRING","NO","","Primary vehicle type used for delivery. e.g. 'Refrigerated Mini Truck'.","Refrigerated Mini Truck","Routing Agent"),
    ("DIM_SUPPLIER","vehicle_count","INTEGER","NO","","Number of vehicles of the primary type available.","4","Routing Agent"),
    ("DIM_SUPPLIER","vehicle_load_capacity_units","INTEGER","NO","","Load capacity per vehicle in units.","34","Routing Agent"),
    ("DIM_SUPPLIER","lead_time_days","INTEGER","NO","","Standard lead time from order to delivery in days. Must be >= 0.","1","Supply Agent, Risk Agent"),
    ("DIM_SUPPLIER","location_note","STRING","YES","","Free-text provenance note about the coordinate data quality.","Approximate planning coordinate near area center","Lineage"),
    ("DIM_SUPPLIER","source_file","STRING","NO","","Provenance.","supplier_inventory.xlsx/Supplier_Master","Lineage"),
    ("DIM_SUPPLIER","pipeline_timestamp","TIMESTAMP","NO","","UTC pipeline write timestamp.","2026-09-21T13:24:00Z","Lineage"),

    # ═══════════════════════════════════════════════════════
    # DIM_CALENDAR_WEEK
    # ═══════════════════════════════════════════════════════
    ("DIM_CALENDAR_WEEK","week_key","STRING","NO","PK","Deterministic week identifier. Format: YYYYMMDD of week_start_date. e.g. 20240101.","20240101","All agents"),
    ("DIM_CALENDAR_WEEK","week_start_date","DATE","NO","","Monday (or first day) of the week. ISO 8601 date.","2024-01-01","All agents"),
    ("DIM_CALENDAR_WEEK","week_end_date","DATE","NO","","Last day of the week (7 days after week_start_date minus 1). Should be week_start + 6 days.","2024-01-07","All agents"),
    ("DIM_CALENDAR_WEEK","year","INTEGER","NO","","Calendar year of week_start_date.","2024","Demand Agent"),
    ("DIM_CALENDAR_WEEK","week_number","INTEGER","NO","","ISO week number within the year (1–53).","1","Demand Agent"),
    ("DIM_CALENDAR_WEEK","season","STRING","NO","","Season label: Winter, Summer, Monsoon, Post-Monsoon, Spring. Derived from Kolkata climate.","Winter","Demand Agent, Risk Agent"),
    ("DIM_CALENDAR_WEEK","source_file","STRING","NO","","Derived from weather_weekly.csv date coverage.","weather_weekly.csv","Lineage"),
    ("DIM_CALENDAR_WEEK","pipeline_timestamp","TIMESTAMP","NO","","UTC pipeline write timestamp.","2026-09-21T13:24:00Z","Lineage"),

    # ═══════════════════════════════════════════════════════
    # DIM_FESTIVAL
    # ═══════════════════════════════════════════════════════
    ("DIM_FESTIVAL","festival_id","STRING","NO","PK","Synthetic festival record identifier. Format: FEST-<NNN>.","FEST-001","Demand Agent, Risk Agent"),
    ("DIM_FESTIVAL","festival_event","STRING","NO","","Name of the festival or public holiday event.","Saraswati Puja","Demand Agent"),
    ("DIM_FESTIVAL","event_date","DATE","NO","","Actual date of the festival event. Sourced directly from festival_calendar.csv; not inferred.","2024-02-14","Demand Agent"),
    ("DIM_FESTIVAL","year","INTEGER","NO","","Calendar year of the event.","2024","Demand Agent"),
    ("DIM_FESTIVAL","week_start_date","DATE","NO","","Monday of the ISO week containing event_date. Derived via period(W-MON).","2024-02-12","Demand Agent"),
    ("DIM_FESTIVAL","festival_category","STRING","NO","","Inferred religious/cultural category: Hindu, Islamic, Christian, National, Cultural/New Year.","Hindu","Demand Agent"),
    ("DIM_FESTIVAL","source_type","STRING","NO","","Data provenance type. SUPPLIED_REFERENCE = provided reference data; not inferred or synthetic.","SUPPLIED_REFERENCE","Lineage"),
    ("DIM_FESTIVAL","source_file","STRING","NO","","Provenance.","festival_calendar.csv","Lineage"),
    ("DIM_FESTIVAL","pipeline_timestamp","TIMESTAMP","NO","","UTC pipeline write timestamp.","2026-09-21T13:24:00Z","Lineage"),

    # ═══════════════════════════════════════════════════════
    # DIM_WEATHER
    # ═══════════════════════════════════════════════════════
    ("DIM_WEATHER","week_start_date","DATE","NO","PK","First day of the weather observation week.","2024-01-01","Demand Agent, Risk Agent"),
    ("DIM_WEATHER","week_end_date","DATE","NO","","Last day of the weather observation week. Should be week_start + 6 days.","2024-01-07","Demand Agent"),
    ("DIM_WEATHER","year","INTEGER","NO","","Calendar year.","2024","Demand Agent"),
    ("DIM_WEATHER","season","STRING","NO","","Season label for Kolkata. Values: Winter, Summer, Monsoon, Post-Monsoon.","Winter","Demand Agent"),
    ("DIM_WEATHER","temperature_mean_c","FLOAT","NO","","Mean weekly temperature in degrees Celsius.","18.6","Demand Agent, Risk Agent"),
    ("DIM_WEATHER","temperature_max_c","FLOAT","NO","","Maximum temperature recorded during the week (°C).","22.3","Demand Agent"),
    ("DIM_WEATHER","temperature_min_c","FLOAT","NO","","Minimum temperature recorded during the week (°C).","16.1","Demand Agent"),
    ("DIM_WEATHER","rainfall_mm","FLOAT","NO","","Total rainfall for the week in millimetres. Domain: >= 0.","12.9","Demand Agent, Risk Agent"),
    ("DIM_WEATHER","humidity_pct","FLOAT","NO","","Average relative humidity for the week as a percentage. Domain: 0–100.","56.8","Demand Agent, Risk Agent"),
    ("DIM_WEATHER","weather_condition","STRING","NO","","Categorical weather label. Values: Clear/Partly Cloudy, Rain, Heavy Rain, Fog, Humid.","Clear/Partly Cloudy","Demand Agent, Risk Agent"),
    ("DIM_WEATHER","weather_data_type","STRING","NO","","Data provenance marker. SUPPLIED_SYNTHETIC = generated for simulation; not real Kolkata observations.","SUPPLIED_SYNTHETIC","Lineage"),
    ("DIM_WEATHER","interval_days","INTEGER","YES","","Computed interval: week_end_date - week_start_date in days. Should = 6. WARNING: 1 record has non-6 interval.","6","Validation"),
    ("DIM_WEATHER","source_file","STRING","NO","","Provenance.","weather_weekly.csv","Lineage"),
    ("DIM_WEATHER","pipeline_timestamp","TIMESTAMP","NO","","UTC pipeline write timestamp.","2026-09-21T13:24:00Z","Lineage"),

    # ═══════════════════════════════════════════════════════
    # FACT_DEMAND
    # ═══════════════════════════════════════════════════════
    ("FACT_DEMAND","demand_id","STRING","NO","PK","Unique demand record identifier. Format: DEM-<7-digit sequence>.","DEM-0000001","Demand Agent"),
    ("FACT_DEMAND","week_start_date","DATE","NO","FK→DIM_CALENDAR_WEEK","First day of the demand observation week.","2024-01-01","Demand Agent"),
    ("FACT_DEMAND","week_end_date","DATE","NO","","Last day of the demand observation week.","2024-01-07","Demand Agent"),
    ("FACT_DEMAND","year","INTEGER","NO","","Calendar year of this demand record.","2024","Demand Agent"),
    ("FACT_DEMAND","week_number","INTEGER","NO","","ISO week number within the year.","1","Demand Agent"),
    ("FACT_DEMAND","location_id","STRING","NO","FK→DIM_LOCATION","Kolkata region identifier. Joins to DIM_LOCATION.location_id.","KOL-LOC-001","Demand Agent"),
    ("FACT_DEMAND","region_of_kolkata","STRING","NO","","Region name (denormalized from DIM_LOCATION for convenience).","Lake Gardens","Demand Agent"),
    ("FACT_DEMAND","demand_rank","INTEGER","NO","","Rank of this product by units_sold within the region-week (1 = top-selling).","1","Demand Agent"),
    ("FACT_DEMAND","product_id","STRING","NO","FK→DIM_PRODUCT","Product identifier. Joins to DIM_PRODUCT.product_id.","DAI-005","Demand Agent"),
    ("FACT_DEMAND","product_name","STRING","NO","","Product name (denormalized).","Mother Dairy Curd","Demand Agent"),
    ("FACT_DEMAND","category_name","STRING","NO","","Product category name (denormalized).","Dairy & Milk Products","Demand Agent"),
    ("FACT_DEMAND","brand","STRING","NO","","Brand name (denormalized).","Mother Dairy","Demand Agent"),
    ("FACT_DEMAND","unit_size","STRING","NO","","Unit size string as used in demand context. Joins to DIM_PRODUCT_VARIANT.unit_size_raw via product_id.","500 g","Demand Agent"),
    ("FACT_DEMAND","weekday_weekend","STRING","NO","","Observation split. Values: Weekday or Weekend. Current source only contains Weekday rows.","Weekday","Demand Agent"),
    ("FACT_DEMAND","weekday_units_sold","INTEGER","NO","","Units sold on weekdays during this week.","111","Demand Agent"),
    ("FACT_DEMAND","weekend_units_sold","INTEGER","NO","","Units sold on weekends during this week.","35","Demand Agent"),
    ("FACT_DEMAND","units_sold","INTEGER","NO","","Total units sold = weekday_units_sold + weekend_units_sold. Validated for consistency.","146","Demand Agent"),
    ("FACT_DEMAND","avg_selling_price_rs","FLOAT","NO","","Average actual selling price per unit in INR during this week.","52.79","Demand Agent"),
    ("FACT_DEMAND","promotion_flag","INTEGER","NO","","1 if a promotion was active this week for this product-location, else 0.","0","Demand Agent"),
    ("FACT_DEMAND","discount_pct","FLOAT","NO","","Discount percentage applied (0–100). 0 if no discount.","0","Demand Agent"),
    ("FACT_DEMAND","holiday_flag","INTEGER","NO","","1 if a public holiday falls within this week, else 0.","0","Demand Agent, Risk Agent"),
    ("FACT_DEMAND","festival_event","STRING","YES","FK→DIM_FESTIVAL","Name of the festival if one falls within this week. NULL if no festival.","None","Demand Agent"),
    ("FACT_DEMAND","season","STRING","NO","","Season label for this week. Matches DIM_WEATHER.season.","Winter","Demand Agent"),
    ("FACT_DEMAND","temperature_c","FLOAT","NO","","Weekly mean temperature in °C. Sourced from weather context.","18.6","Demand Agent"),
    ("FACT_DEMAND","rainfall_mm","FLOAT","NO","","Weekly total rainfall in mm.","12.9","Demand Agent, Risk Agent"),
    ("FACT_DEMAND","humidity_pct","FLOAT","NO","","Weekly average humidity %.","56.8","Demand Agent, Risk Agent"),
    ("FACT_DEMAND","weather_condition","STRING","NO","","Categorical weather label for this week.","Clear/Partly Cloudy","Demand Agent"),
    ("FACT_DEMAND","stockout_flag","INTEGER","NO","","1 if a stockout occurred for this product-location-week, else 0.","0","Demand Agent, Risk Agent"),
    ("FACT_DEMAND","forecast_target_start","DATE","NO","","Start of the forecast target window (= next week_start_date).","2024-01-08","Demand Agent"),
    ("FACT_DEMAND","forecast_target_end","DATE","NO","","End of the forecast target window (= next week_end_date).","2024-01-14","Demand Agent"),
    ("FACT_DEMAND","next_week_demand_target_units","FLOAT","NO","TARGET","Prediction target: units expected to be sold in the NEXT week. MUST NOT be used as a feature. Isolated to DEMAND_TARGETS.csv.","152","Demand Agent (training only)"),
    ("FACT_DEMAND","data_source","STRING","NO","","Pipe-separated provenance flags. e.g. SYNTHETIC_TRAINING | SUPPLIED_WEATHER | SUPPLIED_FESTIVAL.","SYNTHETIC_TRAINING | SUPPLIED_WEATHER","Lineage"),
    ("FACT_DEMAND","region_week_key","STRING","NO","","Composite key: <location_id>_<YYYYMMDD>. Primary join key for region-week aggregation.","KOL-LOC-001_20240101","Demand Agent"),
    ("FACT_DEMAND","region_product_week_key","STRING","NO","","Composite key: <location_id>_<YYYYMMDD>_<product_id>. Natural key for this fact table.","KOL-LOC-001_20240101_DAI-005","Demand Agent"),
    ("FACT_DEMAND","anchor_status","STRING","NO","","Data quality marker from source. e.g. observed_top5_anchor.","observed_top5_anchor","Lineage"),
    ("FACT_DEMAND","fact_source","STRING","NO","","Pipeline tag identifying source dataset.","DEMAND_OF_LAST_2_YEARS","Lineage"),
    ("FACT_DEMAND","pipeline_timestamp","TIMESTAMP","NO","","UTC pipeline write timestamp.","2026-09-21T13:24:00Z","Lineage"),

    # ═══════════════════════════════════════════════════════
    # FACT_INVENTORY_POSITION
    # ═══════════════════════════════════════════════════════
    ("FACT_INVENTORY_POSITION","warehouse_id","STRING","NO","FK→DIM_WAREHOUSE","Warehouse containing this inventory.","WH-KOL-001","Inventory Agent"),
    ("FACT_INVENTORY_POSITION","product_id","STRING","NO","FK→DIM_PRODUCT","Product stocked at this location.","ICE-001","Inventory Agent"),
    ("FACT_INVENTORY_POSITION","shelf_id","STRING","NO","FK→Shelf_Master","Physical shelf identifier within the warehouse zone.","WH-KOL-001-Z01-R01-S01","Inventory Agent"),
    ("FACT_INVENTORY_POSITION","bin_id","STRING","NO","","Bin/slot identifier within the shelf. Most granular physical location.","WH-KOL-001-Z01-R01-S01-B01","Inventory Agent"),
    ("FACT_INVENTORY_POSITION","opening_stock_units","INTEGER","YES","","Stock units at the start of the snapshot period.","94","Inventory Agent"),
    ("FACT_INVENTORY_POSITION","received_units","INTEGER","YES","","Units received (inbound) during the snapshot period.","46","Inventory Agent"),
    ("FACT_INVENTORY_POSITION","current_stock_units","INTEGER","YES","","Total physical units currently on hand. = opening + received - outbound.","84","Inventory Agent"),
    ("FACT_INVENTORY_POSITION","reserved_stock_units","INTEGER","YES","","Units reserved for pending orders. Must be <= current_stock_units.","7","Inventory Agent"),
    ("FACT_INVENTORY_POSITION","available_stock_units","INTEGER","YES","","Units available for new orders. Domain: >= 0. Formula: current - reserved - damaged.","77","Inventory Agent"),
    ("FACT_INVENTORY_POSITION","damaged_units","INTEGER","YES","","Units classified as damaged/unsellable. Domain: >= 0.","0","Inventory Agent, Risk Agent"),
    ("FACT_INVENTORY_POSITION","cost_price_rs","FLOAT","YES","","Average cost price per unit in INR for this product-warehouse combination.","101.6","Inventory Agent"),
    ("FACT_INVENTORY_POSITION","selling_price_rs","FLOAT","YES","","Selling price per unit in INR.","116.8","Inventory Agent"),
    ("FACT_INVENTORY_POSITION","avg_weekly_demand_units","FLOAT","YES","","Historical average weekly demand for this product at this warehouse.","67.3","Inventory Agent"),
    ("FACT_INVENTORY_POSITION","stock_status","STRING","YES","","Qualitative status from source: Healthy, Low, Critical, Overstocked.","Healthy","Inventory Agent"),
    ("FACT_INVENTORY_POSITION","snapshot_date","DATE","NO","","Date when this inventory position was recorded. All records: 2026-08-31.","2026-08-31","Inventory Agent"),
    ("FACT_INVENTORY_POSITION","weeks_of_cover_calc","FLOAT","YES","","PIPELINE-CALCULATED: available_stock / avg_weekly_demand. Formula cache in source was empty (None). Replaces source weeks_of_cover.","1.14","Inventory Agent, Risk Agent"),
    ("FACT_INVENTORY_POSITION","reorder_flag_calc","INTEGER","YES","","PIPELINE-CALCULATED: 1 if weeks_of_cover_calc < 2.0, else 0.","1","Inventory Agent, Risk Agent"),
    ("FACT_INVENTORY_POSITION","stock_cost_value_rs","FLOAT","YES","","PIPELINE-CALCULATED: current_stock_units × cost_price_rs.","8534.4","Inventory Agent"),
    ("FACT_INVENTORY_POSITION","available_sales_value_rs","FLOAT","YES","","PIPELINE-CALCULATED: available_stock_units × selling_price_rs.","8993.6","Inventory Agent"),
    ("FACT_INVENTORY_POSITION","inventory_risk","STRING","YES","","Risk classification from source Inventory_Control sheet. Values: NORMAL, LOW_STOCK, CRITICAL.","NORMAL","Risk Agent"),
    ("FACT_INVENTORY_POSITION","source_file","STRING","NO","","Merged from Inventory_Position + Inventory_Control sheets.","inventory_stock.xlsx/Inventory_Position+Inventory_Control","Lineage"),
    ("FACT_INVENTORY_POSITION","pipeline_timestamp","TIMESTAMP","NO","","UTC pipeline write timestamp.","2026-09-21T13:24:00Z","Lineage"),

    # ═══════════════════════════════════════════════════════
    # FACT_SUPPLIER_AVAILABILITY
    # ═══════════════════════════════════════════════════════
    ("FACT_SUPPLIER_AVAILABILITY","supplier_product_key","STRING","NO","PK","Composite key: <supplier_id>_<product_id>.","SUP-KOL-001-01_ICE-001","Supply Agent"),
    ("FACT_SUPPLIER_AVAILABILITY","supplier_id","STRING","NO","FK→DIM_SUPPLIER","Supplier identifier.","SUP-KOL-001-01","Supply Agent"),
    ("FACT_SUPPLIER_AVAILABILITY","product_id","STRING","NO","FK→DIM_PRODUCT","Product identifier.","ICE-001","Supply Agent"),
    ("FACT_SUPPLIER_AVAILABILITY","supplier_type_id","STRING","NO","","Supplier type code.","SUP-T01","Supply Agent"),
    ("FACT_SUPPLIER_AVAILABILITY","supplier_type_name","STRING","NO","","Supplier type description.","Fresh Produce & Chilled","Supply Agent"),
    ("FACT_SUPPLIER_AVAILABILITY","supplier_cost_price_rs","FLOAT","NO","","Supplier's cost price for this product in INR.","36","Supply Agent"),
    ("FACT_SUPPLIER_AVAILABILITY","supplied_unit_size","STRING","NO","","Unit size in which the supplier provides this product. Joins to DIM_PRODUCT_VARIANT.unit_size_raw.","80 ml","Supply Agent"),
    ("FACT_SUPPLIER_AVAILABILITY","supply_status","STRING","NO","","Availability status. Values: Available, Unavailable, Limited.","Available","Supply Agent"),
    ("FACT_SUPPLIER_AVAILABILITY","unmapped_col_10_quarantine","FLOAT","YES","QUARANTINE","QUARANTINED FIELD: Column at index 10 in Supplier_Product_Catalog had no header. Values are numeric (~9–200). Semantic meaning unresolved. Do NOT use in models without domain review.","35.71","QUARANTINE"),
    ("FACT_SUPPLIER_AVAILABILITY","minimum_order_qty_units","INTEGER","YES","","Minimum Order Quantity from DIM_SUPPLIER. Inherited via supplier_id join.","90","Supply Agent"),
    ("FACT_SUPPLIER_AVAILABILITY","max_order_qty_units","INTEGER","YES","","Maximum order quantity from DIM_SUPPLIER.","1900","Supply Agent"),
    ("FACT_SUPPLIER_AVAILABILITY","max_ship_qty_at_once_units","INTEGER","YES","","Maximum shipment quantity per trip.","750","Supply Agent"),
    ("FACT_SUPPLIER_AVAILABILITY","supplier_storage_capacity_units","INTEGER","YES","","Supplier's total storage capacity.","2300","Supply Agent"),
    ("FACT_SUPPLIER_AVAILABILITY","vehicle_type","STRING","YES","","Primary delivery vehicle type.","Refrigerated Mini Truck","Routing Agent"),
    ("FACT_SUPPLIER_AVAILABILITY","vehicle_count","INTEGER","YES","","Number of vehicles available.","4","Routing Agent"),
    ("FACT_SUPPLIER_AVAILABILITY","vehicle_load_capacity_units","INTEGER","YES","","Capacity per vehicle in units.","34","Routing Agent"),
    ("FACT_SUPPLIER_AVAILABILITY","lead_time_days","INTEGER","YES","","Lead time from supplier in days.","1","Supply Agent, Risk Agent"),
    ("FACT_SUPPLIER_AVAILABILITY","location_id","STRING","YES","FK→DIM_LOCATION","Supplier's operating area.","KOL-LOC-001","Supply Agent"),
    ("FACT_SUPPLIER_AVAILABILITY","snapshot_date","TIMESTAMP","NO","","UTC timestamp of snapshot creation.","2026-09-21T13:24:00Z","Lineage"),
    ("FACT_SUPPLIER_AVAILABILITY","pipeline_timestamp","TIMESTAMP","NO","","UTC pipeline write timestamp.","2026-09-21T13:24:00Z","Lineage"),

    # ═══════════════════════════════════════════════════════
    # BRIDGE_SUPPLIER_PRODUCT
    # ═══════════════════════════════════════════════════════
    ("BRIDGE_SUPPLIER_PRODUCT","supplier_product_key","STRING","NO","PK","Deterministic key: <supplier_id>_<product_id>.","SUP-KOL-001-01_ICE-001","Supply Agent"),
    ("BRIDGE_SUPPLIER_PRODUCT","supplier_id","STRING","NO","FK→DIM_SUPPLIER","Supplier.","SUP-KOL-001-01","Supply Agent"),
    ("BRIDGE_SUPPLIER_PRODUCT","product_id","STRING","NO","FK→DIM_PRODUCT","Product supplied by this supplier.","ICE-001","Supply Agent"),
    ("BRIDGE_SUPPLIER_PRODUCT","supplier_type_id","STRING","NO","","Supplier type code.","SUP-T01","Supply Agent"),
    ("BRIDGE_SUPPLIER_PRODUCT","supplier_type_name","STRING","NO","","Supplier type description.","Fresh Produce & Chilled","Supply Agent"),
    ("BRIDGE_SUPPLIER_PRODUCT","supplier_cost_price_rs","FLOAT","NO","","Cost price for this product from this supplier in INR.","36","Supply Agent"),
    ("BRIDGE_SUPPLIER_PRODUCT","supplied_unit_size","STRING","NO","","Unit size supplied. Matches DIM_PRODUCT_VARIANT.unit_size_raw.","80 ml","Supply Agent"),
    ("BRIDGE_SUPPLIER_PRODUCT","supply_status","STRING","NO","","Availability: Available, Unavailable, Limited.","Available","Supply Agent"),
    ("BRIDGE_SUPPLIER_PRODUCT","unmapped_col_10_quarantine","FLOAT","YES","QUARANTINE","Unresolved numeric column from Supplier_Product_Catalog index 10. Preserved for domain review. Do not use in production until resolved.","35.71","QUARANTINE"),
    ("BRIDGE_SUPPLIER_PRODUCT","source_file","STRING","NO","","Provenance.","supplier_inventory.xlsx/Supplier_Product_Catalog","Lineage"),
    ("BRIDGE_SUPPLIER_PRODUCT","pipeline_timestamp","TIMESTAMP","NO","","UTC pipeline write timestamp.","2026-09-21T13:24:00Z","Lineage"),

    # ═══════════════════════════════════════════════════════
    # BRIDGE_LOCATION_SUPPLIER
    # ═══════════════════════════════════════════════════════
    ("BRIDGE_LOCATION_SUPPLIER","location_id","STRING","NO","FK→DIM_LOCATION","Service area (location) identifier.","KOL-LOC-001","Supply Agent, Routing Agent"),
    ("BRIDGE_LOCATION_SUPPLIER","location_name","STRING","NO","","Area name.","Lake Gardens","Supply Agent"),
    ("BRIDGE_LOCATION_SUPPLIER","supplier_id","STRING","NO","FK→DIM_SUPPLIER","Supplier serving this location.","SUP-KOL-001-01","Supply Agent"),
    ("BRIDGE_LOCATION_SUPPLIER","supplier_type_id","STRING","NO","","Supplier type code.","SUP-T01","Supply Agent"),
    ("BRIDGE_LOCATION_SUPPLIER","supplier_type_name","STRING","NO","","Supplier type name.","Fresh Produce & Chilled","Supply Agent"),
    ("BRIDGE_LOCATION_SUPPLIER","supplier_latitude","FLOAT","NO","","Supplier's latitude.","22.5051","Routing Agent"),
    ("BRIDGE_LOCATION_SUPPLIER","supplier_longitude","FLOAT","NO","","Supplier's longitude.","88.3542","Routing Agent"),
    ("BRIDGE_LOCATION_SUPPLIER","distance_from_location_center_km","FLOAT","NO","","Straight-line distance from supplier to location centre in km. From source data; method not explicitly stated.","0.198","Routing Agent"),
    ("BRIDGE_LOCATION_SUPPLIER","supplier_option_rank","INTEGER","NO","","Rank of this supplier for this location (1 = closest/preferred).","1","Supply Agent"),
    ("BRIDGE_LOCATION_SUPPLIER","service_available_flag","STRING","NO","","Whether the supplier services this location: Yes / No.","Yes","Supply Agent"),
    ("BRIDGE_LOCATION_SUPPLIER","source_file","STRING","NO","","Provenance.","supplier_inventory.xlsx/Area_Supplier_Options","Lineage"),
    ("BRIDGE_LOCATION_SUPPLIER","pipeline_timestamp","TIMESTAMP","NO","","UTC pipeline write timestamp.","2026-09-21T13:24:00Z","Lineage"),

    # ═══════════════════════════════════════════════════════
    # BRIDGE_WAREHOUSE_LOCATION
    # ═══════════════════════════════════════════════════════
    ("BRIDGE_WAREHOUSE_LOCATION","warehouse_id","STRING","NO","FK→DIM_WAREHOUSE","Warehouse identifier.","WH-KOL-001","Warehouse Agent, Routing Agent"),
    ("BRIDGE_WAREHOUSE_LOCATION","location_id","STRING","NO","FK→DIM_LOCATION","Location (delivery area) identifier.","KOL-LOC-001","Warehouse Agent, Routing Agent"),
    ("BRIDGE_WAREHOUSE_LOCATION","euclidean_distance_km","FLOAT","NO","","Haversine great-circle distance between warehouse centroid and location centroid in km. NOT road distance.","0.8644","Routing Agent"),
    ("BRIDGE_WAREHOUSE_LOCATION","service_radius_km","FLOAT","NO","","Service radius of the warehouse (from DIM_WAREHOUSE). Used to compute service_available_flag.","18","Warehouse Agent"),
    ("BRIDGE_WAREHOUSE_LOCATION","service_available_flag","STRING","NO","","'Yes' if euclidean_distance_km <= service_radius_km; else 'No'.","Yes","Warehouse Agent"),
    ("BRIDGE_WAREHOUSE_LOCATION","assignment_method","STRING","NO","","How the mapping was derived. Value: haversine_vs_service_radius.","haversine_vs_service_radius","Lineage"),
    ("BRIDGE_WAREHOUSE_LOCATION","mapping_source","STRING","NO","","Origin of the mapping. DERIVED_FROM_COORDINATES = computed, not sourced.","DERIVED_FROM_COORDINATES","Lineage"),
    ("BRIDGE_WAREHOUSE_LOCATION","pipeline_timestamp","TIMESTAMP","NO","","UTC pipeline write timestamp.","2026-09-21T13:24:00Z","Lineage"),

    # ═══════════════════════════════════════════════════════
    # BRIDGE_PRODUCT_WAREHOUSE
    # ═══════════════════════════════════════════════════════
    ("BRIDGE_PRODUCT_WAREHOUSE","warehouse_id","STRING","NO","FK→DIM_WAREHOUSE","Warehouse holding this product.","WH-KOL-001","Inventory Agent"),
    ("BRIDGE_PRODUCT_WAREHOUSE","product_id","STRING","NO","FK→DIM_PRODUCT","Product stocked in this warehouse.","ICE-001","Inventory Agent"),
    ("BRIDGE_PRODUCT_WAREHOUSE","shelf_id","STRING","NO","FK→Shelf_Master","Physical shelf where product is stored.","WH-KOL-001-Z01-R01-S01","Inventory Agent"),
    ("BRIDGE_PRODUCT_WAREHOUSE","bin_id","STRING","NO","","Bin within the shelf.","WH-KOL-001-Z01-R01-S01-B01","Inventory Agent"),
    ("BRIDGE_PRODUCT_WAREHOUSE","source_file","STRING","NO","","Provenance.","inventory_stock.xlsx/Inventory_Position","Lineage"),
    ("BRIDGE_PRODUCT_WAREHOUSE","pipeline_timestamp","TIMESTAMP","NO","","UTC pipeline write timestamp.","2026-09-21T13:24:00Z","Lineage"),

    # ═══════════════════════════════════════════════════════
    # DEMAND_FEATURES (feature set — not full schema, key fields only)
    # ═══════════════════════════════════════════════════════
    ("DEMAND_FEATURES","lag_1w_units_sold","FLOAT","YES","FEATURE","Units sold 1 week prior (lag-1). Computed per location+product. NULL for first week.","143","Demand Agent"),
    ("DEMAND_FEATURES","lag_2w_units_sold","FLOAT","YES","FEATURE","Units sold 2 weeks prior (lag-2).","138","Demand Agent"),
    ("DEMAND_FEATURES","lag_4w_units_sold","FLOAT","YES","FEATURE","Units sold 4 weeks prior (lag-4).","130","Demand Agent"),
    ("DEMAND_FEATURES","lag_8w_units_sold","FLOAT","YES","FEATURE","Units sold 8 weeks prior (lag-8).","125","Demand Agent"),
    ("DEMAND_FEATURES","lag_12w_units_sold","FLOAT","YES","FEATURE","Units sold 12 weeks prior (lag-12).","120","Demand Agent"),
    ("DEMAND_FEATURES","rolling_mean_4w","FLOAT","YES","FEATURE","4-week rolling mean of lag_1w_units_sold. Leakage-safe (uses lagged values only).","135.0","Demand Agent"),
    ("DEMAND_FEATURES","rolling_mean_8w","FLOAT","YES","FEATURE","8-week rolling mean of lag_1w_units_sold.","130.0","Demand Agent"),
    ("DEMAND_FEATURES","rolling_mean_12w","FLOAT","YES","FEATURE","12-week rolling mean of lag_1w_units_sold.","128.0","Demand Agent"),
    ("DEMAND_FEATURES","demand_trend_4w","FLOAT","YES","FEATURE","OLS slope of lag_1w over the last 4 weeks. Positive = growing demand.","1.5","Demand Agent"),
    ("DEMAND_FEATURES","weekday_ratio","FLOAT","YES","FEATURE","weekday_units_sold / units_sold. Proportion of sales on weekdays.","0.76","Demand Agent"),
    ("DEMAND_FEATURES","weekend_ratio","FLOAT","YES","FEATURE","weekend_units_sold / units_sold. Proportion of sales on weekends.","0.24","Demand Agent"),
    ("DEMAND_FEATURES","days_to_next_festival","FLOAT","YES","FEATURE","Days from week_start_date to the next festival event. NULL if no future festival in data.","14","Demand Agent"),
    ("DEMAND_FEATURES","days_since_last_festival","FLOAT","YES","FEATURE","Days since the most recent past festival event.","7","Demand Agent"),
    ("DEMAND_FEATURES","festival_flag","INTEGER","NO","FEATURE","1 if a festival event falls within this demand week, else 0. Derived from festival_event column.","0","Demand Agent"),
    ("DEMAND_FEATURES","leakage_safe","BOOLEAN","NO","","Pipeline metadata: True confirms next_week_demand_target_units has been removed from this table.","True","Lineage"),
    ("DEMAND_FEATURES","target_column","STRING","NO","","Documents which column was removed as the prediction target.","next_week_demand_target_units (excluded from features)","Lineage"),

    # ═══════════════════════════════════════════════════════
    # DEMAND_TARGETS
    # ═══════════════════════════════════════════════════════
    ("DEMAND_TARGETS","demand_id","STRING","NO","PK","Links to FACT_DEMAND and DEMAND_FEATURES.","DEM-0000001","Demand Agent"),
    ("DEMAND_TARGETS","location_id","STRING","NO","FK→DIM_LOCATION","Location of the demand record.","KOL-LOC-001","Demand Agent"),
    ("DEMAND_TARGETS","product_id","STRING","NO","FK→DIM_PRODUCT","Product of the demand record.","DAI-005","Demand Agent"),
    ("DEMAND_TARGETS","week_start_date","DATE","NO","","Week the observation relates to (not the target week).","2024-01-01","Demand Agent"),
    ("DEMAND_TARGETS","next_week_demand_target_units","FLOAT","NO","TARGET","PREDICTION TARGET: Expected demand for the FOLLOWING week. Must NEVER be used as a feature.","152","Demand Agent (training target)"),
    ("DEMAND_TARGETS","forecast_target_start","DATE","NO","","Start of the target forecast window (next week_start_date).","2024-01-08","Demand Agent"),

    # ═══════════════════════════════════════════════════════
    # ROUTING_FEATURES
    # ═══════════════════════════════════════════════════════
    ("ROUTING_FEATURES","origin_id","STRING","NO","","ID of the origin entity (warehouse_id or supplier_id).","WH-KOL-001","Routing Agent"),
    ("ROUTING_FEATURES","destination_id","STRING","NO","","ID of the destination entity (location_id).","KOL-LOC-001","Routing Agent"),
    ("ROUTING_FEATURES","euclidean_distance_km","FLOAT","NO","","Haversine great-circle distance in km. IMPORTANT: this is NOT road distance.","0.8644","Routing Agent"),
    ("ROUTING_FEATURES","service_available_flag","STRING","NO","","Whether service is available on this route: Yes / No.","Yes","Routing Agent"),
    ("ROUTING_FEATURES","origin_type","STRING","NO","","Entity type of origin: WAREHOUSE or SUPPLIER.","WAREHOUSE","Routing Agent"),
    ("ROUTING_FEATURES","destination_type","STRING","NO","","Entity type of destination: LOCATION.","LOCATION","Routing Agent"),
    ("ROUTING_FEATURES","distance_type","STRING","NO","","Distance calculation method. Always 'euclidean_km' (Haversine). Never call this road distance.","euclidean_km","Routing Agent"),
    ("ROUTING_FEATURES","note","STRING","NO","","Important usage warning about distance type.","Euclidean (Haversine) distance only. Road distance not available.","Routing Agent"),
    ("ROUTING_FEATURES","feature_set","STRING","NO","","Agent this feature set is designed for.","ROUTE_OPTIMIZATION_AGENT","Lineage"),
    ("ROUTING_FEATURES","pipeline_timestamp","TIMESTAMP","NO","","UTC pipeline write timestamp.","2026-09-21T13:24:00Z","Lineage"),
    # ═══════════════════════════════════════════════════════
    # DIM_PICKER
    # ═══════════════════════════════════════════════════════
    ("DIM_PICKER", "picker_id", "STRING", "NO", "PK", "Unique warehouse picker identifier. Format: WH-XXX-PKR-YYY.", "WH-001-PKR-001", "Warehouse Agent"),
    ("DIM_PICKER", "warehouse_id", "STRING", "NO", "FK->DIM_WAREHOUSE", "Assigned warehouse. Aligned to canonical WH-KOL-XXX.", "WH-KOL-001", "Warehouse Agent"),
    ("DIM_PICKER", "source_file", "STRING", "NO", "", "Provenance source file.", "Warehouse_Picker_IDs_Only.csv", "Lineage"),
    ("DIM_PICKER", "pipeline_timestamp", "TIMESTAMP", "NO", "", "UTC pipeline write timestamp.", "2026-09-21T17:49:00Z", "Lineage"),

    # ═══════════════════════════════════════════════════════
    # BRIDGE_WAREHOUSE_PICKER
    # ═══════════════════════════════════════════════════════
    ("BRIDGE_WAREHOUSE_PICKER", "warehouse_id", "STRING", "NO", "FK->DIM_WAREHOUSE", "Canonical warehouse identifier.", "WH-KOL-001", "Warehouse Agent"),
    ("BRIDGE_WAREHOUSE_PICKER", "picker_id", "STRING", "NO", "FK->DIM_PICKER", "Assigned picker identifier.", "WH-001-PKR-001", "Warehouse Agent"),
    ("BRIDGE_WAREHOUSE_PICKER", "source_file", "STRING", "NO", "", "Provenance source file.", "Warehouse_Picker_IDs_Only.csv", "Lineage"),
    ("BRIDGE_WAREHOUSE_PICKER", "pipeline_timestamp", "TIMESTAMP", "NO", "", "UTC pipeline write timestamp.", "2026-09-21T17:49:00Z", "Lineage"),

    # ═══════════════════════════════════════════════════════
    # FACT_SALES
    # ═══════════════════════════════════════════════════════
    ("FACT_SALES", "region_product_week_key", "STRING", "NO", "PK", "Composite natural key: region_id + week_key + product_id.", "KOL-LOC-001_20240101_ICE-001", "Demand Agent"),
    ("FACT_SALES", "region_week_key", "STRING", "NO", "FK", "Region-week aggregation key: region_id + week_key.", "KOL-LOC-001_20240101", "Demand Agent"),
    ("FACT_SALES", "week_start_date", "DATE", "NO", "FK->DIM_CALENDAR_WEEK", "First day of sales observation week.", "2024-01-01", "Demand Agent"),
    ("FACT_SALES", "week_end_date", "DATE", "NO", "", "Last day of sales observation week.", "2024-01-07", "Demand Agent"),
    ("FACT_SALES", "region_id", "STRING", "NO", "FK->DIM_LOCATION", "Region identifier. Joins to DIM_LOCATION.location_id.", "KOL-LOC-001", "Demand Agent"),
    ("FACT_SALES", "product_id", "STRING", "NO", "FK->DIM_PRODUCT", "Product identifier. Joins to DIM_PRODUCT.product_id.", "ICE-001", "Demand Agent"),
    ("FACT_SALES", "units_sold", "INTEGER", "NO", "", "Actual total units sold in this region-product-week.", "146", "Demand Agent"),
    ("FACT_SALES", "sales_value_rs", "FLOAT", "NO", "", "Total monetary sales value in INR.", "5986.0", "Demand Agent"),
    ("FACT_SALES", "avg_selling_price_rs", "FLOAT", "NO", "", "Average unit selling price in INR.", "41.0", "Demand Agent"),
    ("FACT_SALES", "promotion_flag", "INTEGER", "NO", "", "1 if promotion was active, else 0.", "0", "Demand Agent"),
    ("FACT_SALES", "discount_pct", "FLOAT", "NO", "", "Discount percentage applied.", "0.0", "Demand Agent"),
    ("FACT_SALES", "stockout_flag", "INTEGER", "NO", "", "1 if stockout occurred, else 0.", "0", "Demand Agent, Risk Agent"),

    # ═══════════════════════════════════════════════════════
    # FACT_INVENTORY_TRANSACTION
    # ═══════════════════════════════════════════════════════
    ("FACT_INVENTORY_TRANSACTION", "transaction_id", "STRING", "NO", "PK", "Unique inventory transaction identifier.", "TX-000001", "Inventory Agent"),
    ("FACT_INVENTORY_TRANSACTION", "warehouse_product_week_key", "STRING", "NO", "FK", "Composite key linking warehouse, product, and week.", "WH-KOL-001_ICE-001_20240101", "Inventory Agent"),
    ("FACT_INVENTORY_TRANSACTION", "week_start_date", "DATE", "NO", "FK->DIM_CALENDAR_WEEK", "First day of transaction week.", "2024-01-01", "Inventory Agent"),
    ("FACT_INVENTORY_TRANSACTION", "warehouse_id", "STRING", "NO", "FK->DIM_WAREHOUSE", "Warehouse where transaction took place.", "WH-KOL-001", "Inventory Agent"),
    ("FACT_INVENTORY_TRANSACTION", "product_id", "STRING", "NO", "FK->DIM_PRODUCT", "Product transacted.", "ICE-001", "Inventory Agent"),
    ("FACT_INVENTORY_TRANSACTION", "sold_units", "INTEGER", "NO", "", "Quantity of units moved/transacted.", "67", "Inventory Agent"),
    ("FACT_INVENTORY_TRANSACTION", "transaction_type", "STRING", "NO", "", "Type of inventory transaction (e.g. SALE, REPLENISHMENT).", "SALE", "Inventory Agent"),
    ("FACT_INVENTORY_TRANSACTION", "direction", "STRING", "NO", "", "Movement direction: OUT or IN.", "OUT", "Inventory Agent"),
    ("FACT_INVENTORY_TRANSACTION", "record_status", "STRING", "NO", "", "Status of transaction record.", "COMPLETED", "Inventory Agent"),

]

# ─── Write CSV ────────────────────────────────────────────────────────────────
cols = ["table_name","field_name","data_type","nullable","key_type","description","example_value","agent_consumer"]
df = pd.DataFrame(DEFINITIONS, columns=cols)
df.to_csv(DOC / "DATA_DICTIONARY.csv", index=False)
print(f"DATA_DICTIONARY.csv: {len(df)} field definitions across {df['table_name'].nunique()} tables")

# ─── Write Markdown ───────────────────────────────────────────────────────────
lines = [
    "# Data Dictionary",
    f"## Kolkata Multi-Agent Supply Chain System",
    f"**Generated**: {NOW}  ",
    f"**Total tables**: {df['table_name'].nunique()}  ",
    f"**Total fields**: {len(df)}",
    "",
    "> **Key conventions**",
    "> - All final tables use `lowercase_snake_case` column names.",
    "> - `pipeline_timestamp` is always UTC ISO-8601.",
    "> - `PK` = Primary Key, `FK→<table>` = Foreign Key reference.",
    "> - `TARGET` = model prediction target — **must not be used as a feature**.",
    "> - `QUARANTINE` = field with unresolved semantics — do not use in production without domain review.",
    "> - `SUPPLIED_SYNTHETIC` = data generated for simulation, not real-world observations.",
    "> - Euclidean distances are **Haversine great-circle km** — never road distance.",
    "",
    "---",
    "",
]

SECTIONS = {
    "Dimension Tables": ["DIM_PRODUCT","DIM_PRODUCT_VARIANT","DIM_LOCATION","DIM_WAREHOUSE",
                         "DIM_SUPPLIER","DIM_CALENDAR_WEEK","DIM_FESTIVAL","DIM_WEATHER","DIM_PICKER"],
    "Fact Tables": ["FACT_DEMAND","FACT_SALES","FACT_INVENTORY_POSITION","FACT_INVENTORY_TRANSACTION","FACT_SUPPLIER_AVAILABILITY"],
    "Bridge / Mapping Tables": ["BRIDGE_SUPPLIER_PRODUCT","BRIDGE_LOCATION_SUPPLIER",
                                 "BRIDGE_WAREHOUSE_LOCATION","BRIDGE_PRODUCT_WAREHOUSE","BRIDGE_WAREHOUSE_PICKER"],
    "Feature Sets": ["DEMAND_FEATURES","DEMAND_TARGETS","ROUTING_FEATURES"],
    "Blocked Outputs (LFS)": [],
}

# table of contents
lines.append("## Table of Contents")
lines.append("")
for section, tables in SECTIONS.items():
    lines.append(f"- **{section}**")
    for t in tables:
        anchor = t.lower().replace("_","-")
        lines.append(f"  - [{t}](#{anchor})")
lines.append("- [Blocked Outputs](#blocked-outputs)")
lines.append("")
lines.append("---")
lines.append("")

for section, tables in SECTIONS.items():
    if not tables:
        continue
    lines.append(f"## {section}")
    lines.append("")
    for table in tables:
        tdf = df[df["table_name"] == table]
        if tdf.empty:
            continue
        anchor = table.lower().replace("_","-")
        lines.append(f"### {table}")
        lines.append("")

        # Row count from curated/features
        for layer in [CUR, FEAT]:
            fpath = layer / f"{table}.csv"
            if fpath.exists():
                try:
                    row_count = sum(1 for _ in open(fpath, encoding="utf-8")) - 1
                    lines.append(f"**Source layer**: `{'06_curated' if layer == CUR else '07_features'}/{table}.csv`  ")
                    lines.append(f"**Row count**: {row_count:,}  ")
                except:
                    pass
                break

        # Key fields summary
        pks  = tdf[tdf["key_type"].str.contains("PK", na=False)]["field_name"].tolist()
        fks  = tdf[tdf["key_type"].str.startswith("FK", na=False)]["field_name"].tolist()
        tgts = tdf[tdf["key_type"] == "TARGET"]["field_name"].tolist()
        qts  = tdf[tdf["key_type"] == "QUARANTINE"]["field_name"].tolist()

        if pks:  lines.append(f"**Primary key**: `{'`, `'.join(pks)}`  ")
        if fks:  lines.append(f"**Foreign keys**: `{'`, `'.join(fks)}`  ")
        if tgts: lines.append(f"**⚠️ TARGET fields** (excluded from features): `{'`, `'.join(tgts)}`  ")
        if qts:  lines.append(f"**🔶 QUARANTINE fields** (domain review required): `{'`, `'.join(qts)}`  ")
        lines.append("")

        # Field table
        lines.append("| Field | Type | Nullable | Key | Description | Example |")
        lines.append("|---|---|:---:|---|---|---|")
        for _, row in tdf.iterrows():
            nullable_icon = "✅" if row["nullable"] == "YES" else "❌"
            key_disp = row["key_type"] if row["key_type"] not in ("","N/A") else "—"
            desc = row["description"].replace("|","\\|")
            example = str(row["example_value"]).replace("|","\\|")
            lines.append(f"| `{row['field_name']}` | {row['data_type']} | {nullable_icon} | {key_disp} | {desc} | `{example}` |")
        lines.append("")
        lines.append("---")
        lines.append("")

# Blocked outputs section
lines.append("## Blocked Outputs")
lines.append("")
lines.append("These tables **cannot be built** until the Git-LFS source files are fetched.")
lines.append("")
lines.append("| Table | Blocked By | LFS OID | Expected Size | Fix |")
lines.append("|---|---|---|---|---|")
lines.append("| (None) | All previous Git-LFS blocked sources have been unblocked with corrected datasets! | Resolved | Reconstructed | Integrated |")
lines.append("")
lines.append("After running `git lfs pull`, re-execute `pipeline/run_pipeline.py` to build these tables.")
lines.append("")
lines.append("---")
lines.append("")
lines.append("## Quarantine Register")
lines.append("")
lines.append("| QRN-ID | Field | Table | Issue | Action |")
lines.append("|---|---|---|---|---|")
lines.append("| QRN-001 | `unmapped_col_10_quarantine` | BRIDGE_SUPPLIER_PRODUCT, FACT_SUPPLIER_AVAILABILITY | Column index 10 in Supplier_Product_Catalog has no header. Values numeric ~9–200. Possible unit ratio. | Domain expert review required before production use. |")
lines.append("| QRN-002 | ALL | FACT_SALES | sales_history.xlsx is a Git-LFS pointer. | Run `git lfs pull`. |")
lines.append("| QRN-003 | ALL | FACT_INVENTORY_TRANSACTION | inventory_transactions.xlsx is a Git-LFS pointer. | Run `git lfs pull`. |")
lines.append("")

md_text = "\n".join(lines)
(DOC / "DATA_DICTIONARY.md").write_text(md_text, encoding="utf-8")
print(f"DATA_DICTIONARY.md written: {len(lines)} lines")

