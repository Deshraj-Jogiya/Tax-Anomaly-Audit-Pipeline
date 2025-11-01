-- Tax Anomaly Audit Queries

-- 1. Anomaly Overview by Department
-- Calculates the average audit score, number of flagged claims, total claims, and percentage flagged per department.
SELECT 
    gl.department,
    COUNT(tc.claim_id) AS total_claims,
    SUM(tc.audit_flag) AS flagged_claims,
    ROUND(AVG(tc.audit_score), 2) AS avg_audit_score,
    ROUND((CAST(SUM(tc.audit_flag) AS REAL) / COUNT(tc.claim_id)) * 100, 2) AS flag_percentage
FROM general_ledger gl
JOIN tax_claims tc ON gl.entry_id = tc.entry_id
GROUP BY gl.department
ORDER BY avg_audit_score DESC;

-- 2. Top Flagged Tax Claims (High Priority Audits)
-- Lists the highest-risk tax claims with detailed context for audit review.
SELECT 
    tc.claim_id,
    gl.entry_id,
    gl.transaction_date,
    gl.department,
    gl.account_name,
    gl.amount AS transaction_amount,
    tc.category AS tax_category,
    tc.tax_claimed,
    tc.audit_score,
    tc.audit_flag
FROM tax_claims tc
JOIN general_ledger gl ON tc.entry_id = gl.entry_id
WHERE tc.audit_flag = 1
ORDER BY tc.audit_score DESC, tc.tax_claimed DESC
LIMIT 50;

-- 3. Monthly Audit Flags and Trend Analysis
-- Traces the count of flagged transactions and average risk score over time (monthly).
SELECT 
    strftime('%Y-%m', gl.transaction_date) AS audit_month,
    COUNT(tc.claim_id) AS total_claims,
    SUM(tc.audit_flag) AS flagged_claims,
    ROUND(AVG(tc.audit_score), 2) AS avg_audit_score,
    ROUND(SUM(gl.amount), 2) AS total_amount_spent,
    ROUND(SUM(tc.tax_claimed), 2) AS total_tax_claimed
FROM general_ledger gl
JOIN tax_claims tc ON gl.entry_id = tc.entry_id
GROUP BY audit_month
ORDER BY audit_month ASC;

-- 4. Anomaly Risk and Ratios by Tax Claim Category
-- Summarizes tax claims by category, detailing average risk scores and tax-to-amount ratio.
SELECT 
    tc.category AS tax_category,
    COUNT(tc.claim_id) AS total_claims,
    SUM(tc.audit_flag) AS flagged_claims,
    ROUND(AVG(tc.audit_score), 2) AS avg_audit_score,
    ROUND(SUM(tc.tax_claimed), 2) AS total_tax_claimed,
    ROUND(AVG(tc.tax_claimed / gl.amount) * 100, 2) AS avg_tax_to_amount_percent
FROM tax_claims tc
JOIN general_ledger gl ON tc.entry_id = gl.entry_id
GROUP BY tc.category
ORDER BY flagged_claims DESC, avg_audit_score DESC;

-- 5. First-Digit Count (Empirical Benford Law Check in SQL)
-- Extract first digit of the amount and aggregate to see empirical counts and distribution.
WITH digit_extraction AS (
    SELECT 
        CAST(SUBSTR(CAST(ABS(amount) AS TEXT), 1, 1) AS INTEGER) AS first_digit
    FROM general_ledger
    WHERE amount >= 1
)
SELECT 
    first_digit,
    COUNT(*) AS observed_count,
    ROUND((CAST(COUNT(*) AS REAL) / (SELECT COUNT(*) FROM digit_extraction)) * 100, 2) AS observed_percentage
FROM digit_extraction
WHERE first_digit BETWEEN 1 AND 9
GROUP BY first_digit
ORDER BY first_digit ASC;

-- 6. High-Value Multi-Claim Suspicious Entries
-- Finds entries where the amount is large and the tax claimed is disproportionately high (> 20%).
SELECT 
    gl.entry_id,
    gl.transaction_date,
    gl.department,
    gl.amount,
    tc.tax_claimed,
    ROUND((tc.tax_claimed / gl.amount) * 100, 2) AS tax_percentage,
    tc.audit_score
FROM general_ledger gl
JOIN tax_claims tc ON gl.entry_id = tc.entry_id
WHERE gl.amount > 5000 AND (tc.tax_claimed / gl.amount) > 0.20
ORDER BY tax_percentage DESC;
