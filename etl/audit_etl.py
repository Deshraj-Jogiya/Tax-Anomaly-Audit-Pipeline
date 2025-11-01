import os
import sqlite3
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

def create_db_and_schema(db_path, schema_path):
    """Creates the SQLite database and initializes the schema from schema.sql."""
    print(f"Initializing database at: {db_path}")
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    with open(schema_path, 'r') as f:
        schema_sql = f.read()
        
    cursor.executescript(schema_sql)
    conn.commit()
    conn.close()
    print("Database schema successfully created.")

def generate_benford_amount():
    """Generates a number following Benford's Law distribution using 10^U."""
    # U is uniform. 10^U has first digits distributed according to Benford's Law.
    # We choose values between 10^1.5 (~31.62) and 10^4.5 (~31,622.77)
    u = np.random.uniform(1.5, 4.5)
    return round(10**u, 2)

def generate_anomalous_amount():
    """Generates an anomalous amount that violates Benford's Law (e.g., clusters of high digits or specific values)."""
    # Many manual anomalies cluster just below authorization thresholds (e.g., $5,000 or $10,000)
    # or repeat specific digits (e.g., 9900.00, 9995.00, 8888.00)
    anomaly_type = np.random.choice(['threshold', 'repeated', 'high_digit'])
    
    if anomaly_type == 'threshold':
        # Skews towards digits 4 and 9 (e.g., 4950.00, 9950.00)
        base = np.random.choice([4900.00, 9900.00])
        val = base + np.random.uniform(10.00, 95.00)
    elif anomaly_type == 'repeated':
        val = np.random.choice([888.88, 999.99, 8888.88, 9999.99])
    else:
        # High first digits (like 8 or 9) generated uniformly, violating Benford's Law
        val = np.random.uniform(8000.00, 9500.00)
        
    return round(val, 2)

def simulate_data(db_path, num_entries=1200):
    """Simulates general ledger and tax claim entries, and writes them to the database."""
    print(f"Simulating {num_entries} general ledger entries...")
    np.random.seed(42) # Set seed for reproducibility
    
    departments = ['Finance', 'Engineering', 'Marketing', 'Sales', 'Operations', 'HR', 'R&D']
    accounts = {
        'Finance': ['Audit Fees', 'Bank Charges', 'Consulting Fees'],
        'Engineering': ['Software Licenses', 'Hardware Procurement', 'Cloud Infrastructure'],
        'Marketing': ['Advertising Campaigns', 'Event Sponsorship', 'Design Agencies'],
        'Sales': ['Travel & Entertainment', 'Client Dinners', 'Sales Commission Software'],
        'Operations': ['Equipment Rental', 'Logistics & Shipping', 'Office Supplies'],
        'HR': ['Recruitment Services', 'Training Programs', 'Employee Benefits'],
        'R&D': ['Lab Equipment', 'Research Materials', 'Prototyping Services']
    }
    
    tax_categories = {
        'Software Licenses': 'VAT Standard Rate',
        'Hardware Procurement': 'VAT Standard Rate',
        'Cloud Infrastructure': 'VAT Standard Rate',
        'Audit Fees': 'VAT Exempt',
        'Bank Charges': 'VAT Exempt',
        'Consulting Fees': 'VAT Standard Rate',
        'Advertising Campaigns': 'VAT Standard Rate',
        'Event Sponsorship': 'VAT Reduced Rate',
        'Design Agencies': 'VAT Standard Rate',
        'Travel & Entertainment': 'Entertainment Tax Waiver',
        'Client Dinners': 'Entertainment Tax Waiver',
        'Sales Commission Software': 'VAT Standard Rate',
        'Equipment Rental': 'VAT Standard Rate',
        'Logistics & Shipping': 'VAT Reduced Rate',
        'Office Supplies': 'VAT Standard Rate',
        'Recruitment Services': 'VAT Standard Rate',
        'Training Programs': 'VAT Reduced Rate',
        'Employee Benefits': 'VAT Exempt',
        'Lab Equipment': 'R&D Tax Credit',
        'Research Materials': 'R&D Tax Credit',
        'Prototyping Services': 'R&D Tax Credit'
    }
    
    tax_rates = {
        'VAT Standard Rate': 0.20,
        'VAT Reduced Rate': 0.05,
        'VAT Exempt': 0.00,
        'Entertainment Tax Waiver': 0.10,
        'R&D Tax Credit': 0.25
    }
    
    # Generate dates over the last year
    start_date = datetime(2025, 1, 1)
    
    ledger_entries = []
    tax_claim_entries = []
    
    # 3% to 5% anomaly rate
    anomaly_rate = 0.04
    
    for i in range(1, num_entries + 1):
        dept = np.random.choice(departments)
        acct = np.random.choice(accounts[dept])
        
        # Determine if this entry is anomalous
        is_anomalous = np.random.random() < anomaly_rate
        
        if is_anomalous:
            amount = generate_anomalous_amount()
        else:
            amount = generate_benford_amount()
            
        # Add random descriptions
        desc = f"Payment for {acct.lower()} - Ref #{np.random.randint(100000, 999999)}"
        
        # Generate random date in 2025
        days_offset = np.random.randint(0, 300)
        tx_date = (start_date + timedelta(days=days_offset)).strftime('%Y-%m-%d')
        
        ledger_entries.append((i, tx_date, acct, desc, amount, dept))
        
        # Determine tax claims
        cat = tax_categories[acct]
        base_rate = tax_rates[cat]
        
        if is_anomalous:
            # Anomalous tax claim: either zero, extremely high, or double the allowed rate
            anom_tax_type = np.random.choice(['excessive', 'underclaimed', 'flat_large'])
            if anom_tax_type == 'excessive':
                # Claiming 50% to 80% of amount
                tax_claimed = round(amount * np.random.uniform(0.50, 0.80), 2)
            elif anom_tax_type == 'underclaimed':
                tax_claimed = 0.00
            else:
                tax_claimed = round(np.random.uniform(1000.00, 3000.00), 2)
        else:
            # Normal tax claim
            tax_claimed = round(amount * base_rate, 2)
            
        tax_claim_entries.append((i, cat, tax_claimed))

    # Save to database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Insert ledger entries
    cursor.executemany(
        "INSERT INTO general_ledger (entry_id, transaction_date, account_name, description, amount, department) VALUES (?, ?, ?, ?, ?, ?)",
        ledger_entries
    )
    
    # Insert tax claims (audit_score and audit_flag default to NULL/0)
    cursor.executemany(
        "INSERT INTO tax_claims (entry_id, category, tax_claimed) VALUES (?, ?, ?)",
        tax_claim_entries
    )
    
    conn.commit()
    conn.close()
    
    print(f"Successfully loaded data into database. Total ledger entries: {len(ledger_entries)}, Total tax claims: {len(tax_claim_entries)}")

if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db_path = os.path.join(base_dir, "data", "tax_compliance.db")
    schema_path = os.path.join(base_dir, "db", "schema.sql")
    
    create_db_and_schema(db_path, schema_path)
    simulate_data(db_path, num_entries=1200)
