import csv
import re
import dns.resolver
import smtplib
import os
from socket import timeout as socket_timeout


def is_valid_syntax(email):
    """Check if email has valid syntax"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def has_mx_record(domain):
    """Check if domain has MX record"""
    try:
        records = dns.resolver.resolve(domain, 'MX', lifetime=5)
        return bool(records)
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.Timeout):
        return False


def check_smtp(email):
    """Check if SMTP server accepts the email"""
    domain = email.split('@')[1]
    try:
        # Get MX record
        mx_records = dns.resolver.resolve(domain, 'MX', lifetime=5)
        mx_record = str(mx_records[0].exchange)

        # Connect to SMTP server with timeout
        server = smtplib.SMTP(timeout=10)
        server.set_debuglevel(0)
        server.connect(mx_record)
        server.helo(server.local_hostname)
        server.mail('test@example.com')
        code, message = server.rcpt(email)
        server.quit()

        return code == 250
    except Exception as e:
        return False


def validate_email(email):
    if not is_valid_syntax(email):
        return "Invalid syntax"

    domain = email.split('@')[1]
    if not has_mx_record(domain):
        return "Domain not found / no MX record"

    if check_smtp(email):
        return "Deliverable"
    else:
        return "Non-deliverable"


def process_csv_file(input_path):
    # Generate output filename
    base_name = os.path.basename(input_path)
    file_name, file_ext = os.path.splitext(base_name)
    output_path = f"filtered_{file_name}{file_ext}"

    print(f"Processing file: {input_path}")
    print(f"Output will be saved to: {output_path}")

    with open(input_path, 'r', newline='', encoding='utf-8') as infile, \
            open(output_path, 'w', newline='', encoding='utf-8') as outfile:

        reader = csv.DictReader(infile)
        fieldnames = reader.fieldnames
        writer = csv.DictWriter(outfile, fieldnames=fieldnames)

        writer.writeheader()

        total_rows = 0
        deliverable_rows = 0

        for row in reader:
            total_rows += 1
            email = row['emails'].strip()

            print(f"Validating email {total_rows}: {email}")
            result = validate_email(email)
            print(f"Result: {result}")

            if result == "Deliverable":
                writer.writerow(row)
                deliverable_rows += 1

    print(f"\nProcessing complete!")
    print(f"Total rows processed: {total_rows}")
    print(f"Deliverable emails found: {deliverable_rows}")
    print(f"Filtered file saved as: {output_path}")

    return output_path


# Main program
if __name__ == "__main__":
    input_file = input("Enter the path to your CSV file: ")

    if not os.path.exists(input_file):
        print(f"Error: File not found at {input_file}")
    else:
        try:
            process_csv_file(input_file)
        except Exception as e:
            print(f"An error occurred: {str(e)}")