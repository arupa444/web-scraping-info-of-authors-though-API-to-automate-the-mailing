import csv
import smtplib
import time
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
import getpass
import re
import os
import dns.resolver
from datetime import datetime


def load_email_template(template_path):
    """Load email template from HTML file"""
    template_path = f"templates/{template_path}"
    try:
        with open(template_path, 'r', encoding='utf-8') as file:
            return file.read()
    except FileNotFoundError:
        print(f"Error: Template file '{template_path}' not found.")
        exit(1)
    except Exception as e:
        print(f"Error loading template: {e}")
        exit(1)


def send_email(subjectForEmail, sender_email, sender_password, recipient_name, recipient_email, journal, article_title,
               smtp_server,
               smtp_port, template):
    """Send a personalized email to an author using HTML template"""

    # Format the template with personalized data
    html = template.format(
        name=recipient_name,
        article_title=article_title,
        journal=journal
    )
    subjectForEmail = subjectForEmail.format(
        name=recipient_name, article_title=article_title,
        journal=journal)

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subjectForEmail
    msg['From'] = formataddr(("Your Name", sender_email))
    msg['To'] = formataddr((recipient_name, recipient_email))

    # Attach the formatted HTML
    msg.attach(MIMEText(html, 'html'))

    try:
        # Create SSL context with relaxed settings for testing
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls(context=context)
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, recipient_email, msg.as_string())
        return True, "Email sent successfully"
    except Exception as e:
        return False, str(e)


# EMAIL VALIDATION FUNCTIONS
def is_valid_syntax(email):
    """Check if email has valid syntax"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def has_mx_record(domain):
    """Check if domain has MX record"""
    try:
        records = dns.resolver.resolve(domain, 'MX')
        return bool(records)
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.Timeout):
        return False


def check_smtp(email):
    """Check if SMTP server accepts the email"""
    domain = email.split('@')[1]
    try:
        # Get MX record
        mx_records = dns.resolver.resolve(domain, 'MX')
        mx_record = str(mx_records[0].exchange)

        # Connect to SMTP server
        server = smtplib.SMTP()
        server.set_debuglevel(0)  # set to 1 to see SMTP debug messages
        server.connect(mx_record)
        server.helo(server.local_hostname)  # hostname of local machine
        server.mail('test@example.com')  # dummy sender email
        code, message = server.rcpt(email)
        server.quit()
        if code == 250:
            return True
        else:
            return False
    except Exception as e:
        return False


def validate_email(email):
    """Comprehensive email validation"""
    if not is_valid_syntax(email):
        return "Invalid syntax"

    domain = email.split('@')[1]
    if not has_mx_record(domain):
        return "Domain not found / no MX record"

    # Skip SMTP check since it often fails without authentication
    return "Deliverable"


def process_csv_and_send_emails(subjectForEmail, csv_file, sender_email, sender_password, smtp_server, smtp_port,
                                template_path, max_emails=None, delay=5):
    """Process CSV file and send emails to authors"""
    results = []
    validation_stats = {
        "valid_syntax": 0,
        "has_mx": 0,
        "deliverable": 0,
        "failed": 0
    }

    # Load email template
    template = load_email_template(template_path)

    try:
        with open(csv_file, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)

            # Count total rows in CSV if max_emails is not specified
            if max_emails is None:
                max_emails = sum(1 for _ in reader)
                file.seek(0)  # Reset file pointer to beginning
                reader = csv.DictReader(file)  # Recreate reader after counting

            print(f"\nStarting to process emails (max {max_emails}) with {delay} second delays...")
            print("=" * 50)

            for i, row in enumerate(reader):
                if i >= max_emails:
                    break

                name = row['name']
                emails = row['emails'].split(';')
                journal = row['journal']
                article_title = row['article_title']

                print(f"\nProcessing row {i + 1}/{max_emails}: {name}")

                for email in emails:
                    email = email.strip()
                    if not email:
                        continue

                    print(f"  Validating: {email}")
                    validation_result = validate_email(email)

                    # Update validation statistics
                    if validation_result == "Invalid syntax":
                        validation_stats["failed"] += 1
                    elif validation_result == "Domain not found / no MX record":
                        validation_stats["failed"] += 1
                    elif validation_result == "Deliverable":
                        validation_stats["deliverable"] += 1
                        validation_stats["has_mx"] += 1
                        validation_stats["valid_syntax"] += 1
                    else:  # Non-deliverable
                        validation_stats["failed"] += 1
                        validation_stats["has_mx"] += 1
                        validation_stats["valid_syntax"] += 1

                    if validation_result != "Deliverable":
                        print(f"    ✗ Skipped - {validation_result}")
                        results.append({
                            'name': name,
                            'email': email,
                            'journal': journal,
                            'success': False,
                            'message': validation_result
                        })
                        continue

                    print(f"    ✓ Valid - Sending email...")

                    success, message = send_email(
                        subjectForEmail, sender_email, sender_password, name, email,
                        journal, article_title, smtp_server, smtp_port, template
                    )

                    result = {
                        'name': name,
                        'email': email,
                        'journal': journal,
                        'success': success,
                        'message': message
                    }
                    results.append(result)

                    if success:
                        print(f"    ✓ Email sent successfully")
                    else:
                        print(f"    ✗ Failed to send: {message}")

                if i < max_emails - 1:
                    print(f"\nWaiting {delay} seconds before next email...")
                    time.sleep(delay)

    except Exception as e:
        print(f"\nError processing CSV file: {e}")
        return results, validation_stats

    return results, validation_stats


def save_results_to_csv(results, filename):
    """Save email sending results to a CSV file with error handling"""
    max_attempts = 3
    attempt = 0

    while attempt < max_attempts:
        try:
            # Try to create a unique filename if the original exists
            if os.path.exists(filename):
                base, ext = os.path.splitext(filename)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"{base}_{timestamp}{ext}"
                print(f"File already exists. Using new filename: {filename}")

            with open(filename, 'w', newline='', encoding='utf-8') as file:
                fieldnames = ['name', 'email', 'journal', 'success', 'message']
                writer = csv.DictWriter(file, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(results)
            print(f"Results successfully saved to {filename}")
            return True
        except PermissionError:
            attempt += 1
            if attempt < max_attempts:
                print(f"Permission denied. Retrying ({attempt}/{max_attempts})...")
                time.sleep(2)  # Wait before retrying
            else:
                print(f"Error: Could not save results to {filename} after {max_attempts} attempts.")
                print("Please close the file if it's open in another program and try again.")
                return False
        except Exception as e:
            print(f"Error saving results: {e}")
            return False


def count_csv_rows(csv_file):
    """Count the number of rows in a CSV file (excluding header)"""
    with open(csv_file, 'r', encoding='utf-8') as file:
        reader = csv.reader(file)
        # Skip header
        next(reader, None)
        # Count remaining rows
        row_count = sum(1 for row in reader)
    return row_count


def display_summary(results, validation_stats):
    """Display a comprehensive summary of the email sending process"""
    print("\n" + "=" * 60)
    print("               EMAIL SENDING SUMMARY")
    print("=" * 60)

    # Validation statistics
    print("\nVALIDATION RESULTS:")
    print(f"  • Emails with valid syntax: {validation_stats['valid_syntax']}")
    print(f"  • Emails with MX records: {validation_stats['has_mx']}")
    print(f"  • Deliverable emails: {validation_stats['deliverable']}")
    print(f"  • Non-deliverable emails: {validation_stats['failed']}")

    # Sending statistics
    total_attempted = len(results)
    success_count = sum(1 for r in results if r['success'])
    failed_count = total_attempted - success_count

    print("\nSENDING RESULTS:")
    print(f"  • Total emails attempted: {total_attempted}")
    print(f"  • Successfully sent: {success_count}")
    print(f"  • Failed to send: {failed_count}")

    # Detailed failure breakdown
    if failed_count > 0:
        print("\nFAILURE BREAKDOWN:")
        failure_reasons = {}
        for r in results:
            if not r['success']:
                reason = r['message']
                failure_reasons[reason] = failure_reasons.get(reason, 0) + 1

        for reason, count in failure_reasons.items():
            print(f"  • {reason}: {count}")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    print("=== AUTOMATED EMAIL SENDER ===\n")

    csv_file = input("Enter the path to your CSV file: ").strip()

    # Check if file exists
    if not os.path.exists(csv_file):
        print(f"Error: File '{csv_file}' not found.")
        exit(1)

    # Count rows in CSV
    try:
        csv_row_count = count_csv_rows(csv_file)
        print(f"CSV file contains {csv_row_count} rows.")
    except Exception as e:
        print(f"Error reading CSV file: {e}")
        exit(1)

    # Get email template path
    default_template = "email_template.html"
    template_path = input(f"Enter the path to your email template (default: {default_template}): ").strip()
    if not template_path:
        template_path = default_template

    # add the subject for email template

    subjectForEmail = input(f"Enter the Subject for your Email : ")

    # Check if template file exists
    if not os.path.exists(f"templates/{template_path}"):
        print(f"Error: Template file 'templates/{template_path}' not found.")
        exit(1)

    sender_email = input("Enter your email address: ").strip()
    sender_password = getpass.getpass("Enter your email password: ")

    print("\nCommon SMTP servers:")
    print("1. Gmail (smtp.gmail.com:587)")
    print("2. Outlook (smtp.office365.com:587)")
    print("3. Yahoo (smtp.mail.yahoo.com:587)")
    print("4. Any (smtp.any.....:587)")
    print("5. Custom")

    choice = input("Choose your SMTP server (1-5): ").strip()
    if choice == "1":
        smtp_server = "smtp.gmail.com"
        smtp_port = 587
    elif choice == "2":
        smtp_server = "smtp.office365.com"
        smtp_port = 587
    elif choice == "3":
        smtp_server = "smtp.mail.yahoo.com"
        smtp_port = 587
    elif choice == "4":
        smtp_server = f"smtp.{sender_email.split("@")[1]}"
        smtp_port = 587
    else:
        smtp_server = input("Enter SMTP server address: ").strip()
        smtp_port = int(input("Enter SMTP port (usually 587): ").strip())

    # Set default max_emails to CSV row count
    max_emails_input = input(f"Maximum number of emails to send (default {csv_row_count}): ").strip()
    max_emails = int(max_emails_input) if max_emails_input else csv_row_count

    delay = int(input("Delay between emails in seconds (default 5): ") or "5")

    print("\n" + "=" * 50)
    print("          CONFIRMATION")
    print("=" * 50)
    print(f"CSV file: {csv_file}")
    print(f"Email template: {template_path}")
    print(f"Sender: {sender_email}")
    print(f"SMTP server: {smtp_server}:{smtp_port}")
    print(f"Max emails: {max_emails}")
    print(f"Delay between emails: {delay} seconds")
    print("=" * 50)

    confirm = input("\nProceed with sending emails? (yes/no): ").strip().lower()
    if confirm != "yes":
        print("Operation cancelled.")
        exit()

    # Process emails and get results
    results, validation_stats = process_csv_and_send_emails(
        subjectForEmail, csv_file, sender_email, sender_password, smtp_server,
        smtp_port, template_path, max_emails, delay
    )

    # Display summary
    display_summary(results, validation_stats)

    # Save results if we have any
    if results:
        results_file = csv_file.replace('.csv', '_results.csv')
        save_success = save_results_to_csv(results, results_file)

        if not save_success:
            print("\nWarning: Results could not be saved to CSV file.")
            print("Here's a summary of the results:")
            for i, result in enumerate(results[:10]):  # Show first 10 results
                status = "✓" if result['success'] else "✗"
                print(f"{status} {result['name']} ({result['email']}): {result['message']}")

            if len(results) > 10:
                print(f"... and {len(results) - 10} more results.")
    else:
        print("\nNo emails were processed.")