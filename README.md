# Keeco Scraper

A Python-based tool for extracting and processing Keeco Hospitality product data.

## Features
- Automated web scraping of keecohospitality.com
- Excel price list processing
- PostgreSQL database integration
- Data cleaning and normalization

## Prerequisites
- Python 3.8+
- Chrome browser
- PostgreSQL database

## Installation

1. Clone the repository:
```bash
git clone [repository-url]
cd keeco_scraper
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up environment variables in `.env`:
```
DB_NAME=your_db_name
DB_USER=your_db_user
DB_PASSWORD=your_db_password
DB_HOST=your_db_host
DB_PORT=your_db_port
KEECO_USERNAME=your_keeco_username
KEECO_PASSWORD=your_keeco_password
```

4. Initialize database:
```bash
psql -U your_db_user -d your_db_name -f schema.sql
```

## Usage

### Web Scraper
Run the web scraper to collect product data:
```bash
python keeco_scraper.py
```

### Excel Data Processor
Process Excel price lists:
```bash
python keeco_datasheet.py
```

## Output
- CSV file with scraped product data
- PostgreSQL database entries
- Error logs and screenshots (if errors occur)

## Architecture
See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed system design and components.

## Contributing
1. Fork the repository
2. Create your feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License
[Your chosen license]