# Image Python légère
FROM python:3.11-slim

# Dossier de travail
WORKDIR /app

# Copier les dépendances
COPY requirements.txt .

# Installer dépendances Python
RUN pip install --no-cache-dir -r requirements.txt

# Copier le code
COPY multivol_mcp.py .

# Lancement du serveur MCP (mode stdio)
CMD ["python", "multivol_mcp.py"]