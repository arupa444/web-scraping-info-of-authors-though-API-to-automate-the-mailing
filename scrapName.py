import sys
import requests
import time
import re
import xml.etree.ElementTree as ET
from urllib.parse import quote
import csv

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

def search_pubmed_authors_with_emails(search_term, max_authors=1000):
    """
    Search for authors with emails in PubMed related to a specific topic.
    Only includes authors that have at least one email address.
    """
    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
    
    
    search_url = f"{base_url}esearch.fcgi?db=pubmed&term={quote(search_term)}&retmode=json&retmax=1000"
    
    try:
        response = requests.get(search_url)
        response.raise_for_status()
        data = response.json()
        
        article_ids = data.get("esearchresult", {}).get("idlist", [])
        if not article_ids:
            print("No articles found for the search term.")
            return []
            
        print(f"Found {len(article_ids)} articles. Fetching detailed author information...")
        
        
        authors_data = []
        processed_with_emails = 0
        total_processed = 0
        
        
        batch_size = 50
        for i in range(0, len(article_ids), batch_size):
            batch_ids = article_ids[i:i+batch_size]
            
            
            details_url = f"{base_url}efetch.fcgi?db=pubmed&id={','.join(batch_ids)}&retmode=xml"
            details_response = requests.get(details_url)
            details_response.raise_for_status()
            
            
            root = ET.fromstring(details_response.text)
            
            
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
            
            
            time.sleep(1)
            
            
            print(f"Processed {min(i + batch_size, len(article_ids))} of {len(article_ids)} articles. "
                  f"Found {processed_with_emails} authors with emails so far.")
        
        print(f"Total authors processed: {total_processed}")
        print(f"Authors with emails: {processed_with_emails}")
        
        return authors_data[:max_authors]
        
    except Exception as e:
        print(f"Error searching PubMed: {e}")
        return []

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python pubmed_search.py \"search term\"")
        sys.exit(1)
    
    search_term = sys.argv[1]
    print(f"Searching PubMed for authors with emails related to: {search_term}")
    
    authors_data = search_pubmed_authors_with_emails(search_term, max_authors=1000)
    
    print(f"\nFound {len(authors_data)} authors with emails:")
    for i, author in enumerate(authors_data, 1):
        print(f"\n{i}. {author['name']}")
        print(f"   Journal: {author['journal']}")
        print(f"   Article: {author['article_title'][:80]}{'...' if len(author['article_title']) > 80 else ''}")
        print(f"   Emails: {', '.join(author['emails'])}")
    
    
    if authors_data:
        
        safe_filename = re.sub(r'[^\w\s-]', '', search_term).strip().replace(' ', '_')
        csv_filename = f"{safe_filename}_authors_with_emails.csv"
        export_to_csv(authors_data, csv_filename)