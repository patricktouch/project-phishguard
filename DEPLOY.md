# Deployment Guide

This guide walks through deploying PhishGuard on a fresh server (tested on Ubuntu, AWS EC2). It assumes you are starting from nothing but a clean machine with Python available.

## 1. Server Prerequisites

- Ubuntu 20.04 or later (or an equivalent Linux distribution)
- Python 3.10 or later
- Git installed
- Outbound internet access, since the server needs to reach the Hugging Face Hub to download model files
- An AWS account with SES and SNS configured if you intend to receive forwarded emails automatically (see section 6)
- No GPU is required. See the note in section 4 about CUDA related packages.

## 2. Clone the Repository

```
git clone https://github.com/patricktouch/project-phishguard.git
cd project-phishguard
```

## 3. Create a Virtual Environment

Keep the project isolated from system Python packages.

```
python3 -m venv phishing-env
source phishing-env/bin/activate
```

The `phishing-env` directory is excluded from version control by `.gitignore`, so this step must be repeated on every new server.

## 4. Install Dependencies

Two dependency files are provided.

- `requirements.txt` lists the direct, loosely versioned dependencies.
- `requirements.lock.txt` is a full pip freeze snapshot with every dependency pinned to an exact version, including transitive dependencies. This is the recommended file for deployment, since it guarantees the same package versions used during development, which matters for a machine learning stack where minor version differences in torch or transformers can change model behavior.

Install from the lock file for a reproducible deployment:

```
pip install --upgrade pip
pip install -r requirements.lock.txt
```

Note on CUDA packages: `requirements.lock.txt` includes several `nvidia-*` packages (cuBLAS, cuDNN, cuFFT, and others). These are pulled in automatically as dependencies of the standard PyTorch wheel on Linux and do not require a GPU to be present. On a CPU only server, these packages install normally and torch automatically runs on CPU. No GPU or CUDA driver setup is needed to deploy this application.

If you prefer a lighter install and are comfortable resolving versions yourself, you can instead use `requirements.txt`, though this is not guaranteed to reproduce the exact environment the application was built and tested against.

## 5. Configure Environment Variables

Copy the template and add your own Hugging Face API key.

```
cp .env.example .env
```

Open `.env` and set:

```
API_KEY=your_huggingface_api_key_here
```

This key is read by `app.py` through `os.getenv("API_KEY")` and is required for model inference calls against the Hugging Face API. Do not commit `.env` to version control.

## 6. Download Model Artifacts

Model weights are not stored in this repository. They are pulled directly from the Hugging Face Hub repository `ptouch/phishing-distilbert-cyber207` at deploy time.

Run:

```
python pull_models.py
```

This script downloads three things into the project directory:

- The full fine tuned DistilBERT model into `./fine_tuned_distilbert`
- `log_reg_model.joblib`, the logistic regression baseline model
- `tfidf_vectorizer.joblib`, the vectorizer used by the logistic regression model

This step requires outbound internet access and may take a few minutes depending on model size and connection speed.

Once downloaded, verify the models loaded correctly:

```
python verify_models.py
```

Resolve any errors here before proceeding. If verification fails, confirm the server has internet access and that the Hugging Face repository is reachable.

## 7. Database Setup

No manual database setup step is required. `database.py` uses SQLAlchemy against a local SQLite database and creates the schema automatically on import:

```
DATABASE_URL = "sqlite:///./phishing_log.db"
```

The `email_log` table (sender, subject, body preview, model verdicts, confidence, timestamp) is created the first time `app.py` starts if `phishing_log.db` does not already exist. No migration step is needed for a first deployment. `phishing_log.db` is excluded from version control, so each server maintains its own local log.

## 8. Run the Application

The application is a FastAPI app served through Uvicorn. For a quick manual start:

```
uvicorn app:app --host 0.0.0.0 --port 8000
```

The codebase also supports running it directly:

```
python app.py
```

This calls `uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)` internally. The `reload=True` flag is convenient for development but should not be used in production, since it adds overhead and is intended for local iteration. For production, use the `uvicorn app:app --host 0.0.0.0 --port 8000` command directly without reload, and consider running it under a process manager (see section 10).

Once running, the dashboard is served from the `static/` directory, and the application listens for inbound requests on port 8000.

## 9. AWS SES and SNS Configuration (Optional, for Automated Email Ingestion)

If you want the deployment to automatically process forwarded emails rather than only serve the dashboard, configure the following in your AWS account:

1. Verify the domain or email address that will receive forwarded emails in AWS SES.
2. Create an SNS topic to receive SES notifications for incoming mail.
3. Subscribe your server's public endpoint (for example, `http://your-server-ip:8000/inbound-email`) to that SNS topic.
4. On first request, SNS sends a subscription confirmation message. The application handles this automatically. No manual confirmation click is required as long as the server is running and reachable when the subscription is created.
5. Ensure your server's security group or firewall allows inbound traffic on port 8000 (or whichever port you expose) from AWS SNS.

AWS credentials and topic configuration are specific to your AWS account and are not included in this repository. Manage them through your AWS account directly rather than through environment variables in this project, unless your deployment requires an AWS SDK client, in which case add the relevant keys to `.env` and reference them explicitly in `app.py`.

## 10. Running in the Background (Production)

For a deployment that stays running after you disconnect from the server, use a process manager instead of running Uvicorn directly in a terminal session. Two common options:

**Using systemd:**

Create a service file at `/etc/systemd/system/phishguard.service` with a `ExecStart` line pointing to your virtual environment's Uvicorn binary and the project directory, then enable it with `systemctl enable phishguard` and start it with `systemctl start phishguard`.

**Using tmux or screen:**

For a simpler setup without systemd, run the app inside a `tmux` session so it keeps running after you disconnect:

```
tmux new -s phishguard
uvicorn app:app --host 0.0.0.0 --port 8000
```

Detach with `Ctrl+B` then `D`, and reattach later with `tmux attach -t phishguard`.

## 11. Verifying the Deployment

Once the server is running, confirm the setup end to end:

1. Visit `http://your-server-ip:8000` and confirm the dashboard loads.
2. Send a test email or manually POST a sample payload to the inbound email endpoint and confirm a result appears in the dashboard.
3. Check `phishing_log.db` to confirm new rows are being written after each analysis.

## Summary Checklist

- [ ] Clone repository
- [ ] Create and activate virtual environment
- [ ] Install dependencies from requirements.lock.txt
- [ ] Copy .env.example to .env and set API_KEY
- [ ] Run pull_models.py
- [ ] Run verify_models.py and confirm success
- [ ] Start the application with uvicorn
- [ ] Configure AWS SES and SNS if automated email ingestion is needed
- [ ] Set up a process manager for production use
- [ ] Confirm the dashboard loads and results are logged to the database
