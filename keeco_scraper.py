import sys
import os
import re
import csv
import psycopg2
from psycopg2 import sql
from dotenv import load_dotenv
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import undetected_chromedriver as uc
import unicodedata
from ftfy import fix_text

# Load .env file
dotenv_path = r'.env'
load_dotenv(dotenv_path)

# Retrieve credentials
keeco_username = os.getenv('KEECO_USERNAME')
keeco_password = os.getenv('KEECO_PASSWORD')

print("Debug: Checking environment variables:")
print(f"Debug: .env file path: {os.path.abspath(dotenv_path)}")
print(f"Debug: KEECO_USERNAME is {'set' if keeco_username else 'not set'}")
print(f"Debug: KEECO_PASSWORD is {'set' if keeco_password else 'not set'}")

if not keeco_username or not keeco_password:
    print("Error: KEECO_USERNAME and KEECO_PASSWORD environment variables must be set.")
    sys.exit(1)

# Initialize WebDriver with undetected-chromedriver
try:
    print("Initializing Chrome WebDriver...")
    options = uc.ChromeOptions()
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    # Remove headless mode as it can cause issues with undetected-chromedriver
    # options.add_argument('--headless')
    
    # Use version_main to specify your Chrome version
    driver = uc.Chrome(
        options=options,
        version_main=132  # Specify your Chrome version here
    )
    driver.set_window_size(1920, 1080)  # Set a standard window size
    print("WebDriver initialized successfully!")
except Exception as e:
    print(f"Error initializing WebDriver: {e}")
    sys.exit(1)

# Function to log in
def login_to_site():
    try:
        driver.get("https://www.keecohospitality.com/home/FMI")
        email_field = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='text'][placeholder='email address']"))
        )
        password_field = driver.find_element(By.CSS_SELECTOR, "input[type='password'][placeholder='password']")
        email_field.send_keys(keeco_username)
        password_field.send_keys(keeco_password)
        sign_in_button = driver.find_element(By.CSS_SELECTOR, "button.sign-in-button")
        sign_in_button.click()

        # Wait for login confirmation
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "#header > div.content > div.customer-info"))
        )
        print("Login successful!")
    except Exception as e:
        print(f"Error during login: {e}")
        driver.quit()
        sys.exit(1)

# Function to scrape product details from the product page
def scrape_product_page(product_url):
    driver.get(product_url)
    try:
        # Wait for the product page to load
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "#product-content"))
        )

        # Initialize the product data dictionary
        product_data = {"url": product_url}

        # Extract product name
        try:
            parent_product_name = driver.find_element(By.CSS_SELECTOR, "#product-content > h1 > div.product-name").text.strip()
            product_data["parent_name"] = parent_product_name
        except Exception:
            product_data["parent_name"] = "N/A"

        # Extract long description
        try:
            long_description = driver.find_element(By.CSS_SELECTOR, "#product-content > div.product-long-description").text.strip()
            product_data["long_description"] = long_description
        except Exception:
            product_data["long_description"] = "N/A"

        # Extract product information
        try:
            product_information = driver.find_element(By.CSS_SELECTOR, "#product-content > div.product-information").text.strip()
            product_data["product_information"] = product_information
        except Exception:
            product_data["product_information"] = "N/A"

        # Extract images
        try:
            image_container = driver.find_element(By.CSS_SELECTOR, "#product-content > div.product-image-container.mobile-show")
            images = image_container.find_elements(By.TAG_NAME, "img")
            product_data["images"] = [img.get_attribute("src") for img in images]
        except Exception:
            product_data["images"] = []

        # Extract table data (Item, Product Name, Price/Unit, Unit/Case)
        try:
            table_container = driver.find_element(By.CSS_SELECTOR, ".order-table")
            table_headers = table_container.find_elements(By.TAG_NAME, "th")
    
            # Get the header text and corresponding index
            header_mapping = [header.text.strip() for header in table_headers]
            print(f"DEBUG: Table headers: {header_mapping}")
    
            # Extract table rows
            table_rows = table_container.find_elements(By.TAG_NAME, "tr")
            table_data = []
    
            for row in table_rows[1:]:  # Skip the header row
                cols = row.find_elements(By.TAG_NAME, "td")
                if len(cols) == len(header_mapping):  # Ensure the row matches the header count
                    table_data.append({
                        "item": cols[header_mapping.index("Item")].text.strip() if "Item" in header_mapping else "",
                        "type_size": clean_type_size(
                            product_data.get("parent_name", ""),
                            cols[header_mapping.index("Product Name")].text.strip()
                        ) if "Product Name" in header_mapping else "",
                        "price_per_unit": cols[header_mapping.index("Price/Unit")].text.strip() if "Price/Unit" in header_mapping else "",
                        "units_per_case": cols[header_mapping.index("Unit/Case")].text.strip() if "Unit/Case" in header_mapping else "",
                    })
                else:
                    print(f"DEBUG: Skipped row with mismatched column count: {[col.text for col in cols]}")
    
            product_data["table_data"] = table_data
        except Exception as e:
            product_data["table_data"] = []
            print(f"DEBUG: Failed to extract table data: {e}")

        # Extract dynamic specs (Details)
        try:
            detail_section = driver.find_element(By.CSS_SELECTOR, "#detail")
            keys = detail_section.find_elements(By.CSS_SELECTOR, ".col-1")
            values = detail_section.find_elements(By.CSS_SELECTOR, ".col-2")

            # Map keys to values dynamically
            raw_details = {}
            for key, value in zip(keys, values):
                raw_details[key.text.strip()] = value.text.strip()
            
            # Parse details by variant
            variant_details = parse_details_by_variant(raw_details)
            
            # Update table_data with corresponding details
            for row in product_data["table_data"]:
                type_size = row["type_size"]
                print(f"DEBUG: Matching details for type_size: '{type_size}'")
                # Find matching variant details
                for variant, details in variant_details.items():
                    print(f"DEBUG: Checking variant: '{variant}' with details: {details}")
                    if type_size.lower() in variant.lower() or variant.lower() in type_size.lower():
                        print(f"DEBUG: Found matching variant for type_size: '{type_size}' -> '{variant}'")
                        row["details"] = details
                        break
                else:
                    print(f"DEBUG: No specific variant match found for type_size: '{type_size}', using general details")
                    row["details"] = raw_details
            
        except Exception as e:
            product_data["details"] = {}
            print(f"DEBUG: Failed to extract details: {e}")

        print(f"Scraped product data: {product_data}")
        return product_data

    except Exception as e:
        print(f"Error scraping product page: {e}")
        return {"url": product_url, "error": str(e)}


# Function to extract products from a category
def extract_products_from_category(category_name, category_url):
    driver.get(category_url)
    products = []
    print(f"Extracting products from {category_name}...")

    while True:
        try:
            # Wait for the product grid to load
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "search-result-items"))
            )

            # Extract product links from the grid
            product_grid = driver.find_element(By.ID, "search-result-items")
            product_elements = product_grid.find_elements(By.CSS_SELECTOR, ".product-tile a")
            print(f"DEBUG: Found {len(product_elements)} product elements on the page.")

            # Extract links and remove duplicates
            product_links = list(set([element.get_attribute("href") for element in product_elements]))
            print(f"DEBUG: Unique product links found: {product_links}")

            # Click and scrape each product
            for product_link in product_links:
                if product_link:
                    print(f"DEBUG: Clicking on product link: {product_link}")
                    product_details = scrape_product_page(product_link)
                    product_details["category"] = category_name
                    products.append(product_details)
                else:
                    print("DEBUG: Skipped an empty product link.")

            # Check for next page
            try:
                next_button = driver.find_element(By.CSS_SELECTOR, ".pagination .next")
                if "disabled" in next_button.get_attribute("class"):
                    break
                next_button.click()
                WebDriverWait(driver, 10).until(EC.staleness_of(product_grid))  # Wait for the page to refresh
            except Exception:
                print("DEBUG: No more pages in this category.")
                break

        except Exception as e:
            print(f"Error loading products from category: {e}")
            break

    return products


def clean_text(text):
    """Clean up text by fixing encoding issues and normalizing."""
    if not isinstance(text, str):
        return text  # Skip cleaning if it's not a string
    text = fix_text(text)  # Fix text encoding issues
    text = unicodedata.normalize("NFKC", text)  # Normalize Unicode
    text = text.replace("\u00a0", " ")  # Replace non-breaking spaces
    text = re.sub(r"[®™©]", "", text)  # Remove trademark and registered symbols
    text = text.replace("â€", "-")  # Replace specific encoding issue with dash
    return text.strip()  # Trim leading/trailing whitespace
    

def clean_image_urls(images):
    """Clean up image URLs by removing anything after .jpg."""
    cleaned_images = []
    for img_url in images:
        match = re.match(r"(.*?\.jpg)", img_url)  # Properly close the regex pattern
        if match:
            cleaned_images.append(match.group(1))
    return cleaned_images

def save_to_csv(products, filename="products_with_details.csv"):
    # Collect all possible keys from 'details' across all products
    all_details_keys = set()
    for product in products:
        if "table_data" in product:
            for row in product["table_data"]:
                if "details" in row and isinstance(row["details"], dict):
                    all_details_keys.update(row["details"].keys())

    # Prepare header row
    base_headers = [
        "Category",
        "Parent Product Name",
        "Description",
        "Images",
        "Product URL",
    ]
    # Replace "Item" with "SKU" in table headers
    table_headers = ["SKU", "type_size", "price_per_unit", "units_per_case"]
    detail_headers = sorted(all_details_keys)  # Sort for consistency
    headers = base_headers + table_headers + detail_headers

    # Write to CSV
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)  # Write header row

        for product in products:
            # Combine 'long_description' and 'product_information' into 'Description'
            combined_description = "\n".join(
                filter(None, [
                    clean_text(product.get("long_description", "")),
                    clean_text(product.get("product_information", "")),
                ])
            )

            # Base fields that stay constant for all variants
            base_row = [
                product.get("category", ""),
                clean_text(product.get("parent_name", "")),
                combined_description,
                "; ".join(clean_image_urls(product.get("images", []))),
                clean_text(product.get("url", "")),
            ]

            # Handle rows for each variant in table_data
            if "table_data" in product and isinstance(product["table_data"], list):
                for variant in product["table_data"]:
                    row = base_row.copy()
                    
                    # Clean type_size
                    type_size = clean_text(variant.get("type_size", ""))
                    
                    # Add variant-specific data
                    row.extend([
                        clean_text(variant.get("item", "")),
                        type_size,
                        clean_text(variant.get("price_per_unit", "")),
                        clean_text(variant.get("units_per_case", "")),
                    ])

                    # Add variant-specific details
                    variant_details = variant.get("details", {})
                    # Only include details that match this variant's type_size
                    for key in detail_headers:
                        detail_value = variant_details.get(key, "")
                        if key in ['Dimensions', 'Fill Weight', 'Shipping Carton', 'Shipping Carton Weight']:
                            # Extract only the relevant dimension for this variant
                            lines = detail_value.split('\n')
                            for line in lines:
                                if type_size.lower() in line.lower():
                                    detail_value = line.split('-', 1)[-1].strip()
                                    break
                        row.append(clean_text(detail_value))

                    writer.writerow(row)
            else:
                # If no variants, write a single row with empty variant fields
                row = base_row + [""] * (len(table_headers) + len(detail_headers))
                writer.writerow(row)

    print(f"Products saved to {filename}")

def insert_into_postgres(table_name, data):
    """
    Insert data into a PostgreSQL database table.

    Args:
        table_name (str): The name of the table to insert data into.
        data (list of dict): The data to insert, where each dict represents a row.

    Returns:
        None
    """
    try:
        # Connect to the database
        conn = psycopg2.connect(
            dbname=os.getenv('DB_NAME'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD'),
            host=os.getenv('DB_HOST'),
            port=os.getenv('DB_PORT')
        )
        cursor = conn.cursor()

        # Prepare the SQL statement dynamically
        if data:
            # Extract column names from the first row
            columns = data[0].keys()
            insert_query = sql.SQL(
                "INSERT INTO {table} ({fields}) VALUES ({placeholders})"
            ).format(
                table=sql.Identifier(table_name),
                fields=sql.SQL(", ").join(map(sql.Identifier, columns)),
                placeholders=sql.SQL(", ").join(sql.Placeholder() * len(columns))
            )

            # Execute the query for each row of data
            for row in data:
                cursor.execute(insert_query, list(row.values()))

            # Commit the transaction
            conn.commit()
            print(f"Inserted {len(data)} rows into {table_name}.")

    except Exception as e:
        print(f"Error inserting data into PostgreSQL: {e}")
    finally:
        if conn:
            cursor.close()
            conn.close()


def format_table_data(table_data):
    """Format the table_data list of dictionaries into a string for CSV."""
    formatted_data = []
    for row in table_data:
        formatted_data.append(
            f"Item: {clean_text(row.get('item', 'N/A'))}, Product Name: {clean_text(row.get('product_name', 'N/A'))}, "
            f"Price/Unit: {clean_text(row.get('price_per_unit', 'N/A'))}, Units/Case: {clean_text(row.get('units_per_case', 'N/A'))}"
        )
    return "; ".join(formatted_data)

def format_details(details):
    """Format the details dictionary into a string for CSV."""
    return "; ".join([f"{clean_text(key)}: {clean_text(value)}" for key, value in details.items()])

def clean_type_size(parent_name, type_size):
    """
    Clean type_size by removing parent_name and redundant information.
    Returns only the unique variant information.
    """
    if not isinstance(type_size, str) or not isinstance(parent_name, str):
        return type_size
    
    print(f"DEBUG: Cleaning type_size | Parent: '{parent_name}' | Original: '{type_size}'")
    # Remove parent name from type_size
    cleaned = type_size.replace(parent_name, '').strip()
    # Remove common separators
    cleaned = re.sub(r'^[-:,\s]+|[-:,\s]+$', '', cleaned)
    result = cleaned or type_size  # Return original if cleaning results in empty string
    print(f"DEBUG: Cleaned type_size result: '{result}'")
    return result

def parse_details_by_variant(details):
    """
    Parse the details section to map information to specific variants.
    Returns a dictionary mapping variant sizes to their specific details.
    """
    print(f"DEBUG: Parsing details for variants: {details}")
    variant_details = {}
    
    # Define fields that should be variant-specific
    variant_specific_fields = ['Dimensions', 'Fill Weight', 'Shipping Carton', 'Shipping Carton Weight']
    
    for key, value in details.items():
        if not isinstance(value, str):
            continue
            
        print(f"DEBUG: Processing detail | Key: '{key}' | Value: '{value}'")
        
        if key in variant_specific_fields:
            # Split on newlines for variant-specific fields
            lines = value.split('\n')
            for line in lines:
                # Try to extract size/variant and its corresponding value
                match = re.match(r'^(.*?(?:Standard|Queen|King|Twin|Full|Cal King))[\s-]+(.+)$', line.strip())
                if match:
                    variant, detail = match.groups()
                    variant = variant.strip()
                    detail = detail.strip()
                    print(f"DEBUG: Matched variant-specific detail: '{variant}' -> '{detail}' for {key}")
                    
                    if variant not in variant_details:
                        variant_details[variant] = {}
                    variant_details[variant][key] = detail
        else:
            # For non-variant-specific fields, apply to all variants
            print(f"DEBUG: Processing general detail: {key}")
            for variant in set(variant_details.keys()) | {'Standard', 'Queen', 'King'}:
                if variant not in variant_details:
                    variant_details[variant] = {}
                variant_details[variant][key] = value.strip()
    
    print(f"DEBUG: Final variant details mapping: {variant_details}")
    return variant_details

# Main Execution
try:
    # Step 1: Login
    login_to_site()

    # Step 2: Define the top-level categories and their URLs
    categories = [
        {"name": "Pillows", "url": "https://www.keecohospitality.com/pillows/"},  # Testing with just Pillows category
        # {"name": "Comforters", "url": "https://www.keecohospitality.com/comforters/"},
        # {"name": "Protectors", "url": "https://www.keecohospitality.com/protectors/"},
        # {"name": "Mattress Pads", "url": "https://www.keecohospitality.com/mattress-pads/"},
        # {"name": "Sheet Sets", "url": "https://www.keecohospitality.com/sheet-sets/"},
        # {"name": "Bath", "url": "https://www.keecohospitality.com/bath/"},
    ]

    # Step 3: Extract products from each category
    all_products = []
    for category in categories:
        products = extract_products_from_category(category["name"], category["url"])
        all_products.extend(products)

    # Step 4: Save all products to a CSV file
    save_to_csv(all_products)

except Exception as e:
    print(f"An error occurred: {e}")
    driver.save_screenshot("error_screenshot.png")
finally:
    driver.quit()
