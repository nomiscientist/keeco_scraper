# Keeco Scraper Architecture

## Overview
This project consists of two main components for collecting and processing Keeco Hospitality product data:
1. Web Scraper
2. Excel Data Processor

## Components

### 1. Web Scraper (keeco_scraper.py)
- **Purpose**: Extracts product data from keecohospitality.com
- **Key Features**:
	- Headless Chrome automation using undetected-chromedriver
	- Login handling
	- Product category navigation
	- Detailed product information extraction
	- Data cleaning and normalization
	- CSV export
	- PostgreSQL database integration

### 2. Excel Data Processor (keeco_datasheet.py)
- **Purpose**: Processes Excel price lists and product data
- **Key Features**:
	- Excel file parsing
	- Data normalization
	- Database schema compliance
	- Batch database insertion

### Database Schema (schema.sql)
- Schema Name: `manufactured`
- Table: `keeco`
- Key Fields:
	- id (SERIAL PRIMARY KEY)
	- category
	- parent_name
	- sku (UNIQUE)
	- type_size
	- price_per_unit
	- units_per_case
	- specs (JSONB)
	- created_at/updated_at timestamps

## Dependencies
- Web Scraping: selenium, undetected-chromedriver
- Data Processing: pandas, openpyxl
- Database: psycopg2-binary
- Utilities: python-dotenv, ftfy

## Environment Configuration
Required environment variables:
- Database credentials (DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT)
- Keeco login credentials (KEECO_USERNAME, KEECO_PASSWORD)

## Data Flow
1. Web Scraper:
	 - Logs into keecohospitality.com
	 - Navigates through product categories
	 - Extracts product details
	 - Cleans and normalizes data
	 - Saves to CSV and/or database

2. Excel Processor:
	 - Reads Excel price list
	 - Normalizes data
	 - Matches database schema
	 - Performs batch database insertion

## Error Handling
- Screenshot capture on scraper errors
- Logging of scraping errors
- Database transaction management
- Data validation and cleaning

## Future Improvements
1. Add retry mechanisms for failed scrapes
2. Implement incremental updates
3. Add data validation reports
4. Implement parallel processing for faster scraping
5. Add monitoring and alerting