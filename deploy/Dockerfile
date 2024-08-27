FROM python:3.9-slim

WORKDIR /app
COPY gcp_copy_files.py /app/

#RUN pip install azure-storage-blob
RUN pip install google-cloud-storage python-dotenv

CMD ["python", "gcp_copy_files.py"]
