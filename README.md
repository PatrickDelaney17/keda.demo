# keda.demo
basic test and learn project for using KEDA on k3s



# Steps

## Install KEDA on Your k3s Cluster

### Add the KEDA Helm Repository:
```sh
helm repo add kedacore https://kedacore.github.io/charts
helm repo update

```

### Install KEDA:
```
helm repo add kedacore https://kedacore.github.io/charts
helm repo update
helm install keda kedacore/keda --namespace default

```

### Verify Installation: Check that the KEDA components are running:

```
kubectl get pods -n keda
```

## Set up - Azure

### Create or modify your python app

```sh
pip install azure-storage-blob python-dotenv
```
#### Accounting for scaling by using blob leasing 
```python
import os
from azure.storage.blob import BlobServiceClient
from azure.core.exceptions import ResourceExistsError
from dotenv import load_dotenv

# Load environment variables from .env file (useful for local testing)
load_dotenv()

# Get environment variables
connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
source_container = os.getenv("SOURCE_CONTAINER")
destination_container = os.getenv("DESTINATION_CONTAINER")

def copy_files():
    blob_service_client = BlobServiceClient.from_connection_string(connection_string)
    source_client = blob_service_client.get_container_client(source_container)
    dest_client = blob_service_client.get_container_client(destination_container)

    blobs = source_client.list_blobs()
    for blob in blobs:
        source_blob = source_client.get_blob_client(blob.name)
        dest_blob = dest_client.get_blob_client(blob.name)

        try:
            # Attempt to acquire a lease (lock) on the blob
            lease = source_blob.acquire_lease()

            # Copy blob if the lease is successfully acquired
            dest_blob.start_copy_from_url(source_blob.url)

            # Delete the original blob after copying
            source_blob.delete_blob()

            # Release the lease
            lease.release()
        except ResourceExistsError:
            # If another pod has already acquired a lease, skip this blob
            print(f"Blob {blob.name} is already being processed by another pod.")

if __name__ == "__main__":
    copy_files()

```

### create docker image
```Dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY copy_files.py /app/

RUN pip install azure-storage-blob

CMD ["python", "copy_files.py"]

```
### Build and Push the Docker Image:
```
docker build -t your-docker-repo/copy-files:latest .
docker push your-docker-repo/copy-files:latest

```

### Set Up Azure Blob Storage Scaler in KEDA
```bash
kubectl create secret generic azure-blob-secrets \
  --from-literal=AZURE_STORAGE_CONNECTION_STRING="your_connection_string_here" \
  --from-literal=SOURCE_CONTAINER="container-1" \
  --from-literal=DESTINATION_CONTAINER="container-2"
```

```YAML
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: blob-storage-scaler
  labels:
    app: copy-files-app
spec:
  scaleTargetRef:
    name: copy-files-app
  minReplicaCount: 0 # Start with 0 replicas
  maxReplicaCount: 10 # Set the maximum number of pods
  cooldownPeriod: 300  # How long KEDA waits before scaling down
  pollingInterval: 30  # How often KEDA checks the blob storage for new files
  triggers:
  - type: azure-blob
    metadata:
      connectionFromEnv: AZURE_STORAGE_CONNECTION_STRING
      containerName: container-1
      blobCount: "5"  # Target metric value for scaling (sets one pod per 5 files)
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: copy-files-app
  labels:
    app: copy-files-app
  # No need for namespace field here
spec:
  replicas: 0  # Start with 0 replicas
  selector:
    matchLabels:
      app: copy-files-app
  template:
    metadata:
      labels:
        app: copy-files-app
    spec:
      containers:
      - name: copy-files
        image: your-docker-repo/copy-files:latest
        env:
        - name: AZURE_STORAGE_CONNECTION_STRING
          valueFrom:
            secretKeyRef:
              name: azure-blob-secrets
              key: AZURE_STORAGE_CONNECTION_STRING
        - name: SOURCE_CONTAINER
          valueFrom:
            secretKeyRef:
              name: azure-blob-secrets
              key: SOURCE_CONTAINER
        - name: DESTINATION_CONTAINER
          valueFrom:
            secretKeyRef:
              name: azure-blob-secrets
              key: DESTINATION_CONTAINER
```


### You can monitor the scaling behavior with:
```sh
kubectl get hpa
kubectl get pods

```

## Set Up - GCP 

### install dependencies
```bash
pip install google-cloud-storage python-dotenv
```

### create python app
> creaet .env as well...
```python
import os
from google.cloud import storage
from dotenv import load_dotenv
from datetime import datetime, timedelta

# Load environment variables from .env file
load_dotenv()

# Set environment variables
source_bucket_name = os.getenv("SOURCE_BUCKET")
destination_bucket_name = os.getenv("DESTINATION_BUCKET")
lease_duration = int(os.getenv("LEASE_DURATION_MINUTES", 10))  # Default lease duration is 10 minutes

def move_files():
    # Initialize Google Cloud Storage client
    storage_client = storage.Client()

    # Get source and destination buckets
    source_bucket = storage_client.bucket(source_bucket_name)
    destination_bucket = storage_client.bucket(destination_bucket_name)

    # List files in the source bucket
    blobs = source_bucket.list_blobs()

    for blob in blobs:
        # Check if the file is already being processed by checking its metadata
        metadata = blob.metadata or {}
        lease_expiration = metadata.get("lease_expiration")

        if lease_expiration:
            lease_expiration_time = datetime.strptime(lease_expiration, "%Y-%m-%dT%H:%M:%S")
            if lease_expiration_time > datetime.utcnow():
                print(f"Skipping {blob.name}, currently leased until {lease_expiration_time}.")
                continue  # Skip this file if it's currently leased

        # Lease the file by setting a "lease_expiration" metadata tag
        lease_expiration_time = datetime.utcnow() + timedelta(minutes=lease_duration)
        blob.metadata = blob.metadata or {}
        blob.metadata["lease_expiration"] = lease_expiration_time.strftime("%Y-%m-%dT%H:%M:%S")
        blob.patch()  # Update the blob with the new metadata

        print(f"Leased {blob.name} for processing until {lease_expiration_time}.")

        try:
            # Process the file (copy to the destination bucket)
            source_blob = source_bucket.blob(blob.name)
            destination_blob = destination_bucket.blob(blob.name)

            destination_blob.rewrite(source_blob)
            print(f"Moved {blob.name} from {source_bucket_name} to {destination_bucket_name}.")

            # After processing, delete the file from the source bucket
            source_blob.delete()

        except Exception as e:
            # If an error occurs, release the lease by removing the metadata
            blob.metadata.pop("lease_expiration", None)
            blob.patch()
            print(f"Error processing {blob.name}: {e}. Lease released.")

        else:
            # If successful, lease is no longer needed
            print(f"Finished processing {blob.name}. File removed from source bucket.")

if __name__ == "__main__":
    move_files()


```

### KEDA Setup for Google Cloud Storage
```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
helm install prometheus prometheus-community/kube-prometheus-stack

```

### KEDA Configuration Using the Prometheus Trigger: Once the exporter is set up, you can configure KEDA to scale based on the object count.
> See deploy [yaml file](deploy\gcp-scaler-deploy.yaml) for example details