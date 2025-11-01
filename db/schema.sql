-- Database Schema for Tax Anomaly Audit Pipeline

-- Drop tables if they exist
DROP TABLE IF EXISTS tax_claims;
DROP TABLE IF EXISTS general_ledger;

-- general_ledger table
CREATE TABLE general_ledger (
    entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_date TEXT NOT NULL,
    account_name TEXT NOT NULL,
    description TEXT NOT NULL,
    amount REAL NOT NULL,
    department TEXT NOT NULL
);

-- tax_claims table
CREATE TABLE tax_claims (
    claim_id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id INTEGER NOT NULL,
    category TEXT NOT NULL,
    tax_claimed REAL NOT NULL,
    audit_score REAL,
    audit_flag INTEGER DEFAULT 0,
    FOREIGN KEY (entry_id) REFERENCES general_ledger(entry_id) ON DELETE CASCADE
);
