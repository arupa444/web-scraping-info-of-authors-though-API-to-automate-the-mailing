from fastapi import FastAPI, APIRouter, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.templating import Jinja2Templates
from pydantic import EmailStr
from typing import Annotated, Literal, Optional, List, Dict
import random

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
import os, gc
import pandas as pd
import dns.resolver
from datetime import datetime
import tempfile
import shutil
import gc
import psutil

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
def render_template(rand_template_content: str, row: dict) -> str:
    def replacer(match):
        key = match.group(1)
        return str(row.get(key, "{" + key + "}"))
    return re.sub(r"{(\w+)}", replacer, rand_template_content)


def send_email(
    row: Dict,  
    rand_subjectForEmail: str,
    sender_email: str,
    sender_name: str,
    sender_password: str,
    recipient_name: str,
    recipient_email: str,
    smtp_server: str,
    smtp_port: int,
    rand_template_content: str
) -> tuple[bool, str]:
    """Send a personalized email to an author using HTML template."""
    html = render_template(rand_template_content, row)
    formatted_subject = rand_subjectForEmail.format(**row)

    msg = MIMEMultipart('alternative')
    msg['Subject'] = formatted_subject
    msg['From'] = formataddr((sender_name, sender_email))
    msg['To'] = formataddr((recipient_name, recipient_email))
    msg.attach(MIMEText(html, 'html'))
    

    try:
        if smtp_server in ["smtp.gmail.com", "smtp.office365.com", "smtp.mail.yahoo.com"]:
            context = ssl.create_default_context()
        else:
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls(context=context)
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, recipient_email, msg.as_string())
        return True, "Email sent successfully"
    except smtplib.SMTPAuthenticationError:
        return False, "Authentication failed. Check your email and password."
    except smtplib.SMTPConnectError as e:
        return False, f"Could not connect to SMTP server '{smtp_server}:{smtp_port}': {e}. Try asking your email provider for the correct SMTP settings."
    except smtplib.SMTPRecipientsRefused:
        return True, "Recipient email address refused by the SMTP server. YOUR EMAIL MAY HAVE BEEN BLOCKED."
    except Exception as e:
        return False, str(e)

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

def process_csv_and_send_emails(
    subjectForEmail: List,
    csv_file_path: str, 
    sender_email: str,
    sender_name: str,
    sender_password: str,
    smtp_server: str,
    smtp_port: int,
    template_content: List,
    max_emails: int,
    delay: int = 5,
    original_file_extension: str = '.csv'
) -> tuple[list[dict], dict, Optional[str], Optional[pd.DataFrame]]:
    """Process data file (CSV/Excel) and send emails to authors."""
    results = []
    validation_stats = {
        "valid_syntax": 0,
        "has_mx": 0,
        "deliverable": 0,
        "failed_validation": 0
    }
    processing_error = None
    df = None

    try:
        # Use pandas to read the file based on its extension
        if original_file_extension.lower() == '.csv':
            # Try reading with common encodings if 'utf-8' fails
            try:
                df = pd.read_csv(csv_file_path, encoding='utf-8')
            except UnicodeDecodeError:
                print(f"UTF-8 decode failed for {csv_file_path}, trying 'latin1'...")
                try:
                    df = pd.read_csv(csv_file_path, encoding='latin1')
                except UnicodeDecodeError:
                    print(f"Latin1 decode failed for {csv_file_path}, trying 'cp1252'...")
                    df = pd.read_csv(csv_file_path, encoding='cp1252') # Common for Windows-saved CSVs
            except Exception as e:
                raise ValueError(f"Could not read CSV file {csv_file_path}: {e}")
        elif original_file_extension.lower() in ['.xlsx', '.xls', '.xlsn', '.xlsb', '.xltm', '.xltx']:
            # pandas read_excel can handle different Excel formats
            df = pd.read_excel(csv_file_path)
        else:
            raise ValueError(f"Unsupported file type for processing: {original_file_extension}. Only CSV and Excel files are supported.")

        if df.empty:
            raise ValueError("The uploaded data file is empty or could not be parsed.")

        # Convert DataFrame to a list of dictionaries for consistent row access
        csv_rows = df.to_dict('records')

        if max_emails == 0:
            max_emails_actual = len(csv_rows)
        else:
            max_emails_actual = min(max_emails, len(csv_rows))

        print(f"\nStarting to process {max_emails_actual} emails with {delay} second delays...")

        processed_indices = [] # Keep track of original DataFrame indices of processed rows

        for i, row in enumerate(csv_rows):
            # i here is the index in csv_rows (list of dicts), which corresponds to the DataFrame index
            if i >= max_emails_actual:
                break

            required_cols = ['name', 'emails']
            if not all(k in row for k in required_cols):
                # Using the original DataFrame index + 1 for user-friendly error message
                raise ValueError(f"Row {df.index[i]+1} in the data file is missing required columns. Expected: {', '.join(required_cols)}. Row data: {row}")
            
            name = row['name']
            emails = row['emails']
            
            # Ensure 'emails' is treated as a string before splitting
            emails_list = [e.strip() for e in str(emails).split(';') if e.strip()]

            print(f"\nProcessing row {i + 1}/{max_emails_actual}: {name}")

            row_had_any_email_attempted = False # Flag to mark if any email from this row was attempted
            for email in emails_list:
                if not email:
                    continue
                
                row_had_any_email_attempted = True

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
                else: # Catch-all for other validation failures
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
                filename, rand_template_content = random.choice(template_content)
                print(f"    Using template: {filename}")
                
                rand_subjectForEmail = random.choice(subjectForEmail)
                print(f"    Using subject: {rand_subjectForEmail}")

                success, message = send_email(
                    row, rand_subjectForEmail, sender_email, sender_name, sender_password, name, email, smtp_server, smtp_port, rand_template_content
                )
                
                result = {
                    'name': name,
                    'email': email,
                    'success': success,
                    'message': message
                }
                results.append(result)
                if success:
                    print(f"    ✓ Email sent successfully to {email}: {message}")
                else:
                    print(f"    ✗ Failed to send to {email}: {message}")
                    break # Stop further attempts for this row if sending fails
            
            if not success:
                break
            # If any email from this row was processed (attempted to send after validation)
            # then mark this row as processed to remove it from the remaining DataFrame.
            if row_had_any_email_attempted:
                processed_indices.append(df.index[i]) # Get the original DataFrame index

            if i < max_emails_actual - 1 and delay > 0:
                print(f"\nWaiting {delay} seconds before processing next row...")
                time.sleep(delay)

        # Create a DataFrame of remaining rows by dropping the processed ones
        if df is not None:
            # Drop rows by their original indices
            remaining_df = df.drop(index=processed_indices)
            remaining_df = remaining_df.reset_index(drop=True) # Reset index for a clean DataFrame
        else:
            remaining_df = pd.DataFrame() # Return empty DataFrame if df was never initialized

    except FileNotFoundError:
        processing_error = f"Data file not found at {csv_file_path}"
        remaining_df = pd.DataFrame()
    except KeyError as e:
        processing_error = f"Missing expected column in data file: {e}. Ensure file has 'name' and 'emails'."
        remaining_df = pd.DataFrame()
    except ValueError as e:
        processing_error = f"Data processing error: {e}"
        remaining_df = pd.DataFrame()
    except Exception as e:
        processing_error = f"An unexpected error occurred during data processing or email sending: {e}"
        remaining_df = pd.DataFrame()

    return results, validation_stats, processing_error, remaining_df

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

def process_csv_file_filter(input_path: str, sender_email: str, checkpoint_file: str = None) -> str:
    """
    Processes a CSV or Excel file, filters emails based on validation,
    and saves deliverable emails to a new CSV. Supports resuming processing from a checkpoint.

    Args:
        input_path (str): The path to the input CSV or Excel file.
        sender_email (str): The sender email to be used in validation logic.
        checkpoint_file (str, optional): Path to a checkpoint file for resuming.
                                         If None, a default filename will be generated.

    Returns:
        str: The path to the filtered output CSV file.

    Raises:
        HTTPException: If the file cannot be read, lacks an 'emails' column, or is an unsupported type.
    """
    
    base_name = os.path.basename(input_path)
    file_name, file_ext = os.path.splitext(base_name)
    output_path = f"filtered_{file_name}.csv" # Filtered output is always a CSV

    if checkpoint_file is None:
        checkpoint_file = f"{file_name}_checkpoint.txt"

    initial_processed_rows_from_checkpoint = 0
    if os.path.exists(checkpoint_file):
        with open(checkpoint_file, 'r') as f:
            try:
                initial_processed_rows_from_checkpoint = int(f.read().strip())
                print(f"Resuming from row {initial_processed_rows_from_checkpoint} based on checkpoint.")
            except ValueError: # Handle cases where checkpoint file might be empty or malformed
                initial_processed_rows_from_checkpoint = 0
                print(f"Checkpoint file corrupted or empty, starting processing from row 0.")
    
    # Counters for the current processing session
    deliverable_rows_current_session = 0
    skipped_rows_current_session = 0

    print(f"Processing file: {input_path}")
    print(f"Output will be saved to: {output_path}")
    print(f"Checkpoint file: {checkpoint_file}")

    df = None
    # Common encodings to try for CSV files
    encodings_to_try = ['utf-8', 'latin-1', 'cp1252'] 

    # Attempt to read the input file using pandas
    if file_ext.lower() == '.csv':
        for encoding in encodings_to_try:
            try:
                # pandas' encoding_errors='ignore' helps with decoding issues directly
                df = pd.read_csv(input_path, encoding=encoding, encoding_errors='ignore')
                print(f"Successfully read CSV file with encoding: {encoding}")
                break # Exit loop if reading is successful
            except Exception as e:
                print(f"Failed to read CSV with encoding {encoding}: {e}")
                df = None # Ensure df is None if current encoding attempt fails
        if df is None: # If all CSV encoding attempts failed
            raise HTTPException(status_code=400, detail="Could not read the CSV file with any common encoding. Please check file encoding.")
    elif file_ext.lower() in ['.xlsx', '.xls', '.xlsn', '.xlsb', '.xltm', '.xltx']:
        try:
            df = pd.read_excel(input_path)
            print(f"Successfully read Excel file.")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Could not read the Excel file: {e}. Please ensure it's a valid Excel format.")
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {file_ext}. Only CSV and Excel files are supported.")
    
    if 'emails' not in df.columns:
        raise HTTPException(status_code=400, detail="The input file must contain an 'emails' column.")

    deliverable_rows_list_for_this_session = [] # To store new deliverable rows processed in this session

    # Determine overall counts (from previous runs + current run)
    overall_deliverable_count_at_start = 0
    overall_skipped_count_at_start = 0

    if initial_processed_rows_from_checkpoint > 0 and os.path.exists(output_path):
        try:
            existing_filtered_df = pd.read_csv(output_path, encoding='utf-8')
            overall_deliverable_count_at_start = len(existing_filtered_df)
            # Estimate skipped rows from checkpoint, assuming consistency
            overall_skipped_count_at_start = initial_processed_rows_from_checkpoint - overall_deliverable_count_at_start
            if overall_skipped_count_at_start < 0: # Safety check for potential inconsistencies
                overall_skipped_count_at_start = 0
            print(f"Restored: {overall_deliverable_count_at_start} deliverable rows and estimated {overall_skipped_count_at_start} skipped rows from previous runs.")
        except Exception as e:
            print(f"Warning: Could not read existing filtered file {output_path} to restore counts: {e}. Starting deliverable/skipped count from 0 for previous runs.")

    total_rows_in_input = len(df)

    # Iterate only over the rows that haven't been processed yet
    # `index` here is the original 0-based index from the DataFrame
    for index, row in df.iloc[initial_processed_rows_from_checkpoint:].iterrows():
        current_global_row_number = index + 1 # 1-based row number for user-friendly progress/checkpointing

        # Ensure 'emails' column value is a string; handles potential NaN gracefully
        email = str(row['emails']).strip() 
        
        try:
            result = validate_email_filter(email, sender_email)

            if result == "Deliverable":
                deliverable_rows_list_for_this_session.append(row.to_dict())
                deliverable_rows_current_session += 1
            else:
                skipped_rows_current_session += 1
        except Exception as e:
            print(f"Error validating email at row {current_global_row_number} (email: '{email}'): {e}")
            skipped_rows_current_session += 1
            continue

        # Update checkpoint every 10 rows for progress
        if current_global_row_number % 10 == 0:
            with open(checkpoint_file, 'w') as f:
                f.write(str(current_global_row_number))
            
            current_total_deliverable = overall_deliverable_count_at_start + deliverable_rows_current_session
            current_total_skipped = overall_skipped_count_at_start + skipped_rows_current_session
            print(f"Progress: Processed {current_global_row_number}/{total_rows_in_input} rows. Deliverable (Total): {current_total_deliverable}, Skipped (Total): {current_total_skipped}")
            log_memory_usage()
            
            if current_global_row_number % 1000 == 0:
                gc.collect()

    # Final checkpoint save: indicates all rows in the input file have been processed
    with open(checkpoint_file, 'w') as f:
        f.write(str(total_rows_in_input))

    # Convert the list of new deliverable rows from this session to a DataFrame
    new_deliverable_df = pd.DataFrame(deliverable_rows_list_for_this_session)

    # Save the filtered data to the output CSV file
    if initial_processed_rows_from_checkpoint == 0: # If starting fresh (no resume or checkpoint invalid)
        if not new_deliverable_df.empty:
            new_deliverable_df.to_csv(output_path, index=False, encoding='utf-8')
        elif os.path.exists(output_path): # If no deliverable rows in this run, and output file exists, clear it.
            os.remove(output_path) 
    else: # Resuming from a checkpoint
        if not new_deliverable_df.empty:
            # Determine if header needs to be written. If file doesn't exist or is empty, write header.
            append_header = not os.path.exists(output_path) or os.path.getsize(output_path) == 0
            new_deliverable_df.to_csv(output_path, mode='a', header=append_header, index=False, encoding='utf-8')

    # Clean up checkpoint file when done, as processing is complete for this file
    if os.path.exists(checkpoint_file):
        os.remove(checkpoint_file)

    # Final summary calculations
    final_deliverable_count = overall_deliverable_count_at_start + deliverable_rows_current_session
    final_skipped_count = overall_skipped_count_at_start + skipped_rows_current_session

    print(f"\nProcessing complete!")
    print(f"Total rows in input file: {total_rows_in_input}")
    print(f"Deliverable emails found (Total): {final_deliverable_count}")
    print(f"Skipped emails (Total): {final_skipped_count}")
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

@app.post("/email-sender/send", summary="Process CSV and send emails")
async def send_emails_endpoint(
    csv_file: UploadFile = File(...),
    email_template_files: List[UploadFile] = File(...),
    subjectForEmail:  List[str] = Form(...),
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
    # Allowed file extensions for data file
    allowed_data_extensions = ('.csv','.xlsx','.xls','.xlsn','.xlsb','.xltm','.xltx')
    if not csv_file.filename or not csv_file.filename.lower().endswith(allowed_data_extensions):
        raise HTTPException(status_code=400, detail=f"Please upload a valid data file. Allowed types: {', '.join(allowed_data_extensions)}.")
    templates = []

    if not email_template_files:
        raise HTTPException(status_code=400, detail="No template files were uploaded.")

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
            smtp_server = f"smtp.{domain}"
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
        if custom_smtp_port is None:
            raise HTTPException(status_code=400, detail="Custom SMTP port is required when 'Other' is selected.")
        try:
            smtp_port = int(custom_smtp_port)
        except ValueError:
            raise HTTPException(status_code=400, detail="Custom SMTP port must be a valid integer.")
    else:
        raise HTTPException(status_code=400, detail="Invalid SMTP port option.")

    temp_data_file_path = None 

    try:
        # Read uploaded email template content
        for file in email_template_files:
            try:
                if not file.filename.lower().endswith(".html"):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid file type: {file.filename}. Only .html files are allowed."
                    )

                content_bytes = await file.read()
                try:
                    content_str = content_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Failed to decode {file.filename}. Ensure it's saved as UTF-8."
                    )

                if not content_str.strip():
                    raise HTTPException(
                        status_code=400,
                        detail=f"Template file {file.filename} is empty."
                    )

                templates.append((file.filename, content_str))

            except HTTPException:
                # Re-raise FastAPI specific errors
                raise
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail=f"Unexpected error while processing {file.filename}: {str(e)}"
                )

        if not templates:
            raise HTTPException(status_code=400, detail="No valid HTML templates found in uploaded folder.")


        # Save the uploaded data file to a temporary file
        original_filename = csv_file.filename
        file_extension = os.path.splitext(original_filename)[1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as tmp:
            shutil.copyfileobj(csv_file.file, tmp)
            temp_data_file_path = tmp.name

        print(f"Uploaded data file saved temporarily to: {temp_data_file_path}")
        storeTempSubject = []
        for i in subjectForEmail:
            if i != '':
                storeTempSubject.append(i)
                
        subjectForEmail = storeTempSubject[:]
        storeTempSubject = None
        # Process emails
        results, validation_stats, processing_error, remaining_df = process_csv_and_send_emails(
            subjectForEmail=subjectForEmail,
            csv_file_path=temp_data_file_path, 
            sender_email=sender_email,
            sender_name=sender_name,
            sender_password=sender_password,
            smtp_server=smtp_server,
            smtp_port=smtp_port,
            template_content=templates,
            max_emails=max_emails,
            delay=delay,
            original_file_extension=file_extension
        )

        if processing_error:
            raise HTTPException(status_code=500, detail=processing_error)

        summary = display_summary(results, validation_stats)
        
        # Create feedback CSV file
        feedback_csv_path = None
        try:
            feedback_csv_path = f"email_feedback_{int(time.time())}.csv"
            with open(feedback_csv_path, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = ['name', 'email', 'success', 'message']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                
                for result in results:
                    writer.writerow({
                        'name': result['name'],
                        'email': result['email'],
                        'success': result['success'],
                        'message': result['message']
                    })
        except Exception as e:
            print(f"Error creating feedback CSV: {e}")
            feedback_csv_path = None

        # After processing emails and getting results, save the remaining rows
        updated_data_filename = None
        if remaining_df is not None and not remaining_df.empty:
            filename_without_ext, ext = os.path.splitext(original_filename)
            new_data_filename = f"{filename_without_ext}_updateAfterDel{ext}"
            
            # Save the new file in the current working directory
            new_data_file_path = new_data_filename
            
            # Save the remaining DataFrame to a new file based on original extension
            try:
                if ext.lower() == '.csv':
                    remaining_df.to_csv(new_data_file_path, index=False, encoding='utf-8')
                elif ext.lower() in ['.xlsx', '.xls', '.xlsn', '.xlsb', '.xltm', '.xltx']:
                    remaining_df.to_excel(new_data_file_path, index=False)
                else:
                    print(f"Warning: Could not save updated file with extension {ext}. Falling back to CSV format.")
                    remaining_df.to_csv(new_data_file_path, index=False, encoding='utf-8')
                updated_data_filename = new_data_file_path
                print(f"New updated file created with remaining data: {new_data_file_path}")
            except Exception as e:
                print(f"Error saving updated data file: {e}")
        else:
            print("No remaining rows to save or remaining_df is None/empty.")


        # Return JSONResponse with summary and paths to generated files if any
        response_content = {
            "status": "Email sending process completed.",
            "summary": summary
        }
        if feedback_csv_path and os.path.exists(feedback_csv_path):
            response_content["feedback_csv_filename"] = os.path.basename(feedback_csv_path)
        if updated_data_filename and os.path.exists(updated_data_filename):
            response_content["updated_data_filename"] = os.path.basename(updated_data_filename)
            
        return JSONResponse(content=response_content)

    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"An unexpected error occurred in send_emails_endpoint: {e}")
        raise HTTPException(status_code=500, detail=f"An internal server error occurred: {e}")
    finally:
        if temp_data_file_path and os.path.exists(temp_data_file_path):
            os.remove(temp_data_file_path)
            print(f"Temporary data file removed: {temp_data_file_path}")
            
# Email Filter Router




@app.post("/email-filter/process", summary="Process CSV/Excel and filter emails")
async def filter_emails_endpoint(
    csv_file: UploadFile = File(...), # Renamed for clarity, but still accepts various types
    sender_email: EmailStr = Form(...),
    resume: bool = Form(False)
):
    """
    API endpoint to upload a CSV or Excel file, filter emails, and return the filtered CSV.
    Supports resuming processing from a previous attempt if a checkpoint exists.
    """
    allowed_extensions = ('.csv', '.xlsx', '.xls', '.xlsn', '.xlsb', '.xltm', '.xltx')
    file_extension = os.path.splitext(csv_file.filename)[1].lower()

    if not csv_file.filename or file_extension not in allowed_extensions:
        raise HTTPException(status_code=400, detail=f"Please upload a valid file with one of these extensions: {', '.join(allowed_extensions)}.")

    temp_input_file_path = None
    filtered_output_file_path = None
    checkpoint_file_for_resume = None

    try:
        # Save the uploaded file to a temporary location, preserving its original extension
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as tmp:
            shutil.copyfileobj(csv_file.file, tmp)
            temp_input_file_path = tmp.name

        print(f"Uploaded file saved temporarily to: {temp_input_file_path}")

        # Set up checkpoint file path if resuming
        if resume:
            base_name_temp = os.path.basename(temp_input_file_path)
            file_name_temp, _ = os.path.splitext(base_name_temp)
            checkpoint_file_for_resume = f"{file_name_temp}_checkpoint.txt"
            
            if not os.path.exists(checkpoint_file_for_resume):
                raise HTTPException(status_code=400, detail="Resume requested, but no checkpoint file found to resume from. Please ensure the original file name and its temporary path context are consistent with a prior run.")
        
        # Process the file to filter emails
        filtered_output_file_path = process_csv_file_filter(temp_input_file_path, sender_email, checkpoint_file_for_resume)

        # Return the filtered file
        return FileResponse(
            path=filtered_output_file_path,
            filename=os.path.basename(filtered_output_file_path),
            media_type='text/csv' # The output is always a CSV
        )

    except HTTPException as e:
        # Re-raise HTTPExceptions as they are specific errors to be handled by FastAPI
        raise e
    except Exception as e:
        # Catch any other unexpected errors and provide a generic 500 response
        print(f"An unexpected error occurred in filter_emails_endpoint: {e}")
        raise HTTPException(status_code=500, detail=f"An internal server error occurred: {e}")
    finally:
        # Clean up the temporary input file
        if temp_input_file_path and os.path.exists(temp_input_file_path):
            os.remove(temp_input_file_path)
            print(f"Temporary input file removed: {temp_input_file_path}")
        
        # The filtered_output_file_path is returned as a FileResponse and should not be
        # removed immediately here. FastAPI handles sending it. If a more
        # robust temporary file cleanup is needed for output files after they are served,
        # it should be implemented as a separate scheduled task or a FastAPI background task.

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