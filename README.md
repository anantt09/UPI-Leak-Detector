# UPI Leak Detector

UPI Leak Detector is a personal finance tracker that allows users to upload their bank statements (PDF or CSV) to extract and categorize their transactions locally, showing spending insights, spending trends, monthly budget tracking, and potential spending leak alerts.

## Features

- **Import Statements**: Directly import HDFC, ICICI, Canara, SBI, and other bank statements in PDF or CSV formats.
- **Local Parsing**: Safe, local regex-based parsing of bank statements ensuring 100% data privacy.
- **Budget Tracking**: Set a monthly budget and monitor progress.
- **Spend Insights**: Category breakdown and daily spending trends with interactive visual charts.
- **Data Export**: Export your spending report directly to PDF.

---

## Prerequisites

Ensure you have the following installed on your system:
- **Python** (version 3.10 or higher)
- **PostgreSQL** (installed and running)

---

## Installation & Setup

Follow these steps to set up the project on your local machine:

### 1. Extract the Project Files
Extract the zip folder containing the project files to your desired directory.

### 2. Set Up Virtual Environment (Recommended)
Open your terminal/command prompt in the project root directory and run:
```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate
```

### 3. Install Dependencies
Install all required Python libraries:
```bash
pip install -r requirements.txt
```

### 4. Setup Database
1. Open PostgreSQL (via pgAdmin or psql shell).
2. Create a new database named `upitracker`.
3. Set your PostgreSQL server configuration (host, username, password).

### 5. Configure Environment Variables
Create a file named `.env` in the root directory (same folder as `app.py`) and configure the following variables:
```env
# Database Credentials
DB_HOST=localhost
DB_NAME=upitracker
DB_USER=postgres
DB_PASS=YOUR_POSTGRES_PASSWORD
```

### 6. Initialize Database Tables
Run the database initialization script to create the required tables (`users`, `bank_accounts`, `transactions`):
```bash
python init_db.py
```

### 7. Run the Application
Start the Flask development server:
```bash
python app.py
```

Once running, the application will automatically open in your default browser at **http://localhost:5001/login**. If it doesn't open automatically, open your browser and navigate to the link manually.

---

## Folder Structure

```text
upi_tracker/
│
├── static/               # CSS, JS, images, icons
├── templates/            # HTML templates (Flask jinja2 templates)
├── .env                  # Private database credentials config (Do not upload to git)
├── .gitignore            # Git exclusion rules
├── app.py                # Main Flask application file (Routes and controllers)
├── init_db.py            # Database schema setup script
├── schema.sql            # SQL schema definitions
├── requirements.txt      # List of dependencies
└── README.md             # Setup guide (This file)
```
