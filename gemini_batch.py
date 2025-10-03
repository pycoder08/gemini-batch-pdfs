import time
import json
import os.path
import tempfile
import re

from dotenv import load_dotenv
import markdown
from fpdf import FPDF
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload
from google.genai.types import UploadFileConfig

from google import genai
from google.api_core import exceptions

## CONSTANTS ##
SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets.readonly"
]
FOLDER_ID = "YOUR_DRIVE_FOLDER_ID_HERE"
SPREADSHEET_ID = "YOUR_SPREADSHEET_ID_HERE"
SHEET_RANGE = "Sheet1!A:A"
GEMINI_MODEL = "gemini-2.5-flash"
PROMPT = """YOUR PROMPT HERE"""
CONVERT_TO_PDF = True
OUTPUT_FOLDER = "YOUR_OUTPUT_FOLDER_HERE"


def main():
    load_dotenv()
    gemini_client = genai.Client()

    drive_service = get_service("drive", "v3")
    spreadsheet_service = get_service("sheets", "v4")

    file_list = read_links_from_sheet(spreadsheet_service, SPREADSHEET_ID, SHEET_RANGE)

    uploaded_pdfs = process_files_from_list(gemini_client, drive_service, file_list)

    analyze_pdfs(gemini_client, PROMPT, uploaded_pdfs, GEMINI_MODEL)


def get_service(api_name, version):
    """Initializes and returns an authenticated Google service object."""
    creds = None
    if os.path.exists('token.json'):  # If credentials already exist, just use them
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)

    if not creds or not creds.valid:  # If credentials are invalid or expired, refresh them
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
        service = build(api_name, version, credentials=creds)
        return service
    except HttpError as error:
        print(f"An error occurred: {error}")
        return None


def process_files_from_list(gemini_client, drive_service, file_list):
    """Uploads all PDFs in a Google Drive folder to Gemini"""
    # Raise errors if services are not initialized
    if not drive_service:
        print("Failed to connect to Google Drive.")
        return None
    if not file_list:
        print("No files to process.")
        return None

    uploaded_pdfs = []

    for link in file_list:
        file_id = extract_file_id(link)
        if not file_id:
            print(f"Invalid link: {link}")
            continue


        file_metadata = drive_service.files().get(fileId=file_id, fields="name").execute()
        file_name = file_metadata.get("name")

        # Extract student name from file name
        student_name = extract_student_name(file_name)
        student_first_name = student_name[0]
        student_last_name = student_name[1]

        try:
            print(f"  - Processing {file_name} for {student_name}...")
            request = drive_service.files().get_media(fileId=file_id)

            # Store the file in a temporary file
            with tempfile.NamedTemporaryFile(suffix=".pdf", mode='wb', delete=True) as temp_file:
                downloader = MediaIoBaseDownload(temp_file, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
                temp_file.seek(0)

                print("Uploading to gemini")
                gemini_file = gemini_client.files.upload(
                    file=temp_file,
                    config=UploadFileConfig(
                        display_name=file_name,
                        mime_type='application/pdf'
                    )
                )

            uploaded_pdfs.append({
                "file_id": file_id,
                "file_name": file_name,
                "student_name": student_name,
                "gemini_file": gemini_file
            })
            time.sleep(2) # Pause to avoid rate limits

        except HttpError as error:
            print(f"! Error uploading {file_name}: {error}, skipped")
            continue

        return uploaded_pdfs


def analyze_pdfs(gemini_client, prompt, uploaded_pdfs, gemini_model):
    """Analyzes all PDFs uploaded to Gemini"""
    all_responses = []
    for up in uploaded_pdfs:
        try:
            print(f"Analyzing {up['drive_info']['name']}...")
            result = gemini_client.models.generate_content(
                model=gemini_model,
                contents=[{"text": prompt}, {"file_data": {"file_uri": up["gemini_file"].uri}}],
            )
            print("  -Analysis Complete")

            all_responses.append(
                {"file_name": up['drive_info']['name'], "file_id": up['drive_info']['id'], "analysis": result.text})

            ## CLEANUP
            gemini_client.files.delete(name=up['gemini_file'].name)
            print(f"  - Cleaned up file {up['gemini_file'].name} from Gemini.")

            time.sleep(2)  # Avoid rate limits

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

    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
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


def extract_student_name(text):
    #print("Original Text:" + text)

    # Delete everything up to and including the ending parenthesis
    try:
        result = text[text.rindex(')') + 1:]
    except ValueError:
        print("No closing parenthesis found in text.")
        return None

    #print("Text after step 1:" + result)

    # When we find the first ID code containing numbers, we delete it and everything after it
    text_parts_underscores = result.split('_')
    for i in range(len(text_parts_underscores)):
        if text_parts_underscores[i].isalnum() and not text_parts_underscores[i].isalpha():
            selected_range = text_parts_underscores[:i]
            result = '_'.join(selected_range)
            break

    #print("Text after step 2:" + result)

    # Final cleanup
    result = result.strip('_')
    if result[0] == '-':
        result = result[1:]

    result = result.strip('_')

    #print("Text after step 3:" + result)

    name_parts = result.split('_')
    firstname = name_parts[0]
    lastname = name_parts[1]

    #print("Final Result:" + firstname + " " + lastname)
    return name_parts

def read_links_from_sheet(sheets_service, spreadsheet_id, sheet_range):
    """Reads PDF google drive links from a Google Sheets spreadsheet."""
    if not sheets_service:
        print("Failed to connect to Google Sheets.")
        return []

    try:
        result = sheets_service.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range=sheet_range).execute()
        values = result.get('values', [])

        if not values:
            print("No links found in the spreadsheet.")
            return []

        file_list = [item[0] for item in values if item]
        print(f"Found {len(file_list)} links in the spreadsheet.")
        return file_list

    except HttpError as error:
        print(f"An error occurred: {error}")
        return []


if __name__ == "__main__":
    main()
