import time
import json
import os.path
import io

import markdown
from fpdf import FPDF
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
FOLDER_ID = "YOUR_DRIVE_FOLDER_ID_HERE"
GEMINI_MODEL = "gemini-2.5-flash"
PROMPT =  """YOUR PROMPT HERE"""
CONVERT_TO_PDF = True
OUTPUT_FOLDER = "YOUR_OUTPUT_FOLDER_HERE"


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

        results = (drive_service.files().list(q=query, pageSize=250, fields="nextPageToken, files(id, name)").execute())
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
                time.sleep(2) # Pause to avoid rate limits

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

            time.sleep(2) # Avoid rate limits

        except exceptions.GoogleAPICallError as error:
            print(f"! Error analyzing {up['drive_info']['name']}: {error}, skipped")
            continue

        except exceptions.ResourceExhausted as error:
            print(f"! Resource error analyzing {up['drive_info']['name']}: {error}, skipped")
            time.sleep(5)
            continue

        except Exception as error:
            print(f"! Error analyzing {up['drive_info']['name']}: {error}, skipped")
            continue



    # Save reponses to json

    with open('responses.json', 'w') as f:
        json.dump(all_responses, f, indent=4)
        print("Saved responses to responses.json")
    return all_responses

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

def clean_filename(filename):
    """Removes characters that are invalid in Windows/Mac/Linux filenames."""
    # Remove the extension and invalid characters
    name_without_ext = os.path.splitext(filename)[0]
    sanitized_name = re.sub(r'[\\/*?:"<>|]', "", name_without_ext)
    return f"{sanitized_name}.pdf"


def analyses_to_pdf(responses):
    """Converts a list of analysis responses to a PDF file."""
    print("Converting responses to PDF...")

    for i, analysis_data in enumerate(responses):
        original_filename = analysis_data["file_name"]
        analysis_text = analysis_data.get('analysis', 'No analysis available.')

        pdf_filename = clean_filename(original_filename)
        pdf_filepath = OUTPUT_FOLDER + "/" + pdf_filename

        try:
            pdf = FPDF()
            pdf.add_page()

            pdf.set_font('helvetica', '', 12)
            cleaned_text = analysis_text.encode('latin-1', 'replace').decode('latin-1')

            markdown_content = f"#{original_filename.strip(".pdf")}\n\n{cleaned_text}"

            html_content = markdown.markdown(markdown_content)

            pdf.write_html(html_content)

            pdf.output(pdf_filepath)

        except Exception as e:
            print(f"    - FAILED to create PDF for '{original_filename}'. Reason: {e}")


if __name__ == "__main__":
    main()