"""
Trains the Dual-Branch Soft-Voting Document Classifier:
- Branch 1: TF-IDF Vectorizer + Logistic Regression
- Branch 2: all-MiniLM-L6-v2 SentenceTransformer + Dense Logistic Regression
- Evaluates on the held-out test set and saves real metrics to docs/RESULTS.md
"""

import os
import json
import joblib
import numpy as np
from datetime import datetime
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import classification_report, accuracy_score, confusion_matrix
from sentence_transformers import SentenceTransformer

def train_and_evaluate():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    corpus_dir = os.path.join(script_dir, "corpus")
    repo_root = os.path.dirname(script_dir)
    model_cache_dir = os.path.join(repo_root, "ml-service", "model_cache")
    os.makedirs(model_cache_dir, exist_ok=True)
    
    # 1. Load data
    with open(os.path.join(corpus_dir, "train.json"), "r", encoding="utf-8") as f:
        train_data = json.load(f)
    with open(os.path.join(corpus_dir, "test.json"), "r", encoding="utf-8") as f:
        test_data = json.load(f)
        
    X_train_text = [item["text"] for item in train_data]
    y_train_raw = [item["label"] for item in train_data]
    X_test_text = [item["text"] for item in test_data]
    y_test_raw = [item["label"] for item in test_data]
    
    # Label Encoding
    le = LabelEncoder()
    y_train = le.fit_transform(y_train_raw)
    y_test = le.transform(y_test_raw)
    classes = list(le.classes_)
    
    print(f"Training on {len(X_train_text)} samples across classes: {classes}")
    
    # 2. Branch 1: TF-IDF + Logistic Regression
    print("Training Branch 1: TF-IDF N-Gram Vectorizer + Logistic Regression...")
    tfidf = TfidfVectorizer(
        ngram_range=(1, 2),
        max_features=4000,
        sublinear_tf=True,
        strip_accents='unicode'
    )
    X_train_tfidf = tfidf.fit_transform(X_train_text)
    X_test_tfidf = tfidf.transform(X_test_text)
    
    clf_tfidf = LogisticRegression(C=1.0, max_iter=1000, random_state=42)
    clf_tfidf.fit(X_train_tfidf, y_train)
    
    # 3. Branch 2: Dense Embeddings via all-MiniLM-L6-v2 + Logistic Regression
    print("Loading SentenceTransformer ('all-MiniLM-L6-v2') for Branch 2...")
    embedder = SentenceTransformer('all-MiniLM-L6-v2')
    
    print("Computing dense embeddings for training set...")
    X_train_dense = embedder.encode(X_train_text, show_progress_bar=True, batch_size=32)
    print("Computing dense embeddings for held-out test set...")
    X_test_dense = embedder.encode(X_test_text, show_progress_bar=True, batch_size=32)
    
    clf_dense = LogisticRegression(C=2.0, max_iter=1000, random_state=42)
    clf_dense.fit(X_train_dense, y_train)
    
    # 4. Soft-Voting Ensemble Prediction on Held-Out Test Set
    prob_tfidf = clf_tfidf.predict_proba(X_test_tfidf)
    prob_dense = clf_dense.predict_proba(X_test_dense)
    
    weight_tfidf = 0.4
    weight_dense = 0.6
    prob_ensemble = (weight_tfidf * prob_tfidf) + (weight_dense * prob_dense)
    
    y_pred = np.argmax(prob_ensemble, axis=1)
    confidences = np.max(prob_ensemble, axis=1)
    
    # 5. Calculate Metrics
    overall_acc = accuracy_score(y_test, y_pred)
    report_dict = classification_report(y_test, y_pred, target_names=classes, output_dict=True)
    report_text = classification_report(y_test, y_pred, target_names=classes)
    cm = confusion_matrix(y_test, y_pred)
    
    print("\n--- HELD-OUT TEST EVALUATION ---")
    print(f"Overall Accuracy: {overall_acc * 100:.2f}%")
    print(report_text)
    print("Confusion Matrix:\n", cm)
    
    # 6. Save Model Artifacts
    print(f"\nSaving cached models to {model_cache_dir}...")
    joblib.dump(tfidf, os.path.join(model_cache_dir, "tfidf_vectorizer.joblib"))
    joblib.dump(clf_tfidf, os.path.join(model_cache_dir, "tfidf_classifier.joblib"))
    joblib.dump(clf_dense, os.path.join(model_cache_dir, "dense_classifier.joblib"))
    joblib.dump(le, os.path.join(model_cache_dir, "label_encoder.joblib"))
    
    metadata = {
        "model_name": "TFIDF_MiniLM_Ensemble",
        "classes": classes,
        "weights": {"tfidf": weight_tfidf, "dense": weight_dense},
        "embedding_model": "all-MiniLM-L6-v2",
        "train_samples": len(X_train_text),
        "test_samples": len(X_test_text),
        "overall_accuracy": float(overall_acc),
        "macro_f1": float(report_dict["macro avg"]["f1-score"]),
        "weighted_f1": float(report_dict["weighted avg"]["f1-score"]),
        "trained_at": datetime.now().isoformat()
    }
    with open(os.path.join(model_cache_dir, "metadata.json"), "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
        
    # 7. Write Real Measured Numbers into docs/RESULTS.md
    results_path = os.path.join(repo_root, "docs", "RESULTS.md")
    cm_markdown = "| Actual \\ Predicted | " + " | ".join(classes) + " |\n"
    cm_markdown += "|---|" + "---|"*len(classes) + "\n"
    for idx, row in enumerate(cm):
        cm_markdown += f"| **{classes[idx]}** | " + " | ".join(str(c) for c in row) + " |\n"
        
    class_perf_md = "| Class | Precision | Recall | F1-Score | Support |\n|---|---|---|---|---|\n"
    for c in classes:
        m = report_dict[c]
        class_perf_md += f"| **{c}** | {m['precision']*100:.2f}% | {m['recall']*100:.2f}% | {m['f1-score']*100:.2f}% | {m['support']} |\n"
        
    results_content = f"""# Empirical Model Evaluation & Test Results

**Evaluation Date:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}  
**Model Architecture:** Soft-Voting Ensemble ($0.4 \\times$ TF-IDF + $0.6 \\times$ `all-MiniLM-L6-v2` Dense Embeddings)  
**Dataset:** Synthetic Indian KYC Corpus ({len(X_train_text)} Train / {len(X_test_text)} Held-Out Test)  

---

## 1. Overall Performance Metrics

| Metric | Measured Value |
|---|---|
| **Overall Accuracy** | **{overall_acc * 100:.2f}%** |
| **Macro Average Precision** | **{report_dict['macro avg']['precision'] * 100:.2f}%** |
| **Macro Average Recall** | **{report_dict['macro avg']['recall'] * 100:.2f}%** |
| **Macro Average F1-Score** | **{report_dict['macro avg']['f1-score'] * 100:.2f}%** |
| **Weighted Average F1-Score** | **{report_dict['weighted avg']['f1-score'] * 100:.2f}%** |

---

## 2. Per-Class Performance Breakdown

{class_perf_md}

---

## 3. Confusion Matrix

{cm_markdown}

---

## 4. Confidence Threshold Verification

- Average confidence across correct predictions: **{float(np.mean(confidences))*100:.2f}%**
- Any prediction with confidence $< 0.60$ is automatically flagged as `NEEDS_HUMAN_CHECK` in the review pipeline.
- All model artifacts (`tfidf_vectorizer.joblib`, `tfidf_classifier.joblib`, `dense_classifier.joblib`, `label_encoder.joblib`) are cached locally in `ml-service/model_cache/`.
"""
    with open(results_path, "w", encoding="utf-8") as f:
        f.write(results_content)
        
    print(f"Results written to {results_path}")

if __name__ == "__main__":
    train_and_evaluate()
