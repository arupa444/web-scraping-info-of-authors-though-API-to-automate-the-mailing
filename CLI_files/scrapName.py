import sys
import requests
import time
import re
import xml.etree.ElementTree as ET
from urllib.parse import quote
import csv
from datetime import datetime


def extract_emails(text):
    """Extract email addresses from text using regex"""
    if not text:
        return []
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    return re.findall(email_pattern, text)


def export_to_csv(data, filename):
    """Export author data to CSV file"""
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['name', 'journal', 'article_title', 'emails', 'affiliations']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        for author in data:
            emails_str = '; '.join(author['emails']) if author['emails'] else ''
            affiliations_str = '; '.join(author['affiliations']) if author['affiliations'] else ''

            writer.writerow({
                'name': author['name'],
                'journal': author['journal'],
                'article_title': author['article_title'],
                'emails': emails_str,
                'affiliations': affiliations_str
            })
    print(f"Data exported to {filename}")


def make_request_with_retry(url, max_retries=3, delay=1):
    """Make a request with retry logic"""
    for attempt in range(max_retries):
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            return response
        except (requests.exceptions.RequestException, requests.exceptions.Timeout) as e:
            print(f"Request attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(delay * (2 ** attempt))  # Exponential backoff
            else:
                raise


def search_pubmed_authors_with_emails(search_term, max_authors=10000):
    """
    Search for authors with emails in PubMed related to a specific topic.
    Only includes authors that have at least one email address.
    Only searches articles from the last 5 years.
    """
    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"

    # Calculate date range for last 5 years
    current_year = datetime.now().year
    start_year = current_year - 4  # 5 years including current year
    date_filter = f'"{start_year}/01/01"[Date - Publication] : "{current_year}/12/31"[Date - Publication]'

    # Combine search term with date filter
    full_search_term = f"{search_term} AND {date_filter}"

    search_url = f"{base_url}esearch.fcgi?db=pubmed&term={quote(full_search_term)}&retmode=json&retmax=10000"

    try:
        response = make_request_with_retry(search_url)
        data = response.json()

        article_ids = data.get("esearchresult", {}).get("idlist", [])
        if not article_ids:
            print("No articles found for the search term within the last 5 years.")
            return []

        print(f"Found {len(article_ids)} articles from the last 5 years. Fetching detailed author information...")

        authors_data = []
        processed_with_emails = 0
        total_processed = 0

        # Reduced batch size to prevent connection issues
        batch_size = 200
        for i in range(0, len(article_ids), batch_size):
            batch_ids = article_ids[i:i + batch_size]

            details_url = f"{base_url}efetch.fcgi?db=pubmed&id={','.join(batch_ids)}&retmode=xml"

            try:
                details_response = make_request_with_retry(details_url)

                try:
                    root = ET.fromstring(details_response.text)
                except ET.ParseError as e:
                    print(f"XML parsing error for batch {i // batch_size + 1}: {e}")
                    continue

                ns = {
                    'pubmed': 'https://www.ncbi.nlm.nih.gov/pubmed/',
                    'xsi': 'http://www.w3.org/2001/XMLSchema-instance'
                }

                for article in root.findall('.//PubmedArticle', ns):
                    if processed_with_emails >= max_authors:
                        break

                    journal_element = article.find('.//Journal', ns)
                    journal_name = "Unknown Journal"

                    if journal_element is not None:
                        title_element = journal_element.find('Title', ns)
                        if title_element is not None and title_element.text:
                            journal_name = title_element.text

                    article_title = "Unknown Article"
                    title_element = article.find('.//ArticleTitle', ns)
                    if title_element is not None and title_element.text:
                        article_title = title_element.text

                    for author in article.findall('.//Author', ns):
                        if processed_with_emails >= max_authors:
                            break

                        last_name = author.find('LastName', ns)
                        fore_name = author.find('ForeName', ns)
                        if last_name is not None and fore_name is not None:
                            author_name = f"{fore_name.text} {last_name.text}"
                        else:
                            collective_name = author.find('CollectiveName', ns)
                            author_name = collective_name.text if collective_name is not None else "Unknown Author"

                        affiliations = []
                        emails = []

                        for affiliation_info in author.findall('.//AffiliationInfo', ns):
                            affiliation = affiliation_info.find('Affiliation', ns)
                            if affiliation is not None:
                                affiliations.append(affiliation.text)
                                emails.extend(extract_emails(affiliation.text))

                        emails = list(set(emails))
                        total_processed += 1

                        if emails:
                            authors_data.append({
                                'name': author_name,
                                'emails': emails,
                                'affiliations': affiliations,
                                'journal': journal_name,
                                'article_title': article_title
                            })
                            processed_with_emails += 1

                # Increased sleep time between requests
                time.sleep(0.5)

                print(f"Processed {min(i + batch_size, len(article_ids))} of {len(article_ids)} articles. "
                      f"Found {processed_with_emails} authors with emails so far.")

            except Exception as e:
                print(f"Error processing batch {i // batch_size + 1}: {e}")
                # Continue with next batch instead of stopping completely
                continue

        print(f"Total authors processed: {total_processed}")
        print(f"Authors with emails: {processed_with_emails}")

        return authors_data[:max_authors]

    except Exception as e:
        print(f"Error searching PubMed: {e}")
        return []


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scrapName.py \"search term\"")
        sys.exit(1)

    search_term = sys.argv[1]
    print(f"Searching PubMed for authors with emails related to: {search_term}")
    print("Only searching articles published in the last 5 years...")

    authors_data = search_pubmed_authors_with_emails(search_term, max_authors=10000)

    print(f"\nFound {len(authors_data)} authors with emails:")
    for i, author in enumerate(authors_data[:10], 1):  # Only show first 10 to avoid flooding console
        print(f"\n{i}. {author['name']}")
        print(f"   Journal: {author['journal']}")
        print(f"   Article: {author['article_title'][:80]}{'...' if len(author['article_title']) > 80 else ''}")
        print(f"   Emails: {', '.join(author['emails'])}")

    if len(authors_data) > 10:
        print(f"\n... and {len(authors_data) - 10} more authors with emails.")

    if authors_data:
        safe_filename = re.sub(r'[^\w\s-]', '', search_term).strip().replace(' ', '_')
        csv_filename = f"{safe_filename}_authors_with_emails.csv"
        export_to_csv(authors_data, csv_filename)
