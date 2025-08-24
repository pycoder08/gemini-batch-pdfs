# Add these new imports at the top
import time
import json
import os.path
import io
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload
from google.genai import types
from google.genai.types import UploadFileConfig

from google import genai
from google.api_core import exceptions


## CONSTANTS ##
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
FOLDER_ID = "1wBE7XbfBTjFP-60jIB1MIYcBfjL4O5Ux"
PROMPT = (
        "Read this pdf of a student's response. I want you to analyze the response and return any unanswered questions,"
        "concerns, feedback, or suggestions the student has. Don't include general positive statements (i.e., 'I really "
        "enjoyed the course!') or other general statements and don't include any questions/headers from the course material, only relevant student responses."
        "If it's not directly related to something about the course itself don't include it. Don't return anything except the relevant text from the pdf"
        "If no relevent text is found, return 'No relevant text found in pdf'."
    )

def main():
    gemini_client = genai.Client()
    drive_service = get_drive_service()
    uploaded_pdfs = upload_drive_pdfs(gemini_client, drive_service, FOLDER_ID)
    analyze_pdfs(gemini_client, uploaded_pdfs, "gemini-2.5-flash")


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

def upload_drive_pdfs(gemini_client, drive_service, folder_id):
    """Uploads all PDFs in a Google Drive folder to Gemini"""
    if not drive_service:
        print("Failed to connect to Google Drive.")
        return None

    try:
        print(f"Finding PDFs in Google Drive Folder: {FOLDER_ID}...")
        query = f"'{folder_id}' in parents and mimeType='application/pdf'"

        results = (drive_service.files().list(q=query, pageSize=10, fields="nextPageToken, files(id, name)").execute())
        drive_files = results.get("files", [])

        if not drive_files:
            print("No PDF files found.")
            return None
        print(f"Found {len(drive_files)} PDF files.")


        ### Upload to gemini before we build the JSONL batch file ###
        uploaded_pdfs = []
        for file_info in drive_files:
            try:
                print(f"  - Uploading {file_info['name']}...")
                request = drive_service.files().get_media(fileId=file_info['id'])

                # Download the file to a BytesIO buffer
                file_buffer = io.BytesIO()
                downloader = MediaIoBaseDownload(file_buffer, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
                    print(f"Downloading... {int(status.progress() * 100)}%.")

                file_buffer.seek(0)


                print("Uploading to gemini")
                gemini_file = gemini_client.files.upload(
                    file=file_buffer,
                    config=UploadFileConfig(
                        display_name=file_info['name'],
                        mime_type='application/pdf'
                    )
                )
                uploaded_pdfs.append({"drive_info": file_info, "gemini_file": gemini_file})
                time.sleep(1) # Pause to avoid rate limits

            except HttpError as error:
                print(f"! Error uploading {file_info['name']}: {error}, skipped")
                return None

        return uploaded_pdfs

    except HttpError as error:
        print(f"An error occurred: {error}")
        return None

def analyze_pdfs(gemini_client, uploaded_pdfs, gemini_model):
    """Analyzes all PDFs uploaded to Gemini"""
    all_responses = []
    for up in uploaded_pdfs:
        try:
            print(f"Analyzing {up['drive_info']['name']}...")
            result = gemini_client.models.generate_content(
                model=gemini_model,
                contents=[{"text": PROMPT}, {"file_data": {"file_uri": up["gemini_file"].uri}}],
            )
            print("  -Analysis Complete")

            all_responses.append({"file_name": up['drive_info']['name'], "file_id": up['drive_info']['id'], "analysis": result.text})

            ## CLEANUP
            gemini_client.files.delete(name=up['gemini_file'].name)
            print(f"  - Cleaned up file {up['gemini_file'].name} from Gemini.")

            time.sleep(1) # Avoid rate limits

        except exceptions.GoogleAPICallError as error:
            print(f"! Error analyzing {up['drive_info']['name']}: {error}, skipped")
            continue

    # Save reponses to json

    with open('responses.json', 'w') as f:
        json.dump(all_responses, f, indent=4)
        print("Saved responses to responses.json")



if __name__ == "__main__":
    main()