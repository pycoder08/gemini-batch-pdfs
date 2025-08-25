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

import re



from google import genai
from google.api_core import exceptions


## CONSTANTS ##
SCOPES = ["https://www.googleapis.com/auth/drive"]

FOLDER_ID = "1wBE7XbfBTjFP-60jIB1MIYcBfjL4O5Ux"
PROMPT = (
        "Read this pdf of a student's response. I want you to analyze the response and return any unanswered questions,"
        "concerns, feedback, or suggestions the student has. Don't include general positive statements (i.e., 'I really "
        "enjoyed the course!') or other general statements and don't include any questions/headers from the course material, only relevant student responses."
        "If it's not directly related to something about the course itself don't include it. Don't return anything except the relevant text from the pdf"
        "If no relevent text is found, return 'No relevant text found in pdf'."
    )
LINKS = [
    "https://drive.google.com/file/d/1jJL_1odJ2J6_1A0Tm8WSFG81kWbRNQxW/view?usp=drivesdk",
    "https://drive.google.com/file/d/1L5c2ytZPILiz9Q4kT-Dt69WexkbXyw0A/view?usp=drivesdk",
    "https://drive.google.com/file/d/1umkN0Mv3Ab7gSLxPXFp1FTeDXQEtrf28/view?usp=drivesdk",
    "https://drive.google.com/file/d/1DDgSuk8y-tjiXYmoCtAbr6bGNxYTzc2x/view?usp=drivesdk",
    "https://drive.google.com/file/d/1_EKYDepaGJtEqLAre9CXbJm4fzRhAxvs/view?usp=drivesdk",
    "https://drive.google.com/file/d/1VcHMvZnsNMZFC_CsOEDhDwoZ3BNF-MiN/view?usp=drivesdk",
    "https://drive.google.com/file/d/1m40_jTrzDfFZpl3kXh7i8Euq0fLUIEhE/view?usp=drivesdk",
    "https://drive.google.com/file/d/1GlQEW-oTEweuaPXTXWR0lWmQrWUIpuk3/view?usp=drivesdk",
    "https://drive.google.com/file/d/1KeV3T50NnuRmOFgrzdEJtGBxvZWqFSqx/view?usp=drivesdk",
    "https://drive.google.com/file/d/1w9C2hJurO2lttQ5XF7XpaBIMKRcBwP59/view?usp=drivesdk",
    "https://drive.google.com/file/d/1KsQWjUeXIgMSqzhjf-_DqWzaIqpLL3hC/view?usp=drivesdk",
    "https://drive.google.com/file/d/1MaoI2ebhr-aEYnO_ZYr1Gy9Vw5I1iLQ4/view?usp=drivesdk",
    "https://drive.google.com/file/d/1eFJWvEyUCoI13TqP88BfP6NAucdXZB0t/view?usp=drivesdk",
    "https://drive.google.com/file/d/1cfaIkITV9JCOZX_EBk_UDREuoeVzJOoP/view?usp=drivesdk",
    "https://drive.google.com/file/d/1AMpujoQmXpkggMUOt2CUjCfoq4lZHjME/view?usp=drivesdk",
    "https://drive.google.com/file/d/1CiXCNgV89MshkR_UCjmIfATkMry2erox/view?usp=drivesdk",
    "https://drive.google.com/file/d/1MIJW7VT3WGUg9M39UxrO79oeutOYXvAw/view?usp=drivesdk",
    "https://drive.google.com/file/d/1sZUtBsAlHYw6oMuOd_JlK0BOIemyQdiq/view?usp=drivesdk",
    "https://drive.google.com/file/d/1Tm_qwBuifb4Poq1enGDPTomHfadw7-Ru/view?usp=drivesdk",
    "https://drive.google.com/file/d/1Ypn7azs8z5do-7yQv7CnLh4lOYDgzsOr/view?usp=drivesdk",
    "https://drive.google.com/file/d/1VmY511kiiJ_nL2CaQyrAPOHCZS38DqSo/view?usp=drivesdk",
    "https://drive.google.com/file/d/1P1NbOkCaskDc4bqHyiK4XErJvrdi_iME/view?usp=drivesdk",
    "https://drive.google.com/file/d/1ZwO-txElSYgTdBdjXs_GOycp6s3RH9oJ/view?usp=drivesdk",
    "https://drive.google.com/file/d/1CHi963QTFi0XTe_jTQAbCYBs4Vthbysf/view?usp=drivesdk",
    "https://drive.google.com/file/d/1uV2t5tUuwlhdIw7Ya7KclPM3qrGABMcB/view?usp=drivesdk",
    "https://drive.google.com/file/d/1dw_lEzgVPKw5uVmx9JFUHNWOVNLOGC4Q/view?usp=drivesdk",
    "https://drive.google.com/file/d/1OVmKdr4kTC0Kp5N2Syb3Ry13tAvt-diV/view?usp=drivesdk",
    "https://drive.google.com/file/d/1rvoar7wcZ7f3vFkXJodqCo5EUMVVYj8R/view?usp=drivesdk",
    "https://drive.google.com/file/d/1UvZvNsS6IqzY6h9oLUmo-reASB6M62yL/view?usp=drivesdk",
    "https://drive.google.com/file/d/1yE2YforDJCIM4K_XSQNpvXQAGanMVHAL/view?usp=drivesdk",
    "https://drive.google.com/file/d/1A811ElF7Yr4tek8lYDFa3ZCVEubgmO8M/view?usp=drivesdk",
    "https://drive.google.com/file/d/1ALeUrzmX_cQAwPE9z5EhfY6o7y7vPZYe/view?usp=drivesdk",
    "https://drive.google.com/file/d/1pYI4g6raH-Q7GrcayhmCovJzC9N294Q3/view?usp=drivesdk",
    "https://drive.google.com/file/d/1BPNnB3ulla5ss-o0Bzqi26dG_QsQ2_B2/view?usp=drivesdk",
    "https://drive.google.com/file/d/1Ik-QU4TeONDQnsb7o08vcOFD8y_muDoC/view?usp=drivesdk",
    "https://drive.google.com/file/d/1cSJeQLhTRRXu4bVRod0EJGE2O2_w608b/view?usp=drivesdk",
    "https://drive.google.com/file/d/1W_N6_PYrTRijHHBlvfwdDR5ciSt6LmQN/view?usp=drivesdk",
    "https://drive.google.com/file/d/1NwIw7-bIB8rrg3N8gAbmUKsFCZG_DxDg/view?usp=drivesdk",
    "https://drive.google.com/file/d/1cr8mnudDlwiECdLnXyt0WaxuxHqmTsF-/view?usp=drivesdk",
    "https://drive.google.com/file/d/1BNY8xSpxIff0J9kBgvmn-6TofYg9UegF/view?usp=drivesdk"
]


def main():
    new_folder_id = gather_drive_links(get_drive_service(), LINKS)
    gemini_client = genai.Client()
    drive_service = get_drive_service()
    uploaded_pdfs = upload_drive_pdfs(gemini_client, drive_service, new_folder_id)
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