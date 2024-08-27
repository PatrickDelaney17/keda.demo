import os
from google.cloud import storage
from dotenv import load_dotenv
from datetime import datetime, timedelta

# Load environment variables from .env file
load_dotenv()

# Set environment variables
bucket_name = os.getenv("BUCKET_NAME")
source_folder = os.getenv("SOURCE_FOLDER", "source")
destination_folder = os.getenv("DESTINATION_FOLDER", "destination")
lease_duration = int(os.getenv("LEASE_DURATION_MINUTES", 10))  # Default lease duration is 10 minutes

def move_files():
    # Initialize Google Cloud Storage client
    storage_client = storage.Client()

    # Get the bucket
    bucket = storage_client.bucket(bucket_name)

    # List files in the source folder
    blobs = bucket.list_blobs(prefix=source_folder + "/")

    for blob in blobs:
        # Skip directories (Google Cloud Storage does not use actual folders, just prefixes)
        if not blob.name.endswith('/'):
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
                # Define the new destination path within the destination folder
                new_blob_name = destination_folder + "/" + blob.name[len(source_folder) + 1:]
                destination_blob = bucket.blob(new_blob_name)

                # Copy the blob to the destination folder
                destination_blob.rewrite(blob)
                print(f"Moved {blob.name} to {new_blob_name}.")

                # After processing, delete the file from the source folder
                blob.delete()

            except Exception as e:
                # If an error occurs, release the lease by removing the metadata
                blob.metadata.pop("lease_expiration", None)
                blob.patch()
                print(f"Error processing {blob.name}: {e}. Lease released.")

            else:
                # If successful, lease is no longer needed
                print(f"Finished processing {blob.name}. File removed from source folder.")

if __name__ == "__main__":
    move_files()
