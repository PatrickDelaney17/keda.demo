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
