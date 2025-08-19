# Web scraping info of authors though API and email automation

![Python Version](https://img.shields.io/badge/python-3.6%2B-blue.svg)

A powerful two-part Python toolset to automate academic outreach. This project helps you find relevant authors on PubMed based on a research topic and then send them personalized emails for collaboration inquiries.

## Table of Contents

- [Description](#description)
- [Features](#features)
- [How It Works](#how-it-works)
- [Installation](#installation)
- [Usage](#usage)
  - [Step 1: Scrape Authors from PubMed](#step-1-scrape-authors-from-pubmed)
  - [Step 2: Send Automated Emails](#step-2-send-automated-emails)
- [Configuration](#configuration)
- [Disclaimer](#disclaimer)
- [Contributing](#contributing)
- [License](#license)

## Description

This project provides a streamlined workflow for academic and professional outreach. It consists of two main Python scripts:

1.  **`scrapName.py`**: A script that connects to the NCBI PubMed API to search for articles based on a specific keyword. It extracts detailed author information, including names, affiliations, journal, article title, and most importantly, email addresses. The data is saved to a well-structured CSV file.

2.  **`automaticEmailing.py`**: A script that uses the CSV file from the scraper to send personalized emails. It uses a customizable HTML template, securely handles your email credentials, and allows you to configure sending limits and delays to ensure responsible outreach.

This tool is perfect for researchers, students, and professionals looking to build connections, explore collaborations, or conduct targeted outreach within the academic community.

## Scripts Overview

### 1. PubMed Email Extractor (`pubmed_search.py`)
- Searches PubMed for articles related to a specific topic
- Extracts author names, email addresses, affiliations, and article details
- Filters results to include only articles from the last 5 years
- Exports data to a CSV file

### 2. Automated Email Sender (`email_automation.py`)
- Reads author data from CSV files
- Sends personalized emails to authors
- Tracks delivery status and saves results

## Requirements

- Python 3.6 or higher
- Only external dependency: `requests` (install with `pip install requests`)

## Installation

1. Clone or download this repository
2. Install the required package:
   ```bash
   pip install -r requirements.txt
   ```

## Features

-   **Targeted Search**: Find authors based on specific research keywords.
-   **Automated Data Scraping**: Efficiently collects author contact details from PubMed.
-   **Email Extraction**: Intelligently parses affiliation data to find email addresses.
-   **CSV Export**: Saves cleaned data in a universally compatible CSV format.
-
-   **Personalized Emailing**: Uses an HTML template to dynamically insert author-specific details.
-   **Secure & Configurable**: Handles email credentials securely and supports standard SMTP providers (Gmail, Outlook, etc.).
-   **Responsible Sending**: Includes configurable delays and sending limits to avoid spamming.
-   **Logging & Reporting**: Tracks the status of every email sent and saves the results to a separate CSV log file.

## How It Works

1.  **Run `scrapName.py`** with a search term (e.g., "crispr gene editing").
2.  The script queries the PubMed database, fetches article details, and extracts author information for authors with available emails.
3.  It generates a CSV file named `your_search_term_authors_with_emails.csv`.
4.  **Run `automaticEmailing.py`**, providing the path to the generated CSV file and your email credentials.
5.  The script reads the CSV and sends personalized emails one by one, respecting the delay you set.
6.  Finally, it creates a `_results.csv` file to log the outcome of each email sent.

## Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/arupa444/web-scraping-info-of-authors-though-API-to-automate-the-mailing.git
    cd web-scraping-info-of-authors-though-API-to-automate-the-mailing
    ```

2.  **Install the required Python libraries:**
    This project uses the `requests` library. You can install it using pip.
    ```bash
    pip install requests
    ```
    No other external libraries are required beyond the standard Python library.

## Usage

Follow these two steps to perform your outreach campaign.

### Step 1: Scrape Authors from PubMed

Open your terminal or command prompt and run `scrapName.py` with your desired search term enclosed in quotes.

**Syntax:**
```bash
python scrapName.py "your search term"
```

**Example:**
```bash
python scrapName.py "cancer immunotherapy"
```

The script will print its progress and, upon completion, you will find a new CSV file in the same directory (e.g., `cancer_immunotherapy_authors_with_emails.csv`).

### Step 2: Send Automated Emails

Once you have your CSV file, run the `automaticEmailing.py` script. It will interactively prompt you for the necessary information.

**Run the script:**
```bash
python automaticEmailing.py
```

You will be asked to provide the following:
1.  **Path to your CSV file**: The file generated in Step 1.
2.  **Your email address**: The email you want to send from.
3.  **Your email password**: Your password will be hidden for security. **Note:** For Gmail, you may need to generate an "App Password".
4.  **SMTP server choice**: Choose from a list of common providers or enter a custom one.
5.  **Maximum number of emails to send**: To control the volume of your campaign.
6.  **Delay between emails**: The number of seconds to wait between sending each email.

After you confirm the details, the script will begin the sending process and create a results file (e.g., `cancer_immunotherapy_authors_with_emails_results.csv`) when finished.

## Configuration

The email template can be easily customized. Open `yourHTML.html`. You can edit the `html` variable to change the subject, body, and signature of the email.

```HTML
    html = f"""
    <html>
    <body>
        <p>Dear Dr. {recipient_name.split()[-1]},</p>
        
        <p>I hope this email finds you well. My name is [Your Name] and I'm a [Your Position] at [Your Institution].
        I came across your fascinating research titled "<strong>{article_title}</strong>" in <em>{journal}</em>.</p>
        
        <!-- Customize the rest of the email content here -->
        
        <p>Best regards,<br>
        [Your Full Name]</p>
    </body>
    </html>
    """
    # ...
```

Remember to replace placeholders like `[Your Name]`, `[Your Position]`, etc., with your actual information.


## Output Files

1. **Author Data CSV**: `[search_term]_authors_with_emails.csv`
   - Contains: name, journal, article_title, emails, affiliations

2. **Email Results CSV**: `[original_csv]_results.csv`
   - Contains: name, email, journal, success status, error messages

## Important Notes

1. **Email Sending Limits**:
   - Be aware of your email provider's sending limits
   - Gmail has a limit of 500 emails per day
   - Consider using dedicated email services for large campaigns

2. **Ethical Considerations**:
   - Only contact authors for legitimate academic purposes
   - Include an unsubscribe option in your emails
   - Comply with anti-spam regulations in your jurisdiction

3. **Rate Limiting**:
   - The scripts include delays to avoid overwhelming servers
   - Adjust these delays based on your needs and server policies

## Troubleshooting

### Common Issues

1. **"No articles found"**:
   - Try a broader search term
   - Check for typos in your search query
   - Verify there are articles on your topic in the last 5 years

2. **Email sending fails**:
   - Verify your email credentials
   - Check if you need to enable "less secure apps" or generate an app password
   - Confirm your SMTP server settings

3. **CSV file errors**:
   - Ensure the CSV file is in the correct format
   - Check for special characters that might cause encoding issues

### Error Messages

The scripts provide detailed error messages to help diagnose issues. Check the console output for specific error information.




## Disclaimer

-   **Use Responsibly**: This tool is intended for legitimate research and professional collaboration inquiries. Do not use it for spam.
-   **API Usage**: The script respects NCBI's E-utils guidelines by including a delay between API requests. Abusing the API can lead to your IP address being temporarily or permanently blocked.
-   **Email Sending Limits**: Be mindful of your email provider's sending limits to avoid having your account flagged or suspended.
-   **Compliance**: Ensure your outreach complies with anti-spam legislation (e.g., CAN-SPAM, GDPR) applicable to you and your recipients. The default template includes an unsubscribe notice as a best practice.

## Contributing

Contributions are welcome! If you have ideas for improvements or find a bug, please feel free to:
1.  Fork the repository.
2.  Create a new branch (`git checkout -b feature/your-feature-name`).
3.  Make your changes.
4.  Commit your changes (`git commit -m 'Add some feature'`).
5.  Push to the branch (`git push origin feature/your-feature-name`).
6.  Open a Pull Request.

## License

This project is open to use. Use this project and contribute in the project.
