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
import re

from google import genai
from google.api_core import exceptions


## CONSTANTS ##
SCOPES = ["https://www.googleapis.com/auth/drive"]
FOLDER_ID = "1wBE7XbfBTjFP-60jIB1MIYcBfjL4O5Ux"
GEMINI_MODEL = "gemini-2.5-flash"
PROMPT =  """You are a transcription assistant specializing in educational documents. Your task is to transcribe the provided PDF, preserving the distinction between printed text (headers, questions) and handwritten text (student responses).

        The output must be in Markdown format.
    
        Follow these rules precisely:
    
        Transcribe the document page by page, starting each page with 2 blank lines, then --- PAGE X ---, then another blank line.
    
        Identify all printed text, such as section titles (e.g., "SECTION 1"), questions, and field labels (e.g., "Name:", "ID Number:"). Format all of this printed text as bold Markdown text.
    
        Identify the student's handwritten responses.
    
        Present the transcribed text for each section with the bolded headers first, followed by a blank line, and then the student's response in plain text.
    
        When you encounter a checkmark, just ignore it
    
        Do not omit any text from the original document, including page numbers or marginal notes like "Mail back to Tayba."
    
        Correct obvious English spelling errors in the student's response based on context (e.g., "Kusowing" to "Knowing", "ferents" to "parents").
    
        Do NOT correct the spelling of transliterated Arabic words like 'birr', 'Deen', 'Allah', 'Insha Allah', 'Ameen', 'hadith', 'Qur'an', etc. 
        
        Make sure to properly identify when a word is actually arabic and correct it accordingly.
        
        Do NOT use any special characters. Only alphanumeric characters and spaces with markdown formatting. If something isn't normal text just ignore it.
        
        Make sure to separate things properly and don't put things on the same line when they should be on different lines.
    
        Do not add any commentary, greetings, or explanations. Provide only the transcribed Markdown text from the document."""


def main():
    gemini_client = genai.Client()
    drive_service = get_drive_service()
    uploaded_pdfs = upload_drive_pdfs(gemini_client, drive_service, FOLDER_ID)
    analyze_pdfs(gemini_client, uploaded_pdfs, GEMINI_MODEL)


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

        results = (drive_service.files().list(q=query, pageSize=100, fields="nextPageToken, files(id, name)").execute())
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


def gather_drive_links(drive_service, link_list):
    folder_id = create_folder(drive_service, "Copied Files from Links")
    for link in link_list:
        file_id = extract_file_id(link)
        if file_id:
            file = drive_service.files().get(fileId=file_id, fields="name").execute()
            name = file.get("name")

            copied_file = {
                "name": name,
                "parents": [folder_id]
            }
            drive_service.files().copy(fileId=file_id, body=copied_file).execute()
            print(f"Copied {name} to {folder_id}")

    return folder_id


def extract_file_id(link):
    match = re.search(r"file\/d\/([a-zA-Z0-9-_]+)", link)
    return match.group(1) if match else None

def create_folder(drive_service, folder_name):
    folder_metadata = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder"
    }
    folder = drive_service.files().create(body=folder_metadata, fields="id").execute()
    return folder.get("id")


if __name__ == "__main__":
    main()