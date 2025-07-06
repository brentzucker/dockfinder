import logging
import os
import re
import json
from pathlib import Path
from typing import List, Dict, Optional, Any

import requests
import pandas as pd
from bs4 import BeautifulSoup
from tqdm import tqdm
from datetime import datetime

# Constants
CACHE_DIR = Path("cache")
CSV_FILE = Path("scrape.csv")
HEADERS_FILE = Path("headers.txt")
BASE_URL = "https://www.withroam.com"
STATE_URL = f"{BASE_URL}/state/GA?page={{}}"
CITY_URL = f"{BASE_URL}/cities/34526/Gainesville-GA?page={{}}"

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

def load_headers(headers_file: Path = HEADERS_FILE) -> Dict[str, str]:
    """Load HTTP headers from a file."""
    headers = {}
    if headers_file.exists():
        with headers_file.open("r") as f:
            for line in f:
                if ':' in line:
                    key, value = line.split(':', 1)
                    headers[key.strip()] = value.strip()
    else:
        logging.warning(f"{headers_file} not found. Proceeding without custom headers.")
    return headers

def fetch_html(url: str, headers: Optional[Dict[str, str]] = None) -> str:
    """Fetch HTML content from a URL."""
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.text

def find_multiline_ellipsis_links(html: str) -> List[str]:
    """Find all <a> tags with '...' as their text."""
    soup = BeautifulSoup(html, 'html.parser')
    return [str(a) for a in soup.find_all('a') if a.get_text(strip=True) == '...']

def get_maxpageid(html: str) -> int:
    """Extract the maximum page ID from HTML."""
    for line in find_multiline_ellipsis_links(html):
        try:
            val = int(line.split('page=')[1].split('"')[0].split('&')[0])
            return val
        except (IndexError, ValueError):
            continue
    raise ValueError("Could not determine max page id.")

def find_listing_links(html: str) -> List[str]:
    """Extract all listing links from HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    return [a['href'] for a in soup.find_all('a', href=True) if a['href'].startswith('/listing/')]

def parse_listing_html(html: str) -> Dict[str, Any]:
    """Parse main listing details from HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    title = soup.title.string.strip() if soup.title else None
    meta_description = soup.find('meta', attrs={'name': 'description'})
    description = meta_description['content'].strip() if meta_description else None
    canonical_link = soup.find('link', rel='canonical')
    canonical_url = canonical_link['href'] if canonical_link else None
    og_image = soup.find('meta', property='og:image')
    image_url = og_image['content'].strip() if og_image else None

    # Address extraction
    address = None
    h1_address = soup.find('h1', class_='fs-14 text-body-secondary fw-bold')
    if h1_address:
        address = h1_address.get_text(strip=True)
    elif canonical_url:
        address = canonical_url.split('/')[-1].replace('-', ' ').upper()

    # Bed, bath, sqft extraction
    bed = bath = sqft = None
    desc_p = soup.find('p', class_='fs-6 pb-1 text-body')
    if desc_p:
        desc_text = desc_p.get_text(strip=True)
        bed_match = re.search(r'(\d+)\s*beds?', desc_text)
        bath_match = re.search(r'(\d+)\s*baths?', desc_text)
        sqft_match = re.search(r'([\d,]+)\s*sqft', desc_text)
        bed = int(bed_match.group(1)) if bed_match else None
        bath = int(bath_match.group(1)) if bath_match else None
        sqft = int(sqft_match.group(1).replace(',', '')) if sqft_match else None

    # City extraction
    city = None
    if address:
        parts = [p.strip() for p in address.split(',')]
        if len(parts) >= 2:
            city = parts[-2]
        elif canonical_url:
            slug = canonical_url.split('/')[-1]
            slug_parts = slug.split('-')
            if len(slug_parts) >= 3:
                city = slug_parts[-3].upper()
            elif slug_parts:
                city = slug_parts[0].upper()

    return {
        'title': title,
        'description': description,
        'address': address,
        'city': city,
        'image_url': image_url,
        'bedrooms': bed,
        'bathrooms': bath,
        'sqft': sqft,
        'canonical_url': canonical_url
    }

def parse_details(html: str, class_: str = 'loan-feature') -> Dict[str, Any]:
    """Parse details from a given class in HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    details = []
    for feature in soup.find_all('div', class_=class_):
        detail = [div.get_text(strip=True) for div in feature.find_all('div')]
        if detail:
            details.append(detail)
    return details_list_to_dict(details)

def details_list_to_dict(details: List[List[str]]) -> Dict[str, Any]:
    """Convert a list of details into a dictionary."""
    result = {}
    for detail in details:
        if len(detail) > 1:
            result[detail[0]] = detail[1] if len(detail) == 2 else detail[1:]
        elif detail:
            result[detail[0]] = None
    return result

def get_financials(html: str) -> Dict[str, Any]:
    """Extract financial details from HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    section = soup.find(id='calculator-section')
    details = []
    if section:
        for d_flex in section.find_all(class_='d-flex'):
            detail = [div.get_text(strip=True) for div in d_flex.find_all('div')]
            details.append(detail)
    return details_list_to_dict(details)

def get_description(html: str) -> Optional[str]:
    """Extract the property description from HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    desc = soup.find('p', class_='description')
    return desc.get_text(strip=True) if desc else None

def contains_str(text: Optional[str], substring: str) -> bool:
    """Check if substring is in text (case-insensitive)."""
    return substring.lower() in text.lower() if text else False

def load_existing_dataframe(csv_file: Path) -> pd.DataFrame:
    """Load existing DataFrame from CSV if it exists."""
    if csv_file.exists():
        logging.info(f"Loaded existing {csv_file}")
        return pd.read_csv(csv_file)
    return pd.DataFrame()

def cache_html(filename: Path, html: str) -> None:
    """Cache HTML content to a file."""
    filename.parent.mkdir(parents=True, exist_ok=True)
    filename.write_text(html, encoding='utf-8')

def get_cached_html(filename: Path) -> Optional[str]:
    """Retrieve cached HTML if it exists."""
    if filename.exists():
        return filename.read_text(encoding='utf-8')
    return None

def main():
    city = None  # Set to "Gainesville" for city-specific scraping
    headers = load_headers()
    url = CITY_URL.format(1) if city == "Gainesville" else STATE_URL.format(1)
    html = fetch_html(url, headers)
    maxpageid = get_maxpageid(html)
    logging.info(f"Max page ID: {maxpageid}")

    # Gather all listing links
    listing_links = []
    for i in tqdm(range(1, maxpageid + 1), desc="Fetching listing links"):
        page_url = CITY_URL.format(i) if city == "Gainesville" else STATE_URL.format(i)
        html = fetch_html(page_url, headers)
        listing_links.extend(find_listing_links(html))

    # Prepare DataFrame
    columns = [
        "contains_dock", "city", "url", "address", "bedrooms", "bathrooms", "sqft",
        "listing_price", "cash_down_payment", "loan_type", "rate", "remaining_balance", "monthly_payment"
    ]
    df = load_existing_dataframe(CSV_FILE)

    for link in tqdm(listing_links, desc="Fetching home data"):
        home_url = f"{BASE_URL}{link}"
        if 'url' in df.columns and home_url in df['url'].values:
            logging.info(f"Skipping already processed link: {link}")
            continue

        cache_file = CACHE_DIR / f"{home_url.split('/')[-1]}.html"
        html = get_cached_html(cache_file)
        if not html:
            logging.info(f"Fetching data for home: {home_url}")
            html = fetch_html(home_url, headers)
            cache_html(cache_file, html)
        else:
            logging.info(f"Using cached file: {cache_file}")

        listing_data = parse_listing_html(html)
        details = {cls: parse_details(html, class_=cls) for cls in ['loan-feature', 'home-feature']}
        financials = get_financials(html)
        description = get_description(html)
        contains_dock = contains_str(description, 'dock')

        record = [
            contains_dock,
            listing_data['city'],
            listing_data['canonical_url'],
            listing_data['address'],
            listing_data['bedrooms'],
            listing_data['bathrooms'],
            listing_data['sqft'],
            financials.get('Listing price'),
            financials.get('Your cash down payment'),
            details['loan-feature'].get('Loan Type'),
            details['loan-feature'].get('Rate'),
            details['loan-feature'].get('Remaining balance'),
            details['home-feature'].get('Total')
        ]
        _df = pd.DataFrame([record], columns=columns)
        df = pd.concat([df, _df], ignore_index=True)
        df.to_csv(CSV_FILE, index=False)

if __name__ == "__main__":
    main()
