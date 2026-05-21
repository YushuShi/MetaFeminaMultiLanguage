# MetaFemina

**Meta-Analysis Tool for Women's Cancers & Nutrition**

MetaFemina pools MetaMamm, MetaOvary, and MetaUturus into one Flask website for nutritional exposure meta-analyses across breast, ovarian, and uterine cancer. Cached results and generated plots keep their disease-specific filenames, so each selected disease scope resolves to the matching cached outcome.

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
