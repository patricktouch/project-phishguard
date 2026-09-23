# verify_models.py — confirm everything loads correctly
from transformers import DistilBertTokenizerFast, DistilBertForSequenceClassification
import joblib, torch

tokenizer = DistilBertTokenizerFast.from_pretrained('./fine_tuned_distilbert')
model     = DistilBertForSequenceClassification.from_pretrained('./fine_tuned_distilbert')
lr_model  = joblib.load('log_reg_model.joblib')
tfidf     = joblib.load('tfidf_vectorizer.joblib')

# Quick smoke test
test_email = "Congratulations! Click here to claim your free prize now!"
inputs     = tokenizer(test_email, return_tensors='pt',
                       truncation=True, max_length=256)
with torch.no_grad():
    logits = model(**inputs).logits
prob = torch.softmax(logits, dim=-1)[0][1].item()
print(f"✅ Models loaded successfully")
print(f"🎣 Phishing probability: {prob*100:.1f}%")
