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
from google.genai.types import UploadFileConfig

from google import genai

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
    batch_jsonl = build_jsonl_batch_folder(gemini_client, FOLDER_ID, PROMPT)



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


def build_jsonl_batch_folder(gemini_client, folder_id, prompt):
    """Takes link to google drive folder and constructs a jsonl file to use in gemini batch script"""
    drive_service = get_drive_service()
    if not drive_service:
        print("Failed to connect to Google Drive.")
        return

    try:
        print("Finding PDFs in Google Drive Folder: {FOLDER_ID}...")
        query = f"'{folder_id}' in parents and mimeType='application/pdf'"

        results = (drive_service.files().list(q=query, pageSize=10, fields="nextPageToken, files(id, name)").execute())
        drive_files = results.get("files", [])

        if not drive_files:
            print("No PDF files found.")
            return
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
                return



        jsonl_requests = []
        for up in uploaded_pdfs:
            request_data = {
                "key": up["gemini_file"].name,
                "request": {
                    "contents": {
                        "parts":
                            [{"text": prompt}, {"file_data": {"file_uri": up["gemini_file"].uri}}]
                    },
                }
            }
            jsonl_requests.append(request_data)

        jsonl_filename = "batch_requests.jsonl"
        with open(jsonl_filename, "w") as f:
            for request in jsonl_requests:
                f.write(f"{json.dumps(request)}\n")
        print(f"Created {jsonl_filename}")
        return jsonl_requests


        '''
        result = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[gemini_file, prompt],
        )

        print("\n>>> Gemini Analysis Result:")
        print(result.text)

        # 5. CLEAN UP
        gemini_client.files.delete(name=gemini_file.name)
        print(f"\nCleaned up file {gemini_file.name} from Gemini.")'''


    except HttpError as error:
        print(f"An error occurred: {error}")


if __name__ == "__main__":
    main()