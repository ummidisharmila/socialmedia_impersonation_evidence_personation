# Social Media Impersonation Detection and Evidence Archiving System

SignalTrace is a local Streamlit application for recording suspected impersonation reports, running transparent rule-based profile triage, archiving supporting files, checking archived file consistency with SHA-256, and exporting case reports as PDFs.

## Run locally

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run app.py
```

The app creates `data/investigations.sqlite3` and `data/evidence/` automatically. Dashboard totals and charts are derived from those records. A new installation contains no seeded or fabricated case data.

## Included workflows

- Analyze a profile with clearly disclosed rule-based risk indicators.
- Submit a complaint and receive a unique case ID.
- Archive supported images, PDFs, and text files, optionally linking them to a case.
- Search and filter archive metadata, including original filename, file type, size, upload time, and SHA-256 digest.
- Recalculate evidence hashes and compare them with the stored digest.
- Export a case summary and linked evidence metadata as a PDF.
- Maintain a local team directory and update case status in SQLite.

## Security and integrity notes

- The risk score is a triage aid, not an AI determination or proof of impersonation.
- A matching SHA-256 digest means the file matches the version archived by this application. It does not prove authenticity, authorship, or provenance.
- This prototype has no authentication or role enforcement. User management is a directory only.
- Evidence is stored unencrypted on the host filesystem. Restrict access to the machine and data directory, back up records securely, and add authentication, authorization, encrypted storage, retention controls, and audit logging before handling sensitive real-world cases or exposing the app to a network.
- Files are limited to 20 MB and accepted extensions are PNG, JPG, JPEG, WEBP, PDF, and TXT.