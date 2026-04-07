# Installation Guide

This project uses a hybrid architecture to ensure stability and reproducibility:

1. **Conda (Python):** Manages the `bib` pipeline, Snakemake orchestrator, and ML libraries (Docling).
2. **Docker (Service):** Runs the GROBID service for bibliographic parsing, isolating its Java dependencies.

## Prerequisites

* **Linux** (Ubuntu/Debian recommended) or macOS.
* **Miniconda** or **Anaconda** installed. [Install Guide](https://docs.anaconda.com/miniconda/)
* **Docker Engine** installed and running. [Install Guide](https://docs.docker.com/engine/install/)
* **Git**

---

## 1. Set up the Python Environment (Conda)

We use a dedicated Conda environment named `bib`. This is critical because `docling` relies on specific system libraries (like `libGL`) and acts sensitively towards NumPy versions. Conda handles these binary dependencies better than pip.

1. **Create the `environment.yml` file** in your project root:
```yaml
name: bib
channels:
  - conda-forge
  - pytorch
  - defaults
dependencies:
  - python=3.10           # Pin Python 3.10 for ML stability
  - pip
  - snakemake             # Workflow orchestrator
  - libgl                 # System lib required by Docling/OpenCV
  - poppler               # PDF rendering utils
  - pip:
    - docling             # Main PDF extraction engine
    - torch               # Deep learning backend
    - torchvision
    - bibtexparser>=1.4.0 # For parsing .bib files
    - pydantic            # Configuration management
    - requests            # For API calls to GROBID/OpenAlex
    - beautifulsoup4      # For web scraping
    - lxml                # Faster XML/HTML parser

```


2. **Create and activate the environment:**
```bash
# Create the environment (this may take a few minutes)
conda env create -f environment.yml

# Activate the environment
conda activate bib

```

3. **Install the project package (for `import bib_pipeline`):**
```bash
pip install -e .

```

> **Important:** always ensure the `bib` environment is active (`(bib)` in your prompt) before running pipeline commands.



---

## 2. Set up the GROBID Service (Docker)

GROBID runs as a separate microservice. This keeps your local environment clean of Java/Maven dependencies.

1. **Pull the Docker image:**
```bash
docker pull lfoppiano/grobid:0.8.0

```


2. **Start the service:**
Run GROBID in a detached container listening on port `8070`.
```bash
docker run -d --rm --name grobid -p 8070:8070 lfoppiano/grobid:0.8.0

```


* `-d`: Run in background.
* `--rm`: Delete the container when stopped (keeps disk clean).
* `-p 8070:8070`: Expose the API on localhost.


3. **Verify the service is running:**
Wait 10-20 seconds for initialization, then run:
```bash
curl http://localhost:8070/api/isalive
# Output should be: true

```



---

## 3. Verify the Pipeline

To ensure both environments are communicating correctly, run a test of the extraction phase using the sample data.

1. **Ensure you have a Bronze artifact** (i.e., you have run the ingestion step).
2. **Run the GROBID extraction:**
```bash
snakemake -j1 extract_grobid

```


3. **Run the Docling extraction:**
```bash
snakemake -j1 extract_docling

```

If successful, this confirms:
* Snakemake is correctly installed in Conda.
* Your Python scripts can reach the Dockerized GROBID service (Universe A talking to Universe B).
* The `requests` library is functioning.



---

## Troubleshooting

### `ImportError: libGL.so.1: cannot open shared object file`

This error occurs if `docling` (specifically its `cv2` dependency) cannot find OpenGL libraries.

* **Fix:** Ensure you created the env using the `environment.yml` above, which includes `libgl`.
* **Manual Fix (Ubuntu):** `sudo apt-get install libgl1-mesa-glx`

### GROBID Connection Refused

* **Check:** Is the container running? `docker ps`
* **Check:** Is port 8070 exposed?
* **Fix:** Restart the container with the run command in Section 2.

### NumPy Version Errors (`numpy>=2.0`)

If you see errors related to NumPy 2.0, it means a pip install updated NumPy incompatibly with PyTorch.

* **Fix:** Delete and recreate the Conda environment to let the solver enforce constraints:
```bash
conda env remove -n bib
conda env create -f environment.yml

```
