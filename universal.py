from fastapi import FastAPI, APIRouter, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.templating import Jinja2Templates
from pydantic import EmailStr
from typing import Annotated, Literal, Optional, List, Dict

from pydantic import BaseModel, Field, field_validator, computed_field, AnyUrl, EmailStr
import requests
from urllib.parse import quote
import xml.etree.ElementTree as ET

import csv
import smtplib
import time
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
import re
import os
import dns.resolver
from datetime import datetime
import tempfile
import shutil
import gc
import psutil
import socket

from dotenv import load_dotenv
load_dotenv()

app = FastAPI(title="Email Tools Application for Pulsus")




class SendEndpoint(BaseModel):
    csv_file: Annotated[UploadFile, File(..., title="CSV File", description="Upload the CSV File...")]
    email_template_file: Annotated[UploadFile, File(..., title="Email Template", description="Upload the Email Template...")]
    subjectForEmail: Annotated[str, Form(..., title="Subject for email", description="Enter the subject for the email...")]
    sender_email: Annotated[EmailStr, Form(..., title="Sender's email", description="Enter the sender's email...")]
    sender_name: Annotated[str, Form(..., title="Sender's name", description="Enter the sender's name...")]
    sender_password: Annotated[str, Form(..., title="Sender's email password", description="Enter the sender's email password...")]
    smtp_server_option: Annotated[str, Form(..., title="SMTP server Option", description="Select the SMTP Server...")]
    custom_smtp_server: Annotated[Optional[str], Form(default=None,title="Custom SMTP server", description="Enter the custom SMTP server...")]
    smtp_port_option: Annotated[str, Form(...,title="SMTP port option...", description="Select the SMTP port...")]
    custom_smtp_port: Annotated[Optional[str], Form(default=None, title="Custom SMTP Port...", description="Enter a custom SMTP Port...")]
    max_emails: Annotated[int, Form(..., title="Max Email to send", description="Enter a int which gonna limit the email sharing...")]
    delay: Annotated[int, Form(default=5, title="The delay inbetween two mails", description="Enter the delay you want to create which gonna reflect inbetween two mail sending...")]


class ScrapeEmail(BaseModel):
    search_term: Annotated[str, Field(..., title="Search Term", description="Enter the Search Term...")]
    max_authors: Annotated[Optional[int], Field(default=10000, title="Maximum authors to search", description="Enter The No. of authors you want to search...")]


class FilterEmail(BaseModel):
    csv_file: UploadFile = File(..., title="CSV File", description="Upload the CSV File")
    sender_email: EmailStr = Form(..., title="Sender's email", description="Enter the sender's email")
    resume: bool = Form(False, title="Resume the steps", description="Resume from last checkpoint")

@app.get("/", response_class=HTMLResponse, summary="Serve the email sender HTML form")
def get_email_form(request: Request):
    return templates.TemplateResponse("upload_form.html", {"request": request, "active_page": "sender"})

@app.get("/email-filter", response_class=HTMLResponse, summary="Serve the email filter HTML form")
def get_email_filter_form(request: Request):
    return templates.TemplateResponse("email_filter.html", {"request": request, "active_page": "filter"})

@app.get("/email-scraper", response_class=HTMLResponse, summary="Serve the email scraper HTML form")
def get_email_scraper_form(request: Request):
    return templates.TemplateResponse("email_scraper.html", {"request": request, "active_page": "scraper"})



# Configure Jinja2Templates to find templates in the "templates" directory
templates = Jinja2Templates(directory="templates")

# ====================================================================
# Utility Functions
# ====================================================================

def log_memory_usage():
    """Log current memory usage"""
    process = psutil.Process(os.getpid())
    memory_info = process.memory_info()
    print(f"Memory usage: {memory_info.rss / 1024 / 1024:.2f} MB")

# ====================================================================
# Email Sending and Validation Functions
# ====================================================================

# def send_email(
#     row: Dict,  
#     subjectForEmail: str,
#     sender_email: str,
#     sender_name: str,
#     sender_password: str,
#     recipient_name: str,
#     recipient_email: str,
#     smtp_server: str,
#     smtp_port: int,
#     template_content: str
# ) -> tuple[bool, str]:
#     """Send a personalized email to an author using HTML template."""
#     html = template_content.format(**row)
#     formatted_subject = subjectForEmail.format(**row)

#     msg = MIMEMultipart('alternative')
#     msg['Subject'] = formatted_subject
#     msg['From'] = formataddr((sender_name, sender_email))
#     msg['To'] = formataddr((recipient_name, recipient_email))
#     msg.attach(MIMEText(html, 'html'))
    

#     try:
#         if smtp_server in ["smtp.gmail.com", "smtp.office365.com", "smtp.mail.yahoo.com"]:
#             context = ssl.create_default_context()
#         else:
#             context = ssl.create_default_context()
#             context.check_hostname = False
#             context.verify_mode = ssl.CERT_NONE
        
#         with smtplib.SMTP(smtp_server, smtp_port) as server:
#             server.starttls(context=context)
#             server.login(sender_email, sender_password)
#             server.sendmail(sender_email, recipient_email, msg.as_string())
#         return True, "Email sent successfully"
#     except smtplib.SMTPAuthenticationError:
#         return False, "Authentication failed. Check your email and password."
#     except smtplib.SMTPConnectError as e:
#         return False, f"Could not connect to SMTP server '{smtp_server}:{smtp_port}': {e}"
#     except smtplib.SMTPRecipientsRefused:
#         return False, "Recipient email address refused by the SMTP server."
#     except Exception as e:
#         return False, str(e)

def send_email(
    row: Dict,
    subjectForEmail: str,
    sender_email: str,
    sender_name: str,
    sender_password: str,
    recipient_name: str,
    recipient_email: str,
    smtp_server: str,
    smtp_port: int,
    template_content: str
) -> tuple[bool, str]:
    """Send a personalized email to an author using HTML template."""
    html = template_content.format(**row)
    formatted_subject = subjectForEmail.format(**row)

    msg = MIMEMultipart('alternative')
    msg['Subject'] = formatted_subject
    msg['From'] = formataddr((sender_name, sender_email))
    msg['To'] = formataddr((recipient_name, recipient_email))
    msg.attach(MIMEText(html, 'html'))

    try:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

        if smtp_port == 465:
            print("inside 465")
            # Use SMTPS for implicit SSL on port 465
            with smtplib.SMTP_SSL(smtp_server, smtp_port, context=context) as server:
                server.login(sender_email, sender_password)
                server.sendmail(sender_email, recipient_email, msg.as_string())
        else:
            # Use SMTP for STARTTLS on other ports (like 587, 25)
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls(context=context)
                server.login(sender_email, sender_password)
                server.sendmail(sender_email, recipient_email, msg.as_string())

        return True, "Email sent successfully"
    except smtplib.SMTPAuthenticationError:
        return False, "Authentication failed. Check your email and password. For services like Gmail or Outlook with 2FA, you might need to use an App-Specific Password instead of your regular password."
    except smtplib.SMTPConnectError as e:
        return False, f"Could not connect to SMTP server '{smtp_server}:{smtp_port}'. Please check the server address and port, and ensure they are accessible from where this application is hosted. Error: {e}"
    except smtplib.SMTPRecipientsRefused:
        return False, "Recipient email address refused by the SMTP server. This could be due to an invalid recipient email, or the sender's email (yours) being blocked or having misconfigured SPF/DKIM/DMARC records."
    except smtplib.SMTPServerDisconnected as e:
        return False, f"SMTP server disconnected unexpectedly. This can happen with incorrect server/port settings, or if the server closes the connection due to security policy or activity. Error: {e}"
    except ssl.SSLError as e:
        return False, f"SSL/TLS error during connection. This might indicate issues with the server's security certificate, an unsupported TLS version, or a handshake failure. Error: {e}"
    except ConnectionRefusedError:
        return False, f"Connection refused by the SMTP server at '{smtp_server}:{smtp_port}'. This often means the server is not running, or a firewall is blocking the connection from your end."
    except socket.gaierror as e: # Catch "getaddress" (hostname resolution) errors
        return False, f"Hostname resolution error for SMTP server '{smtp_server}'. The server address might be incorrect or there could be a DNS issue. Error: {e}"
    except Exception as e:
        return False, f"An unexpected error occurred during email sending: {e}. Please review your SMTP settings or try again."

# EMAIL VALIDATION FUNCTIONS
def is_valid_syntax(email: str) -> bool:
    """Check if email has valid syntax."""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def has_mx_record(domain: str) -> bool:
    """Check if domain has MX record with retry logic."""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # Use different DNS resolvers for redundancy
            resolvers = ['8.8.8.8', '1.1.1.1', '208.67.222.222']
            resolver = dns.resolver.Resolver()
            resolver.nameservers = resolvers
            resolver.timeout = 5
            resolver.lifetime = 10
            
            records = resolver.resolve(domain, 'MX')
            return bool(records)
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.Timeout):
            if attempt == max_retries - 1:
                return False
            time.sleep(1)
        except Exception as e:
            print(f"Error checking MX record for {domain}: {e}")
            if attempt == max_retries - 1:
                return False
            time.sleep(1)
    return False

def validate_email(email: str) -> str:
    """Comprehensive email validation."""
    if not is_valid_syntax(email):
        return "Invalid syntax"

    domain = email.split('@')[1]
    if not has_mx_record(domain):
        return "Domain not found / no MX record"

    return "Deliverable"

async def process_csv_and_send_emails(
    subjectForEmail: str,
    csv_file_path: str,
    sender_email: str,
    sender_name: str,
    sender_password: str,
    smtp_server: str,
    smtp_port: int,
    template_content: str,
    max_emails: int,
    delay: int = 5
) -> tuple[list[dict], dict, Optional[str]]:
    """Process CSV file and send emails to authors."""
    results = []
    validation_stats = {
        "valid_syntax": 0,
        "has_mx": 0,
        "deliverable": 0,
        "failed_validation": 0
    }
    processing_error = None

    try:
        with open(csv_file_path, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            csv_rows = list(reader)
            
            if max_emails == 0:
                max_emails_actual = len(csv_rows)
            else:
                max_emails_actual = len(csv_rows) if max_emails is None else min(max_emails, len(csv_rows))

            print(f"\nStarting to process {max_emails_actual} emails with {delay} second delays...")

            for i, row in enumerate(csv_rows):
                if i >= max_emails_actual:
                    break

                required_cols = ['name', 'emails']
                if not all(k in row for k in required_cols):
                    raise ValueError(f"CSV row {i+1} is missing required columns. Expected: {', '.join(required_cols)}. Row data: {row}")
                
                name = row['name']
                emails = row['emails']
                
                emails_list = [e.strip() for e in emails.split(';') if e.strip()]

                print(f"\nProcessing row {i + 1}/{max_emails_actual}: {name}")

                for email in emails_list:
                    if not email:
                        continue

                    print(f"  Validating: {email}")
                    validation_result_msg = validate_email(email)

                    if validation_result_msg == "Invalid syntax":
                        validation_stats["failed_validation"] += 1
                    elif validation_result_msg == "Domain not found / no MX record":
                        validation_stats["failed_validation"] += 1
                    elif validation_result_msg == "Deliverable":
                        validation_stats["deliverable"] += 1
                        validation_stats["has_mx"] += 1
                        validation_stats["valid_syntax"] += 1
                    else:
                        validation_stats["failed_validation"] += 1

                    if validation_result_msg != "Deliverable":
                        print(f"    ✗ Skipped - {validation_result_msg}")
                        results.append({
                            'name': name,
                            'email': email,
                            'success': False,
                            'message': f"Validation failed: {validation_result_msg}"
                        })
                        continue

                    print(f"    ✓ Valid - Attempting to send email to {email} via {smtp_server}:{smtp_port}...")

                    success, message = send_email(
                        row, subjectForEmail, sender_email, sender_name, sender_password, name, email, smtp_server, smtp_port, template_content
                    )

                    result = {
                        'name': name,
                        'email': email,
                        'success': success,
                        'message': message
                    }
                    results.append(result)

                    if success:
                        print(f"    ✓ Email sent successfully to {email}")
                    else:
                        print(f"    ✗ Failed to send to {email}: {message}")

                if i < max_emails_actual - 1 and delay > 0:
                    print(f"\nWaiting {delay} seconds before processing next row...")
                    time.sleep(delay)

    except FileNotFoundError:
        processing_error = f"CSV file not found at {csv_file_path}"
    except KeyError as e:
        processing_error = f"Missing expected CSV column: {e}. Ensure CSV has 'name', 'emails'."
    except ValueError as e:
        processing_error = f"CSV data error: {e}"
    except Exception as e:
        processing_error = f"An unexpected error occurred during CSV processing or email sending: {e}"

    return results, validation_stats, processing_error

def display_summary(results: list[dict], validation_stats: dict) -> dict:
    """Generate a comprehensive summary dictionary of the email sending process."""
    summary = {}

    summary["validation_results"] = {
        "valid_syntax_checked": validation_stats['valid_syntax'],
        "has_mx_record_checked": validation_stats['has_mx'],
        "passed_all_pre_send_validation": validation_stats['deliverable'],
        "failed_pre_send_validation": validation_stats['failed_validation']
    }

    total_attempted_sends = len(results)
    success_count = sum(1 for r in results if r['success'])
    failed_to_send_count = total_attempted_sends - success_count

    summary["sending_results"] = {
        "total_emails_processed_from_csv": total_attempted_sends,
        "successfully_sent": success_count,
        "failed_to_send": failed_to_send_count
    }

    if failed_to_send_count > 0:
        failure_reasons = {}
        for r in results:
            if not r['success']:
                reason = r['message']
                failure_reasons[reason] = failure_reasons.get(reason, 0) + 1
        summary["failure_breakdown"] = failure_reasons

    return summary

# ====================================================================
# Email Filter Functions
# ====================================================================

def is_valid_syntax_filter(email):
    """Check if email has valid syntax"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def has_mx_record_filter(domain):
    """Check if domain has MX record"""
    try:
        records = dns.resolver.resolve(domain, 'MX', lifetime=5)
        return bool(records)
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.Timeout):
        return False

def check_smtp_filter(email, sender_email):
    """Check if SMTP server accepts the email"""
    domain = email.split('@')[1]
    try:
        mx_records = dns.resolver.resolve(domain, 'MX', lifetime=5)
        mx_record = str(mx_records[0].exchange)

        server = smtplib.SMTP(timeout=10)
        server.set_debuglevel(0)
        server.connect(mx_record)
        server.helo(server.local_hostname)
        server.mail(sender_email)
        code, message = server.rcpt(email)
        server.quit()

        return code == 250
    except Exception as e:
        return False

def validate_email_filter(email, sender_email):
    if not is_valid_syntax_filter(email):
        return "Invalid syntax"

    domain = email.split('@')[1]
    if not has_mx_record_filter(domain):
        return "Domain not found / no MX record"

    if check_smtp_filter(email, sender_email):
        return "Deliverable"
    else:
        return "Non-deliverable"

def process_csv_file_filter(input_path, sender_email, checkpoint_file=None):
    # Generate output filename
    base_name = os.path.basename(input_path)
    file_name, file_ext = os.path.splitext(base_name)
    output_path = f"filtered_{file_name}{file_ext}"
    
    # Create checkpoint file if not provided
    if checkpoint_file is None:
        checkpoint_file = f"{file_name}_checkpoint.txt"
    
    # Load checkpoint if exists
    processed_rows = 0
    if os.path.exists(checkpoint_file):
        with open(checkpoint_file, 'r') as f:
            try:
                processed_rows = int(f.read().strip())
                print(f"Resuming from row {processed_rows}")
            except:
                processed_rows = 0
    
    print(f"Processing file: {input_path}")
    print(f"Output will be saved to: {output_path}")
    print(f"Checkpoint file: {checkpoint_file}")

    with open(input_path, 'r', newline='', encoding='utf-8') as infile, \
            open(output_path, 'a' if processed_rows > 0 else 'w', newline='', encoding='utf-8') as outfile:

        reader = csv.DictReader(infile)
        fieldnames = reader.fieldnames
        
        # Write header if starting fresh
        if processed_rows == 0:
            writer = csv.DictWriter(outfile, fieldnames=fieldnames)
            writer.writeheader()
        else:
            writer = csv.DictWriter(outfile, fieldnames=fieldnames)
            # Skip already processed rows
            for _ in range(processed_rows):
                next(reader)

        total_rows = processed_rows
        deliverable_rows = 0
        skipped_rows = 0

        for row in reader:
            total_rows += 1
            email = row['emails'].strip()

            print(f"Validating email {total_rows}: {email}")
            
            try:
                result = validate_email_filter(email, sender_email)
                print(f"Result: {result}")

                if result == "Deliverable":
                    writer.writerow(row)
                    deliverable_rows += 1
                else:
                    skipped_rows += 1
            except Exception as e:
                print(f"Error validating {email}: {e}")
                skipped_rows += 1
                continue

            # Update checkpoint every 10 rows
            if total_rows % 10 == 0:
                with open(checkpoint_file, 'w') as f:
                    f.write(str(total_rows))
                
                # Progress indicator
                print(f"Processed {total_rows} rows, {deliverable_rows} deliverable, {skipped_rows} skipped")
                log_memory_usage()
                
                # Periodic garbage collection
                if total_rows % 1000 == 0:
                    gc.collect()

    # Clean up checkpoint file when done
    if os.path.exists(checkpoint_file):
        os.remove(checkpoint_file)

    print(f"\nProcessing complete!")
    print(f"Total rows processed: {total_rows}")
    print(f"Deliverable emails found: {deliverable_rows}")
    print(f"Skipped emails: {skipped_rows}")
    print(f"Filtered file saved as: {output_path}")

    return output_path

# ====================================================================
# Email Scraper Functions
# ====================================================================

def extract_emails_scrape(text):
    """Extract email addresses from text using regex"""
    if not text:
        return []
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    return re.findall(email_pattern, text)

def make_request_with_retry_scrape(url, max_retries=3, delay=1):
    """Make a request with retry logic"""
    for attempt in range(max_retries):
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            return response
        except (requests.exceptions.RequestException, requests.exceptions.Timeout) as e:
            print(f"Request attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(delay * (2 ** attempt))
            else:
                raise

def process_batch(batch_ids, details_url, unique_authors, max_authors, current_batch_num, total_batches):
    """Process a batch of article IDs"""
    details_response = make_request_with_retry_scrape(details_url)
    
    try:
        root = ET.fromstring(details_response.text)
    except ET.ParseError as e:
        print(f"XML parsing error: {e}")
        return 0, 0  # Return zeros for counts
    
    ns = {
        'pubmed': 'https://www.ncbi.nlm.nih.gov/pubmed/',
        'xsi': 'http://www.w3.org/2001/XMLSchema-instance'
    }
    
    batch_emails_found = 0
    batch_duplicates_filtered = 0
    total_processed_in_batch = 0
    
    for article in root.findall('.//PubmedArticle', ns):
        # Check if we've reached the maximum number of authors
        current_unique_count = len([k for k in unique_authors if isinstance(unique_authors[k], dict)])
        if current_unique_count >= max_authors:
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
            # Check if we've reached the maximum number of authors
            current_unique_count = len([k for k in unique_authors if isinstance(unique_authors[k], dict)])
            if current_unique_count >= max_authors:
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
                    emails.extend(extract_emails_scrape(affiliation.text))

            emails = list(set(emails))
            total_processed_in_batch += 1

            if emails:
                # Deduplication: Check if we've seen any of these emails before
                is_duplicate = False
                for email in emails:
                    if email in unique_authors:
                        is_duplicate = True
                        batch_duplicates_filtered += 1
                        break
                
                if not is_duplicate:
                    # Add all emails to the tracking set
                    for email in emails:
                        unique_authors[email] = True
                    
                    unique_authors[author_name] = {
                        'name': author_name,
                        'emails': emails,
                        'affiliations': affiliations,
                        'journal': journal_name,
                        'article_title': article_title
                    }
                    batch_emails_found += 1

    time.sleep(1)

    # Calculate progress percentage
    current_total = len([k for k in unique_authors if isinstance(unique_authors[k], dict)])
    progress_percentage = min(100, int((current_total / max_authors) * 100))
    
    print(f"Batch {current_batch_num} | New: {batch_emails_found} | Dups: {batch_duplicates_filtered} | Total: {current_total}/{max_authors} | Progress: {progress_percentage}%")
    
    return total_processed_in_batch, batch_emails_found

def search_pubmed_authors_with_emails_scrape(search_term, max_authors=100000):
    """
    Search for authors with emails in PubMed related to a specific topic.
    Only includes authors that have at least one email address.
    Only searches articles from the last 5 years.
    """
    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"

    # Calculate date range for last 5 years
    current_year = datetime.now().year
    start_year = current_year - 4
    date_filter = f'"{start_year}/01/01"[Date - Publication] : "{current_year}/12/31"[Date - Publication]'

    # Combine search term with date filter
    full_search_term = f"{search_term} AND {date_filter}"

    # Use retmax to get more results - PubMed allows up to 99999 per request
    retmax = 99999  # Always get maximum articles
    search_url = f"{base_url}esearch.fcgi?db=pubmed&term={quote(full_search_term)}&retmode=json&retmax={retmax}"

    try:
        response = make_request_with_retry_scrape(search_url)
        data = response.json()

        article_ids = data.get("esearchresult", {}).get("idlist", [])
        if not article_ids:
            print("No articles found for the search term within the last 5 years.")
            return []

        print(f"Found {len(article_ids)} articles from the last 5 years. Fetching detailed author information...")
        print(f"Maximum authors to retrieve: {max_authors}")
        print("=" * 80)

        # Use a dictionary to track unique authors by email
        unique_authors = {}
        total_processed = 0
        batches_processed = 0

        # Process in smaller batches to avoid URL length issues
        batch_size = 200
        
        for i in range(0, len(article_ids), batch_size):
            # Check if we've reached the maximum number of authors
            current_unique_count = len([k for k in unique_authors if isinstance(unique_authors[k], dict)])
            if current_unique_count >= max_authors:
                print(f"\nReached maximum number of authors ({max_authors}). Stopping.")
                break
                
            batches_processed += 1
            current_batch = batches_processed
            print(f"\nStarting batch {current_batch}")
            
            batch_ids = article_ids[i:i + batch_size]
            
            # Create the URL for this batch
            details_url = f"{base_url}efetch.fcgi?db=pubmed&id={','.join(batch_ids)}&retmode=xml"
            
            # Check URL length to avoid 414 errors
            if len(details_url) > 8000:
                print(f"URL too long ({len(details_url)} chars), splitting into smaller batches")
                sub_batch_size = batch_size // 2
                if sub_batch_size < 10:
                    sub_batch_size = 10
                
                # Process this batch in smaller sub-batches
                for j in range(0, len(batch_ids), sub_batch_size):
                    # Check if we've reached the maximum number of authors
                    current_unique_count = len([k for k in unique_authors if isinstance(unique_authors[k], dict)])
                    if current_unique_count >= max_authors:
                        print(f"\nReached maximum number of authors ({max_authors}). Stopping.")
                        break
                        
                    sub_batch_ids = batch_ids[j:j + sub_batch_size]
                    sub_details_url = f"{base_url}efetch.fcgi?db=pubmed&id={','.join(sub_batch_ids)}&retmode=xml"
                    
                    try:
                        processed_in_sub_batch, new_in_sub_batch = process_batch(
                            sub_batch_ids, sub_details_url, unique_authors, max_authors, 
                            current_batch, 0  # We don't need total_batches for sub-batches
                        )
                        total_processed += processed_in_sub_batch
                    except Exception as e:
                        print(f"Error processing sub-batch {j // sub_batch_size + 1}: {e}")
                        continue
                    
                    # Check after each sub-batch
                    current_unique_count = len([k for k in unique_authors if isinstance(unique_authors[k], dict)])
                    if current_unique_count >= max_authors:
                        print(f"\nReached maximum number of authors ({max_authors}). Stopping.")
                        break
            else:
                try:
                    processed_in_batch, new_in_batch = process_batch(
                        batch_ids, details_url, unique_authors, max_authors, 
                        current_batch, 0  # We don't need total_batches for batches
                    )
                    total_processed += processed_in_batch
                except Exception as e:
                    print(f"Error processing batch {current_batch}: {e}")
                    continue
                
                # Check after each batch
                current_unique_count = len([k for k in unique_authors if isinstance(unique_authors[k], dict)])
                if current_unique_count >= max_authors:
                    print(f"\nReached maximum number of authors ({max_authors}). Stopping.")
                    break

        # Get final counts
        unique_authors_list = [unique_authors[key] for key in unique_authors if isinstance(unique_authors[key], dict)]
        unique_count = len(unique_authors_list)
        duplicate_count = total_processed - unique_count
        
        # Calculate total unique emails
        all_emails = set()
        for author in unique_authors_list:
            for email in author['emails']:
                all_emails.add(email)
        total_unique_emails = len(all_emails)

        print("\n" + "=" * 80)
        print("Scraping completed!")
        print(f"Total articles processed: {len(article_ids)}")
        print(f"Total authors processed: {total_processed}")
        print(f"Unique authors with emails: {unique_count}")
        print(f"Duplicate authors removed: {duplicate_count}")
        print(f"Total unique emails extracted: {total_unique_emails}")
        print(f"Batches processed: {batches_processed}")

        return unique_authors_list

    except Exception as e:
        print(f"Error searching PubMed: {e}")
        return []
    
    
    
def export_to_csv_scrape(data, filename):
    """Export author data to CSV file"""
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['name', 'journal', 'article_title', 'emails', 'affiliations']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        for author in data:
            emails = '; '.join(author['emails']) if author['emails'] else ''
            affiliations_str = '; '.join(author['affiliations']) if author['affiliations'] else ''

            writer.writerow({
                'name': author['name'],
                'journal': author['journal'],
                'article_title': author['article_title'],
                'emails': emails,
                'affiliations': affiliations_str
            })
    print(f"Data exported to {filename}")
    return filename

# ====================================================================
# FastAPI Routers
# ====================================================================

# Email Sender Router

# @app.post("/email-sender/send", summary="Process CSV and send emails")
# async def send_emails_endpoint(
#     csv_file: UploadFile = File(...),
#     email_template_file: UploadFile = File(...),
#     subjectForEmail: str = Form(...),
#     sender_email: EmailStr = Form(...),
#     sender_name: str = Form(...),
#     sender_password: str = Form(...),
#     smtp_server_option: str = Form(...),
#     custom_smtp_server: Optional[str] = Form(None),
#     smtp_port_option: str = Form(...),
#     custom_smtp_port: Optional[str] = Form(None),
#     max_emails: int = Form(...),
#     delay: int = Form(5),
# ):
#     if not csv_file.filename or not csv_file.filename.lower().endswith('.csv'):
#         raise HTTPException(status_code=400, detail="Please upload a valid CSV file.")
#     if not email_template_file.filename or not email_template_file.filename.lower().endswith('.html'):
#         raise HTTPException(status_code=400, detail="Please upload a valid HTML email template file.")

#     # Determine SMTP Server
#     smtp_server = ""
#     if smtp_server_option == "gmail":
#         smtp_server = "smtp.gmail.com"
#     elif smtp_server_option == "outlook":
#         smtp_server = "smtp.office365.com"
#     elif smtp_server_option == "yahoo":
#         smtp_server = "smtp.mail.yahoo.com"
#     elif smtp_server_option == "universal":
#         try:
#             domain = sender_email.split('@')[1]
#             smtp_server = f"smtp.{domain}"
#         except IndexError:
#             raise HTTPException(status_code=400, detail="Invalid sender email format for 'Universal' SMTP server option.")
#     elif smtp_server_option == "other":
#         if not custom_smtp_server:
#             raise HTTPException(status_code=400, detail="Custom SMTP server address is required when 'Other' is selected.")
#         smtp_server = custom_smtp_server
#     else:
#         raise HTTPException(status_code=400, detail="Invalid SMTP server option.")

#     # Determine SMTP Port
#     smtp_port = 0
#     if smtp_port_option == "587":
#         smtp_port = 587
#     elif smtp_port_option == "465":
#         smtp_port = 465
#     elif smtp_port_option == "25":
#         smtp_port = 25
#     elif smtp_port_option == "other":
#         if custom_smtp_port is None:
#             raise HTTPException(status_code=400, detail="Custom SMTP port is required when 'Other' is selected.")
#         smtp_port = custom_smtp_port
#     else:
#         raise HTTPException(status_code=400, detail="Invalid SMTP port option.")


@app.post("/email-sender/send", summary="Process CSV and send emails")
async def send_emails_endpoint(
    csv_file: UploadFile = File(...),
    email_template_file: UploadFile = File(...),
    subjectForEmail: str = Form(...),
    sender_email: EmailStr = Form(...),
    sender_name: str = Form(...),
    sender_password: str = Form(...),
    smtp_server_option: str = Form(...),
    custom_smtp_server: Optional[str] = Form(None),
    smtp_port_option: str = Form(...),
    custom_smtp_port: Optional[str] = Form(None),
    max_emails: int = Form(...),
    delay: int = Form(5),
):
    if not csv_file.filename or not csv_file.filename.lower().endswith('.csv'):
        raise HTTPException(status_code=400, detail="Please upload a valid CSV file.")
    if not email_template_file.filename or not email_template_file.filename.lower().endswith('.html'):
        raise HTTPException(status_code=400, detail="Please upload a valid HTML email template file.")

    # Determine SMTP Server
    smtp_server = ""
    if smtp_server_option == "gmail":
        smtp_server = "smtp.gmail.com"
    elif smtp_server_option == "outlook":
        smtp_server = "smtp.office365.com"
    elif smtp_server_option == "yahoo":
        smtp_server = "smtp.mail.yahoo.com"
    elif smtp_server_option == "universal":
        try:
            domain = sender_email.split('@')[1]
            try:
                # Attempt to resolve MX records first for robustness
                mx_records = dns.resolver.resolve(domain, 'MX')
                # Take the primary MX record (lowest preference) and remove trailing dot
                smtp_server = str(mx_records[0].exchange).rstrip('.')
                print(f"Determined SMTP server for {domain} via MX record: {smtp_server}")
            except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.Timeout):
                print(f"No MX record found for {domain}, attempting common SMTP patterns.")
                # Fallback to common patterns if no MX record is found
                if "gmail.com" in domain:
                    smtp_server = "smtp.gmail.com"
                elif any(d in domain for d in ["outlook.com", "hotmail.com", "live.com"]):
                    smtp_server = "smtp.office365.com"
                elif "yahoo.com" in domain:
                    smtp_server = "smtp.mail.yahoo.com"
                else:
                    # Generic fallback; for many smaller hosts, smtp.domain or mail.domain works
                    # If this still fails, the user will need to use 'Other'
                    smtp_server = f"smtp.{domain}"
                print(f"Guessed SMTP server for {domain}: {smtp_server}")

            if not smtp_server:
                 raise HTTPException(status_code=400, detail=f"Could not automatically determine SMTP server for '{domain}'. Please use 'Other' option to specify it manually.")

        except IndexError:
            raise HTTPException(status_code=400, detail="Invalid sender email format for 'Universal' SMTP server option.")
    elif smtp_server_option == "other":
        if not custom_smtp_server:
            raise HTTPException(status_code=400, detail="Custom SMTP server address is required when 'Other' is selected.")
        smtp_server = custom_smtp_server
    else:
        raise HTTPException(status_code=400, detail="Invalid SMTP server option.")

    # Determine SMTP Port
    smtp_port = 0
    if smtp_port_option == "587":
        smtp_port = 587
    elif smtp_port_option == "465":
        smtp_port = 465
    elif smtp_port_option == "25":
        smtp_port = 25
    elif smtp_port_option == "other":
        if not custom_smtp_port: # Use 'not custom_smtp_port' to catch empty strings
            raise HTTPException(status_code=400, detail="Custom SMTP port is required when 'Other' is selected.")
        try:
            smtp_port = int(custom_smtp_port) # Convert to int
        except ValueError:
            raise HTTPException(status_code=400, detail="Custom SMTP port must be a valid integer.")
    else:
        raise HTTPException(status_code=400, detail="Invalid SMTP port option.")

    temp_csv_file_path = None
    email_template_content = None

    try:
        # Read uploaded email template content
        email_template_content = (await email_template_file.read()).decode('utf-8')

        # Save the uploaded CSV to a temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
            shutil.copyfileobj(csv_file.file, tmp)
            temp_csv_file_path = tmp.name

        print(f"Uploaded CSV saved temporarily to: {temp_csv_file_path}")

        # Process emails
        results, validation_stats, processing_error = await process_csv_and_send_emails(
            subjectForEmail=subjectForEmail,
            csv_file_path=temp_csv_file_path,
            sender_email=sender_email,
            sender_name=sender_name,
            sender_password=sender_password,
            smtp_server=smtp_server,
            smtp_port=smtp_port,
            template_content=email_template_content,
            max_emails=max_emails,
            delay=delay
        )

        if processing_error:
            raise HTTPException(status_code=500, detail=processing_error)

        summary = display_summary(results, validation_stats)

        return JSONResponse(content={
            "status": "Email sending process completed.",
            "summary": summary,
        })

    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"An unexpected error occurred in send_emails_endpoint: {e}")
        raise HTTPException(status_code=500, detail=f"An internal server error occurred: {e}")
    finally:
        if temp_csv_file_path and os.path.exists(temp_csv_file_path):
            os.remove(temp_csv_file_path)
            print(f"Temporary CSV file removed: {temp_csv_file_path}")

# Email Filter Router




@app.post("/email-filter/process", summary="Process CSV and filter emails")
async def filter_emails_endpoint(
    csv_file: UploadFile = File(...),
    sender_email: EmailStr = Form(...),
    resume: bool = Form(False)
):
    if not csv_file.filename or not csv_file.filename.lower().endswith('.csv'):
        raise HTTPException(status_code=400, detail="Please upload a valid CSV file.")

    temp_csv_file_path = None
    filtered_file_path = None
    checkpoint_file = None

    try:
        # Save the uploaded CSV to a temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
            shutil.copyfileobj(csv_file.file, tmp)
            temp_csv_file_path = tmp.name

        print(f"Uploaded CSV saved temporarily to: {temp_csv_file_path}")

        # Set up checkpoint file if resuming
        if resume:
            base_name = os.path.basename(temp_csv_file_path)
            file_name, _ = os.path.splitext(base_name)
            checkpoint_file = f"{file_name}_checkpoint.txt"
            
            if not os.path.exists(checkpoint_file):
                raise HTTPException(status_code=400, detail="No checkpoint file found to resume from.")
        
        # Process the CSV file to filter emails
        filtered_file_path = process_csv_file_filter(temp_csv_file_path, sender_email, checkpoint_file)

        # Return the filtered file
        return FileResponse(
            path=filtered_file_path,
            filename=os.path.basename(filtered_file_path),
            media_type='text/csv'
        )

    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"An unexpected error occurred in filter_emails_endpoint: {e}")
        raise HTTPException(status_code=500, detail=f"An internal server error occurred: {e}")
    finally:
        if temp_csv_file_path and os.path.exists(temp_csv_file_path):
            os.remove(temp_csv_file_path)
            print(f"Temporary CSV file removed: {temp_csv_file_path}")

# Email Scraper Router



@app.post("/email-scraper/scrape", summary="Scrape author emails from PubMed")
async def scrape_emails_endpoint(
    search_term: str = Form(...),
    max_authors: int = Form(10000),
):
    try:
        # Scrape author data from PubMed
        authors_data = search_pubmed_authors_with_emails_scrape(search_term, max_authors)
        
        if not authors_data:
            raise HTTPException(status_code=404, detail="No authors with emails found for the search term.")
        
        # Calculate statistics
        unique_authors_count = len(authors_data)
        
        # Calculate total unique emails
        all_emails = set()
        for author in authors_data:
            for email in author['emails']:
                all_emails.add(email)
        total_unique_emails = len(all_emails)
        
        # Generate a safe filename
        safe_filename = re.sub(r'[^\w\s-]', '', search_term).strip().replace(' ', '_')
        csv_filename = f"{safe_filename}_authors_with_emails.csv"
        
        # Create a temporary file to store the CSV data
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv', newline='', encoding='utf-8') as tmp:
            # Export data to CSV
            export_to_csv_scrape(authors_data, tmp.name)
            temp_file_path = tmp.name
        
        # Return the CSV file
        response = FileResponse(
            path=temp_file_path,
            filename=csv_filename,
            media_type='text/csv'
        )
        
        # Add custom success message with statistics
        success_message = f"Successfully extracted {total_unique_emails} unique emails from {unique_authors_count} authors."
        response.headers["X-Success-Message"] = success_message
        
        return response
        
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"An unexpected error occurred in scrape_emails_endpoint: {e}")
        raise HTTPException(status_code=500, detail=f"An internal server error occurred: {e}")
