# MetaFemina

**Meta-Analysis Tool for Women's Cancers & Nutrition**

MetaFemina conducts nutritional exposure meta-analyses across breast, ovarian, and uterine cancer. Cached results and generated plots keep their disease-specific filenames, so each selected disease scope resolves to the matching cached outcome.

## Key Features

- **Automated Evidence Synthesis**: Automatically searches PubMed for relevant studies based on a specific nutritional exposure (e.g., Coffee, Vitamin D, Fat intake).
- **Scope**: Select **Breast Cancer**, **Ovarian Cancer**, or **Uterine Cancer** from one website.
- **Pooled Caches**: Preserves existing cached analyses, plots, synonym data, and verification records from the three source projects.
- **Data Extraction**:  Parses abstracts to extract sample sizes, effect sizes, confidence intervals, and study metadata (Year, Journal, Design).
- **Statistical Analysis**: Performs a **Random-Effects Meta-Analysis** to calculate a pooled effect size.
- **Visualization**:
  - **Forest Plots**: Visual representation of individual study results and the overall pooled effect.
  - **Funnel Plots**: Assessment of potential publication bias.
- **Interactive Web Interface**: User-friendly Flask application for easy searching and filtering.

## Installation

1.  **Clone the repository** (or download the source code).
2.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```
3.  **Set up Environment Variables**:
    - Create a file named `mykey.env` in the root directory.
    - Add your PubMed API email (optional but recommended for higher rate limits):
      ```
      PUBMED_EMAIL=your_email@example.com
      ```
    - Configure an SMTP account so matching crowdsourced submissions and repeated
      exclusion flags can email the developer review list without changing results:
      ```
      SMTP_HOST=smtp.gmail.com
      SMTP_PORT=587
      SMTP_USE_TLS=true
      SMTP_USE_SSL=false
      SMTP_USERNAME=your_sender@gmail.com
      SMTP_PASSWORD=your_app_password
      SMTP_FROM=your_sender@gmail.com
      ```
      For Gmail, use an app password rather than the account's normal password.
    - Keep review identities and flags stable across restarts:
      ```
      REPORTER_ID_SECRET=a-long-random-secret-kept-stable-across-deploys
      VERIFICATIONS_FILE=/path/on/persistent-storage/verifications.json
      ```
      The anonymous identity distinguishes signed browser installations, not
      authenticated people. Clearing cookies or changing devices creates a new
      reviewer identity. Use authenticated user IDs if person-level identity is
      required.

### Render review storage

`render.yaml` mounts a persistent disk at `/var/data` and writes review state to
`/var/data/verifications.json`. Set the three `SMTP_*` secret values and
`REPORTER_ID_SECRET` in the Render dashboard; entries marked `sync: false` are
declarations, not secret values. A Render disk is attached to one service
instance, so move review state to a transactional shared database before
scaling the web service to multiple instances.

## Usage

1.  Start the application:
    ```bash
    python app.py
    ```
2.  Open your web browser and navigate to:
    `http://localhost:5000`
3.  Enter a nutritional exposure (e.g., "Coffee") and click **Analyze Evidence**.
4.  View the generated Forest Plot, Funnel Plot, and detailed table of extracted studies.

## Technology Stack

- **Backend**: Python, Flask, Pandas, Statsmodels, Biopython (Entrez)
- **Frontend**: HTML, CSS, JavaScript
- **Visualization**: Matplotlib
