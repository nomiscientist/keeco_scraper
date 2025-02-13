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
from selenium.webdriver.common.keys import Keys
import undetected_chromedriver as uc
import unicodedata
from ftfy import fix_text
import time

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
            product_data["parent_name"] = clean_text(parent_product_name)
        except Exception:
            product_data["parent_name"] = ""

        # Extract long description
        try:
            long_description = driver.find_element(By.CSS_SELECTOR, "#product-content > div.product-long-description").text.strip()
            product_data["long_description"] = clean_text(long_description)
        except Exception:
            product_data["long_description"] = ""

        # Extract images
        try:
            image_container = driver.find_element(By.CSS_SELECTOR, "#product-content > div.product-image-container.mobile-show")
            images = image_container.find_elements(By.TAG_NAME, "img")
            product_data["images"] = [img.get_attribute("src") for img in images]
        except Exception:
            product_data["images"] = []

        # Extract table data with enhanced cleaning
        try:
            table_container = driver.find_element(By.CSS_SELECTOR, ".order-table")
            table_headers = table_container.find_elements(By.TAG_NAME, "th")
            header_mapping = [clean_text(header.text.strip()) for header in table_headers]
            
            table_rows = table_container.find_elements(By.TAG_NAME, "tr")
            table_data = []
            
            for row in table_rows[1:]:
                cols = row.find_elements(By.TAG_NAME, "td")
                if len(cols) == len(header_mapping):
                    variant_data = {
                        "item": clean_text(cols[header_mapping.index("Item")].text.strip()) if "Item" in header_mapping else "",
                        "type_size": clean_type_size(
                            product_data.get("parent_name", ""),
                            cols[header_mapping.index("Product Name")].text.strip()
                        ) if "Product Name" in header_mapping else "",
                        "price_per_unit": cols[header_mapping.index("Price/Unit")].text.strip() if "Price/Unit" in header_mapping else "",
                        "units_per_case": standardize_case_info(cols[header_mapping.index("Unit/Case")].text.strip()) if "Unit/Case" in header_mapping else "",
                    }
                    table_data.append(variant_data)
            
            product_data["table_data"] = table_data
        except Exception as e:
            product_data["table_data"] = []
            print(f"DEBUG: Failed to extract table data: {e}")

        # Extract and process details with size-specific handling
        try:
            detail_section = driver.find_element(By.CSS_SELECTOR, "#detail")
            keys = detail_section.find_elements(By.CSS_SELECTOR, ".col-1")
            values = detail_section.find_elements(By.CSS_SELECTOR, ".col-2")

            raw_details = {}
            for key, value in zip(keys, values):
                key_text = clean_text(key.text.strip())
                value_text = clean_text(value.text.strip())
                raw_details[key_text] = value_text
            
            # Parse details by variant and apply enhanced cleaning
            variant_details = parse_details_by_variant(raw_details)
            
            # Update table_data with cleaned and merged details
            for row in product_data["table_data"]:
                type_size = row["type_size"]
                matched_details = None
                
                # Find matching variant details
                for variant, details in variant_details.items():
                    if type_size.lower() in variant.lower() or variant.lower() in type_size.lower():
                        matched_details = details
                        break
                
                if not matched_details:
                    matched_details = raw_details
                
                # Clean and merge dimensions and weights
                dimensions = clean_dimensions(
                    matched_details.get("Dimensions", ""),
                    matched_details.get("Shipping Carton", "")
                )
                
                fill_weight = merge_fill_weights(
                    matched_details.get("Fill Weight", ""),
                    matched_details.get("Additional Fill Weight", "")
                )
                
                row["details"] = {
                    "Dimensions": dimensions,
                    "Fill Weight": fill_weight,
                    "Care": clean_text(matched_details.get("Care", "")),
                    "Design": clean_text(matched_details.get("Design", "")),
                    "Fabric": clean_text(matched_details.get("Fabric", "")),
                    "Fill Type": clean_text(matched_details.get("Fill Type", "")),
                    "Origin": clean_text(matched_details.get("Origin", "")),
                    "Warranties": clean_text(matched_details.get("Warranties", ""))
                }
            
        except Exception as e:
            print(f"DEBUG: Failed to extract details: {e}")
            for row in product_data["table_data"]:
                row["details"] = {}

        return product_data

    except Exception as e:
        print(f"Error scraping product page: {e}")
        return {"url": product_url, "error": str(e)}

def refresh_session():
    """Refresh the browser session if needed."""
    global driver  # Add global declaration
    try:
        # Test if session is still valid
        driver.current_url
        return True
    except Exception:
        print("Session expired, refreshing...")
        try:
            # Re-initialize driver
            driver.quit()
            options = uc.ChromeOptions()
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            driver = uc.Chrome(
                options=options,
                version_main=132
            )
            driver.set_window_size(1920, 1080)
            
            # Re-login
            login_to_site()
            return True
        except Exception as e:
            print(f"Failed to refresh session: {e}")
            return False

def get_fresh_elements(driver, selector, timeout=30):
    """Get fresh elements with retry logic for stale elements."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            elements = WebDriverWait(driver, 5).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, selector))
            )
            # Verify elements are not stale
            for element in elements:
                try:
                    _ = element.is_displayed()
                except:
                    raise Exception("Stale element found")
            return elements
        except Exception as e:
            print(f"Retrying to get fresh elements: {str(e)}")
            time.sleep(1)
    raise Exception(f"Could not get fresh elements after {timeout} seconds")

def get_product_links(driver):
    """Get all product links from the current page."""
    links = []
    max_attempts = 3
    delay = 2
    
    for attempt in range(max_attempts):
        try:
            # Wait for product grid
            WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.ID, "search-result-items"))
            )
            
            # Get all product links directly using XPath
            elements = driver.find_elements(By.XPATH, "//div[contains(@class, 'product-tile')]//a[contains(@class, 'name-link')]")
            
            # Extract href attributes
            for element in elements:
                try:
                    link = element.get_attribute("href")
                    if link and link not in links:
                        links.append(link)
                except:
                    continue
            
            if links:
                return links
                
        except Exception as e:
            print(f"Attempt {attempt + 1} failed to get product links: {str(e)}")
            if attempt < max_attempts - 1:
                time.sleep(delay)
                delay *= 2
                continue
            else:
                print("Failed to get product links after all attempts")
                return []
    
    return links

def extract_products_from_category(category_name, category_url):
    global driver
    driver.get(category_url)
    products = []
    processed_urls = set()  # Keep track of processed URLs
    print(f"Extracting products from {category_name}...")
    
    while True:
        try:
            # Get all product links on current page
            product_links = get_product_links(driver)
            print(f"DEBUG: Found {len(product_links)} product links on the page.")
            
            if not product_links:
                print("No product links found on page, trying to refresh session...")
                if not refresh_session():
                    break
                continue
            
            # Process each product link
            for product_link in product_links:
                try:
                    if product_link in processed_urls:
                        print(f"DEBUG: Already processed: {product_link}")
                        continue
                    
                    processed_urls.add(product_link)
                    print(f"DEBUG: Processing product: {product_link}")
                    
                    # Process the product
                    product_details = process_product(product_link)
                    if product_details:
                        product_details["category"] = category_name
                        products.append(product_details)
                        print(f"Successfully processed product: {product_link}")
                    
                    # Add a small delay between products
                    time.sleep(1)
                    
                except Exception as e:
                    print(f"ERROR: Failed to process product: {str(e)}")
                    if not refresh_session():
                        break
                    continue
            
            # Check for next page
            try:
                next_button = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".pagination .next"))
                )
                
                if "disabled" in next_button.get_attribute("class"):
                    print("DEBUG: Reached last page in category.")
                    break
                
                print("DEBUG: Clicking next page button...")
                driver.execute_script("arguments[0].click();", next_button)
                
                # Wait for page to load
                time.sleep(2)
                
            except Exception as e:
                print(f"DEBUG: No more pages in this category: {str(e)}")
                break
            
        except Exception as e:
            print(f"Error loading products from category: {str(e)}")
            if not refresh_session():
                break
    
    return products

def process_product(product_url, max_retries=3):
    """Process a single product with retry logic."""
    global driver
    retry_delay = 2
    original_url = driver.current_url
    
    for attempt in range(max_retries):
        try:
            # Navigate to product
            driver.get(product_url)
            
            # Wait for product content with multiple conditions
            try:
                WebDriverWait(driver, 30).until(
                    EC.presence_of_element_located((By.ID, "product-content"))
                )
                WebDriverWait(driver, 30).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "product-detail"))
                )
            except Exception as e:
                print(f"Error waiting for product content: {e}")
                driver.get(original_url)
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                return None
            
            # Add a small delay to ensure content is fully loaded
            time.sleep(2)
            
            # Scrape product details
            product_details = scrape_product_page(product_url)
            
            # Return to previous page
            driver.get(original_url)
            time.sleep(1)
            
            return product_details
            
        except Exception as e:
            print(f"Attempt {attempt + 1} failed for {product_url}: {str(e)}")
            try:
                driver.get(original_url)
            except:
                if not refresh_session():
                    return None
            
            if attempt < max_retries - 1:
                print(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
                retry_delay *= 2
            else:
                print(f"Failed to process product after {max_retries} attempts")
                return None
    
    return None

def clean_text(text):
    """Clean up text by fixing encoding issues and normalizing."""
    if not isinstance(text, str):
        return ""  # Return empty string for non-string inputs
    text = fix_text(text)  # Fix text encoding issues
    text = unicodedata.normalize("NFKC", text)  # Normalize Unicode
    text = text.replace("\u00a0", " ")  # Replace non-breaking spaces
    text = re.sub(r"[®™©]", "", text)  # Remove trademark and registered symbols
    text = text.replace("â€", "-")  # Replace specific encoding issue with dash
    text = re.sub(r'\s+', ' ', text)  # Normalize whitespace
    return text.strip()

def extract_dimensions(text):
    """Extract standardized dimensions from text with size context."""
    if not isinstance(text, str):
        return ""
    
    def standardize_measurement(dimension):
        # Convert fraction strings to decimal
        fraction_pattern = r'(\d+)\s*(?:-|and)?\s*(\d+)/(\d+)'
        fraction_match = re.search(fraction_pattern, dimension)
        if fraction_match:
            whole = int(fraction_match.group(1))
            num = int(fraction_match.group(2))
            denom = int(fraction_match.group(3))
            decimal = whole + (num / denom)
            dimension = str(decimal)
        
        # Clean up the number and convert to float for standardization
        try:
            num = float(re.sub(r'[^\d.]', '', dimension))
            return '{:.2f}'.format(num)
        except ValueError:
            return dimension
    
    def process_dimension_group(dim_text):
        # Common dimension patterns with optional size prefixes
        patterns = [
            # Standard dimensions with optional quotes/inches
            r'(\d+(?:\s*-?\s*\d+/\d+)?|\d+(?:\.\d+)?)\s*(?:"|in(?:ch(?:es)?)?|\'|feet)?\s*[xX]\s*'
            r'(\d+(?:\s*-?\s*\d+/\d+)?|\d+(?:\.\d+)?)\s*(?:"|in(?:ch(?:es)?)?|\'|feet)?\s*'
            r'(?:[xX]\s*(\d+(?:\s*-?\s*\d+/\d+)?|\d+(?:\.\d+)?)\s*(?:"|in(?:ch(?:es)?)?|\'|feet)?)?',
            
            # Dimensions with explicit labels
            r'(?:L|Length|W|Width|H|Height)\s*[=:]\s*'
            r'(\d+(?:\s*-?\s*\d+/\d+)?|\d+(?:\.\d+)?)\s*(?:"|in(?:ch(?:es)?)?|\'|feet)?'
        ]
        
        for pattern in patterns:
            matches = list(re.finditer(pattern, dim_text, re.IGNORECASE))
            if matches:
                dimensions = []
                for match in matches:
                    # Get all capturing groups that contain numbers
                    dims = [g for g in match.groups() if g and re.search(r'\d', g)]
                    if dims:
                        # Standardize each measurement
                        standardized_dims = [standardize_measurement(d) for d in dims]
                        dimensions.append(' x '.join([f'{d}"' for d in standardized_dims]))
                return '; '.join(dimensions)
        return ""
    
    # Split text into size-specific sections
    size_sections = re.split(r'(?:\b(?:Standard|Queen|King|Twin|Full|Cal(?:ifornia)?\s*King)\b)[:\s-]+', text)
    
    # Process each section
    dimensions = []
    current_size = ""
    
    for i, section in enumerate(size_sections):
        if i == 0 and not re.search(r'\b(?:Standard|Queen|King|Twin|Full|Cal(?:ifornia)?\s*King)\b', text):
            # This is the only section and has no size prefix
            processed = process_dimension_group(section)
            if processed:
                dimensions.append(processed)
        else:
            # Look for size prefix before this section
            size_match = re.search(r'\b(Standard|Queen|King|Twin|Full|Cal(?:ifornia)?\s*King)\b', 
                                 text[:text.find(section)], 
                                 re.IGNORECASE)
            if size_match:
                current_size = size_match.group(1)
                processed = process_dimension_group(section)
                if processed:
                    dimensions.append(f"{current_size}: {processed}")
    
    return '; '.join(filter(None, dimensions))

def clean_dimensions(dimensions_data, shipping_data=""):
    """Clean and merge dimension data from different sources."""
    if not dimensions_data and not shipping_data:
        return ""
        
    all_dimensions = []
    
    # Helper function to process dimension text
    def process_dim_text(text, prefix=""):
        if not isinstance(text, str):
            return []
        
        # Split by common separators
        parts = re.split(r'[;,\n]|\s+(?=[A-Za-z]+:)', text)
        processed_dims = []
        
        for part in parts:
            # Look for size prefixes
            size_match = re.match(r'(?:Standard|Queen|King|Twin|Full|Cal(?:ifornia)?\s*King)[:\s-]+(.+)', part, re.IGNORECASE)
            dims = size_match.group(1) if size_match else part
            
            # Extract dimensions
            dim_matches = re.findall(r'(\d+(?:\.\d+)?)\s*(?:"|inches?|\'|[xX])+\s*(\d+(?:\.\d+)?)\s*(?:"|inches?|\')?(?:\s*[xX]\s*(\d+(?:\.\d+)?)\s*(?:"|inches?|\')?)?', dims)
            
            for match in dim_matches:
                # Filter out zero dimensions and standardize
                valid_dims = ['{:.2f}'.format(float(d)) for d in match if d and float(d) > 0]
                if valid_dims:
                    dim_str = ' x '.join(f'{d}"' for d in valid_dims)
                    if size_match:
                        dim_str = f"{size_match.group(0).strip()}: {dim_str}"
                    if prefix:
                        dim_str = f"{prefix}: {dim_str}"
                    processed_dims.append(dim_str)
                    
        return processed_dims

    # Process product dimensions
    if dimensions_data:
        all_dimensions.extend(process_dim_text(dimensions_data, "Product"))
        
    # Process shipping dimensions
    if shipping_data:
        ship_dims = process_dim_text(shipping_data, "Shipping")
        # Only add shipping dimensions if they're different from product dimensions
        for dim in ship_dims:
            if dim not in all_dimensions:
                all_dimensions.append(dim)
    
    return '; '.join(filter(None, all_dimensions))

def merge_fill_weights(product_fill_weight, shipping_fill_weight):
    """Merge and standardize fill weights from multiple sources."""
    weights = []
    
    for weight_text in [product_fill_weight, shipping_fill_weight]:
        if not isinstance(weight_text, str):
            continue
            
        # Split by size indicators
        parts = re.split(r'(?:Standard|Queen|King|Twin|Full|Cal(?:ifornia)?\s*King)[:\s-]+', weight_text)
        
        for part in parts:
            # Extract weights with units
            matches = re.finditer(r'(\d+(?:\.\d+)?)\s*(?:oz\.?|ounces?|lbs?\.?|pounds?)', part, re.IGNORECASE)
            
            for match in matches:
                weight = match.group(1)
                unit = match.group(0)[len(weight):].strip().lower()
                
                # Convert to ounces if in pounds
                if any(u in unit for u in ['lb', 'pound']):
                    weight = str(float(weight) * 16)
                
                # Standardize format
                weight = '{:.2f}'.format(float(weight))
                weights.append(f"{weight} oz")
    
    # Remove duplicates and sort
    return '; '.join(sorted(set(weights)))

def clean_fill_weight(weight_text):
    """Standardize fill weight format."""
    if not isinstance(weight_text, str):
        return ""
    
    weights = []
    # Split by common separators
    parts = re.split(r'[;,\n]|\s+(?=[A-Za-z]+:)', weight_text)
    
    for part in parts:
        # Extract size-specific weights
        size_match = re.match(r'(Standard|Queen|King|Twin|Full|Cal[ifornia]*\s*King)[:\s-]+(.+)', part, re.IGNORECASE)
        if size_match:
            size, weight_part = size_match.groups()
        else:
            weight_part = part
            
        # Extract weight and unit
        weight_matches = re.finditer(r'(\d+(?:\.\d+)?)\s*(?:oz\.?|ounces?|lbs?\.?|pounds?)', weight_part, re.IGNORECASE)
        for match in weight_matches:
            weight = match.group(1)
            unit_text = match.group(0)[len(weight):].strip().lower()
            
            # Convert to ounces if in pounds
            if 'lb' in unit_text or 'pound' in unit_text:
                weight = str(float(weight) * 16)
            
            # Round to 2 decimal places and remove trailing zeros
            weight = str(float('{:.2f}'.format(float(weight))))
            weights.append(f"{weight} oz")
    
    return "; ".join(weights)

def clean_type_size(parent_name, type_size):
    """Clean and standardize type_size."""
    if not isinstance(type_size, str):
        return ""
    
    # Remove parent name and special characters
    type_size = re.sub(r'[®™©]', '', type_size)
    if parent_name:
        type_size = re.sub(re.escape(parent_name), '', type_size, flags=re.IGNORECASE)
    
    # Standardize size formats
    size_patterns = {
        r'\b(?:std|standard)\b': 'Standard',
        r'\b(?:kg|king)\b': 'King',
        r'\bcal(?:ifornia)?\s*k(?:ing)?\b': 'California King',
        r'\b(?:qn|queen)\b': 'Queen',
        r'\bfull\b': 'Full',
        r'\btwin\s*xl\b': 'Twin XL',
        r'\btwin\b': 'Twin',
        r'\bjumbo\b': 'Jumbo',
        r'\beuro\b': 'Euro'
    }
    
    # Clean up the text
    cleaned = type_size.lower()
    cleaned = re.sub(r'^.*?(?:pillow|insert|cover|protector|pack|size)\s*[-:,]?\s*', '', cleaned)
    cleaned = re.sub(r'(?:by|from)\s+.*$', '', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned)
    cleaned = cleaned.strip()
    
    # Apply standardization
    result = cleaned
    for pattern, replacement in size_patterns.items():
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    
    # Extract density if present
    density_match = re.search(r'(soft|medium|firm)\s*(?:density|support)?', result, re.IGNORECASE)
    density = density_match.group(1).title() if density_match else ""
    
    # Clean up size
    size_match = re.search(r'\b(Standard|Queen|King|Twin XL|Twin|Full|California King|Jumbo|Euro)\b', result)
    size = size_match.group(1) if size_match else ""
    
    # Combine size and density
    if size and density:
        return f"{size} - {density}"
    return size if size else cleaned

def clean_shipping_info(dimensions, weight):
    """Clean and standardize shipping information."""
    if not isinstance(dimensions, str) or not isinstance(weight, str):
        return "", ""
    
    # Process dimensions
    dims = extract_dimensions(dimensions)
    
    # Process weight
    weights = []
    matches = re.finditer(r'(\d+(?:\.\d+)?)\s*(?:lbs?\.?|pounds?)', weight, re.IGNORECASE)
    
    for match in matches:
        weight_val = match.group(1)
        # Standardize to 2 decimal places
        weight_val = '{:.2f}'.format(float(weight_val))
        weights.append(f"{weight_val} lbs")
    
    return dims, "; ".join(sorted(set(weights)))

def clean_image_urls(images):
    """Clean up image URLs by removing anything after .jpg."""
    cleaned_images = []
    for img_url in images:
        match = re.match(r"(.*?\.jpg)", img_url)  # Properly close the regex pattern
        if match:
            cleaned_images.append(match.group(1))
    return cleaned_images

def save_to_csv(products, filename="products_with_details.csv"):
    """Save products to CSV with standardized data."""
    headers = [
        "Category",
        "Parent Product Name",
        "Description",
        "Images",
        "Product URL",
        "SKU",
        "type_size",
        "price_per_unit",
        "units_per_case",
        "Care",
        "Design",
        "Dimensions",
        "Fabric",
        "Fill Type",
        "Fill Weight",
        "Origin",
        "Warranties"
    ]

    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()

        for product in products:
            base_row = {
                "Category": clean_text(product.get("category", "")),
                "Parent Product Name": clean_text(product.get("parent_name", "")),
                "Description": clean_text(product.get("long_description", "")),
                "Images": "; ".join(clean_image_urls(product.get("images", []))),
                "Product URL": clean_text(product.get("url", "")),
            }

            if "table_data" in product:
                for variant in product["table_data"]:
                    row = base_row.copy()
                    details = variant.get("details", {})
                    
                    # Clean type size
                    type_size = clean_type_size(
                        row["Parent Product Name"],
                        variant.get("type_size", "")
                    )
                    
                    # Merge and standardize dimensions
                    dimensions = clean_dimensions(
                        details.get("Dimensions", ""),
                        details.get("Shipping Carton", "")
                    )
                    
                    # Merge and standardize fill weights
                    fill_weight = merge_fill_weights(
                        details.get("Fill Weight", ""),
                        details.get("Additional Fill Weight", "")
                    )
                    
                    # Clean units per case
                    units_per_case = standardize_case_info(variant.get("units_per_case", ""))
                    
                    row.update({
                        "SKU": clean_text(variant.get("item", "")),
                        "type_size": type_size,
                        "price_per_unit": re.sub(r'[^\d.]', '', variant.get("price_per_unit", "")),
                        "units_per_case": units_per_case,
                        "Care": clean_text(details.get("Care", "")),
                        "Design": clean_text(details.get("Design", "")),
                        "Dimensions": dimensions,
                        "Fabric": clean_text(details.get("Fabric", "")),
                        "Fill Type": clean_text(details.get("Fill Type", "")),
                        "Fill Weight": fill_weight,
                        "Origin": clean_text(details.get("Origin", "")),
                        "Warranties": clean_text(details.get("Warranties", ""))
                    })

                    writer.writerow(row)
            else:
                writer.writerow(base_row)

    print(f"Products saved to {filename}")
    print(f"Total products saved: {len(products)}")

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

def parse_details_by_variant(details):
    """
    Parse details section to map information to specific variants.
    Returns a dictionary mapping variant sizes to their specific details.
    """
    variant_details = {}
    
    # Fields that should be variant-specific
    variant_specific_fields = {
        'Dimensions': True,
        'Fill Weight': True,
        'Shipping Carton': True,
        'Shipping Carton Weight': True,
        'units_per_case': True
    }
    
    # Process each detail field
    for key, value in details.items():
        if not isinstance(value, str):
            continue
            
        # Check if this is a variant-specific field
        if key in variant_specific_fields:
            # Split on line breaks and common separators
            parts = re.split(r'[;\n]', value)
            for part in parts:
                # Try to extract size/variant and corresponding value
                size_match = re.match(
                    r'^(Standard|Queen|King|Twin|Full|Cal(?:ifornia)?\s*King)[:\s-]+(.+)$',
                    part.strip(),
                    re.IGNORECASE
                )
                if size_match:
                    variant, detail = size_match.groups()
                    variant = variant.strip()
                    detail = detail.strip()
                    
                    if variant not in variant_details:
                        variant_details[variant] = {}
                    variant_details[variant][key] = detail
        else:
            # For non-variant-specific fields, apply to all known variants
            for variant in set(variant_details.keys()) | {'Standard', 'Queen', 'King', 'Twin', 'Full', 'California King'}:
                if variant not in variant_details:
                    variant_details[variant] = {}
                variant_details[variant][key] = value.strip()
    
    return variant_details

def standardize_shipping_info(shipping_dims, shipping_weight):
    """Standardize shipping information format."""
    standardized_info = []
    
    # Process dimensions
    if shipping_dims:
        dims = extract_dimensions(shipping_dims)
        if dims:
            standardized_info.append(f"Shipping Dimensions: {dims}")
    
    # Process weight
    if shipping_weight:
        weight_matches = re.finditer(r'(\d+(?:\.\d+)?)\s*(?:lbs?\.?|pounds?)', shipping_weight, re.IGNORECASE)
        weights = []
        for match in weight_matches:
            weight_val = float(match.group(1))
            weights.append(f"{weight_val:.2f} lbs")
        if weights:
            standardized_info.append(f"Shipping Weight: {'; '.join(weights)}")
    
    return " | ".join(standardized_info)

def standardize_case_info(units_per_case):
    """Standardize case quantity information."""
    if not units_per_case:
        return ""
    
    # Extract numeric value only
    case_match = re.search(r'(\d+)', str(units_per_case))
    if case_match:
        return case_match.group(1)
    return ""

# Main Execution
def main():
    all_products = []
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
        total_products = 0
        for i, category in enumerate(categories, 1):
            try:
                print(f"\n{'='*50}")
                print(f"Processing category {i} of {len(categories)}: {category['name']}")
                print(f"{'='*50}\n")
                
                products = extract_products_from_category(category["name"], category["url"])
                all_products.extend(products)
                total_products += len(products)
                print(f"Successfully processed {len(products)} products from {category['name']}")
                
                # Save incremental backup
                save_to_csv(all_products, f"products_with_details_{i}_of_{len(categories)}_backup.csv")
                print(f"Backup saved to products_with_details_{i}_of_{len(categories)}_backup.csv")
                
                # Save consolidated data after each category
                save_to_csv(all_products, "products_with_details.csv")
                print(f"Updated consolidated data in products_with_details.csv (Total: {len(all_products)} products)")
                
            except Exception as category_error:
                print(f"Error processing category {category['name']}: {str(category_error)}")
                # Save progress before moving to next category
                if all_products:
                    save_to_csv(all_products, f"products_with_details_error_at_{i}_of_{len(categories)}.csv")
                    print(f"Progress saved to products_with_details_error_at_{i}_of_{len(categories)}.csv")
                    # Also update the main consolidated file
                    save_to_csv(all_products, "products_with_details.csv")
                continue

        # Step 4: Print final summary
        if all_products:
            print(f"\n{'='*50}")
            print("Final Summary:")
            print(f"{'='*50}")
            print(f"Total products processed: {len(all_products)}")
            print(f"Categories processed: {len(categories)}")
            print("All data has been saved to products_with_details.csv")
            
            # Calculate category-wise breakdown
            category_counts = {}
            for product in all_products:
                category = product.get("category", "Unknown")
                category_counts[category] = category_counts.get(category, 0) + 1
            
            print("\nCategory-wise breakdown:")
            for category, count in category_counts.items():
                print(f"{category}: {count} products")
        else:
            print("\nNo products were processed successfully.")

    except Exception as e:
        print(f"An error occurred in main execution: {e}")
        if all_products:
            save_to_csv(all_products, "products_with_details_error_recovery.csv")
            print("Partial results saved to products_with_details_error_recovery.csv")
            # Also update the main consolidated file
            save_to_csv(all_products, "products_with_details.csv")
        driver.save_screenshot("error_screenshot.png")
    finally:
        try:
            driver.quit()
        except Exception as e:
            print(f"Error while closing driver: {e}")

if __name__ == "__main__":
    main()