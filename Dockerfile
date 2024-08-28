FROM python:3.9-slim

WORKDIR /app
COPY gcp_copy_files.py /app/

#RUN pip install azure-storage-blob
RUN pip install google-cloud-storage python-dotenv

# Copy only the necessary files
#COPY requirements.txt .

# Install dependencies
#RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 5000

CMD ["python", "gcp_copy_files.py"]
