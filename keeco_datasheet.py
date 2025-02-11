import pandas as pd
import re
import psycopg2
from psycopg2.extras import execute_values
from dotenv import dotenv_values
import json

# Load environment variables from .env file
env_path = r"C:\\Users\\juddu\\Downloads\\PAM\\Staging Area\\Keeco\\.env"
config = dotenv_values(env_path)

# Database connection details
DB_NAME = config['DB_NAME']
DB_USER = config['DB_USER']
DB_PASSWORD = config['DB_PASSWORD']
DB_HOST = config['DB_HOST']
DB_PORT = config['DB_PORT']

# Define the file path
file_path = r"C:\\Users\\juddu\\Downloads\\PAM\\Staging Area\\Keeco\\Hospitality General Line Price List New Hookless Pricing 110624 final.xlsx"

# Load the Excel file
sheet_name = "keeco"
df = pd.read_excel(file_path, sheet_name=sheet_name)

# Cleaning and normalizing the data
# Step 1: Drop empty columns and rows
df = df.dropna(how='all', axis=0)
df = df.dropna(how='all', axis=1)

# Step 2: Handle duplicates
df = df.drop_duplicates()

# Step 3: Ensure proper data types for specific columns
df['case_length'] = pd.to_numeric(df.get('Case Length', pd.Series(dtype='float')), errors='coerce')
df['case_width'] = pd.to_numeric(df.get('Case Width', pd.Series(dtype='float')), errors='coerce')
df['case_height'] = pd.to_numeric(df.get('Case Height', pd.Series(dtype='float')), errors='coerce')
df['case_pack'] = pd.to_numeric(df.get('Case Pack', pd.Series(dtype='int')), errors='coerce')
df['price_each_fob'] = pd.to_numeric(df.get('Price Each (FOB Plant)', pd.Series(dtype='float')), errors='coerce')
df['liner'] = df.get('Liner (Yes or No)', '').str.lower().map({'yes': True, 'no': False})

# Convert 'liner' to boolean or None
df['liner'] = df['liner'].map({True: True, False: False}).where(df['liner'].notna(), None)

# Debugging: Check the 'liner' column values
print("Liner column values:")
print(df['liner'].unique())

# Step 4: Create 'specs' column
specs_columns = [
    'Thread Count / GSM', 'Materal ', 'Edge Designs', 'Fabric Treatments',
    'Quilting Designs', 'Specialized Features'
]
df['specs'] = df[specs_columns].apply(lambda row: row.dropna().to_dict(), axis=1)

# Convert 'specs' to JSON strings for database insertion
df['specs'] = df['specs'].apply(lambda x: json.dumps(x) if isinstance(x, dict) else x)

# Drop unused columns
columns_to_drop = specs_columns + [
    'Case Length', 'Case Width', 'Case Height', 'Case Pack', 'Price Each (FOB Plant)', 'Liner (Yes or No)'
]
df = df.drop(columns=columns_to_drop)

# Rename columns to match database schema
column_mapping = {
    'Category': 'category',
    'Sub Category': 'sub_category',
    'Collection': 'collection',
    'SKU': 'sku',
    'Size Type': 'size_type',
    'Size': 'size',
    'Fill Weight': 'fill_weight',
}
df.rename(columns=column_mapping, inplace=True)

# Step 5: Remove ™ and ® symbols from all text columns
def clean_symbols(value):
    if isinstance(value, str):
        return re.sub(r"[™®]", "", value).strip()
    return value

df = df.applymap(clean_symbols)

# Debugging: Ensure all columns have correct data types
print("DataFrame dtypes:")
print(df.dtypes)
print("Preview of cleaned data:")
print(df.head())

# Insert data into PostgreSQL
def insert_to_db(df, table_name):
    # Define the connection
    conn = psycopg2.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT
    )
    cursor = conn.cursor()

    # Define the columns to insert
    columns = list(df.columns)
    values = df.to_dict(orient='records')

    # Debug: Print first few rows to ensure compatibility
    print("Prepared rows for insertion:")
    for value in values[:5]:
        print(value)

    # SQL statement
    sql = f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES %s ON CONFLICT (sku) DO NOTHING"
    
    # Prepare the data for insertion
    data_to_insert = [tuple(row[col] for col in columns) for row in values]
    
    # Execute batch insert
    execute_values(cursor, sql, data_to_insert)
    
    # Commit and close connection
    conn.commit()
    cursor.close()
    conn.close()
    print(f"Data inserted into {table_name} successfully.")

# Insert the data into the database
table_name = "manufactured.keeco"
insert_to_db(df, table_name)
