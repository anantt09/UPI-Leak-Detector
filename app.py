import os
import psycopg2
import psycopg2.extras
import pandas as pd
import pdfplumber
import re
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_bcrypt import Bcrypt
from datetime import datetime
import io
import csv
from flask import Response
import os
from dotenv import load_dotenv
from google import genai
import json
from fpdf import FPDF

load_dotenv()
client = genai.Client() if os.environ.get("GEMINI_API_KEY") else None


app = Flask(__name__)
app.secret_key = 'super_secret_key_for_development' # Change in production
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Database configuration
# Update these with actual credentials if needed
DB_HOST = "localhost"
DB_NAME = "upitracker"
DB_USER = "postgres"
DB_PASS = "root"

def get_db_connection():
    """Connects to the PostgreSQL database."""
    conn = psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASS
    )
    return conn

def save_bank_account(user_id, bank_name, account_no, current_balance):
    """Helper to save or update a bank account in the database."""
    if not bank_name or str(bank_name).strip().upper() in ('GENERIC', 'UNKNOWN', ''):
        return
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO bank_accounts (user_id, bank_name, account_no, current_balance, last_updated)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (user_id, bank_name, account_no) DO UPDATE 
            SET current_balance = EXCLUDED.current_balance, last_updated = EXCLUDED.last_updated
        ''', (user_id, bank_name, account_no, current_balance, datetime.now().date()))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print("Error saving bank account:", e)

# User model for Flask-Login
class User(UserMixin):
    def __init__(self, id, username):
        self.id = id
        self.username = username

@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute('SELECT * FROM users WHERE id = %s', (user_id,))
    user = cur.fetchone()
    cur.close()
    conn.close()
    if user:
        u = User(id=user['id'], username=user['username'])
        u.monthly_budget = user.get('monthly_budget', 0)
        return u
    return None

def auto_categorize(merchant_name):
    merchant = str(merchant_name).lower()
    if any(k in merchant for k in ['swiggy', 'zomato', 'blinkit', 'zepto', 'domino', 'kfc', 'cafe', 'restaurant', 'food', 'bakery', 'sweet']):
        return 'Food & Dining'
    if any(k in merchant for k in ['amazon', 'flipkart', 'myntra', 'ajio', 'reliance', 'mart', 'supermarket', 'dmart', 'store', 'kirana']):
        return 'Shopping'
    if any(k in merchant for k in ['jio', 'airtel', 'vi', 'bsnl', 'electricity', 'water', 'bill', 'recharge', 'broadband']):
        return 'Utilities'
    if any(k in merchant for k in ['uber', 'ola', 'rapido', 'irctc', 'petrol', 'fuel', 'hpcl', 'bpcl', 'indianoil', 'metro', 'auto', 'taxi']):
        return 'Transport'
    if any(k in merchant for k in ['netflix', 'prime', 'spotify', 'hotstar', 'bookmyshow', 'pvr', 'movie']):
        return 'Entertainment'
    if any(k in merchant for k in ['pharmacy', 'apollo', 'medplus', 'hospital', 'clinic', 'medical']):
        return 'Health'
    return 'Other'

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        # Hash password for security
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            # Store new user in DB
            cur.execute('INSERT INTO users (username, password_hash) VALUES (%s, %s) RETURNING id',
                        (username, hashed_password))
            conn.commit()
            flash('Account created successfully! Please log in.', 'success')
            return redirect(url_for('login'))
        except psycopg2.errors.UniqueViolation:
            conn.rollback()
            flash('Username already exists. Choose another one.', 'danger')
        finally:
            cur.close()
            conn.close()
            
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute('SELECT * FROM users WHERE username = %s', (username,))
        user = cur.fetchone()
        cur.close()
        conn.close()
        
        # Verify user exists and password is correct
        if user and bcrypt.check_password_hash(user['password_hash'], password):
            user_obj = User(id=user['id'], username=user['username'])
            login_user(user_obj)
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password', 'danger')
            
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    # Check for bank filter
    selected_bank = request.args.get('bank', 'All')
    
    # 1. Get bank accounts and total net worth
    cur.execute('SELECT * FROM bank_accounts WHERE user_id = %s', (current_user.id,))
    bank_accounts = cur.fetchall()
    total_net_worth = sum(float(acc['current_balance']) for acc in bank_accounts)
    
    # 2. Get all transactions for the logged-in user
    if selected_bank != 'All':
        cur.execute('SELECT * FROM transactions WHERE user_id = %s AND bank_name = %s ORDER BY date DESC', (current_user.id, selected_bank))
    else:
        cur.execute('SELECT * FROM transactions WHERE user_id = %s ORDER BY date DESC', (current_user.id,))
    transactions = cur.fetchall()
    
    # 3. Calculate True Total Spend (excluding Internal Transfers)
    total_spend = sum(float(t['amount']) for t in transactions if t['category'] != 'Internal Transfer')
    
    # 4. Calculate Category-wise spend and Merchant frequency
    category_spend = {}
    merchant_spend = {}
    
    for t in transactions:
        cat = t['category']
        merch = t['merchant']
        amount = float(t['amount'])
        
        # Don't show Internal Transfers in analytics charts to keep it clean
        if cat != 'Internal Transfer':
            # Category aggregation
            category_spend[cat] = category_spend.get(cat, 0) + amount
            
            # Merchant aggregation
            if merch not in merchant_spend:
                merchant_spend[merch] = {'amount': 0, 'count': 0}
            merchant_spend[merch]['amount'] += amount
            merchant_spend[merch]['count'] += 1
        
    # Sort categories and merchants to show top ones
    sorted_categories = sorted(category_spend.items(), key=lambda x: x[1], reverse=True)
    frequent_merchants = sorted(merchant_spend.items(), key=lambda x: x[1]['count'], reverse=True)[:5]
    
    # --- 5. Leak Detection Logic ---
    leaks = []
    
    for merch, data in merchant_spend.items():
        # Condition A: Repeated small transactions (e.g. amount < 150, count >= 5)
        if data['count'] >= 4 and (data['amount'] / data['count']) < 200:
            leaks.append(f"Small spend leak: You spent at '{merch}' {data['count']} times for small amounts. Total: ₹{data['amount']:.2f}")
        # Condition B: Same merchant frequent spending
        elif data['count'] >= 7:
            leaks.append(f"Frequent merchant: You made {data['count']} transactions at '{merch}'. Consider if all are necessary.")
            
    # Condition C: Large Single Spends
    for t in transactions:
        if float(t['amount']) > 2000 and t['category'] != 'Internal Transfer':
            leaks.append(f"Large expense alert: You spent ₹{t['amount']} at '{t['merchant']}' on {t['date']}.")
            
    cur.close()
    conn.close()
    
    # Get budget info
    budget = getattr(current_user, 'monthly_budget', 0)
    budget_used_percent = min(100, (total_spend / float(budget) * 100)) if budget and float(budget) > 0 else 0
    
    return render_template('dashboard.html', 
                           transactions=transactions,
                           total_spend=total_spend,
                           category_spend=sorted_categories,
                           frequent_merchants=frequent_merchants,
                           leaks=leaks,
                           budget=float(budget) if budget else 0,
                           budget_used_percent=budget_used_percent,
                           bank_accounts=bank_accounts,
                           total_net_worth=total_net_worth,
                           selected_bank=selected_bank)

@app.route('/set_budget', methods=['POST'])
@login_required
def set_budget():
    budget = request.form.get('budget', 0)
    try:
        budget = float(budget)
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('UPDATE users SET monthly_budget = %s WHERE id = %s', (budget, current_user.id))
        conn.commit()
        cur.close()
        conn.close()
        flash('Monthly budget updated!', 'success')
    except ValueError:
        flash('Invalid budget amount.', 'danger')
    return redirect(url_for('dashboard'))

@app.route('/delete_bank/<path:bank_name>', methods=['POST'])
@login_required
def delete_bank(bank_name):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        # Delete from transactions
        cur.execute('DELETE FROM transactions WHERE user_id = %s AND bank_name = %s', (current_user.id, bank_name))
        # Delete from bank_accounts
        cur.execute('DELETE FROM bank_accounts WHERE user_id = %s AND bank_name = %s', (current_user.id, bank_name))
        conn.commit()
        cur.close()
        conn.close()
        flash(f'Successfully deleted all records for {bank_name}.', 'success')
    except Exception as e:
        flash(f'Error deleting bank: {str(e)}', 'danger')
    return redirect(url_for('dashboard'))

@app.route('/export')
@login_required
def export_pdf():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute('SELECT date, merchant, category, amount, bank_name FROM transactions WHERE user_id = %s ORDER BY date DESC', (current_user.id,))
    transactions = cur.fetchall()
    cur.close()
    conn.close()

    pdf = FPDF()
    pdf.add_page()
    
    # Title
    pdf.set_font("helvetica", "B", 20)
    pdf.cell(0, 15, "Spend Tracker Report", new_x="LMARGIN", new_y="NEXT", align="C")
    
    # Date
    pdf.set_font("helvetica", "I", 10)
    pdf.cell(0, 10, f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M')}", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(5)
    
    # Table Header
    pdf.set_font("helvetica", "B", 10)
    pdf.set_fill_color(200, 220, 255)
    pdf.cell(30, 10, "Date", border=1, fill=True)
    pdf.cell(75, 10, "Merchant", border=1, fill=True)
    pdf.cell(35, 10, "Category", border=1, fill=True)
    pdf.cell(25, 10, "Bank", border=1, fill=True)
    pdf.cell(25, 10, "Amount", border=1, new_x="LMARGIN", new_y="NEXT", align="R", fill=True)
    
    # Table Content
    pdf.set_font("helvetica", size=9)
    total_spend = 0
    
    for txn in transactions:
        pdf.cell(30, 10, str(txn['date']), border=1)
        pdf.cell(75, 10, str(txn['merchant'])[:40], border=1)
        pdf.cell(35, 10, str(txn['category'])[:15], border=1)
        pdf.cell(25, 10, str(txn['bank_name'])[:12] if txn['bank_name'] else "Generic", border=1)
        pdf.cell(25, 10, f"Rs {txn['amount']:.2f}", border=1, new_x="LMARGIN", new_y="NEXT", align="R")
        
        if txn['category'] != 'Internal Transfer':
            total_spend += float(txn['amount'])
            
    pdf.ln(5)
    pdf.set_font("helvetica", "B", 12)
    pdf.cell(0, 10, f"Total Spend (Excluding Transfers): Rs {total_spend:.2f}", new_x="LMARGIN", new_y="NEXT", align="R")

    pdf_bytes = bytes(pdf.output())
    response = Response(pdf_bytes, mimetype='application/pdf')
    response.headers["Content-Disposition"] = f"attachment; filename=spend_report_{datetime.now().strftime('%Y%m%d')}.pdf"
    return response

@app.route('/alerts')
@login_required
def alerts():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute('SELECT * FROM transactions WHERE user_id = %s ORDER BY date DESC', (current_user.id,))
    transactions = cur.fetchall()
    
    merchant_spend = {}
    for t in transactions:
        merch = t['merchant']
        if merch not in merchant_spend:
            merchant_spend[merch] = {'amount': 0, 'count': 0}
        merchant_spend[merch]['amount'] += float(t['amount'])
        merchant_spend[merch]['count'] += 1
        
    leaks = []
    for merch, data in merchant_spend.items():
        if data['count'] >= 4 and (data['amount'] / data['count']) < 200:
            leaks.append(f"Small spend leak: You spent at '{merch}' {data['count']} times for small amounts. Total: ₹{data['amount']:.2f}")
        elif data['count'] >= 7:
            leaks.append(f"Frequent merchant: You made {data['count']} transactions at '{merch}'. Consider if all are necessary.")
            
    for t in transactions:
        if float(t['amount']) > 2000 and t['category'] != 'Internal Transfer':
            leaks.append(f"Large expense alert: You spent ₹{t['amount']} at '{t['merchant']}' on {t['date']}.")
            
    cur.close()
    conn.close()
    return render_template('alerts.html', leaks=leaks, total_txns=len(transactions))

@app.route('/transaction/<int:id>', methods=['GET', 'POST'])
@login_required
def transaction_details(id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    if request.method == 'POST' and 'delete' in request.form:
        cur.execute('DELETE FROM transactions WHERE id = %s AND user_id = %s', (id, current_user.id))
        conn.commit()
        flash('Transaction deleted.', 'success')
        cur.close()
        conn.close()
        return redirect(url_for('dashboard'))
        
    cur.execute('SELECT * FROM transactions WHERE id = %s AND user_id = %s', (id, current_user.id))
    txn = cur.fetchone()
    cur.close()
    conn.close()
    
    if not txn:
        flash('Transaction not found.', 'danger')
        return redirect(url_for('dashboard'))
        
    return render_template('transaction_details.html', txn=txn)

@app.route('/add_transaction', methods=['GET', 'POST'])
@login_required
def add_transaction():
    if request.method == 'POST':
        amount = request.form['amount']
        date = request.form['date']
        merchant = request.form['merchant']
        category = request.form['category']
        
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO transactions (user_id, amount, date, merchant, category)
            VALUES (%s, %s, %s, %s, %s)
        ''', (current_user.id, amount, date, merchant, category))
        conn.commit()
        cur.close()
        conn.close()
        
        flash('Transaction added successfully!', 'success')
        return redirect(url_for('dashboard'))
        
    return render_template('add_transaction.html')

@app.route('/upload_csv', methods=['GET', 'POST'])
@login_required
def upload_csv():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file part', 'danger')
            return redirect(request.url)
            
        file = request.files['file']
        if file.filename == '':
            flash('No selected file', 'danger')
            return redirect(request.url)
            
        # --- Handle CSV ---
        if file and file.filename.endswith('.csv'):
            try:
                # Parse CSV using pandas
                df = pd.read_csv(file)
                
                # Detect bank name from filename
                detected_bank = 'Generic'
                for keyword in ['hdfc', 'icici', 'sbi', 'axis', 'canara', 'pnb', 'bob', 'kotak', 'yesbank', 'paytm']:
                    if keyword in file.filename.lower():
                        detected_bank = keyword.upper()
                        break
                
                # Detect account number if there are digits in filename
                detected_acc = 'Unknown'
                digits = re.findall(r'\d+', file.filename)
                if digits:
                    # Pick the longest digit string (typically the account number part)
                    longest_digit = max(digits, key=len)
                    if len(longest_digit) >= 4:
                        detected_acc = f"******{longest_digit[-4:]}"
                
                # Detect running balance from columns
                detected_balance = 0.0
                balance_col = None
                for col in df.columns:
                    if any(k in col.lower() for k in ['balance', 'bal', 'running balance', 'outstanding', 'cr_bal', 'dr_bal']):
                        balance_col = col
                        break
                
                if balance_col and not df.empty:
                    try:
                        row_idx = -1
                        if 'Date' in df.columns:
                            # Parse dates to find the index of the latest date
                            df['ParsedDate'] = pd.to_datetime(df['Date'], errors='coerce')
                            if not df['ParsedDate'].isna().all():
                                row_idx = df['ParsedDate'].idxmax()
                        
                        bal_str = str(df.loc[row_idx][balance_col]).replace(',', '').replace('INR', '').replace('Rs', '').strip()
                        match = re.search(r'([\d\.]+)', bal_str)
                        if match:
                            detected_balance = float(match.group(1))
                    except Exception as e:
                        print("Error extracting balance from CSV:", e)
                
                # Save the bank account to table
                if detected_bank != 'Generic':
                    save_bank_account(current_user.id, detected_bank, detected_acc, detected_balance)
                
                conn = get_db_connection()
                cur = conn.cursor()
                
                count = 0
                for index, row in df.iterrows():
                    date_val = pd.to_datetime(row['Date']).date() if 'Date' in row else datetime.now().date()
                    merchant_val = row['Merchant'] if 'Merchant' in row else 'Unknown'
                    amount_val = row['Amount'] if 'Amount' in row else 0
                    
                    if 'Category' in row and pd.notna(row['Category']):
                        category_val = row['Category']
                    else:
                        category_val = auto_categorize(merchant_val)
                    
                    # Avoid duplicates
                    cur.execute('''
                        SELECT id FROM transactions 
                        WHERE user_id = %s AND date = %s AND merchant = %s AND amount = %s
                    ''', (current_user.id, date_val, merchant_val, amount_val))
                    if not cur.fetchone():
                        cur.execute('''
                            INSERT INTO transactions (user_id, amount, date, merchant, category, bank_name, account_no)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ''', (current_user.id, amount_val, date_val, merchant_val, category_val, detected_bank, detected_acc))
                        count += 1
                    
                conn.commit()
                cur.close()
                conn.close()
                
                flash(f'Successfully imported {count} transactions from CSV! Bank account: {detected_bank}', 'success')
                return redirect(url_for('dashboard'))
            except Exception as e:
                flash(f'Error processing CSV: {str(e)}', 'danger')
                
        # --- Handle PDF ---
        elif file and file.filename.endswith('.pdf'):
            try:
                file.save('debug_statement.pdf')
                password = request.form.get('pdf_password', '')
                bank_name = request.form.get('bank_name', 'Generic')
                
                text = ""
                with pdfplumber.open('debug_statement.pdf', password=password if password else None) as pdf:
                    for page in pdf.pages:
                        text += page.extract_text() + "\n"
                        
                transactions_found = []
                
                # --- AI Statement Parser (Primary) ---
                if os.environ.get("GEMINI_API_KEY") and text.strip() and client:
                    try:
                        prompt = f"""You are a precise financial data extractor. I am giving you the raw text of a bank statement from an Indian bank.
Your job is to extract account details and ONLY the debit/spend transactions. Do not include credits, deposits, opening/closing balances as transactions, or summary lines.
For each transaction, assign a smart category from this exact list: ["Food & Dining", "Shopping", "Utilities", "Transport", "Entertainment", "Health", "Investments", "Internal Transfer", "Other"].
Return ONLY a valid JSON object with this exact structure:
{{
  "bank_name": "string (e.g. HDFC, ICICI, SBI, Axis)",
  "account_no": "string (masked, e.g. ******4086)",
  "current_balance": float (the final closing balance of the statement),
  "transactions": [
    {{ "date": "YYYY-MM-DD", "merchant": "string (max 100 chars, cleaned up name)", "amount": float, "category": "string" }}
  ]
}}
Do not return markdown, backticks, or any other text. Here is the statement text:

{text[:50000]}"""
                        
                        response = client.models.generate_content(
                            model='gemini-2.5-flash',
                            contents=prompt
                        )
                        res_text = response.text.replace('```json', '').replace('```', '').strip()
                        data = json.loads(res_text)
                        
                        extracted_bank_name = data.get('bank_name', bank_name)
                        extracted_acc_no = data.get('account_no', 'Unknown')
                        extracted_balance = float(data.get('current_balance', 0))
                        
                        for item in data.get('transactions', []):
                            cat = item.get('category', 'Other')
                            # Ensure safety
                            if cat not in ["Food & Dining", "Shopping", "Utilities", "Transport", "Entertainment", "Health", "Investments", "Internal Transfer", "Other"]:
                                cat = 'Other'
                                
                            # Self transfer detection logic (hardcoded fallback)
                            if 'TRANSFER' in item['merchant'].upper() or 'SELF' in item['merchant'].upper() or 'TO OWN A/C' in item['merchant'].upper():
                                cat = 'Internal Transfer'
                                
                            transactions_found.append({
                                'date': pd.to_datetime(item['date']).date(),
                                'merchant': str(item['merchant'])[:250],
                                'amount': float(item['amount']),
                                'category': cat,
                                'bank_name': extracted_bank_name,
                                'account_no': extracted_acc_no
                            })
                            
                        # Update bank_accounts table using helper
                        save_bank_account(current_user.id, extracted_bank_name, extracted_acc_no, extracted_balance)
                            
                    except Exception as ai_e:
                        print("AI Parsing failed, falling back to regex. Error:", ai_e)
                
                # --- Universal Regex Parser (Fallback for ALL Banks) ---
                if not transactions_found:
                    print("Running Universal Regex Mega-Parser...")
                    
                    # 1. Try to detect Bank Name from statement text (checking header first)
                    detected_bank = 'Generic'
                    text_upper = text.upper()
                    
                    # Look for IFSC patterns first (very robust)
                    ifsc_match = re.search(r'IFSC\s*(?:CODE)?\s*[:\-\s\.]*([A-Z]{4})\d{7}', text_upper)
                    if ifsc_match:
                        ifsc_prefix = ifsc_match.group(1)
                        ifsc_map = {
                            'CNRB': 'CANARA',
                            'SBIN': 'SBI',
                            'HDFC': 'HDFC',
                            'ICIC': 'ICICI',
                            'UTIB': 'AXIS',
                            'BARB': 'BOB',
                            'KKBK': 'KOTAK',
                            'YESB': 'YESBANK',
                            'PYTM': 'PAYTM',
                            'PUNB': 'PNB'
                        }
                        if ifsc_prefix in ifsc_map:
                            detected_bank = ifsc_map[ifsc_prefix]
                            
                    # If IFSC not found or not matched, check for full bank names in the header (excluding transaction details)
                    if detected_bank == 'Generic':
                        header_lines = []
                        for line in text.split('\n')[:40]:
                            if not re.search(r'\d{2}[-/\.]\d{2}[-/\.]\d{2,4}', line):
                                header_lines.append(line.upper())
                        
                        header_text = "\n".join(header_lines)
                        
                        bank_keywords = {
                            'ICICI': ['ICICI BANK', 'ICICI '],
                            'HDFC': ['HDFC BANK', 'HDFC '],
                            'SBI': ['STATE BANK OF INDIA', 'SBI '],
                            'AXIS': ['AXIS BANK', 'AXIS '],
                            'CANARA': ['CANARA BANK', 'CANARA '],
                            'PNB': ['PUNJAB NATIONAL BANK', 'PNB '],
                            'BOB': ['BANK OF BARODA', 'BOB '],
                            'KOTAK': ['KOTAK MAHINDRA', 'KOTAK '],
                            'YESBANK': ['YES BANK'],
                            'PAYTM': ['PAYTM PAYMENTS BANK', 'PAYTM ']
                        }
                        for bank, keywords in bank_keywords.items():
                            if any(k in header_text for k in keywords):
                                detected_bank = bank
                                break
                    if detected_bank == 'Generic':
                        detected_bank = bank_name
                        
                    # 2. Try to detect Account Number from statement text
                    detected_acc = 'Unknown'
                    acc_match = re.search(r'(?:A/C\s*(?:NO|NUMBER)?|ACCOUNT\s*(?:NO|NUMBER)?)\s*[:\-\s\.]*([A-Z0-9\*xX]+)', text_upper)
                    if acc_match:
                        val = acc_match.group(1).strip()
                        if any(c.isdigit() for c in val) or '*' in val or 'X' in val:
                            detected_acc = val[:20]
                            
                    # 3. Try to detect Closing Balance from statement text
                    detected_balance = 0.0
                    bal_match = re.search(r'(?:CLOSING|AVAILABLE|AVAILABLE\s+BALANCE|CLEAR|LEDGER|BAL|BALANCE)\s*(?:BALANCE)?\s*[:\-\s\.]*(?:INR|RS\.?)?\s*([\d,]+\.\d{2})', text_upper)
                    if bal_match:
                        try:
                            detected_balance = float(bal_match.group(1).replace(',', ''))
                        except:
                            pass
                    
                    lines = text.split('\n')
                    # Match dates like 23/04/2026, 23-04-2026, 23.04.2026, 23-Apr-2026
                    date_pattern = r'(\d{2}[-/\.]\d{2}[-/\.]\d{2,4}|\d{2}[-/\.][A-Za-z]{3}[-/\.]\d{2,4})'
                    
                    for i, line in enumerate(lines):
                        date_match = re.search(date_pattern, line)
                        if date_match:
                            # Extract all currency-like numbers
                            amounts = re.findall(r'[\d,]+\.\d{2}', line)
                            
                            if len(amounts) >= 1:
                                date_str = date_match.group(1)
                                amount = float(amounts[0].replace(',', ''))
                                
                                # If running balance is present on transaction line and direct balance was not found
                                if len(amounts) >= 2 and detected_balance == 0.0:
                                    try:
                                        run_bal = float(amounts[-1].replace(',', ''))
                                        detected_balance = run_bal
                                    except:
                                        pass
                                
                                # Isolate merchant text
                                merchant = line.replace(date_str, '').strip()
                                for a in amounts:
                                    merchant = merchant.replace(a, '').strip()
                                merchant = re.sub(r'^\d+\s+', '', merchant).strip() # Remove S.No if present
                                
                                # If narration is empty or very short, it's likely on the next or previous line (e.g. ICICI)
                                if len(merchant) < 10 and i + 1 < len(lines):
                                    merchant += " " + lines[i+1].strip()
                                    
                                # Heuristics to determine if it's a debit/spend
                                is_spend = False
                                if 'UPI' in merchant.upper() or 'DR' in merchant.upper() or 'DEBIT' in merchant.upper() or 'POS' in merchant.upper():
                                    is_spend = True
                                elif len(amounts) >= 2:
                                    # If there are multiple amounts, it's a good guess it's a standard bank row.
                                    # We'll assume the first amount is a debit if the text implies a merchant.
                                    if len(merchant) > 5 and not ('CR' in merchant.upper() or 'DEPOSIT' in merchant.upper()):
                                        is_spend = True
                                        
                                if is_spend and amount > 0:
                                    merchant_clean = merchant
                                    # Extract exact merchant name from UPI narration
                                    if 'UPI/DR/' in merchant_clean.upper() or 'UPI/CR/' in merchant_clean.upper():
                                        parts = merchant_clean.split('/')
                                        if len(parts) > 3:
                                            merchant_clean = parts[3]
                                    elif 'UPI/' in merchant_clean.upper():
                                        parts = merchant_clean.split('/')
                                        if len(parts) > 2:
                                            merchant_clean = parts[2]
                                            
                                    if len(merchant_clean) < 3:
                                        merchant_clean = merchant[-50:]
                                        
                                    try:
                                        date_str_clean = date_str.replace('.', '/')
                                        date_val = pd.to_datetime(date_str_clean, dayfirst=True).date()
                                        
                                        transactions_found.append({
                                            'date': date_val,
                                            'merchant': merchant_clean[:250],
                                            'amount': amount,
                                            'category': auto_categorize(merchant_clean),
                                            'bank_name': detected_bank,
                                            'account_no': detected_acc
                                        })
                                    except Exception as e:
                                        print("Date parse error:", e)
                                        
                    # Save detected bank account after processing all lines to get the latest running balance
                    if detected_bank != 'Generic':
                        save_bank_account(current_user.id, detected_bank, detected_acc, detected_balance)
                                        
                # Save to DB
                conn = get_db_connection()
                cur = conn.cursor()
                inserted_count = 0
                for txn in transactions_found:
                    # Avoid duplicates
                    cur.execute('SELECT id FROM transactions WHERE user_id = %s AND date = %s AND merchant = %s AND amount = %s', (current_user.id, txn['date'], txn['merchant'], txn['amount']))
                    if not cur.fetchone():
                        cur.execute('''
                            INSERT INTO transactions (user_id, amount, date, merchant, category, bank_name, account_no)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ''', (current_user.id, txn['amount'], txn['date'], txn['merchant'], txn['category'], txn.get('bank_name', 'Generic'), txn.get('account_no', 'Unknown')))
                        inserted_count += 1
                conn.commit()
                cur.close()
                conn.close()
                
                flash(f'Successfully imported {inserted_count} new spends from PDF! (Skipped duplicates)', 'success')
                return redirect(url_for('dashboard'))
                
            except Exception as e:
                flash(f'Error processing PDF: {str(e)}. Make sure password is correct.', 'danger')
                
        else:
            flash('Invalid file format. Please upload a PDF or CSV statement.', 'danger')
            
    return render_template('upload_csv.html')



if __name__ == '__main__':
    import webbrowser
    from threading import Timer
    
    def open_browser():
        webbrowser.open_new("http://localhost:5001/login")
        
    if not os.environ.get("WERKZEUG_RUN_MAIN"):
        Timer(1.5, open_browser).start()
        
    app.run(host='localhost', debug=True, port=5001)
