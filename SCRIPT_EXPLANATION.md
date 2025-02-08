# Script Explanation: From Scrape to Database Insertion

## Overview
This script automates the process of scraping product data from keecohospitality.com, cleaning the data, and inserting it into a PostgreSQL database.

## Process Flow

### 1. Login and Authentication
- Uses Selenium WebDriver with undetected-chromedriver
- Retrieves credentials from .env file
- Handles login process with wait conditions for page elements

### 2. Product Data Scraping
- Iterates through predefined product categories
- For each product page:
	- Extracts parent product name
	- Captures product descriptions and images
	- Processes variant-specific details
	- Collects table data with pricing and SKUs

### 3. Data Processing
- Text normalization and cleaning
- Encoding fixes and special character handling
- Dynamic processing of nested fields
- Deduplication of records

### 4. Data Storage
- CSV Export:
	- Combines product details and variants
	- Creates consistent column structure
	- Handles nested data serialization
- Database Insertion:
	- PostgreSQL schema compliance
	- Batch insertion for performance
	- Conflict handling for SKUs

## Current Issues

### 1. Parent Product Name and type_size Redundancy
**Problem:**
- type_size column often contains redundant parent product name
- Makes variant identification more complex
- Example:
	```
	Parent Name: "Simple Comfort Pillow"
	type_size: "Simple Comfort Pillow - Standard"
	```

**Solution Needed:**
- Extract only unique variant information
- Expected output: `type_size: "Standard"`

### 2. Details Section Data Mapping
**Problem:**
- Details section contains nested variant data
- Difficult to map specific details to correct variants
- Example:
	```
	Details:
	"Dimensions: Standard - 20"W x 26"L, Queen - 20"W x 30"L"
	```

**Solution Needed:**
- Parse and map details to specific variants
- Create one-to-one relationships between variants and their details

## Improvement Plan

1. Refactor Data Extraction:
	 - Implement smarter parsing for type_size
	 - Create mapping system for variant details

2. Enhance Data Structure:
	 - Normalize nested data
	 - Improve variant-detail relationships

3. Optimize Database Schema:
	 - Consider separate tables for variants
	 - Add constraints for data integrity

## Example Data Structure

### Current Output:
```json
{
	"parent_name": "Simple Comfort Pillow",
	"type_size": "Simple Comfort Pillow - Standard",
	"details": {
		"dimensions": "Standard - 20\"W x 26\"L, Queen - 20\"W x 30\"L"
	}
}
```

### Desired Output:
```json
{
	"parent_name": "Simple Comfort Pillow",
	"type_size": "Standard",
	"details": {
		"dimensions": "20\"W x 26\"L"
	}
}
```