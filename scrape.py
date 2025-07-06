import requests
import re
from bs4 import BeautifulSoup
from tqdm import tqdm
from datetime import datetime
import logging
import json
import os
import pandas as pd

logging.basicConfig(
    # filename=f"scrape_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def fetch_html(url):
    """
    Fetches the HTML content of the given URL.

    Args:
        url (str): The URL to fetch.

    Returns:
        str: The HTML content as a string.

    Raises:
        requests.RequestException: If the request fails.
    """
    # Read in headers from headers.txt and use with requests.get
    headers = {}
    try:
        with open('headers.txt', 'r') as f:
            for line in f:
                if ':' in line:
                    key, value = line.split(':', 1)
                    headers[key.strip()] = value.strip()
    except FileNotFoundError:
        logging.warning("headers.txt not found. Proceeding without custom headers.")

    response = requests.get(url, headers=headers if headers else None)
    # response = requests.get(url)
    response.raise_for_status()
    return response.text

def get_maxpageid(html):
    """
    Extracts the maximum page ID from the HTML content.

    Args:
        html (str): The HTML content as a string.

    Returns:
        int: The maximum page ID found in the HTML.
    """


    def find_multiline_ellipsis_links(html: str):
        """
        Finds all <a> tag blocks that contain only '...' as their inner text,
        even if the content is spread across multiple lines.

        Args:
            html (str): Full HTML content as a string.

        Returns:
            List[str]: A list of full <a>...</a> HTML strings where the text is '...'.
        """
        soup = BeautifulSoup(html, 'html.parser')
        ellipsis_links = []

        for a_tag in soup.find_all('a'):
            if a_tag.get_text(strip=True) == '...':
                ellipsis_links.append(str(a_tag))

        return ellipsis_links

    html_lines = find_multiline_ellipsis_links(html)
    
    for line in html_lines:
        val = line.split('page=')[1].split('"')[0].split('&')[0]
        val = int(val)
        return val
    
from bs4 import BeautifulSoup

def find_listing_links(html: str):
    """
    Extracts all href values from <a> tags where the href starts with '/listing/'.

    Args:
        html (str): Full HTML content as a string.

    Returns:
        List[str]: List of href values that start with '/listing/'.
    """
    soup = BeautifulSoup(html, 'html.parser')
    listing_links = []

    for a_tag in soup.find_all('a', href=True):
        href = a_tag['href']
        if href.startswith('/listing/'):
            listing_links.append(href)

    return listing_links

from bs4 import BeautifulSoup

def parse_listing_html(html):
    soup = BeautifulSoup(html, 'html.parser')

    # Title
    title = soup.title.string.strip() if soup.title else None

    # Meta description
    meta_description = soup.find('meta', attrs={'name': 'description'})
    description = meta_description['content'].strip() if meta_description else None

    # Canonical URL
    canonical_link = soup.find('link', rel='canonical')
    canonical_url = canonical_link['href'] if canonical_link else None

    # og:image
    og_image = soup.find('meta', property='og:image')
    image_url = og_image['content'].strip() if og_image else None

    # Extract address from title or canonical link
    address = None
    # Try to extract address from <h1> with specific class
    h1_address = soup.find('h1', class_='fs-14 text-body-secondary fw-bold')
    if h1_address:
        address = h1_address.get_text(strip=True)
    elif canonical_url:
        try:
            # Fallback: Extract portion after the last '/' and split by '-'
            address_parts = canonical_url.split('/')[-1].replace('-', ' ').upper()
            address = address_parts
        except Exception:
            pass

    # Parse description for bed, bath, and property type
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
    else:
        bed = bath = sqft = None

    # Parse city from address if possible
    city = None
    if address:
        # Try to extract city from address string (assumes format: "123 Main St, City, STATE ZIP")
        parts = [p.strip() for p in address.split(',')]
        if len(parts) >= 2:
            city = parts[-2]
        else:
            # Try to extract city from canonical_url if address is not standard
            if canonical_url:
                # e.g., .../city-state-zip
                slug = canonical_url.split('/')[-1]
                slug_parts = slug.split('-')
                if len(slug_parts) >= 2:
                    city = slug_parts[-3].upper() if len(slug_parts) >= 3 else slug_parts[0].upper()

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

def parse_details(html, class_='loan-feature'):
    soup = BeautifulSoup(html, 'html.parser')

    loan_features = soup.find_all('div', class_=class_)

    details = []
    for loan_feature in loan_features:
        # Loop through each div within the selected element
        detail = []
        for div in loan_feature.find_all('div'):
            # Extract the text from each div
            text = div.get_text(strip=True)
            # Print or process the text as needed
            detail.append(text)
        if len(detail) > 0:
            details.append(detail)

    return details_list_to_dict(details)

def details_list_to_dict(details):
    """
    Converts a list of details into a dictionary.

    Args:
        details (list): List of details where each detail is a list of strings.

    Returns:
        dict: Dictionary with the first element as key and the rest as value.
    """
    details_dict = {}
    for detail in details:
        if len(detail) > 1:
            key = detail[0]
            value = detail[1] if len(detail) == 2 else detail[1:]
            details_dict[key] = value
        elif len(detail) == 1:
            details_dict[detail[0]] = None
    return details_dict

def get_financials(html):
    soup = BeautifulSoup(html, 'html.parser')
    financials_link = soup.find(id='calculator-section')
    details = []
    if financials_link:
        for d_flex in financials_link.find_all(class_='d-flex'):
            detail = []
            for div in d_flex.find_all('div'):
                text = div.get_text(strip=True)
                detail.append(text)
            details.append(detail)
    return details_list_to_dict(details)

def get_description(html):
    soup = BeautifulSoup(html, 'html.parser')
    description = soup.find('p', class_='description')
    if description:
        return description.get_text(strip=True)
    return None

def contains_str(text, str):
    """
    Checks if the given text contains the specified string.

    Args:
        text (str): The text to check.
        str (str): The string to search for.

    Returns:
        bool: True if the text contains the string, False otherwise.
    """
    return str.lower() in text.lower() if text else False

if __name__ == "__main__":
    city = "Gainesville"
    city = None

    url = "https://www.withroam.com/state/GA?page=1"
    if city == 'Gainesville':
        url = "https://www.withroam.com/cities/34526/Gainesville-GA?page=1"
    html = fetch_html(url)
    maxpageid = get_maxpageid(html)
    # maxpageid = 3  # For testing purposes, set to 3
    verbose = False

    # Create Logger with datetime format 
    logging.info(f"Max page ID: {maxpageid}")

    # Get All Links to Homes
    listing_links = []
    for i in tqdm(range(1, maxpageid + 1), desc="Fetching listing links"):
        page_url = f"https://www.withroam.com/state/GA?page={i}"
        if city == 'Gainesville':
            page_url = f"https://www.withroam.com/cities/34526/Gainesville-GA?page={i}"
        html = fetch_html(page_url)
        _listing_links_ = find_listing_links(html)
        for link in _listing_links_:
            listing_links.append(link)
            # print(link)
            logging.info(f"Page {i} link: {link}")

    # For Each Home Link fetch data
    columns = [
        "contains_dock",                    # Whether the description mentions 'dock'
        "city",                             # City extracted from the address
        "url",                              # Canonical URL of the listing
        "address",                          # Address of the property
        "bedrooms",                         # Number of bedrooms
        "bathrooms",                        # Number of bathrooms
        "sqft",                             # Square footage
        "listing_price",                    # Listing price from financials
        "cash_down_payment",                # Cash down payment from financials
        "loan_type",                        # Loan type from loan features
        "rate",                             # Loan rate from loan features
        "remaining_balance",                # Remaining balance from loan features
        "monthly_payment"                   # Total from home features
    ]
    df = pd.DataFrame(columns=[])
    # Try reading in df from scrape.csv if it exists
    if os.path.exists('scrape.csv'):
        df = pd.read_csv('scrape.csv')
        logging.info("Loaded existing scrape.csv")
    for link in tqdm(listing_links, desc="Fetching home data"):
        home_url = f"https://www.withroam.com{link}"

        if home_url in df['url'].values:
            logging.info(f"Skipping already processed link: {link}")
            continue

        # Check if the file already exists in cache
        home_filename = f"cache/{home_url.split('/')[-1]}.html"
        if os.path.exists(home_filename):
            logging.info(f"Using cached file: {home_filename}")
            with open(home_filename, 'r', encoding='utf-8') as f:
                html = f.read()
        else:
            logging.info(f"Fetching data for home: {home_url}")
            # Fetch the HTML content
            # If headers.txt is not found, it will proceed without custom headers
            html = fetch_html(home_url)

        # Save each html to a file cache/{home_url}.html
        home_filename = f"cache/{home_url.split('/')[-1]}.html"
        os.makedirs(os.path.dirname(home_filename), exist_ok=True)
        with open(home_filename, 'w', encoding='utf-8') as f:
            f.write(html)

        # Process the HTML content as needed
        logging.info(f"Fetched data for home: {home_url}")

        listing_data = parse_listing_html(html)
        details = {}
        for class_ in ['loan-feature', 'home-feature']:
            details[class_] = parse_details(html, class_=class_)
        financials = get_financials(html)
        description = get_description(html)
        contains_dock = contains_str(description, 'dock')

        if verbose:
            print(json.dumps(listing_data, indent=2))
            print(json.dumps(details, indent=2))
            print(json.dumps(financials, indent=2))
            print(description)
            print(f"Contains dock: {contains_dock}")

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
        _df_ = pd.DataFrame([record], columns=columns)
        df = pd.concat([df, _df_], ignore_index=True)
        print(df)
        df.to_csv('scrape.csv', index=False)