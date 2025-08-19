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

def send_email(sender_email, sender_password, recipient_name, recipient_email, journal, article_title, smtp_server, smtp_port):
    """Send a personalized email to an author"""
    
    msg = MIMEMultipart('alternative')
    msg['Subject'] = f"Collaboration Inquiry Regarding Your Research in {journal}"
    msg['From'] = formataddr(("Your Name", sender_email))
    msg['To'] = formataddr((recipient_name, recipient_email))
    
    
    html = f"""
    <html>
    <body>
        <p>Dear Dr. {recipient_name.split()[-1]},</p>
        
        <p>I hope this email finds you well. My name is Arupa and I'm reaching out to you regarding your interesting research 
        titled "<strong>{article_title}</strong>" published in <em>{journal}</em>.</p>
        
        <p>I'm particularly impressed by your work in this field and would like to explore potential collaboration opportunities 
        or discuss your research further.</p>
        
        <p>Would you be available for a brief conversation at your convenience? I'm flexible and can work around your schedule.</p>
        
        <p>Looking forward to hearing from you.</p>
        
        <p>Best regards,<br>
        Arupa Nanda Swain<br>
        Pulsus Managing editor<br>
        773460467<br>
        arupaswain7735@gmail.com</p>
        
        <hr>
        <p style="font-size: 10px; color: #666;">
        This email was sent in relation to your research publication. If you believe you've received this message in error, 
        please disregard it. To unsubscribe from future communications, please reply with "Unsubscribe" in the subject line.
        </p>
    </body>
    </html>
    """
    
    
    msg.attach(MIMEText(html, 'html'))
    
    
    context = ssl.create_default_context()
    
    try:
        
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls(context=context)
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, recipient_email, msg.as_string())
        return True, "Email sent successfully"
    except Exception as e:
        return False, str(e)

def process_csv_and_send_emails(csv_file, sender_email, sender_password, smtp_server, smtp_port, max_emails=None, delay=5):
    """Process CSV file and send emails to authors"""
    results = []
    
    try:
        with open(csv_file, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            
            # Count total rows in CSV if max_emails is not specified
            if max_emails is None:
                max_emails = sum(1 for _ in reader)
                file.seek(0)  # Reset file pointer to beginning
                reader = csv.DictReader(file)  # Recreate reader after counting
            
            print(f"Starting to send emails (max {max_emails}) with {delay} second delays...")
            
            for i, row in enumerate(reader):
                if i >= max_emails:
                    break
                
                
                name = row['name']
                emails = row['emails'].split(';')
                journal = row['journal']
                article_title = row['article_title']
                
                
                for email in emails:
                    email = email.strip()
                    if not email:
                        continue
                    
                    print(f"\nSending email {i+1}/{max_emails} to {name} at {email}")
                    
                    
                    success, message = send_email(
                        sender_email, sender_password, name, email, 
                        journal, article_title, smtp_server, smtp_port
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
                        print(f"✓ Success: {message}")
                    else:
                        print(f"✗ Failed: {message}")
                
                
                if i < max_emails - 1:
                    print(f"Waiting {delay} seconds before next email...")
                    time.sleep(delay)
    
    except Exception as e:
        print(f"Error processing CSV file: {e}")
    
    return results

def save_results_to_csv(results, filename):
    """Save email sending results to a CSV file"""
    with open(filename, 'w', newline='', encoding='utf-8') as file:
        fieldnames = ['name', 'email', 'journal', 'success', 'message']
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)
    print(f"Results saved to {filename}")

def validate_email(email):
    """Basic email validation"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def count_csv_rows(csv_file):
    """Count the number of rows in a CSV file (excluding header)"""
    with open(csv_file, 'r', encoding='utf-8') as file:
        reader = csv.reader(file)
        # Skip header
        next(reader, None)
        # Count remaining rows
        row_count = sum(1 for row in reader)
    return row_count

if __name__ == "__main__":
    print("=== Automated Email Sender ===\n")
    
    
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
    
    sender_email = input("Enter your email address: ").strip()
    sender_password = getpass.getpass("Enter your email password: ")
    
    
    print("\nCommon SMTP servers:")
    print("1. Gmail (smtp.gmail.com:587)")
    print("2. Outlook (smtp.office365.com:587)")
    print("3. Yahoo (smtp.mail.yahoo.com:587)")
    print("4. Custom")
    
    choice = input("Choose your SMTP server (1-4): ").strip()
    if choice == "1":
        smtp_server = "smtp.gmail.com"
        smtp_port = 587
    elif choice == "2":
        smtp_server = "smtp.office365.com"
        smtp_port = 587
    elif choice == "3":
        smtp_server = "smtp.mail.yahoo.com"
        smtp_port = 587
    else:
        smtp_server = input("Enter SMTP server address: ").strip()
        smtp_port = int(input("Enter SMTP port (usually 587): ").strip())
    
    # Set default max_emails to CSV row count
    max_emails_input = input(f"Maximum number of emails to send (default {csv_row_count}): ").strip()
    max_emails = int(max_emails_input) if max_emails_input else csv_row_count
    
    delay = int(input("Delay between emails in seconds (default 5): ") or "5")
    
    
    print("\n=== CONFIRMATION ===")
    print(f"CSV file: {csv_file}")
    print(f"Sender: {sender_email}")
    print(f"SMTP server: {smtp_server}:{smtp_port}")
    print(f"Max emails: {max_emails}")
    print(f"Delay between emails: {delay} seconds")
    
    confirm = input("\nProceed with sending emails? (yes/no): ").strip().lower()
    if confirm != "yes":
        print("Operation cancelled.")
        exit()
    
    
    results = process_csv_and_send_emails(csv_file, sender_email, sender_password, smtp_server, smtp_port, max_emails, delay)
    
    
    if results:
        results_file = csv_file.replace('.csv', '_results.csv')
        save_results_to_csv(results, results_file)
        
        
        success_count = sum(1 for r in results if r['success'])
        print(f"\n=== SUMMARY ===")
        print(f"Total emails attempted: {len(results)}")
        print(f"Successfully sent: {success_count}")
        print(f"Failed: {len(results) - success_count}")
    else:
        print("No emails were sent.")
