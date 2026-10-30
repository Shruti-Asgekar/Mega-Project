"""
Module 2: Document Classifier.
Ensemble classifier utilizing TF-IDF n-grams + all-MiniLM-L6-v2 dense embeddings.
Models are cached in memory on startup.
"""

import os
import json
import joblib
import numpy as np
from sentence_transformers import SentenceTransformer

class DocumentClassifier:
    _instance = None
    
    def __init__(self, cache_dir: str = None):
        if cache_dir is None:
            cache_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "model_cache")
            
        self.cache_dir = cache_dir
        self.tfidf_vectorizer = None
        self.tfidf_classifier = None
        self.dense_classifier = None
        self.label_encoder = None
        self.dense_embedder = None
        self.metadata = None
        self.classes = []
        self.loaded = False
        
        self.load_models()
        
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
        
    def load_models(self):
        """Loads and caches models in memory."""
        if self.loaded:
            return
            
        tfidf_vec_path = os.path.join(self.cache_dir, "tfidf_vectorizer.joblib")
        tfidf_clf_path = os.path.join(self.cache_dir, "tfidf_classifier.joblib")
        dense_clf_path = os.path.join(self.cache_dir, "dense_classifier.joblib")
        le_path = os.path.join(self.cache_dir, "label_encoder.joblib")
        meta_path = os.path.join(self.cache_dir, "metadata.json")
        
        if not all(os.path.exists(p) for p in [tfidf_vec_path, tfidf_clf_path, dense_clf_path, le_path]):
            raise FileNotFoundError(f"Model artifacts not found in {self.cache_dir}. Run train_classifier.py first.")
            
        self.tfidf_vectorizer = joblib.load(tfidf_vec_path)
        self.tfidf_classifier = joblib.load(tfidf_clf_path)
        self.dense_classifier = joblib.load(dense_clf_path)
        self.label_encoder = joblib.load(le_path)
        self.classes = list(self.label_encoder.classes_)
        
        if os.path.exists(meta_path):
            with open(meta_path, "r", encoding="utf-8") as f:
                self.metadata = json.load(f)
                
        # Initialize dense embedder with offline fallback
        try:
            self.dense_embedder = SentenceTransformer('all-MiniLM-L6-v2', local_files_only=True)
        except Exception:
            self.dense_embedder = None

        self.loaded = True
        print(f"Classifier loaded successfully for classes: {self.classes}")
        
    def predict(self, text: str) -> dict:
        """
        Runs soft-voting ensemble prediction.
        Returns:
            document_type: str
            confidence: float (0.0 to 1.0)
            probabilities: dict of class -> float
            needs_human_check: bool (True if confidence < 0.60)
        """
        if not text or len(text.strip()) < 10:
            return {
                "document_type": "OTHER",
                "confidence": 0.50,
                "probabilities": {c: 0.20 for c in self.classes},
                "needs_human_check": True,
                "model_version": "ensemble-v1.0"
            }
            
        # 1. TF-IDF branch
        X_tfidf = self.tfidf_vectorizer.transform([text])
        prob_tfidf = self.tfidf_classifier.predict_proba(X_tfidf)[0]
        
        # 2. Dense branch if available
        if self.dense_embedder is not None:
            dense_emb = self.dense_embedder.encode([text], show_progress_bar=False)
            prob_dense = self.dense_classifier.predict_proba(dense_emb)[0]
            # Soft-voting combination (0.4 TFIDF + 0.6 Dense)
            prob_ensemble = (0.4 * prob_tfidf) + (0.6 * prob_dense)
        else:
            prob_ensemble = prob_tfidf
        
        pred_idx = int(np.argmax(prob_ensemble))
        best_class = self.classes[pred_idx]
        confidence = float(prob_ensemble[pred_idx])
        
        prob_dict = {
            cls_name: round(float(prob_ensemble[i]), 4)
            for i, cls_name in enumerate(self.classes)
        }
        
        return {
            "document_type": best_class,
            "confidence": round(confidence, 4),
            "probabilities": prob_dict,
            "needs_human_check": bool(confidence < 0.60),
            "model_version": "ensemble-v1.0"
        }
