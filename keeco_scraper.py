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

if not keeco_username or not keeco_password:
    print("Error: KEECO_USERNAME and KEECO_PASSWORD environment variables must be set.")
    sys.exit(1)

# Initialize Chrome options with debugging
chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
print(f"Using Chrome from: {chrome_path}")

chrome_options = uc.ChromeOptions()
chrome_options.add_argument("--headless=new")
chrome_options.add_argument("--window-size=1920,1080")
chrome_options.binary_location = chrome_path

# Initialize WebDriver with options and error handling
try:
    print("Starting undetected-chromedriver...")
    driver = uc.Chrome(
        options=chrome_options,
        version_main=133  # Chrome version 133.0.6943.53
    )
    print("WebDriver initialized successfully")
    
except Exception as e:
    print(f"Failed to initialize WebDriver: {str(e)}")
    print(f"Chrome path exists: {os.path.exists(chrome_path)}")
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

def extract_variant_size(product_name, parent_name):
    """
    Extract and standardize the variant-specific size/type from the product name
    by removing parent name and standardizing common size patterns.
    """
    if not product_name or not parent_name:
        return ""
        
    # Remove parent name and any leading/trailing delimiters
    variant = product_name.replace(parent_name, "").strip(" -,")
    
    # If nothing left after removing parent name, return original product name
    if not variant:
        return product_name
        
    # Standardize common size patterns
    # Convert variations of King, Queen, etc. to standard format
    size_mappings = {
        r'\bKING\b': 'King',
        r'\bQUEEN\b': 'Queen',
        r'\bFULL\b': 'Full',
        r'\bTWIN\b': 'Twin',
        r'\bTWIN XL\b': 'Twin XL',
        r'\bSTANDARD\b': 'Standard',
        r'\bJUMBO\b': 'Jumbo'
    }
    
    # Apply size standardization
    variant_upper = variant.upper()
    for pattern, replacement in size_mappings.items():
        if re.search(pattern, variant_upper):
            variant = re.sub(pattern, replacement, variant_upper, flags=re.IGNORECASE)
            
    # Remove any double spaces and standardize separators
    variant = re.sub(r'\s+', ' ', variant)
    variant = re.sub(r'\s*-\s*', '-', variant)
    
    return variant.strip()

def parse_dimensions(dimension_str):
    """Parse dimension string to extract size-specific dimensions."""
    if not dimension_str:
        return {}
    # Split by common delimiters
    parts = re.split(r'[,.]', dimension_str)
    size_dimensions = {}
    
    for part in parts:
        # Look for size pattern followed by dimensions
        match = re.match(r'(.*?)\s*-\s*([^-]+)$', part.strip())
        if match:
            size, dims = match.groups()
            size_dimensions[size.strip()] = dims.strip()
    return size_dimensions

# Function to scrape product details from the product page
def scrape_product_page(product_url):
    driver.get(product_url)
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "#product-content"))
        )

        product_data = {"url": product_url}

        # Extract parent product name
        try:
            parent_product_name = driver.find_element(By.CSS_SELECTOR, "#product-content > h1 > div.product-name").text.strip()
            product_data["parent_name"] = parent_product_name
        except Exception:
            product_data["parent_name"] = "N/A"

        # Extract other basic information
        try:
            long_description = driver.find_element(By.CSS_SELECTOR, "#product-content > div.product-long-description").text.strip()
            product_data["long_description"] = long_description
        except Exception:
            product_data["long_description"] = "N/A"

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

        # Extract details section first to map variant-specific details
        try:
            detail_section = driver.find_element(By.CSS_SELECTOR, "#detail")
            details = {}
            keys = detail_section.find_elements(By.CSS_SELECTOR, ".col-1")
            values = detail_section.find_elements(By.CSS_SELECTOR, ".col-2")
            
            for key, value in zip(keys, values):
                key_text = key.text.strip()
                value_text = value.text.strip()
                details[key_text] = value_text
                
                # Parse dimensions and other size-specific details
                if key_text == "Dimensions":
                    details["dimensions_by_size"] = parse_dimensions(value_text)
                elif key_text == "Fill Weight":
                    details["weights_by_size"] = parse_dimensions(value_text)

            product_data["details"] = details
        except Exception as e:
            product_data["details"] = {}
            print(f"DEBUG: Failed to extract details: {e}")

        # Extract and process table data
        try:
            table_container = driver.find_element(By.CSS_SELECTOR, ".order-table")
            table_headers = table_container.find_elements(By.TAG_NAME, "th")
            header_mapping = [header.text.strip() for header in table_headers]
            
            table_rows = table_container.find_elements(By.TAG_NAME, "tr")
            table_data = []
            
            for row in table_rows[1:]:  # Skip header row
                cols = row.find_elements(By.TAG_NAME, "td")
                if len(cols) == len(header_mapping):
                    row_data = {}
                    for idx, header in enumerate(header_mapping):
                        cell_text = cols[idx].text.strip()
                        if header == "Product Name":
                            # Extract only the variant-specific part
                            row_data["type_size"] = extract_variant_size(cell_text, product_data["parent_name"])
                        else:
                            row_data[header.lower().replace("/", "_per_")] = cell_text
                    
                    # Map corresponding details for this variant
                    variant_size = row_data["type_size"]
                    if "dimensions_by_size" in product_data["details"]:
                        for size, dims in product_data["details"]["dimensions_by_size"].items():
                            if size.lower() in variant_size.lower():
                                row_data["dimensions"] = dims
                                break
                    
                    if "weights_by_size" in product_data["details"]:
                        for size, weight in product_data["details"]["weights_by_size"].items():
                            if size.lower() in variant_size.lower():
                                row_data["fill_weight"] = weight
                                break
                    
                    table_data.append(row_data)
            
            product_data["table_data"] = table_data
        except Exception as e:
            product_data["table_data"] = []
            print(f"DEBUG: Failed to extract table data: {e}")

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
        if "details" in product and isinstance(product["details"], dict):
            all_details_keys.update(product["details"].keys())

    # Collect all possible keys from 'table_data' across all products
    all_table_keys = set()
    for product in products:
        if "table_data" in product and isinstance(product["table_data"], list):
            for table_row in product["table_data"]:
                all_table_keys.update(table_row.keys())

    # Prepare header row
    base_headers = [
        "Category",
        "Parent Product Name",  # New column for the parent product name
        "Description",  # Combined column
        "Images",
        "Product URL",
    ]
    # Replace "Item" with "SKU" in table headers
    table_headers = [
        f"SKU" if key == "item" else f"{key}" for key in sorted(all_table_keys)
    ]
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

            # Handle rows for each `table_data` entry
            if "table_data" in product and isinstance(product["table_data"], list) and product["table_data"]:
                for table_row in product["table_data"]:
                    # Base fields
                    row = [
                        product.get("category", ""),
                        clean_text(product.get("parent_name", "")),  # Parent product name
                        combined_description,  # Use the combined description
                        "; ".join(clean_image_urls(product.get("images", []))),  # Clean image URLs
                        clean_text(product.get("url", "")),
                    ]

                    # Add table_data columns
                    row += [
                        clean_text(table_row.get("item", "")) if key == "item" else clean_text(table_row.get(key, ""))
                        for key in sorted(all_table_keys)
                    ]

                    # Add details columns
                    row += [clean_text(product.get("details", {}).get(key, "")) for key in detail_headers]

                    writer.writerow(row)  # Write the row
            else:
                # If no table_data, write a single row with empty table_data columns
                row = [
                    product.get("category", ""),
                    clean_text(product.get("parent_name", "")),  # Parent product name
                    combined_description,
                    "; ".join(clean_image_urls(product.get("images", []))),
                    clean_text(product.get("url", "")),
                ]

                # Add empty table_data columns
                row += ["" for _ in sorted(all_table_keys)]

                # Add details columns
                row += [clean_text(product.get("details", {}).get(key, "")) for key in detail_headers]

                writer.writerow(row)  # Write the row

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





# Main Execution
try:
    # Step 1: Login
    login_to_site()

    # Step 2: Define the top-level categories and their URLs
    categories = [
        {"name": "Pillows", "url": "https://www.keecohospitality.com/pillows/"},
        {"name": "Comforters", "url": "https://www.keecohospitality.com/comforters/"},
        {"name": "Protectors", "url": "https://www.keecohospitality.com/protectors/"},
        {"name": "Mattress Pads", "url": "https://www.keecohospitality.com/mattress-pads/"},
        {"name": "Sheet Sets", "url": "https://www.keecohospitality.com/sheet-sets/"},
        {"name": "Bath", "url": "https://www.keecohospitality.com/bath/"},
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
