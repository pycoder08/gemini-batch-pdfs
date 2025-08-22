# Add these new imports at the top
import os.path
import io
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

# Keep your original import
from google import genai

from google import genai

## CONSTANTS ##
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

def main():
    get_drive_service()

def get_drive_service():
    """Initializes and returns an authenticated Google Drive service object."""
    creds = None
    if os.path.exists('token.json'): # If credentials already exist, just use them
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid: # If credentials are invalid or expired, refresh them
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        # If no credentials are available, run the auth flow
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

        try:
            # Build the service object
            service = build("drive", "v3", credentials=creds)
            return service
        except HttpError as error:
            print(f"An error occurred: {error}")
            return None
    return None


if __name__ == "__main__":
    main()