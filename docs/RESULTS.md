# Empirical Model Evaluation & Test Results

**Evaluation Date:** 2026-10-30 15:25:27  
**Model Architecture:** Soft-Voting Ensemble ($0.4 \times$ TF-IDF + $0.6 \times$ `all-MiniLM-L6-v2` Dense Embeddings)  
**Dataset:** Synthetic Indian KYC Corpus (500 Train / 125 Held-Out Test)  

---

## 1. Overall Performance Metrics

| Metric | Measured Value |
|---|---|
| **Overall Accuracy** | **100.00%** |
| **Macro Average Precision** | **100.00%** |
| **Macro Average Recall** | **100.00%** |
| **Macro Average F1-Score** | **100.00%** |
| **Weighted Average F1-Score** | **100.00%** |

---

## 2. Per-Class Performance Breakdown

| Class | Precision | Recall | F1-Score | Support |
|---|---|---|---|---|
| **AADHAAR** | 100.00% | 100.00% | 100.00% | 25.0 |
| **BANK_STATEMENT** | 100.00% | 100.00% | 100.00% | 25.0 |
| **OTHER** | 100.00% | 100.00% | 100.00% | 25.0 |
| **PAN** | 100.00% | 100.00% | 100.00% | 25.0 |
| **SALARY_SLIP** | 100.00% | 100.00% | 100.00% | 25.0 |


---

## 3. Confusion Matrix

| Actual \ Predicted | AADHAAR | BANK_STATEMENT | OTHER | PAN | SALARY_SLIP |
|---|---|---|---|---|---|
| **AADHAAR** | 25 | 0 | 0 | 0 | 0 |
| **BANK_STATEMENT** | 0 | 25 | 0 | 0 | 0 |
| **OTHER** | 0 | 0 | 25 | 0 | 0 |
| **PAN** | 0 | 0 | 0 | 25 | 0 |
| **SALARY_SLIP** | 0 | 0 | 0 | 0 | 25 |


---

## 4. Confidence Threshold Verification

- Average confidence across correct predictions: **92.53%**
- Any prediction with confidence $< 0.60$ is automatically flagged as `NEEDS_HUMAN_CHECK` in the review pipeline.
- All model artifacts (`tfidf_vectorizer.joblib`, `tfidf_classifier.joblib`, `dense_classifier.joblib`, `label_encoder.joblib`) are cached locally in `ml-service/model_cache/`.
