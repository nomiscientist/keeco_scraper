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
from selenium.webdriver.chrome.service import Service
from selenium import webdriver
from webdriver_manager.chrome import ChromeDriverManager
import unicodedata
from ftfy import fix_text

def init_driver():
    """Initialize and return the Chrome WebDriver."""
    print("Initializing Chrome WebDriver...")
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service)
        print("Chrome WebDriver initialized successfully")
        return driver
    except Exception as e:
        print(f"Error initializing Chrome WebDriver: {str(e)}")
        sys.exit(1)

def init_environment():
    """Initialize and validate environment variables."""
    print("\nLoading environment variables...")
    try:
        # Load environment variables from .env file
        if not load_dotenv():
            print("Error: .env file not found. Please create one using the template.")
            sys.exit(1)

        # Required environment variables
        required_vars = {
            'KEECO_USERNAME': 'Keeco login username/email',
            'KEECO_PASSWORD': 'Keeco login password',
            'DB_NAME': 'Database name',
            'DB_USER': 'Database user',
            'DB_PASSWORD': 'Database password',
            'DB_HOST': 'Database host',
            'DB_PORT': 'Database port'
        }

        # Check for missing environment variables
        missing_vars = []
        env_vars = {}
        
        for var, description in required_vars.items():
            value = os.getenv(var)
            if not value:
                missing_vars.append(f"{var} ({description})")
            else:
                env_vars[var] = value

        if missing_vars:
            print("Error: The following environment variables are missing:")
            for var in missing_vars:
                print(f"- {var}")
            print("\nPlease set these variables in your .env file.")
            sys.exit(1)

        print("Environment variables loaded successfully")
        return env_vars
        
    except Exception as e:
        print(f"Error loading environment: {str(e)}")
        sys.exit(1)

def login_to_site(driver, env):
    """Log in to the Keeco website."""
    try:
        print("\nNavigating to login page...")
        driver.get("https://www.keecohospitality.com/home/FMI")
        
        print("Waiting for login form...")
        email_field = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='text'][placeholder='email address']"))
        )
        password_field = driver.find_element(By.CSS_SELECTOR, "input[type='password'][placeholder='password']")
        
        print("Entering credentials...")
        email_field.send_keys(env['KEECO_USERNAME'])
        password_field.send_keys(env['KEECO_PASSWORD'])
        
        print("Clicking sign in button...")
        sign_in_button = driver.find_element(By.CSS_SELECTOR, "button.sign-in-button")
        sign_in_button.click()

        print("Waiting for login confirmation...")
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "#header > div.content > div.customer-info"))
        )
        print("Login successful!")
    except Exception as e:
        print(f"Error during login: {str(e)}")
        driver.quit()
        sys.exit(1)

def extract_variant_info(parent_name, full_variant_name):
    """
    Extract only the type or size information from the variant name, removing product names and other redundant information.
    
    Args:
        parent_name (str): The parent product name
        full_variant_name (str): The full variant name including parent name
    
    Returns:
        str: The unique type or size information
    """
    if not full_variant_name or not parent_name:
        return full_variant_name
    
    # Clean and normalize both strings
    parent_clean = clean_text(parent_name).lower()
    variant_clean = clean_text(full_variant_name).lower()
    
    # Split parent name into words to remove each part
    parent_parts = parent_clean.split()
    for part in parent_parts:
        if part and len(part) > 2:  # Only remove parts longer than 2 chars to avoid removing size indicators
            variant_clean = variant_clean.replace(part, '')
    
    # Remove dimensions patterns
    dimension_patterns = [
        r'\d+"\s*[xX]\s*\d+"',  # e.g., 22" x 22"
        r'\d+\s*[xX]\s*\d+\s*(?:inch|inches)?',  # e.g., 22 x 22 inches
        r'\d+["\']?\s*[xX]\s*\d+["\']?(?:\s*-\s*\d+\s*oz\.?)?',  # e.g., 22" X 22" - 27 oz
        r'single pack\s*-?\s*\d+["\']?\s*[xX]\s*\d+["\']?',  # e.g., Single Pack - 22" X 22"
        r'double pack\s*-?\s*\d+["\']?\s*[xX]\s*\d+["\']?',  # e.g., Double Pack - 22" X 22"
    ]
    
    for pattern in dimension_patterns:
        variant_clean = re.sub(pattern, '', variant_clean, flags=re.IGNORECASE)
    
    # Remove common product type indicators and their variations
    product_indicators = [
        r'pillow\s*(?:case|protector|sham)?s?',
        r'comforter\s*(?:set)?s?',
        r'mattress\s*(?:pad|protector|cover|topper)?s?',
        r'sheet\s*(?:set)?s?',
        r'duvet\s*(?:cover|set)?s?',
        r'bed\s*(?:spread|cover|skirt)?s?',
        r'towel\s*(?:set)?s?',
        r'protect\s*-?\s*a\s*-?\s*bed',
        r'classic',
        r'premium',
        r'luxury',
        r'signature',
        r'collection',
        r'series'
    ]
    
    for indicator in product_indicators:
        variant_clean = re.sub(indicator, '', variant_clean, flags=re.IGNORECASE)
    
    # Clean up common prefixes/suffixes
    cleanup_patterns = [
        r'^(?:size|pack)\s*[-:]\s*',  # Remove "Size -" or "Pack -" prefix
        r'\s*[-:]\s*(?:size|pack)$',  # Remove "- Size" or "- Pack" suffix
        r'^(?:single|double)\s+pack\s*[-:]\s*',  # Remove "Single Pack -" prefix
        r'\s*[-:]\s*(?:single|double)\s+pack$',  # Remove "- Single Pack" suffix
        r'^\s*[-–—]\s*',  # Remove leading dashes
        r'\s*[-–—]\s*$',  # Remove trailing dashes
        r'^\s*[,;]\s*',  # Remove leading separators
        r'\s*[,;]\s*$',  # Remove trailing separators
    ]
    
    for pattern in cleanup_patterns:
        variant_clean = re.sub(pattern, '', variant_clean, flags=re.IGNORECASE)
    
    # Clean up multiple spaces, dashes, and other separators
    variant_clean = re.sub(r'\s+', ' ', variant_clean)  # Replace multiple spaces with single space
    variant_clean = re.sub(r'[-\s]*$', '', variant_clean)  # Remove trailing dashes and spaces
    variant_clean = re.sub(r'^[-\s]*', '', variant_clean)  # Remove leading dashes and spaces
    
    # If after all cleaning we have nothing left or only have numbers, return a default value
    cleaned = variant_clean.strip()
    if not cleaned or cleaned.isdigit():
        return "Standard"
    
    return cleaned.strip().title()

def parse_dimensions_string(dimensions_str):
    """
    Parse a dimensions string to extract size-specific information.
    
    Args:
        dimensions_str (str): String containing dimension information
        
    Returns:
        dict: Dictionary mapping sizes to their dimensions
    """
    if not dimensions_str:
        return {}
    
    dimensions_map = {}
    # Split by common separators
    parts = re.split(r'[,;]\s*', dimensions_str)
    
    for part in parts:
        # Try to match size and dimensions
        # Pattern matches: "Size - dimensions" or just "dimensions"
        match = re.match(r'(?:([^-]+?)\s*-\s*)?(\d+["\']?\s*[xX]\s*\d+["\']?(?:\s*-\s*\d+\s*oz\.?)?)', part.strip())
        if match:
            size, dims = match.groups()
            if size:
                dimensions_map[size.strip()] = dims.strip()
            else:
                dimensions_map['default'] = dims.strip()
                
    return dimensions_map

def match_variant_details(variant_size, details):
    """
    Match variant-specific details from the details section.
    
    Args:
        variant_size (str): The variant size/type
        details (dict): The full details dictionary
        
    Returns:
        dict: Matched details for the specific variant
    """
    matched_details = {}
    
    if not details:
        return matched_details
        
    # Clean and normalize variant size
    variant_size = clean_text(variant_size).lower() if variant_size else ""
    
    for key, value in details.items():
        key = clean_text(key)
        value = clean_text(value)
        
        if key == "Dimensions":
            dims_map = parse_dimensions_string(value)
            
            # First try: exact match with variant size
            dimension_found = False
            if variant_size:
                for size_key, dims in dims_map.items():
                    size_key_clean = clean_text(size_key).lower() if size_key else ""
                    if size_key_clean and (size_key_clean in variant_size or variant_size in size_key_clean):
                        matched_details[key] = dims
                        dimension_found = True
                        break
            
            # Second try: if no match found and there's only one dimension, use it
            if not dimension_found and len(dims_map) == 1:
                matched_details[key] = next(iter(dims_map.values()))
            
            # Third try: use default dimension if available
            elif not dimension_found and "default" in dims_map:
                matched_details[key] = dims_map["default"]
            
            # Fourth try: if still no match and we have dimensions without size keys, use the first one
            elif not dimension_found and dims_map:
                matched_details[key] = next(iter(dims_map.values()))
            
            # If still no dimensions found, try to extract from the value directly
            if key not in matched_details:
                # Try to find any dimension pattern in the value
                dimension_patterns = [
                    r'\d+["\']?\s*[xX]\s*\d+["\']?(?:\s*-\s*\d+\s*oz\.?)?',
                    r'\d+\s*(?:inch|inches|in)\s*[xX]\s*\d+\s*(?:inch|inches|in)',
                    r'\d+["\']?\s*by\s*\d+["\']?'
                ]
                for pattern in dimension_patterns:
                    match = re.search(pattern, value, re.IGNORECASE)
                    if match:
                        matched_details[key] = match.group(0)
                        break
        
        elif key in ["Fill Weight", "Shipping Carton", "Shipping Carton Weight"]:
            # Try to find variant-specific information
            parts = re.split(r'[,;]\s*', value)
            value_found = False
            
            # First try: match with variant size
            if variant_size:
                for part in parts:
                    if variant_size in clean_text(part).lower():
                        matched_details[key] = part.strip()
                        value_found = True
                        break
            
            # Second try: if no match found and there's only one part, use it
            if not value_found and len(parts) == 1:
                matched_details[key] = parts[0].strip()
            
            # Third try: if multiple parts but no match, use the first relevant part
            elif not value_found and parts:
                matched_details[key] = parts[0].strip()
        
        else:
            # For non-variant-specific details, keep as is
            matched_details[key] = value
            
    return matched_details

def scrape_product_page(driver, product_url):
    """Scrape details from a product page."""
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

        # Extract dynamic specs (Details) first
        try:
            detail_section = driver.find_element(By.CSS_SELECTOR, "#detail")
            keys = detail_section.find_elements(By.CSS_SELECTOR, ".col-1")
            values = detail_section.find_elements(By.CSS_SELECTOR, ".col-2")

            # Map keys to values dynamically
            details = {}
            for key, value in zip(keys, values):
                details[key.text.strip()] = value.text.strip()
            product_data["details"] = details
        except Exception as e:
            product_data["details"] = {}
            print(f"DEBUG: Failed to extract details: {e}")

        # Extract table data
        try:
            table_container = driver.find_element(By.CSS_SELECTOR, ".order-table")
            table_headers = table_container.find_elements(By.TAG_NAME, "th")
            header_mapping = [header.text.strip() for header in table_headers]
            
            table_rows = table_container.find_elements(By.TAG_NAME, "tr")
            table_data = []
            
            for row in table_rows[1:]:
                cols = row.find_elements(By.TAG_NAME, "td")
                if len(cols) == len(header_mapping):
                    full_variant_name = cols[header_mapping.index("Product Name")].text.strip() if "Product Name" in header_mapping else ""
                    variant_type = extract_variant_info(product_data["parent_name"], full_variant_name)
                    variant_details = match_variant_details(variant_type, product_data["details"])
                    
                    row_data = {
                        "item": cols[header_mapping.index("Item")].text.strip() if "Item" in header_mapping else "",
                        "type_size": variant_type,
                        "price_per_unit": cols[header_mapping.index("Price/Unit")].text.strip() if "Price/Unit" in header_mapping else "",
                        "units_per_case": cols[header_mapping.index("Unit/Case")].text.strip() if "Unit/Case" in header_mapping else "",
                        "variant_details": variant_details
                    }
                    table_data.append(row_data)
            
            product_data["table_data"] = table_data
        except Exception as e:
            product_data["table_data"] = []
            print(f"DEBUG: Failed to extract table data: {e}")

        return product_data

    except Exception as e:
        print(f"Error scraping product page: {e}")
        return {"url": product_url, "error": str(e)}

def extract_products_from_category(category_name, category_url, driver, batch_size=10):
    """Extract products from a category and save in batches of 10."""
    current_batch = []
    all_products = []
    batch_number = 1
    error_count = 0
    
    print(f"\n{'='*50}")
    print(f"Starting extraction from category: {category_name}")
    print(f"Category URL: {category_url}")
    print(f"{'='*50}\n")

    try:
        driver.get(category_url)
        while True:
            try:
                print(f"\nProcessing page for category: {category_name}")
                # Wait for the product grid to load
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.ID, "search-result-items"))
                )

                # Extract product links from the grid
                product_grid = driver.find_element(By.ID, "search-result-items")
                product_elements = product_grid.find_elements(By.CSS_SELECTOR, ".product-tile a")
                print(f"Found {len(product_elements)} product elements on the page")

                # Extract links and remove duplicates
                product_links = list(set([element.get_attribute("href") for element in product_elements]))
                print(f"Unique product links found: {len(product_links)}")

                # Click and scrape each product
                for index, product_link in enumerate(product_links, 1):
                    try:
                        if product_link:
                            print(f"\nProcessing product {index}/{len(product_links)}")
                            print(f"URL: {product_link}")
                            product_details = scrape_product_page(driver, product_link)
                            
                            if "error" in product_details:
                                error_count += 1
                                print(f"Error scraping product: {product_details['error']}")
                                continue
                                
                            product_details["category"] = category_name
                            all_products.append(product_details)
                            
                            # Add to current batch
                            current_batch.append(product_details)
                            print(f"Successfully scraped product: {product_details.get('parent_name', 'Unknown')}")
                            
                            # Save batch if it reaches the batch size
                            if len(current_batch) >= batch_size:
                                print(f"\nSaving batch {batch_number} with {len(current_batch)} records...")
                                save_to_csv(current_batch, f"products_batch_{batch_number}")
                                print(f"Batch {batch_number} saved successfully")
                                current_batch = []
                                batch_number += 1
                                
                        else:
                            error_count += 1
                            print("Skipped empty product link")
                    except Exception as e:
                        error_count += 1
                        print(f"Error processing product link: {str(e)}")
                        continue

                # Check for next page
                try:
                    next_button = driver.find_element(By.CSS_SELECTOR, ".pagination .next")
                    if "disabled" in next_button.get_attribute("class"):
                        print("\nReached last page of category")
                        break
                    print("\nMoving to next page...")
                    next_button.click()
                    WebDriverWait(driver, 10).until(EC.staleness_of(product_grid))
                except Exception as e:
                    print(f"No more pages or error navigating: {str(e)}")
                    break

            except Exception as e:
                error_count += 1
                print(f"Error loading category page: {str(e)}")
                break

    finally:
        # Save any remaining records in the last batch
        if current_batch:
            print(f"\nSaving final batch {batch_number} with {len(current_batch)} records...")
            save_to_csv(current_batch, f"products_batch_{batch_number}")
            print(f"Final batch saved successfully")

        print(f"\n{'='*50}")
        print(f"Category Summary - {category_name}")
        print(f"Total products scraped: {len(all_products)}")
        print(f"Total batches saved: {batch_number}")
        print(f"Total errors encountered: {error_count}")
        print(f"{'='*50}\n")

    return all_products

def save_to_csv(products, filename="keeco_products.csv"):
    """Save all products to a single CSV file with proper error handling and data validation."""
    # Ensure filename has .csv extension
    if not filename.lower().endswith('.csv'):
        filename = filename + '.csv'

    print(f"\n{'='*50}")
    print("Starting CSV Generation Process")
    print(f"{'='*50}\n")
    
    # Initialize counters and error log
    error_log = []
    processed_count = 0
    skipped_count = 0
    
    print("Phase 1: Collecting and validating product data")
    # Collect all possible keys from variant_details across all products
    all_variant_detail_keys = set()
    valid_products = []
    
    # First pass: collect all valid keys and validate product data
    for index, product in enumerate(products, 1):
        try:
            print(f"\nValidating product {index}/{len(products)}")
            
            if not isinstance(product, dict):
                error_msg = f"Invalid product format: {product}"
                print(f"Error: {error_msg}")
                error_log.append(error_msg)
                skipped_count += 1
                continue
                
            if "error" in product:
                error_msg = f"Product error: {product['error']} for URL: {product.get('url', 'unknown')}"
                print(f"Error: {error_msg}")
                error_log.append(error_msg)
                skipped_count += 1
                continue
                
            if "table_data" in product and isinstance(product["table_data"], list):
                variant_count = 0
                for table_row in product["table_data"]:
                    if isinstance(table_row, dict) and "variant_details" in table_row:
                        if isinstance(table_row["variant_details"], dict):
                            all_variant_detail_keys.update(table_row["variant_details"].keys())
                            variant_count += 1
                valid_products.append(product)
                print(f"Valid product found: {product.get('parent_name', 'Unknown')} with {variant_count} variants")
            else:
                error_msg = f"Invalid table_data for product: {product.get('url', 'unknown')}"
                print(f"Error: {error_msg}")
                error_log.append(error_msg)
                skipped_count += 1
                
        except Exception as e:
            error_msg = f"Error processing product {product.get('url', 'unknown')}: {str(e)}"
            print(f"Error: {error_msg}")
            error_log.append(error_msg)
            skipped_count += 1
    
    print("\nPhase 2: Generating CSV file")
    # Prepare header row
    base_headers = [
        "Category",
        "Parent Product Name",
        "Description",
        "Images",
        "Product URL",
        "SKU",
        "Type/Size",
        "Price/Unit",
        "Units/Case"
    ]
    variant_detail_headers = sorted(all_variant_detail_keys)
    headers = base_headers + variant_detail_headers
    
    print(f"Headers prepared: {len(headers)} columns")
    
    # Sort valid products by category
    valid_products.sort(key=lambda x: x.get('category', ''))
    
    # Write to CSV
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        
        current_category = None
        
        # Process products category by category
        for product in valid_products:
            try:
                category = product.get('category', '')
                if category != current_category:
                    print(f"\nProcessing category: {category}")
                    current_category = category
                
                print(f"Processing product: {product.get('parent_name', 'Unknown')}")
                
                # Combine and clean description fields
                description_parts = []
                if product.get("long_description"):
                    description_parts.append(clean_text(product["long_description"]))
                if product.get("product_information"):
                    description_parts.append(clean_text(product["product_information"]))
                combined_description = "\n".join(filter(None, description_parts))
                
                # Clean and validate image URLs
                image_urls = []
                if product.get("images"):
                    image_urls = clean_image_urls(product["images"])
                image_string = "; ".join(image_urls) if image_urls else ""
                
                # Process each table row
                if "table_data" in product and isinstance(product["table_data"], list):
                    for row_index, table_row in enumerate(product["table_data"], 1):
                        try:
                            # Validate required fields
                            if not all(key in table_row for key in ["item", "type_size"]):
                                error_msg = f"Missing required fields in table row for product: {product.get('url', 'unknown')}"
                                print(f"Error: {error_msg}")
                                error_log.append(error_msg)
                                continue
                            
                            # Base fields with proper error handling
                            row = [
                                clean_text(category),
                                clean_text(product.get("parent_name", "")),
                                combined_description,
                                image_string,
                                clean_text(product.get("url", "")),
                                clean_text(table_row.get("item", "")),
                                clean_text(table_row.get("type_size", "")),
                                clean_text(table_row.get("price_per_unit", "")),
                                clean_text(table_row.get("units_per_case", ""))
                            ]
                            
                            # Add variant-specific details with validation
                            variant_details = table_row.get("variant_details", {})
                            if isinstance(variant_details, dict):
                                row.extend(clean_text(variant_details.get(key, "")) for key in variant_detail_headers)
                                writer.writerow(row)
                                processed_count += 1
                                print(f"Successfully processed variant: {table_row.get('type_size', 'Unknown')}")
                            else:
                                error_msg = f"Invalid variant details format for product: {product.get('url', 'unknown')}"
                                print(f"Error: {error_msg}")
                                error_log.append(error_msg)
                                
                        except Exception as e:
                            error_msg = f"Error processing table row for product {product.get('url', 'unknown')}: {str(e)}"
                            print(f"Error: {error_msg}")
                            error_log.append(error_msg)
                            continue
                            
            except Exception as e:
                error_msg = f"Error processing product {product.get('url', 'unknown')}: {str(e)}"
                print(f"Error: {error_msg}")
                error_log.append(error_msg)
                continue
    
    # Save error log
    error_log_filename = "scraping_errors.txt"
    save_error_log(error_log, error_log_filename)
    
    print(f"\n{'='*50}")
    print("Processing Summary")
    print(f"{'='*50}")
    print(f"Total products processed: {processed_count}")
    print(f"Total products skipped: {skipped_count}")
    print(f"Total errors logged: {len(error_log)}")
    print(f"Files generated:")
    print(f"- CSV file: {filename}")
    print(f"- Error log: {error_log_filename}")
    print(f"{'='*50}\n")

def save_error_log(error_log, filename):
    """Save error messages to a text file."""
    with open(filename, "w", encoding="utf-8") as f:
        f.write("Error Log:\n")
        f.write("==========\n\n")
        for i, error in enumerate(error_log, 1):
            f.write(f"{i}. {error}\n")

def clean_text(text):
    """Clean up text by fixing encoding issues and normalizing."""
    if not isinstance(text, str):
        return "" if text is None else str(text)
    try:
        text = fix_text(text)  # Fix text encoding issues
        text = unicodedata.normalize("NFKC", text)  # Normalize Unicode
        text = text.replace("\u00a0", " ")  # Replace non-breaking spaces
        text = re.sub(r"[®™©]", "", text)  # Remove trademark and registered symbols
        text = text.replace("â€", "-")  # Replace specific encoding issue with dash
        return text.strip()  # Trim leading/trailing whitespace
    except Exception:
        return ""

def clean_image_urls(images):
    """Clean up image URLs by removing anything after .jpg and validating URLs."""
    if not isinstance(images, (list, tuple)):
        return []
        
    cleaned_images = []
    for img_url in images:
        try:
            if not isinstance(img_url, str):
                continue
            # Match common image extensions
            match = re.match(r"(.*?\.(?:jpg|jpeg|png|gif|webp))", img_url, re.IGNORECASE)
            if match:
                cleaned_url = match.group(1)
                # Basic URL validation
                if cleaned_url.startswith(('http://', 'https://')):
                    cleaned_images.append(cleaned_url)
        except Exception:
            continue
    return cleaned_images

def insert_into_postgres(table_name, data):
    """
    Insert data into a PostgreSQL database table.

    Args:
        table_name (str): The name of the table to insert data into.
        data (list of dict): The data to insert, where each dict represents a row.

    Returns:
        None
    """
    conn = None
    try:
        # Connect to the database using environment variables
        conn = psycopg2.connect(
            dbname=env['DB_NAME'],
            user=env['DB_USER'],
            password=env['DB_PASSWORD'],
            host=env['DB_HOST'],
            port=env['DB_PORT']
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
            print(f"Successfully inserted {len(data)} rows into {table_name}.")

    except psycopg2.Error as e:
        print(f"Database error: {e}")
        if conn:
            conn.rollback()
    except Exception as e:
        print(f"Error inserting data into PostgreSQL: {e}")
        if conn:
            conn.rollback()
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
if __name__ == "__main__":
    try:
        print("\n" + "="*50)
        print("Starting Keeco Scraper")
        print("="*50 + "\n")

        # Step 1: Initialize environment and driver
        env = init_environment()
        driver = init_driver()

        # Step 2: Login using environment variables
        print("\nAttempting login...")
        login_to_site(driver, env)

        # Step 3: Define the top-level categories and their URLs
        categories = [
            {"name": "Pillows", "url": "https://www.keecohospitality.com/pillows/"},
            {"name": "Comforters", "url": "https://www.keecohospitality.com/comforters/"},
            {"name": "Protectors", "url": "https://www.keecohospitality.com/protectors/"},
            {"name": "Mattress Pads", "url": "https://www.keecohospitality.com/mattress-pads/"},
            {"name": "Sheet Sets", "url": "https://www.keecohospitality.com/sheet-sets/"},
            {"name": "Bath", "url": "https://www.keecohospitality.com/bath/"},
        ]

        # Step 4: Extract products from each category
        print("\nStarting product extraction...")
        all_products = []
        for category in categories:
            products = extract_products_from_category(category["name"], category["url"], driver)
            all_products.extend(products)

        # Step 5: Save final consolidated CSV
        print("\nSaving consolidated product data...")
        save_to_csv(all_products, "keeco_products.csv")

    except Exception as e:
        print(f"\nA critical error occurred: {str(e)}")
        try:
            driver.save_screenshot("error_screenshot.png")
            print("Error screenshot saved as 'error_screenshot.png'")
        except:
            print("Could not save error screenshot")
    finally:
        try:
            if 'driver' in locals():
                print("\nClosing Chrome WebDriver...")
                driver.quit()
                print("Chrome WebDriver closed successfully")
        except:
            print("Error closing Chrome WebDriver")
        
        print("\n" + "="*50)
        print("Scraper Execution Completed")
        print("="*50 + "\n")
