# PhishGuard

PhishGuard is a machine learning powered phishing email detection pipeline. Emails forwarded to a monitored address are analyzed automatically using a fine tuned DistilBERT model and a logistic regression model, with results served through a FastAPI backend and displayed on a web dashboard.

## Architecture

The system is organized into five layers.

1. End User / Email: A user forwards a suspicious email to a monitored address (for example, analyze@phishguard.networkcloudify.com).
2. AWS Layer: AWS SES receives the forwarded email. AWS SNS triggers a notification that starts processing.
3. Model Layer: The email content is passed to a fine tuned DistilBERT model (trained in Google Colab) through the Hugging Face API, alongside a logistic regression baseline model.
4. FastAPI Backend: A FastAPI service running on AWS EC2 receives the SNS notification, parses the email, runs both models, and stores the result.
5. Frontend / Output: The verdict (Legit or Phishing) is displayed on a results dashboard so the end user can see the outcome.

Data flows from the inbox through AWS, into the model layer, through the backend, and out to the dashboard. Clean results and phishing alerts are routed back to the frontend for display.

## Project Structure

```
project-phishguard/
├── app.py                  FastAPI application and API endpoints
├── database.py              Database connection and query logic
├── pull_models.py            Downloads and stages ML model artifacts
├── verify_models.py          Verifies that model artifacts loaded correctly
├── requirements.txt          Python dependencies
├── .env.example              Template for required environment variables
├── static/
│   ├── index.html            Landing page
│   └── phishguard-dashboard.html   Results dashboard
└── .gitignore
```

Model weights, the local database file, and virtual environments are intentionally excluded from this repository. See the Configuration and Models sections below for how to regenerate them.

## Technology Stack

- Backend: Python, FastAPI
- Machine Learning: DistilBERT (fine tuned), logistic regression, Hugging Face API
- Email Ingestion: AWS SES, AWS SNS
- Hosting: AWS EC2
- Frontend: HTML, CSS

## Getting Started

### Prerequisites

- Python 3.10 or later
- An AWS account with SES and SNS configured for the domain receiving forwarded emails
- A Hugging Face account and API token for model inference

### Installation

1. Clone the repository.

```
git clone https://github.com/patricktouch/project-phishguard.git
cd project-phishguard
```

2. Create and activate a virtual environment.

```
python3 -m venv venv
source venv/bin/activate
```

3. Install dependencies.

```
pip install -r requirements.txt
```

4. Copy the environment template and fill in your own values.

```
cp .env.example .env
```

## Configuration

This project reads configuration from a `.env` file, which is never committed to version control. Use `.env.example` as a starting point and provide your own credentials.

| Variable | Description | Example |
|---|---|---|
| API_KEY | Hugging Face API token used for model inference calls | hf_xxxxxxxxxxxxxxxxxxxx |

Additional variables for AWS access (SES and SNS) and database configuration should be added to `.env` as the deployment requires. Do not commit real credentials to this repository at any point.

## Models

The fine tuned DistilBERT model and supporting artifacts (`fine_tuned_distilbert/`, `*.joblib` files) are not stored in this repository due to size and because they are treated as generated build artifacts rather than source code.

To retrieve them, run:

```
python pull_models.py
```

Then confirm they loaded correctly:

```
python verify_models.py
```

## Running the Application

Start the FastAPI server with Uvicorn:

```
uvicorn app:app --host 0.0.0.0 --port 8000
```

Once running, the dashboard is available through the configured static route, and the inbound email endpoint is ready to receive AWS SNS notifications.

## How It Works

1. A user forwards a suspicious email to the monitored inbox.
2. AWS SES receives the email and AWS SNS sends a notification to the FastAPI backend.
3. The backend confirms the SNS subscription on first setup, then parses incoming email notifications on each trigger.
4. The email subject and body are extracted and passed to both the DistilBERT model and the logistic regression model.
5. Results are saved to the database and returned as a verdict of Legit or Phishing.
6. The dashboard displays the verdict for the end user.

## Security Notes

This repository does not contain API keys, AWS credentials, trained model weights, or the runtime database. Anyone deploying this project must supply their own credentials through a local `.env` file and regenerate model artifacts using `pull_models.py`. Review `.gitignore` before committing any new files to confirm sensitive material stays out of version control.

## Contributors

This project was built as a team effort.

- Patrick Touch
- Uchenna Edeh
- Mario Rincon

## License

No license has been selected yet for this project. All rights reserved by the contributors until a license is added.
