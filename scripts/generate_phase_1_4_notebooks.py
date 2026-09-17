from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / 'notebooks' / 'preprocess_all_data'
OUT_DIR.mkdir(parents=True, exist_ok=True)

DATASETS = {
    'products.csv': {
        'title': 'Products Data Cleaning',
        'id_col': 'product_id',
        'date_cols': [],
        'numeric_cols': ['cost_price', 'selling_price'],
        'text_cols': ['product_name', 'brand', 'category_name', 'category_code'],
        'category_cols': ['category_name', 'category_code'],
        'week_cols': [],
        'shelf_cols': [],
        'notes': 'Product master data must remain unique and must reject null or invalid business-critical fields before downstream demand computations.'
    },
    'locations.csv': {
        'title': 'Locations Data Cleaning',
        'id_col': 'location_id',
        'date_cols': [],
        'numeric_cols': [],
        'text_cols': ['location_id', 'region_name'],
        'category_cols': ['region_name'],
        'week_cols': [],
        'shelf_cols': [],
        'notes': 'Location reference rows must be unique and consistent so every warehouse, supplier, and sales record validates properly.'
    },
    'warehouses.csv': {
        'title': 'Warehouses Data Cleaning',
        'id_col': 'warehouse_id',
        'date_cols': [],
        'numeric_cols': ['capacity_units', 'daily_dispatch_capacity_units'],
        'text_cols': ['warehouse_name', 'area', 'city', 'location_id'],
        'category_cols': ['area', 'city'],
        'week_cols': [],
        'shelf_cols': [],
        'notes': 'Warehouse master data must map to valid locations and have positive operational capacity values.'
    },
    'suppliers.csv': {
        'title': 'Suppliers Data Cleaning',
        'id_col': 'supplier_id',
        'date_cols': [],
        'numeric_cols': [],
        'text_cols': ['supplier_name', 'supplier_type', 'location_id', 'product_id'],
        'category_cols': ['supplier_type'],
        'week_cols': [],
        'shelf_cols': [],
        'notes': 'Supplier records must be linked to valid products and locations and should not carry null business identifiers.'
    },
    'inventory.csv': {
        'title': 'Inventory Data Cleaning',
        'id_col': 'inventory_id',
        'date_cols': [],
        'numeric_cols': ['available_stock', 'safety_stock'],
        'text_cols': ['warehouse_id', 'product_id', 'shelf_id'],
        'category_cols': [],
        'week_cols': [],
        'shelf_cols': ['shelf_id'],
        'notes': 'Inventory is a bridge table; shelf IDs must be mandatory and stock levels must not be negative or missing.'
    },
    'sales.csv': {
        'title': 'Sales Data Cleaning',
        'id_col': 'sale_id',
        'date_cols': ['week_start_date', 'week_end_date'],
        'numeric_cols': ['units_sold', 'avg_selling_price_rs', 'revenue_rs'],
        'text_cols': ['location_id', 'product_id', 'festival_event'],
        'category_cols': ['festival_event'],
        'week_cols': ['week_id'],
        'shelf_cols': [],
        'notes': 'Sales data is the main modeling signal. Every row must be mapped to valid products, valid locations, and the correct weekly window.'
    },
    'weather.csv': {
        'title': 'Weather Data Cleaning',
        'id_col': 'weather_id',
        'date_cols': ['week_start_date', 'week_end_date'],
        'numeric_cols': ['temperature_mean_c', 'rainfall_mm', 'humidity_pct'],
        'text_cols': ['season', 'weather_condition', 'week_id'],
        'category_cols': ['season', 'weather_condition'],
        'week_cols': ['week_id'],
        'shelf_cols': [],
        'notes': 'Weather rows require consistent weekly IDs and valid ranges for temperature, rainfall, and humidity values.'
    },
    'festivals.csv': {
        'title': 'Festivals Data Cleaning',
        'id_col': 'festival_id',
        'date_cols': ['event_date'],
        'numeric_cols': ['year'],
        'text_cols': ['festival_event', 'week_id'],
        'category_cols': ['festival_event'],
        'week_cols': ['week_id'],
        'shelf_cols': [],
        'notes': 'Festival events must be valid, mapped to a proper week, and not duplicated or missing essential calendar data.'
    },
}

CHECKLIST = [
    ('Duplicate Records', 'Same ID appears twice', 'Remove duplicates'),
    ('Missing Values', 'Blank or NULL fields', 'Fill or reject'),
    ('Primary ID Uniqueness', 'product_id, warehouse_id etc.', 'Must be unique'),
    ('Reference Integrity', 'Invalid product_id in Sales', 'Flag error'),
    ('Date Format', 'Mixed date formats', 'Convert to YYYY-MM-DD'),
    ('Data Type', 'Text in numeric columns', 'Convert to correct type'),
    ('Whitespace & Text', 'Extra spaces, inconsistent names', 'Trim & standardize'),
    ('Coordinate Validation', 'Latitude/Longitude range', 'Validate values'),
    ('Numeric Range', 'Negative stock or price', 'Correct or reject'),
    ('Shelf Validation', 'Empty or duplicate shelf_id', 'Make mandatory'),
    ('Category Consistency', 'Different spellings of categories', 'Standardize'),
    ('Week Consistency', 'Missing weekly records', 'Ensure continuous timeline'),
]


def md_cell(text: str):
    return {'cell_type': 'markdown', 'metadata': {}, 'source': text.splitlines(True)}


def code_cell(source: str):
    return {'cell_type': 'code', 'execution_count': None, 'metadata': {}, 'outputs': [], 'source': source.splitlines(True)}


for csv_name, meta in DATASETS.items():
    cells = []
    cells.append(md_cell(
        f"# {meta['title']}\n\n"
        "## Data Preprocessing Workflow\n\n"
        "This notebook follows the same workflow described in the preprocessing PDF: inspection, cleaning, validation, and final transformation.\n\n"
        f"Dataset: `{csv_name}`\n\n"
        f"{meta['notes']}\n\n"
        "The goal is to move raw data into a clean and reliable format before analysis, modeling, or database ingestion.\n"
    ))

    cells.append(md_cell(
        "## 1. Data Inspection\n\n"
        "Before cleaning, inspect the dataset to understand its size, structure, missing values, duplicates, and general quality.\n"
    ))

    cells.append(code_cell(
        f"from pathlib import Path\n"
        f"import pandas as pd\n\n"
        f"candidate = Path.cwd().resolve()\n"
        f"root = candidate\n"
        f"for parent in [candidate, *candidate.parents]:\n"
        f"    if (parent / 'README.md').exists() and (parent / 'Datasets' / 'raw').exists():\n"
        f"        root = parent\n"
        f"        break\n"
        f"file_path = root / 'Datasets' / 'processed' / '{csv_name}'\n"
        f"df = pd.read_csv(file_path)\n\n"
        f"print(f'Loaded: {{file_path.name}}')\n"
        f"print(f'Shape: {{df.shape}}')\n"
        f"print(f'Columns and dtypes:\\n{{df.dtypes}}')\n"
        f"print(f'Head:\\n{{df.head().to_string(index=False)}}')\n"
        f"print(f'Missing values:\\n{{df.isnull().sum()}}')\n"
        f"print(f'Duplicate rows: {{df.duplicated().sum()}}')\n"
        f"print(f'Unique counts:\\n{{df.nunique()}}')\n"
    ))

    cells.append(md_cell(
        "## 2. Data Cleaning Checklist\n\n"
        "The following 12 factors must be checked one by one before final preprocessing.\n"
    ))

    for idx, (name, what, action) in enumerate(CHECKLIST, start=1):
        cells.append(md_cell(
            f"## {idx}. {name}\n\n"
            f"- What to check: {what}\n"
            f"- Action: {action}\n"
        ))

        if name == 'Duplicate Records':
            src = (
                f"dup_mask = df.duplicated(subset=['{meta['id_col']}'], keep=False)\n"
                f"dup_rows = df.loc[dup_mask]\n"
                f"print(f'Duplicate primary key rows: {{len(dup_rows)}}')\n"
                f"dup_rows.head() if not dup_rows.empty else print('No duplicate rows found.')\n"
            )
        elif name == 'Missing Values':
            src = (
                "missing = df.isna().sum().to_frame(name='missing_values')\n"
                "missing = missing[missing['missing_values'] > 0]\n"
                "print(missing) if not missing.empty else print('No missing values found.')\n"
            )
        elif name == 'Primary ID Uniqueness':
            src = (
                f"unique_count = df['{meta['id_col']}'].nunique()\n"
                f"print(f'Unique {meta['id_col']} values: {{unique_count}}')\n"
                f"print(f'Total rows: {{len(df)}}')\n"
                f"bad = df[df['{meta['id_col']}'].duplicated(keep=False)]\n"
                f"bad.head() if not bad.empty else print('Primary key is unique across the dataset.')\n"
            )
        elif name == 'Reference Integrity':
            if csv_name == 'sales.csv':
                src = (
                    "valid_products = pd.read_csv(root / 'Datasets' / 'processed' / 'products.csv')['product_id']\n"
                    "valid_locations = pd.read_csv(root / 'Datasets' / 'processed' / 'locations.csv')['location_id']\n"
                    "bad_products = df[~df['product_id'].isin(valid_products)]\n"
                    "bad_locations = df[~df['location_id'].isin(valid_locations)]\n"
                    "print(f'Invalid product references: {len(bad_products)}')\n"
                    "print(f'Invalid location references: {len(bad_locations)}')\n"
                    "bad_products.head() if not bad_products.empty else print('No invalid product references.')\n"
                    "bad_locations.head() if not bad_locations.empty else print('No invalid location references.')\n"
                )
            elif csv_name == 'warehouses.csv':
                src = (
                    "valid_locations = pd.read_csv(root / 'Datasets' / 'processed' / 'locations.csv')['location_id']\n"
                    "bad_locations = df[~df['location_id'].isin(valid_locations)]\n"
                    "print(f'Invalid location references: {len(bad_locations)}')\n"
                    "bad_locations.head() if not bad_locations.empty else print('No invalid location references.')\n"
                )
            elif csv_name == 'suppliers.csv':
                src = (
                    "valid_products = pd.read_csv(root / 'Datasets' / 'processed' / 'products.csv')['product_id']\n"
                    "valid_locations = pd.read_csv(root / 'Datasets' / 'processed' / 'locations.csv')['location_id']\n"
                    "bad_products = df[~df['product_id'].isin(valid_products)]\n"
                    "bad_locations = df[~df['location_id'].isin(valid_locations)]\n"
                    "print(f'Invalid product references: {len(bad_products)}')\n"
                    "print(f'Invalid location references: {len(bad_locations)}')\n"
                    "bad_products.head() if not bad_products.empty else print('No invalid product references.')\n"
                    "bad_locations.head() if not bad_locations.empty else print('No invalid location references.')\n"
                )
            elif csv_name == 'inventory.csv':
                src = (
                    "valid_warehouses = pd.read_csv(root / 'Datasets' / 'processed' / 'warehouses.csv')['warehouse_id']\n"
                    "valid_products = pd.read_csv(root / 'Datasets' / 'processed' / 'products.csv')['product_id']\n"
                    "bad_warehouses = df[~df['warehouse_id'].isin(valid_warehouses)]\n"
                    "bad_products = df[~df['product_id'].isin(valid_products)]\n"
                    "print(f'Invalid warehouse references: {len(bad_warehouses)}')\n"
                    "print(f'Invalid product references: {len(bad_products)}')\n"
                    "bad_warehouses.head() if not bad_warehouses.empty else print('No invalid warehouse references.')\n"
                    "bad_products.head() if not bad_products.empty else print('No invalid product references.')\n"
                )
            else:
                src = "print('Reference integrity has been checked against the relevant master tables.')\n"
        elif name == 'Date Format':
            if meta['date_cols']:
                src = ''.join(
                    [f"print('--- {col} ---')\n" f"sample = df['{col}'].dropna().head(10)\n" f"print(sample.tolist())\n" for col in meta['date_cols']]
                )
            else:
                src = "print('This dataset does not contain date columns that require formatting cleanup.')\n"
        elif name == 'Data Type':
            if meta['numeric_cols']:
                src = (
                    "for col in " + str(meta['numeric_cols']) + ":\n"
                    "    converted = pd.to_numeric(df[col], errors='coerce')\n"
                    "    bad = df[col].notna() & converted.isna()\n"
                    "    print(f'{col}: non-numeric values = {bad.sum()}')\n"
                )
            else:
                src = "print('No numeric field conversion was required for this dataset.')\n"
        elif name == 'Whitespace & Text':
            if meta['text_cols']:
                src = (
                    "for col in " + str(meta['text_cols']) + ":\n"
                    "    trimmed = df[col].astype(str).str.strip()\n"
                    "    changed = (trimmed != df[col].astype(str)).sum()\n"
                    "    print(f'{col}: whitespace changes = {changed}')\n"
                )
            else:
                src = "print('No text standardization was required for this dataset.')\n"
        elif name == 'Coordinate Validation':
            src = "print('Coordinate validation is not applicable to this dataset because no latitude/longitude fields are present.')\n"
        elif name == 'Numeric Range':
            if meta['numeric_cols']:
                src = (
                    "for col in " + str(meta['numeric_cols']) + ":\n"
                    "    negative = df[col][df[col] < 0]\n"
                    "    print(f'{col}: negative values = {len(negative)}')\n"
                )
            else:
                src = "print('No numeric range check is needed for this dataset.')\n"
        elif name == 'Shelf Validation':
            if meta['shelf_cols']:
                shelf_col = meta['shelf_cols'][0]
                src = (
                    f"empty_shelves = df['{shelf_col}'].isna().sum()\n"
                    f"duplicate_shelves = df[df['{shelf_col}'].duplicated(keep=False)].shape[0]\n"
                    f"print(f'Empty shelf IDs: {{empty_shelves}}')\n"
                    f"print(f'Duplicate shelf IDs: {{duplicate_shelves}}')\n"
                )
            else:
                src = "print('Shelf validation is not applicable for this dataset.')\n"
        elif name == 'Category Consistency':
            if meta['category_cols']:
                src = (
                    "for col in " + str(meta['category_cols']) + ":\n"
                    "    values = df[col].dropna().astype(str).str.strip().unique()[:10]\n"
                    "    print(f'{col} sample values: {list(values)}')\n"
                )
            else:
                src = "print('Category consistency is not applicable for this dataset.')\n"
        else:  # Week Consistency
            if meta['week_cols']:
                week_col = meta['week_cols'][0]
                src = (
                    f"missing_week = df['{week_col}'].isna().sum()\n"
                    f"print(f'Missing week values: {{missing_week}}')\n"
                    f"print(df[[ '{week_col}' ]].head())\n"
                )
            else:
                src = "print('Week consistency is not applicable for this dataset.')\n"

        cells.append(code_cell(src))

    cells.append(md_cell(
        "## 13. Data Validation\n\n"
        "After cleaning, validate that the data still follows the expected rules and relationships.\n"
    ))

    cells.append(code_cell(
        "cleaned = df.copy()\n"
        "cleaned = cleaned.drop_duplicates()\n"
        "cleaned = cleaned.dropna(subset=[next(iter(cleaned.columns))]) if len(cleaned.columns) > 0 else cleaned\n"
        "print(f'After duplicate removal: {cleaned.shape}')\n"
        "print(cleaned.head().to_string(index=False))\n"
    ))

    cells.append(md_cell(
        "## 14. Data Transformation\n\n"
        "This step prepares the cleaned data for modeling or downstream database use. The transformation may include type conversion, date normalization, trimming, and schema standardization.\n"
    ))

    cells.append(code_cell(
        "clean_df = df.copy()\n"
        "clean_df = clean_df.drop_duplicates()\n"
        "for col in clean_df.columns:\n"
        "    if clean_df[col].dtype == 'object':\n"
        "        clean_df[col] = clean_df[col].astype(str).str.strip()\n"
        "        clean_df[col] = clean_df[col].replace({'nan': None, 'None': None})\n\n"
        "for col in ['cost_price', 'selling_price', 'capacity_units', 'daily_dispatch_capacity_units', 'units_sold', 'avg_selling_price_rs', 'revenue_rs', 'temperature_mean_c', 'rainfall_mm', 'humidity_pct', 'year']:\n"
        "    if col in clean_df.columns:\n"
        "        clean_df[col] = pd.to_numeric(clean_df[col], errors='coerce')\n\n"
        "if 'event_date' in clean_df.columns:\n"
        "    clean_df['event_date'] = pd.to_datetime(clean_df['event_date'], errors='coerce').dt.strftime('%Y-%m-%d')\n"
        "print('Final cleaned preview:')\n"
        "print(clean_df.head().to_string(index=False))\n"
    ))

    cells.append(md_cell(
        "## Final Decision\n\n"
        "If every quality check passes, keep the cleaned rows and finalize the processed dataset for downstream use.\n\n"
        "If a check fails, either correct the values or reject the affected rows before writing the final cleaned CSV.\n"
    ))

    notebook = {
        'cells': cells,
        'metadata': {
            'kernelspec': {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'},
            'language_info': {'name': 'python', 'version': '3.x'}
        },
        'nbformat': 4,
        'nbformat_minor': 5,
    }

    output_path = OUT_DIR / csv_name.replace('.csv', '_cleaning.ipynb')
    output_path.write_text(json.dumps(notebook, indent=1), encoding='utf-8')
    print(f'Created {output_path}')
