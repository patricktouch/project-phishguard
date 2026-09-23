"""
FastAPI backend for Phishing Email Detection
Models: DistilBERT (transformer) + TF-IDF / Logistic Regression (sklearn baseline)
Repo:   https://huggingface.co/ptouch/phishing-distilbert-cyber207
"""

import os
import json
import torch
import joblib
import httpx
from pathlib import Path
from contextlib import asynccontextmanager
from datetime import datetime
from email import policy
from email.parser import BytesParser

from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from transformers import DistilBertTokenizer, DistilBertForSequenceClassification
from huggingface_hub import hf_hub_download

from database import SessionLocal, EmailLog
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("API_KEY")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
HF_REPO   = "ptouch/phishing-distilbert-cyber207"
MODEL_DIR = Path("models")
LABELS    = {0: "Legitimate", 1: "Phishing"}

# ---------------------------------------------------------------------------
# Global model holders (populated on startup)
# ---------------------------------------------------------------------------
bert_model       = None
bert_tokenizer   = None
tfidf_vectorizer = None
lr_model         = None
device           = None


def download_models():
    MODEL_DIR.mkdir(exist_ok=True)
    files = [
        "config.json", "model.safetensors",
        "tokenizer.json", "tokenizer_config.json",
        "tfidf_vectorizer.joblib", "log_reg_model.joblib",
    ]
    for fname in files:
        hf_hub_download(
            repo_id=HF_REPO, filename=fname,
            local_dir=str(MODEL_DIR),
        )
    print(f"[startup] All model files cached in {MODEL_DIR.resolve()}")


def load_models():
    global bert_model, bert_tokenizer, tfidf_vectorizer, lr_model, device

    device         = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    bert_tokenizer = DistilBertTokenizer.from_pretrained(str(MODEL_DIR))
    bert_model     = DistilBertForSequenceClassification.from_pretrained(str(MODEL_DIR))
    bert_model.to(device)
    bert_model.eval()

    tfidf_vectorizer = joblib.load(MODEL_DIR / "tfidf_vectorizer.joblib")
    lr_model         = joblib.load(MODEL_DIR / "log_reg_model.joblib")
    print(f"[startup] All models loaded on {device}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    download_models()
    load_models()
    yield
    print("[shutdown] Cleaning up")


app = FastAPI(
    title="Phishing Email Detector - Cyber 207",
    description="Classify emails as phishing or legitimate using DistilBERT and TF-IDF baseline.",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------
class EmailRequest(BaseModel):
    email_text: str
    sender:     str = "manual"
    subject:    str = ""

class PredictionResult(BaseModel):
    label:      str
    confidence: float

class EmailResponse(BaseModel):
    distilbert:          PredictionResult
    logistic_regression: PredictionResult


# ---------------------------------------------------------------------------
# Prediction Helpers
# ---------------------------------------------------------------------------
def predict_distilbert(text: str) -> PredictionResult:
    inputs = bert_tokenizer(
        text, return_tensors="pt",
        truncation=True, max_length=512, padding="max_length",
    ).to(device)
    with torch.no_grad():
        logits = bert_model(**inputs).logits
    probs    = torch.softmax(logits, dim=-1).squeeze()
    pred_idx = int(probs.argmax())
    return PredictionResult(label=LABELS[pred_idx],
                            confidence=round(float(probs[pred_idx]), 4))


def predict_lr(text: str) -> PredictionResult:
    X        = tfidf_vectorizer.transform([text])
    pred_idx = int(lr_model.predict(X)[0])
    prob     = float(lr_model.predict_proba(X)[0][pred_idx])
    return PredictionResult(label=LABELS[pred_idx], confidence=round(prob, 4))


def confidence_label(score: float) -> str:
    if score > 0.85 or score < 0.15: return "High"
    if score > 0.65 or score < 0.35: return "Medium"
    return "Low"


def save_to_db(sender: str, subject: str, body: str,
               bert_result: PredictionResult,
               lr_result: PredictionResult,
               source: str = "manual"):
    db  = SessionLocal()
    log = EmailLog(
        received_at       = datetime.utcnow(),
        source            = source,
        sender            = sender,
        subject           = subject,
        body_preview      = body[:300],
        bert_phishing_pct = round(
            bert_result.confidence * 100 if bert_result.label == "Phishing"
            else (1 - bert_result.confidence) * 100, 2),
        lr_phishing_pct   = round(
            lr_result.confidence * 100 if lr_result.label == "Phishing"
            else (1 - lr_result.confidence) * 100, 2),
        verdict           = bert_result.label.upper(),
        confidence        = confidence_label(bert_result.confidence),
    )
    db.add(log)
    db.commit()
    db.close()



# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
def verify_api_key(x_api_key: str = Header(...)):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
# ---------------------------------------------------------------------------
# Existing Endpoints
# ---------------------------------------------------------------------------
@app.get("/health")
async def health_check():
    return {
        "status":       "ok",
        "device":       str(device),
        "models_loaded": all([bert_model, bert_tokenizer,
                               tfidf_vectorizer, lr_model]),
    }


@app.post("/predict", response_model=EmailResponse)
async def predict(req: EmailRequest):
    text = req.email_text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="email_text cannot be empty.")

    bert_result = predict_distilbert(text)
    lr_result   = predict_lr(text)

    # Log every manual prediction to DB
    save_to_db(
        sender      = req.sender,
        subject     = req.subject,
        body        = text,
        bert_result = bert_result,
        lr_result   = lr_result,
        source      = "manual"
    )

    return EmailResponse(distilbert=bert_result, logistic_regression=lr_result)


# ---------------------------------------------------------------------------
# NEW — Phase 6B Endpoints
# ---------------------------------------------------------------------------
@app.post("/inbound-email")
async def inbound_email(request: Request):
    """Receives forwarded emails via AWS SNS → SES."""
    body = await request.json()

    # Step 1 — SNS sends a confirmation ping first; auto-confirm it
    if body.get("Type") == "SubscriptionConfirmation":
        async with httpx.AsyncClient() as client:
            await client.get(body["SubscribeURL"])
        return {"status": "subscription confirmed"}

    # Step 2 — Parse the actual SES email notification
    try:
        message = json.loads(body.get("Message", "{}"))
        mail    = message.get("mail", {})
        headers = {h["name"].lower(): h["value"]
                   for h in mail.get("headers", [])}

        sender  = mail.get("source", "unknown")
        subject = headers.get("subject", "No Subject")

        # Get email body from content field
        content = message.get("content", "")
        if content:
            parsed  = BytesParser(policy=policy.default).parsebytes(
                          content.encode())
            body_part = parsed.get_body(preferencelist=("plain", "html"))
            email_body = body_part.get_content() if body_part else content
        else:
            email_body = ""

    except Exception as e:
        raise HTTPException(status_code=400,
                            detail=f"Failed to parse email: {str(e)}")

    # Step 3 — Run both models
    full_text   = f"{subject} {email_body}".strip()
    bert_result = predict_distilbert(full_text)
    lr_result   = predict_lr(full_text)

    # Step 4 — Save to DB
    save_to_db(
        sender      = sender,
        subject     = subject,
        body        = email_body,
        bert_result = bert_result,
        lr_result   = lr_result,
        source      = "forwarded"
    )

    return {
        "status":  "processed",
        "verdict": bert_result.label,
        "sender":  sender,
        "subject": subject,
    }


@app.get("/history")
async def get_history(limit: int = 100, source: str = None, x_api_key: str = Header(...)):
    verify_api_key(x_api_key)
    """Return analyzed email log, newest first."""
    db    = SessionLocal()
    query = db.query(EmailLog).order_by(EmailLog.received_at.desc())
    if source:                          # filter by "manual" or "forwarded"
        query = query.filter(EmailLog.source == source)
    logs  = query.limit(limit).all()
    db.close()
    return [
        {
            "id":                l.id,
            "received_at":       l.received_at.isoformat(),
            "source":            l.source,
            "sender":            l.sender,
            "subject":           l.subject,
            "body_preview":      l.body_preview,
            "bert_phishing_pct": l.bert_phishing_pct,
            "lr_phishing_pct":   l.lr_phishing_pct,
            "verdict":           l.verdict,
            "confidence":        l.confidence,
        }
        for l in logs
    ]


@app.get("/history/stats")
async def get_stats(x_api_key: str = Header(...)):
    verify_api_key(x_api_key)
    """Summary counts for the dashboard header."""
    db         = SessionLocal()
    total      = db.query(EmailLog).count()
    phishing   = db.query(EmailLog).filter(
                     EmailLog.verdict == "PHISHING").count()
    legitimate = db.query(EmailLog).filter(
                     EmailLog.verdict == "LEGITIMATE").count()
    forwarded  = db.query(EmailLog).filter(
                     EmailLog.source == "forwarded").count()
    db.close()
    return {
        "total":      total,
        "phishing":   phishing,
        "legitimate": legitimate,
        "forwarded":  forwarded,
    }

@app.post("/upload-email")
async def upload_email(file: UploadFile = File(...)):
    """Accept a .eml file, analyze it, save to DB."""

    # Read and parse the .eml file
    raw     = await file.read()
    msg     = BytesParser(policy=policy.default).parsebytes(raw)

    sender  = str(msg.get("from",    "unknown"))
    subject = str(msg.get("subject", "No Subject"))

    # Extract plain text body, fall back to HTML
    body_part = msg.get_body(preferencelist=("plain", "html"))
    if body_part:
        email_body = body_part.get_content()
    else:
        email_body = raw.decode("utf-8", errors="replace")

    if not email_body.strip():
        raise HTTPException(status_code=400,
                            detail="Could not extract text from email file.")

    # Run both models
    full_text   = f"{subject} {email_body}".strip()
    bert_result = predict_distilbert(full_text)
    lr_result   = predict_lr(full_text)

    # Save to DB with source="forwarded"
    save_to_db(
        sender      = sender,
        subject     = subject,
        body        = email_body,
        bert_result = bert_result,
        lr_result   = lr_result,
        source      = "forwarded"
    )

    return {
        "status":            "processed",
        "sender":            sender,
        "subject":           subject,
        "verdict":           bert_result.label,
        "bert_phishing_pct": round(
            bert_result.confidence * 100 if bert_result.label == "Phishing"
            else (1 - bert_result.confidence) * 100, 2),
        "lr_phishing_pct":   round(
            lr_result.confidence * 100 if lr_result.label == "Phishing"
            else (1 - lr_result.confidence) * 100, 2),
        "confidence":        confidence_label(bert_result.confidence),
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
