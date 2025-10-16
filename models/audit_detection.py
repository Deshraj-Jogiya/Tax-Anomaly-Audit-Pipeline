import os
import sys
import sqlite3
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from etl.validate import validate  # noqa: E402

def load_data(db_path):
    """Loads ledger and tax claims data and joins them into a pandas DataFrame."""
    print(f"Loading data from database: {db_path}")
    conn = sqlite3.connect(db_path)
    
    query = """
        SELECT 
            gl.entry_id,
            gl.transaction_date,
            gl.account_name,
            gl.description,
            gl.amount,
            gl.department,
            tc.claim_id,
            tc.category,
            tc.tax_claimed
        FROM general_ledger gl
        JOIN tax_claims tc ON gl.entry_id = tc.entry_id
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def get_first_digit(num):
    """Extracts the first significant digit of a number."""
    s = str(abs(num)).replace('.', '').lstrip('0')
    if s:
        return int(s[0])
    return 0

def calculate_benford_scores(df):
    """Calculates Benford's Law first-digit deviations at individual transaction levels."""
    # Extract first digit for each transaction amount
    df['first_digit'] = df['amount'].apply(get_first_digit)
    
    # Calculate empirical counts and proportions
    digit_counts = df['first_digit'].value_counts()
    total_valid = len(df[df['first_digit'].between(1, 9)])
    
    empirical_probs = {}
    for d in range(1, 10):
        empirical_probs[d] = digit_counts.get(d, 0) / total_valid
        
    # Theoretical Benford distribution
    benford_probs = {d: np.log10(1 + 1.0/d) for d in range(1, 10)}
    
    # Calculate deviation for each digit (overrepresentation of a digit is risky)
    # relative_deviation = (observed - expected) / expected
    digit_deviations = {}
    for d in range(1, 10):
        diff = empirical_probs[d] - benford_probs[d]
        digit_deviations[d] = max(0.0, diff) / benford_probs[d] # focus on overrepresented digits
        
    # Max-min normalize digit deviations to scale scores to [0, 1]
    max_dev = max(digit_deviations.values()) if max(digit_deviations.values()) > 0 else 1.0
    scaled_digit_scores = {d: digit_deviations[d] / max_dev for d in range(1, 10)}
    scaled_digit_scores[0] = 0.0 # for entries with no valid first digit
    
    # Map back to dataframe
    df['benford_dev_score'] = df['first_digit'].map(scaled_digit_scores)
    return df

def run_isolation_forest(df):
    """Trains Isolation Forest on numeric features to compute spatial anomaly scores."""
    # Feature Engineering
    df['tax_ratio'] = df['tax_claimed'] / (df['amount'] + 1e-5) # Prevent division by zero
    
    # Compute department-level average amount and deviations
    dept_avg = df.groupby('department')['amount'].transform('mean')
    df['dept_amount_ratio'] = df['amount'] / (dept_avg + 1e-5)
    
    # Select features for Isolation Forest
    features = ['amount', 'tax_claimed', 'tax_ratio', 'dept_amount_ratio']
    X = df[features].copy()
    
    # Scale features
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    # Fit Isolation Forest
    # Contamination is set to 5% to capture the simulated anomalies
    clf = IsolationForest(n_estimators=100, contamination=0.05, random_state=42)
    clf.fit(X_scaled)
    
    # Decision function returns lower values for anomalies. We invert and scale.
    raw_scores = -clf.decision_function(X_scaled)
    
    # Scale scores to [0, 1]
    min_score = raw_scores.min()
    max_score = raw_scores.max()
    
    df['iforest_score'] = (raw_scores - min_score) / (max_score - min_score)
    return df

def compute_compliance_scores(df, db_path):
    """Combines Benford and Isolation Forest scores, flags audits, and updates database."""
    print("Computing combined Compliance Risk Scores...")
    # Weights for risk score: 30% Benford's Law deviation, 70% Isolation Forest multi-feature anomaly
    w_benford = 0.30
    w_iforest = 0.70
    
    df['compliance_risk_score'] = (w_benford * df['benford_dev_score'] + w_iforest * df['iforest_score']) * 100
    
    # Set threshold for flagging high priority audits (top 5% or risk score >= 65)
    threshold = 65.0
    df['model_flag'] = (df['compliance_risk_score'] >= threshold).astype(int)
    # Deterministic rule layer: a tax claim that is not the category's rate times the amount (etl/validate.py)
    df['rule_flag'] = validate(df)['tax_rate_mismatch'].astype(int)
    df['audit_flag'] = (df['model_flag'] | df['rule_flag']).astype(int)
    
    # Summarize results
    flagged = df[df['audit_flag'] == 1]
    print(f"Audit execution complete.")
    print(f"Total entries processed: {len(df)}")
    print(f"Total claims flagged for audit: {len(flagged)} ({len(flagged)/len(df)*100:.2f}%)")
    print(f"Average Compliance Risk Score: {df['compliance_risk_score'].mean():.2f}")
    
    # Write results back to SQLite
    print("Updating database with audit scores and flags...")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Prepare batch update statements
    updates = []
    for _, row in df.iterrows():
        updates.append((
            float(row['compliance_risk_score']),
            int(row['audit_flag']),
            int(row['claim_id'])
        ))
        
    cursor.executemany(
        "UPDATE tax_claims SET audit_score = ?, audit_flag = ? WHERE claim_id = ?",
        updates
    )
    
    conn.commit()
    conn.close()
    print("Database successfully updated.")
    
    # Print the top 5 anomalies
    print("\n--- TOP 5 SUSPICIOUS ENTRIES ---")
    top_5 = df.sort_values(by='compliance_risk_score', ascending=False).head(5)
    for idx, row in top_5.iterrows():
        print(f"Risk Score: {row['compliance_risk_score']:.1f} | Dept: {row['department']} | Category: {row['category']}")
        print(f"  Amount: ${row['amount']:.2f} | Tax Claimed: ${row['tax_claimed']:.2f} (Ratio: {row['tax_ratio']*100:.1f}%)")
        print(f"  Description: {row['description']}\n")

def _layer_metrics(flagged, truth):
    tp = int((flagged & truth).sum())
    return {"flagged": int(flagged.sum()), "true_positives": tp,
            "precision": tp / int(flagged.sum()) if flagged.any() else 0.0,
            "recall": tp / int(truth.sum()) if truth.any() else 0.0}


def review_effort(df, truth, share=0.9):
    """Entries an auditor opens to find `share` of the injected anomalies: in priority order (rule hits first, then by risk
    score) and in ledger order (entry id)."""
    need = int(np.ceil(share * truth.sum()))
    priority = df.assign(_t=truth).sort_values(["rule_flag", "compliance_risk_score"], ascending=False)
    ledger = df.assign(_t=truth).sort_values("entry_id")
    by_priority = int(np.argmax(priority["_t"].cumsum().to_numpy() >= need)) + 1
    by_ledger = int(np.argmax(ledger["_t"].cumsum().to_numpy() >= need)) + 1
    return {"share_of_anomalies": share, "anomalies_to_find": need, "entries_opened_priority_order": by_priority,
            "entries_opened_ledger_order": by_ledger, "reduction": round(1 - by_priority / by_ledger, 4)}


def evaluate_against_labels(df, db_path):
    """Score each detection layer against the simulator's injected anomalies (labels the detectors never see), measure review
    effort, and write exports/detection_layers.csv and exports/review_effort.csv."""
    conn = sqlite3.connect(db_path)
    labels = {r[0] for r in conn.execute("SELECT entry_id FROM injected_anomalies")}
    conn.close()
    truth = df["entry_id"].isin(labels)
    layers = {name: _layer_metrics(df[col] == 1, truth)
              for name, col in (("model", "model_flag"), ("rule", "rule_flag"), ("combined", "audit_flag"))}
    effort = review_effort(df, truth)
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(db_path))), "exports")
    os.makedirs(out_dir, exist_ok=True)
    pd.DataFrame([{"layer": k, **v} for k, v in layers.items()]).round(4).to_csv(os.path.join(out_dir, "detection_layers.csv"), index=False)
    pd.DataFrame([effort]).to_csv(os.path.join(out_dir, "review_effort.csv"), index=False)
    print("\n--- EVALUATION AGAINST INJECTED ANOMALIES ---")
    for name, m in layers.items():
        print(f"{name:8s} flagged {m['flagged']:4d} | correct {m['true_positives']:3d} | precision {m['precision']:.1%} | recall {m['recall']:.1%}")
    print(f"To find {effort['anomalies_to_find']} of {int(truth.sum())} anomalies an auditor opens {effort['entries_opened_priority_order']} "
          f"entries in priority order vs {effort['entries_opened_ledger_order']} in ledger order ({effort['reduction']:.0%} fewer)")
    combined = layers["combined"]
    return {"injected": int(truth.sum()), **combined, "review_effort": effort}


def run(db_path):
    df = load_data(db_path)
    df = calculate_benford_scores(df)
    df = run_isolation_forest(df)
    compute_compliance_scores(df, db_path)
    return df, evaluate_against_labels(df, db_path)


if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    run(os.path.join(base_dir, "data", "tax_compliance.db"))
