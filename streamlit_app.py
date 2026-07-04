# Cortex Analyst chat app for Insurance Underwriting with Golden Set evaluation
# Co-authored with CoCo

import os
import re
import pandas as pd
from typing import Optional

try:
    import streamlit as st
    STREAMLIT_AVAILABLE = True
except ImportError:
    STREAMLIT_AVAILABLE = False

# --- Configuration ---
SEMANTIC_VIEW_FQN = "INSURANCE_UNDERWRITING.RAW.UNDERWRITING_ANALYTICS"
DB_SCHEMA = "INSURANCE_UNDERWRITING.RAW"

# --- Pre-built query catalog ---
QUERY_CATALOG = {
    "total policyholders": {
        "sql": f"SELECT COUNT(*) AS TOTAL_POLICYHOLDERS FROM {DB_SCHEMA}.RAW_POLICYHOLDERS",
        "description": "Total number of policyholders in the system.",
    },
    "smoker count": {
        "sql": f"SELECT COUNT(*) AS SMOKER_COUNT FROM {DB_SCHEMA}.RAW_POLICYHOLDERS WHERE SMOKER_FLAG = TRUE",
        "description": "Number of policyholders who are smokers.",
    },
    "policies by status": {
        "sql": f"SELECT POLICY_STATUS, COUNT(*) AS POLICY_COUNT FROM {DB_SCHEMA}.RAW_POLICIES GROUP BY POLICY_STATUS ORDER BY POLICY_COUNT DESC",
        "description": "Breakdown of policies by their current status.",
    },
    "premium by product line": {
        "sql": f"SELECT PRODUCT_LINE, COUNT(*) AS POLICY_COUNT, ROUND(SUM(ANNUAL_PREMIUM), 2) AS TOTAL_PREMIUM, ROUND(AVG(ANNUAL_PREMIUM), 2) AS AVG_PREMIUM FROM {DB_SCHEMA}.RAW_POLICIES GROUP BY PRODUCT_LINE ORDER BY TOTAL_PREMIUM DESC",
        "description": "Total and average premium by product line.",
    },
    "underwriting decisions": {
        "sql": f"SELECT DECISION_OUTCOME, COUNT(*) AS DECISION_COUNT, ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) AS PERCENTAGE FROM {DB_SCHEMA}.RAW_UNDERWRITING_DECISIONS GROUP BY DECISION_OUTCOME ORDER BY DECISION_COUNT DESC",
        "description": "Distribution of underwriting decision outcomes.",
    },
    "risk class": {
        "sql": f"SELECT RISK_CLASS, COUNT(*) AS COUNT, ROUND(AVG(RISK_SCORE), 2) AS AVG_RISK_SCORE FROM {DB_SCHEMA}.RAW_UNDERWRITING_DECISIONS GROUP BY RISK_CLASS ORDER BY AVG_RISK_SCORE",
        "description": "Risk class distribution with average risk scores.",
    },
    "payment status": {
        "sql": f"SELECT PAYMENT_STATUS, COUNT(*) AS PAYMENT_COUNT, SUM(AMOUNT_DUE) AS TOTAL_DUE, SUM(AMOUNT_PAID) AS TOTAL_PAID FROM {DB_SCHEMA}.RAW_PREMIUMS GROUP BY PAYMENT_STATUS ORDER BY PAYMENT_COUNT DESC",
        "description": "Premium collection performance by payment status.",
    },
    "claims by status": {
        "sql": f"SELECT CLAIM_STATUS, COUNT(*) AS CLAIM_COUNT, ROUND(SUM(CLAIM_AMOUNT), 2) AS TOTAL_CLAIMED, ROUND(SUM(APPROVED_AMOUNT), 2) AS TOTAL_APPROVED FROM {DB_SCHEMA}.RAW_CLAIMS GROUP BY CLAIM_STATUS ORDER BY CLAIM_COUNT DESC",
        "description": "Claims summary grouped by claim status.",
    },
    "claims by product": {
        "sql": f"SELECT p.PRODUCT_LINE, COUNT(c.CLAIM_ID) AS CLAIM_COUNT, ROUND(AVG(c.CLAIM_AMOUNT), 2) AS AVG_CLAIM_AMOUNT FROM {DB_SCHEMA}.RAW_CLAIMS c JOIN {DB_SCHEMA}.RAW_POLICIES p ON c.POLICY_ID = p.POLICY_ID GROUP BY p.PRODUCT_LINE ORDER BY CLAIM_COUNT DESC",
        "description": "Claims breakdown by product line with average claim amounts.",
    },
    "fraud claims": {
        "sql": f"SELECT COUNT(*) AS FRAUD_CLAIM_COUNT, ROUND(SUM(CLAIM_AMOUNT), 2) AS TOTAL_FRAUD_AMOUNT FROM {DB_SCHEMA}.RAW_CLAIMS WHERE FRAUD_FLAG = TRUE",
        "description": "Count and total amount of fraud-flagged claims.",
    },
    "top states": {
        "sql": f"SELECT ph.STATE_CODE, COUNT(DISTINCT pol.POLICY_ID) AS POLICIES, SUM(pol.SUM_ASSURED) AS TOTAL_SUM_ASSURED FROM {DB_SCHEMA}.RAW_POLICIES pol JOIN {DB_SCHEMA}.RAW_POLICYHOLDERS ph ON pol.POLICYHOLDER_ID = ph.POLICYHOLDER_ID GROUP BY ph.STATE_CODE ORDER BY TOTAL_SUM_ASSURED DESC LIMIT 10",
        "description": "Top states by total sum assured.",
    },
    "loss ratio": {
        "sql": f"SELECT p.PRODUCT_LINE, SUM(p.ANNUAL_PREMIUM) AS TOTAL_PREMIUM, SUM(c.PAID_AMOUNT) AS TOTAL_PAID_CLAIMS, ROUND(SUM(c.PAID_AMOUNT) / NULLIF(SUM(p.ANNUAL_PREMIUM), 0) * 100, 2) AS LOSS_RATIO_PCT FROM {DB_SCHEMA}.RAW_POLICIES p LEFT JOIN {DB_SCHEMA}.RAW_CLAIMS c ON p.POLICY_ID = c.POLICY_ID AND c.CLAIM_STATUS = 'Paid' GROUP BY p.PRODUCT_LINE ORDER BY LOSS_RATIO_PCT DESC",
        "description": "Loss ratio (paid claims / premium) by product line.",
    },
    "collection rate": {
        "sql": f"SELECT PAYMENT_METHOD, COUNT(*) AS TOTAL_PAYMENTS, SUM(CASE WHEN PAYMENT_STATUS IN ('Paid', 'Paid Late') THEN 1 ELSE 0 END) AS SUCCESSFUL_PAYMENTS, ROUND(SUM(CASE WHEN PAYMENT_STATUS IN ('Paid', 'Paid Late') THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS COLLECTION_RATE_PCT FROM {DB_SCHEMA}.RAW_PREMIUMS GROUP BY PAYMENT_METHOD ORDER BY COLLECTION_RATE_PCT DESC",
        "description": "Premium collection rate by payment method.",
    },
    "smoker risk": {
        "sql": f"SELECT ph.SMOKER_FLAG, COUNT(DISTINCT ph.POLICYHOLDER_ID) AS POLICYHOLDERS, ROUND(AVG(ph.ANNUAL_INCOME), 2) AS AVG_INCOME, ROUND(AVG(ph.BMI), 1) AS AVG_BMI, COUNT(DISTINCT c.CLAIM_ID) AS TOTAL_CLAIMS, ROUND(COUNT(DISTINCT c.CLAIM_ID) * 1.0 / COUNT(DISTINCT ph.POLICYHOLDER_ID), 3) AS CLAIMS_PER_HOLDER FROM {DB_SCHEMA}.RAW_POLICYHOLDERS ph LEFT JOIN {DB_SCHEMA}.RAW_CLAIMS c ON ph.POLICYHOLDER_ID = c.POLICYHOLDER_ID GROUP BY ph.SMOKER_FLAG",
        "description": "Smoker vs non-smoker risk profile comparison.",
    },
    "policy funnel": {
        "sql": f"SELECT p.PRODUCT_LINE, COUNT(DISTINCT p.POLICY_ID) AS TOTAL_POLICIES, COUNT(DISTINCT CASE WHEN ud.DECISION_OUTCOME LIKE 'Approved%' THEN p.POLICY_ID END) AS APPROVED_POLICIES, COUNT(DISTINCT c.CLAIM_ID) AS CLAIMS_FILED, COUNT(DISTINCT CASE WHEN c.CLAIM_STATUS = 'Paid' THEN c.CLAIM_ID END) AS CLAIMS_PAID FROM {DB_SCHEMA}.RAW_POLICIES p LEFT JOIN {DB_SCHEMA}.RAW_UNDERWRITING_DECISIONS ud ON p.POLICY_ID = ud.POLICY_ID LEFT JOIN {DB_SCHEMA}.RAW_CLAIMS c ON p.POLICY_ID = c.POLICY_ID GROUP BY p.PRODUCT_LINE ORDER BY TOTAL_POLICIES DESC",
        "description": "End-to-end funnel from policies to claims by product line.",
    },
}

# --- Golden Set: ground truth questions with expected SQL and results ---
GOLDEN_SET = [
    {
        "id": 1,
        "question": "How many policyholders are there in total?",
        "complexity": "Simple",
        "ground_truth_sql": f"SELECT COUNT(*) AS TOTAL_POLICYHOLDERS FROM {DB_SCHEMA}.RAW_POLICYHOLDERS",
        "expected_row_count": 1,
        "expected_columns": ["TOTAL_POLICYHOLDERS"],
    },
    {
        "id": 2,
        "question": "How many policyholders are smokers?",
        "complexity": "Simple",
        "ground_truth_sql": f"SELECT COUNT(*) AS SMOKER_COUNT FROM {DB_SCHEMA}.RAW_POLICYHOLDERS WHERE SMOKER_FLAG = TRUE",
        "expected_row_count": 1,
        "expected_columns": ["SMOKER_COUNT"],
    },
    {
        "id": 3,
        "question": "What is the breakdown of policies by status?",
        "complexity": "Simple",
        "ground_truth_sql": f"SELECT POLICY_STATUS, COUNT(*) AS POLICY_COUNT FROM {DB_SCHEMA}.RAW_POLICIES GROUP BY POLICY_STATUS ORDER BY POLICY_COUNT DESC",
        "expected_row_count": 5,
        "expected_columns": ["POLICY_STATUS", "POLICY_COUNT"],
    },
    {
        "id": 4,
        "question": "What is the average annual premium by product line?",
        "complexity": "Medium",
        "ground_truth_sql": f"SELECT PRODUCT_LINE, ROUND(AVG(ANNUAL_PREMIUM), 2) AS AVG_ANNUAL_PREMIUM FROM {DB_SCHEMA}.RAW_POLICIES GROUP BY PRODUCT_LINE ORDER BY AVG_ANNUAL_PREMIUM DESC",
        "expected_row_count": 5,
        "expected_columns": ["PRODUCT_LINE", "AVG_ANNUAL_PREMIUM"],
    },
    {
        "id": 5,
        "question": "What is the distribution of underwriting decision outcomes?",
        "complexity": "Medium",
        "ground_truth_sql": f"SELECT DECISION_OUTCOME, COUNT(*) AS DECISION_COUNT, ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) AS PERCENTAGE FROM {DB_SCHEMA}.RAW_UNDERWRITING_DECISIONS GROUP BY DECISION_OUTCOME ORDER BY DECISION_COUNT DESC",
        "expected_row_count": 4,
        "expected_columns": ["DECISION_OUTCOME", "DECISION_COUNT", "PERCENTAGE"],
    },
    {
        "id": 6,
        "question": "What is the premium collection performance by payment status?",
        "complexity": "Medium",
        "ground_truth_sql": f"SELECT PAYMENT_STATUS, COUNT(*) AS PAYMENT_COUNT, SUM(AMOUNT_DUE) AS TOTAL_DUE, SUM(AMOUNT_PAID) AS TOTAL_PAID FROM {DB_SCHEMA}.RAW_PREMIUMS GROUP BY PAYMENT_STATUS ORDER BY PAYMENT_COUNT DESC",
        "expected_row_count": 4,
        "expected_columns": ["PAYMENT_STATUS", "PAYMENT_COUNT", "TOTAL_DUE", "TOTAL_PAID"],
    },
    {
        "id": 7,
        "question": "What is the claim count and average claim amount by product line?",
        "complexity": "Medium",
        "ground_truth_sql": f"SELECT p.PRODUCT_LINE, COUNT(c.CLAIM_ID) AS CLAIM_COUNT, ROUND(AVG(c.CLAIM_AMOUNT), 2) AS AVG_CLAIM_AMOUNT FROM {DB_SCHEMA}.RAW_CLAIMS c JOIN {DB_SCHEMA}.RAW_POLICIES p ON c.POLICY_ID = p.POLICY_ID GROUP BY p.PRODUCT_LINE ORDER BY CLAIM_COUNT DESC",
        "expected_row_count": 5,
        "expected_columns": ["PRODUCT_LINE", "CLAIM_COUNT", "AVG_CLAIM_AMOUNT"],
    },
    {
        "id": 8,
        "question": "What are the top 5 states by total sum assured?",
        "complexity": "Medium",
        "ground_truth_sql": f"SELECT ph.STATE_CODE, COUNT(DISTINCT pol.POLICY_ID) AS POLICIES, SUM(pol.SUM_ASSURED) AS TOTAL_SUM_ASSURED FROM {DB_SCHEMA}.RAW_POLICIES pol JOIN {DB_SCHEMA}.RAW_POLICYHOLDERS ph ON pol.POLICYHOLDER_ID = ph.POLICYHOLDER_ID GROUP BY ph.STATE_CODE ORDER BY TOTAL_SUM_ASSURED DESC LIMIT 5",
        "expected_row_count": 5,
        "expected_columns": ["STATE_CODE", "POLICIES", "TOTAL_SUM_ASSURED"],
    },
    {
        "id": 9,
        "question": "What is the risk class distribution with average risk scores?",
        "complexity": "Medium",
        "ground_truth_sql": f"SELECT RISK_CLASS, COUNT(*) AS COUNT, ROUND(AVG(RISK_SCORE), 2) AS AVG_RISK_SCORE FROM {DB_SCHEMA}.RAW_UNDERWRITING_DECISIONS GROUP BY RISK_CLASS ORDER BY AVG_RISK_SCORE",
        "expected_row_count": 6,
        "expected_columns": ["RISK_CLASS", "COUNT", "AVG_RISK_SCORE"],
    },
    {
        "id": 10,
        "question": "How many claims are flagged as potential fraud?",
        "complexity": "Medium",
        "ground_truth_sql": f"SELECT COUNT(*) AS FRAUD_CLAIM_COUNT, SUM(CLAIM_AMOUNT) AS TOTAL_FRAUD_AMOUNT FROM {DB_SCHEMA}.RAW_CLAIMS WHERE FRAUD_FLAG = TRUE",
        "expected_row_count": 1,
        "expected_columns": ["FRAUD_CLAIM_COUNT", "TOTAL_FRAUD_AMOUNT"],
    },
    {
        "id": 11,
        "question": "What is the loss ratio by product line?",
        "complexity": "Complex",
        "ground_truth_sql": f"SELECT p.PRODUCT_LINE, SUM(p.ANNUAL_PREMIUM) AS TOTAL_PREMIUM, SUM(c.PAID_AMOUNT) AS TOTAL_PAID_CLAIMS, ROUND(SUM(c.PAID_AMOUNT) / NULLIF(SUM(p.ANNUAL_PREMIUM), 0) * 100, 2) AS LOSS_RATIO_PCT FROM {DB_SCHEMA}.RAW_POLICIES p LEFT JOIN {DB_SCHEMA}.RAW_CLAIMS c ON p.POLICY_ID = c.POLICY_ID AND c.CLAIM_STATUS = 'Paid' GROUP BY p.PRODUCT_LINE ORDER BY LOSS_RATIO_PCT DESC",
        "expected_row_count": 5,
        "expected_columns": ["PRODUCT_LINE", "TOTAL_PREMIUM", "TOTAL_PAID_CLAIMS", "LOSS_RATIO_PCT"],
    },
    {
        "id": 12,
        "question": "What is the average days from application to underwriting decision by risk class?",
        "complexity": "Complex",
        "ground_truth_sql": f"SELECT ud.RISK_CLASS, ROUND(AVG(DATEDIFF('day', p.APPLICATION_DATE, ud.DECISION_DATE)), 1) AS AVG_DAYS_TO_DECISION, COUNT(*) AS DECISIONS FROM {DB_SCHEMA}.RAW_UNDERWRITING_DECISIONS ud JOIN {DB_SCHEMA}.RAW_POLICIES p ON ud.POLICY_ID = p.POLICY_ID GROUP BY ud.RISK_CLASS ORDER BY AVG_DAYS_TO_DECISION DESC",
        "expected_row_count": 6,
        "expected_columns": ["RISK_CLASS", "AVG_DAYS_TO_DECISION", "DECISIONS"],
    },
    {
        "id": 13,
        "question": "What is the premium collection rate by payment method?",
        "complexity": "Complex",
        "ground_truth_sql": f"SELECT PAYMENT_METHOD, COUNT(*) AS TOTAL_PAYMENTS, SUM(CASE WHEN PAYMENT_STATUS IN ('Paid', 'Paid Late') THEN 1 ELSE 0 END) AS SUCCESSFUL_PAYMENTS, ROUND(SUM(CASE WHEN PAYMENT_STATUS IN ('Paid', 'Paid Late') THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS COLLECTION_RATE_PCT FROM {DB_SCHEMA}.RAW_PREMIUMS GROUP BY PAYMENT_METHOD ORDER BY COLLECTION_RATE_PCT DESC",
        "expected_row_count": 5,
        "expected_columns": ["PAYMENT_METHOD", "TOTAL_PAYMENTS", "SUCCESSFUL_PAYMENTS", "COLLECTION_RATE_PCT"],
    },
    {
        "id": 14,
        "question": "How do smokers compare to non-smokers in terms of claims frequency?",
        "complexity": "Complex",
        "ground_truth_sql": f"SELECT ph.SMOKER_FLAG, COUNT(DISTINCT ph.POLICYHOLDER_ID) AS POLICYHOLDERS, ROUND(AVG(ph.ANNUAL_INCOME), 2) AS AVG_INCOME, ROUND(AVG(ph.BMI), 1) AS AVG_BMI, COUNT(DISTINCT c.CLAIM_ID) AS TOTAL_CLAIMS, ROUND(COUNT(DISTINCT c.CLAIM_ID) * 1.0 / COUNT(DISTINCT ph.POLICYHOLDER_ID), 3) AS CLAIMS_PER_HOLDER FROM {DB_SCHEMA}.RAW_POLICYHOLDERS ph LEFT JOIN {DB_SCHEMA}.RAW_CLAIMS c ON ph.POLICYHOLDER_ID = c.POLICYHOLDER_ID GROUP BY ph.SMOKER_FLAG",
        "expected_row_count": 2,
        "expected_columns": ["SMOKER_FLAG", "POLICYHOLDERS", "AVG_INCOME", "AVG_BMI", "TOTAL_CLAIMS", "CLAIMS_PER_HOLDER"],
    },
    {
        "id": 15,
        "question": "What is the end-to-end funnel from policies to claims by product line?",
        "complexity": "Complex",
        "ground_truth_sql": f"SELECT p.PRODUCT_LINE, COUNT(DISTINCT p.POLICY_ID) AS TOTAL_POLICIES, COUNT(DISTINCT CASE WHEN ud.DECISION_OUTCOME LIKE 'Approved%' THEN p.POLICY_ID END) AS APPROVED_POLICIES, COUNT(DISTINCT c.CLAIM_ID) AS CLAIMS_FILED, COUNT(DISTINCT CASE WHEN c.CLAIM_STATUS = 'Paid' THEN c.CLAIM_ID END) AS CLAIMS_PAID FROM {DB_SCHEMA}.RAW_POLICIES p LEFT JOIN {DB_SCHEMA}.RAW_UNDERWRITING_DECISIONS ud ON p.POLICY_ID = ud.POLICY_ID LEFT JOIN {DB_SCHEMA}.RAW_CLAIMS c ON p.POLICY_ID = c.POLICY_ID GROUP BY p.PRODUCT_LINE ORDER BY TOTAL_POLICIES DESC",
        "expected_row_count": 5,
        "expected_columns": ["PRODUCT_LINE", "TOTAL_POLICIES", "APPROVED_POLICIES", "CLAIMS_FILED", "CLAIMS_PAID"],
    },
]

# Keywords to match queries
KEYWORD_MAP = {
    "total policyholders": ["how many policyholders", "total policyholders", "policyholder count", "number of policyholders"],
    "smoker count": ["smoker", "smokers", "how many smoke"],
    "policies by status": ["policies by status", "policy status", "active policies", "lapsed", "policy breakdown"],
    "premium by product line": ["premium by product", "total premium", "average premium", "premium breakdown"],
    "underwriting decisions": ["underwriting decision", "decision outcome", "approval rate", "approved", "declined"],
    "risk class": ["risk class", "risk score", "risk distribution", "preferred", "substandard"],
    "payment status": ["payment status", "premium collection", "paid late", "overdue", "missed payment"],
    "claims by status": ["claims by status", "claim status", "claims summary", "open claims", "denied claims"],
    "claims by product": ["claims by product", "claim.*product line", "average claim amount"],
    "fraud claims": ["fraud", "fraudulent", "fraud flag"],
    "top states": ["top states", "state.*sum assured", "states by", "geographic"],
    "loss ratio": ["loss ratio", "paid claims.*premium", "claims ratio"],
    "collection rate": ["collection rate", "payment method", "successful payment"],
    "smoker risk": ["smoker.*risk", "smoker.*claim", "smoker.*non-smoker", "smoking risk"],
    "policy funnel": ["funnel", "end-to-end", "policies.*claims", "approved.*claims"],
}


def match_question(question: str) -> Optional[str]:
    """Match a user question to the best query in the catalog."""
    q_lower = question.lower()
    for key, patterns in KEYWORD_MAP.items():
        for pattern in patterns:
            if re.search(pattern, q_lower):
                return key
    return None


def run_golden_set_evaluation(session) -> pd.DataFrame:
    """Run the full golden set evaluation, returning a results DataFrame."""
    results = []
    for item in GOLDEN_SET:
        row = {
            "ID": item["id"],
            "Question": item["question"],
            "Complexity": item["complexity"],
            "Status": "",
            "Accuracy": "",
            "Details": "",
            "SQL": item["ground_truth_sql"],
        }
        try:
            # Execute ground truth SQL
            df = session.sql(item["ground_truth_sql"]).to_pandas()

            # Check row count
            row_count_match = len(df) == item["expected_row_count"]

            # Check columns present
            actual_cols = [c.upper() for c in df.columns.tolist()]
            expected_cols = [c.upper() for c in item["expected_columns"]]
            cols_match = all(c in actual_cols for c in expected_cols)

            # Check data is non-empty
            has_data = len(df) > 0 and not df.isnull().all().all()

            # Compute accuracy score
            checks_passed = sum([row_count_match, cols_match, has_data])
            accuracy = round(checks_passed / 3 * 100, 0)

            if checks_passed == 3:
                row["Status"] = "Pass"
            else:
                row["Status"] = "Fail"

            row["Accuracy"] = f"{int(accuracy)}%"

            issues = []
            if not row_count_match:
                issues.append(f"Rows: expected {item['expected_row_count']}, got {len(df)}")
            if not cols_match:
                missing = set(expected_cols) - set(actual_cols)
                issues.append(f"Missing cols: {missing}")
            if not has_data:
                issues.append("No data returned")
            row["Details"] = "; ".join(issues) if issues else "All checks passed"

        except Exception as e:
            row["Status"] = "Error"
            row["Accuracy"] = "0%"
            row["Details"] = str(e)[:100]

        results.append(row)

    return pd.DataFrame(results)


# ==============================================================
# KERNEL MODE: validate logic and SQL
# ==============================================================
if not STREAMLIT_AVAILABLE:
    from snowflake.snowpark.context import get_active_session
    session = get_active_session()

    print("=" * 60)
    print("GOLDEN SET EVALUATION (kernel mode)")
    print("=" * 60)

    results_df = run_golden_set_evaluation(session)
    passed = (results_df["Status"] == "Pass").sum()
    total = len(results_df)
    print(f"\nResults: {passed}/{total} passed ({round(passed/total*100, 1)}%)\n")
    print(results_df[["ID", "Question", "Complexity", "Status", "Accuracy"]].to_string(index=False))

    failed = results_df[results_df["Status"] != "Pass"]
    if not failed.empty:
        print("\n--- Failed/Error Queries ---")
        for _, row in failed.iterrows():
            print(f"  Q{row['ID']}: {row['Details']}")

    print("\n" + "=" * 60)
    print("EVALUATION COMPLETE")
    print("=" * 60)

# ==============================================================
# STREAMLIT MODE: full app UI with Golden Set sidebar
# ==============================================================
else:
    st.set_page_config(
        page_title="Underwriting Analyst",
        page_icon=":shield:",
        layout="wide",
    )

    st.title(":shield: Insurance Underwriting Analyst")
    st.caption("Ask questions about policyholders, policies, underwriting decisions, premiums, and claims.")

    # --- Snowflake connection ---
    conn = st.connection("snowflake", ttl=os.getenv("SNOWFLAKE_CONNECTION_TTL"))
    session = conn.session()

    # --- Session state ---
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "golden_set_results" not in st.session_state:
        st.session_state.golden_set_results = None
    if "editing_query" not in st.session_state:
        st.session_state.editing_query = None

    # --- Sidebar ---
    with st.sidebar:
        st.header("Settings")
        show_sql = st.toggle("Show Generated SQL", value=True)
        st.divider()
        if st.button("Clear conversation", use_container_width=True):
            st.session_state.messages = []
            st.rerun()

        # ===== GOLDEN SET EVALUATION SECTION =====
        st.divider()
        st.header(":test_tube: Golden Set Evaluation")
        st.caption("Run 15 ground-truth queries to validate the semantic model.")

        if st.button("Run Golden Set", type="primary", use_container_width=True):
            with st.spinner("Running 15 evaluation queries..."):
                st.session_state.golden_set_results = run_golden_set_evaluation(session)
                st.session_state.editing_query = None

        # Display results if available
        if st.session_state.golden_set_results is not None:
            results_df = st.session_state.golden_set_results
            passed = (results_df["Status"] == "Pass").sum()
            total = len(results_df)
            errored = (results_df["Status"] == "Error").sum()
            failed = (results_df["Status"] == "Fail").sum()

            # Summary metrics
            col1, col2, col3 = st.columns(3)
            col1.metric("Passed", f"{passed}/{total}")
            col2.metric("Failed", str(failed))
            col3.metric("Errors", str(errored))

            overall_accuracy = round(passed / total * 100, 1)
            st.progress(passed / total, text=f"Overall: {overall_accuracy}% accuracy")

            # Results table
            display_df = results_df[["ID", "Question", "Status", "Accuracy"]].copy()
            display_df["Question"] = display_df["Question"].str[:40] + "..."

            def highlight_status(val):
                if val == "Pass":
                    return "background-color: #d4edda"
                elif val == "Fail":
                    return "background-color: #fff3cd"
                elif val == "Error":
                    return "background-color: #f8d7da"
                return ""

            st.dataframe(
                display_df.style.applymap(highlight_status, subset=["Status"]),
                use_container_width=True,
                hide_index=True,
            )

            # Show failed queries with Edit option
            failed_rows = results_df[results_df["Status"] != "Pass"]
            if not failed_rows.empty:
                st.markdown("**Failed Queries:**")
                for _, row in failed_rows.iterrows():
                    with st.expander(f"Q{row['ID']}: {row['Question'][:35]}..."):
                        st.markdown(f"**Status:** {row['Status']}")
                        st.markdown(f"**Details:** {row['Details']}")
                        st.code(row["SQL"], language="sql")
                        if st.button(f"Edit Query Q{row['ID']}", key=f"edit_{row['ID']}"):
                            st.session_state.editing_query = int(row["ID"])
                            st.rerun()

        st.divider()
        st.markdown("**Semantic Model:**")
        st.code(SEMANTIC_VIEW_FQN, language=None)

    # ===== QUERY EDITOR (main area, shown when editing) =====
    if st.session_state.editing_query is not None:
        qid = st.session_state.editing_query
        item = next((g for g in GOLDEN_SET if g["id"] == qid), None)
        if item:
            st.subheader(f":wrench: Edit Query Q{qid}")
            st.markdown(f"**Question:** {item['question']}")
            st.markdown(f"**Complexity:** {item['complexity']}")

            edited_sql = st.text_area(
                "SQL Query",
                value=item["ground_truth_sql"],
                height=200,
                key=f"editor_{qid}",
            )

            col1, col2, col3 = st.columns([1, 1, 2])
            with col1:
                if st.button("Test Query"):
                    try:
                        test_df = session.sql(edited_sql).to_pandas()
                        st.success(f"Query returned {len(test_df)} rows")
                        st.dataframe(test_df, use_container_width=True)
                    except Exception as e:
                        st.error(f"Error: {e}")
            with col2:
                if st.button("Save & Close"):
                    for g in GOLDEN_SET:
                        if g["id"] == qid:
                            g["ground_truth_sql"] = edited_sql
                            break
                    st.session_state.editing_query = None
                    st.success("Query updated! Re-run Golden Set to verify.")
                    st.rerun()
            with col3:
                if st.button("Cancel"):
                    st.session_state.editing_query = None
                    st.rerun()

    # ===== MAIN CHAT INTERFACE =====
    else:
        # --- Display conversation history ---
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                if msg.get("sql") and show_sql:
                    with st.expander("Generated SQL", expanded=False):
                        st.code(msg["sql"], language="sql")
                if msg.get("dataframe") is not None:
                    st.dataframe(msg["dataframe"], use_container_width=True)

        # --- Suggestion buttons for first-time users ---
        SUGGESTIONS = [
            "What is the total premium by product line?",
            "What is the claims summary by status?",
            "How are underwriting decisions distributed across risk classes?",
            "What is the loss ratio by product line?",
        ]

        if not st.session_state.messages:
            st.markdown("**Try one of these questions:**")
            cols = st.columns(len(SUGGESTIONS))
            for i, suggestion in enumerate(SUGGESTIONS):
                short_label = suggestion.split("?")[0].replace("What is the ", "").replace("How are ", "").strip()
                if cols[i].button(short_label, key=f"suggestion_{i}", use_container_width=True):
                    st.session_state.messages.append({"role": "user", "content": suggestion})
                    st.rerun()

        # --- Handle new input ---
        if prompt := st.chat_input("Ask about underwriting data..."):
            st.session_state.messages.append({"role": "user", "content": prompt})

            with st.chat_message("user"):
                st.markdown(prompt)

            with st.chat_message("assistant"):
                matched_key = match_question(prompt)

                if matched_key:
                    entry = QUERY_CATALOG[matched_key]
                    sql = entry["sql"]
                    description = entry["description"]

                    st.markdown(f"**{description}**")

                    if show_sql:
                        with st.expander("Generated SQL", expanded=False):
                            st.code(sql, language="sql")

                    try:
                        df = session.sql(sql).to_pandas()
                        st.dataframe(df, use_container_width=True)
                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": f"**{description}**",
                            "sql": sql,
                            "dataframe": df,
                        })
                    except Exception as e:
                        error_msg = f"Error executing query: {e}"
                        st.error(error_msg)
                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": error_msg,
                            "sql": sql,
                            "dataframe": None,
                        })
                else:
                    help_msg = (
                        "I couldn't match your question to a known query pattern. "
                        "Try asking about:\n"
                        "- **Policyholders** (total count, smokers)\n"
                        "- **Policies** (by status, by product line, premiums)\n"
                        "- **Underwriting** (decisions, risk classes)\n"
                        "- **Premiums** (payment status, collection rate, payment method)\n"
                        "- **Claims** (by status, by product, fraud, loss ratio)\n"
                        "- **Analytics** (smoker risk, policy funnel, top states)"
                    )
                    st.markdown(help_msg)
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": help_msg,
                        "sql": None,
                        "dataframe": None,
                    })
