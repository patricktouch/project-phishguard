# pull_models.py — run this ONCE on EC2 to download everything
from huggingface_hub import hf_hub_download, snapshot_download
import os

HF_REPO = "ptouch/phishing-distilbert-cyber207"
os.makedirs('./fine_tuned_distilbert', exist_ok=True)

# Download DistilBERT model (all files at once)
snapshot_download(repo_id=HF_REPO,
                  local_dir='./fine_tuned_distilbert')

# Download LR + TF-IDF with YOUR correct filenames
hf_hub_download(repo_id=HF_REPO, filename='log_reg_model.joblib',
                local_dir='.')
hf_hub_download(repo_id=HF_REPO, filename='tfidf_vectorizer.joblib',
                local_dir='.')

print("✅ All models downloaded to EC2")
