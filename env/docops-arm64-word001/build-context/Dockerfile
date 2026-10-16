# DocOps native arm64 adapted environment for atomic__word_001_engineering_report_toc_hierarchy_seed
# NOT the official environment: official DocOps ships only amd64 base archives
# (harbor-claude-code-base:2.1.114); this is a project-built linux/arm64 replacement
# covering the declared dependency surface of the Word task, its DocumentToolsAgent
# runtime and its pytest verifier. No QEMU emulation. No credentials baked in.
FROM python:3.12-slim@sha256:05cda9777409a9c3ffddd94a4c476b79f0769a0b4857f0c7ed9226b6800b0d6f

# Declared dependency surface (DocOps requirements.txt constraints, resolved at build):
# python-docx>=1.1.2 openpyxl>=3.1.5 python-pptx>=1.0.2 pypdf>=5.0.0
# pdfplumber>=0.11.4 PyMuPDF>=1.24.0 reportlab>=4.2.0 Pillow>=10.0.0
# pandas>=2.2.0 numpy>=1.26.0 pytest>=8.0.0
# Actual resolved versions are recorded via pip freeze after build (requirements-frozen.txt).
COPY requirements-adapted.txt /tmp/requirements-adapted.txt
RUN pip install --no-cache-dir -r /tmp/requirements-adapted.txt && rm /tmp/requirements-adapted.txt

# Skills layout expected by task.toml ([environment] skills_dir = "/skills").
# Only the doc skill ships with this task; the optional render_docx.py helper
# additionally requires soffice + poppler (pdf2image) which this adapted
# environment intentionally does NOT provide (see ENV-DIFFERENCES.md).
COPY skills/ /skills/

WORKDIR /root
