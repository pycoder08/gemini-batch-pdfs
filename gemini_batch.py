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
    "https://www.googleapis.com/auth/spreadsheets"
]
FOLDER_ID = "1LSmm1yVUXuUHC2H5y7TXzFcWFs6efieZ"
SPREADSHEET_ID = "1mZ-7DdPHqg13sFu0KWclWtzVbvZzPnlnhl86X0DuvdY"
SHEET_RANGE = "'TEST SHEET - Adab 99 Purity your speech'!D1:D"
GEMINI_MODEL = "gemini-2.5-flash"
PROMPT = (
        "Read this pdf of a student's response. I want you to analyze the response and return any unanswered questions,"
        "concerns, feedback, or suggestions the student has. Don't include general positive statements (i.e., 'I really "
        "enjoyed the course!') or other general statements and don't include any questions/headers from the course material, only relevant student responses."
        "Never include text from the course itself, such as 'If I don't understand why my answer was wrong, I will write Tayba and ask'."
        "If it's not directly related to something about the course itself don't include it. Don't return anything except the relevant text from the pdf"
        "If no relevant text is found, return 'No relevant text found in pdf'."
    )
OCR_PROMPT = """You are a transcription assistant specializing in educational documents. Your task is to transcribe the provided PDF, preserving the distinction between printed text (headers, questions) and handwritten text (student responses).

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
CONVERT_TO_PDF = True
OUTPUT_FOLDER = "1LSmm1yVUXuUHC2H5y7TXzFcWFs6efieZ"


def main():
    load_dotenv()
    gemini_client = genai.Client()

    drive_service = get_service("drive", "v3")
    spreadsheet_service = get_service("sheets", "v4")

    with open('responsesOUT.txt', 'w') as f:
        for response in json.load(open('responses.json')):
            f.write(response["file_name"] + "\n")
            f.write(response['analysis'] + "\n\n\n")


    #links = get_sheet_data(spreadsheet_service, SPREADSHEET_ID, SHEET_RANGE)
    #uploaded_pdfs = process_files_from_list(gemini_client, drive_service, links)
    #analyze_pdfs(gemini_client, PROMPT, uploaded_pdfs, GEMINI_MODEL)


    #analyses_to_pdf(json.load(open('responses.json')))


    #uploaded_pdfs = process_files_from_list(gemini_client, drive_service, ["https://drive.google.com/file/d/1NZ1T9atC_eVb9I92IqDwX7Wl9pXOcP2q/view"])


    #print(gather_drive_links(drive_service, links))

    #update_sheet(drive_service, spreadsheet_service)

    """file_list = get_sheet_data(spreadsheet_service, SPREADSHEET_ID, SHEET_RANGE)

    """


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

    print("Fetching list of existing files from Gemini...")
    gemini_files_map = {}
    try:
        for f in gemini_client.files.list():
            # Store files in a dictionary for fast lookups
            gemini_files_map[f.display_name] = f
        print(f"Found {len(gemini_files_map)} files already on Gemini.")
    except Exception as e:
        print(f"Could not list Gemini files: {e}. Will attempt to upload all.")


    uploaded_pdfs = []

    for link in file_list:
        file_id = extract_file_id(link)
        if not file_id:
            print(f"Invalid link: {link}")
            continue


        try:
            file_metadata = drive_service.files().get(fileId=file_id, fields="name").execute()
            file_name = file_metadata.get("name")
            if not file_name:
                print(f"  - File ID {file_id} has no name. Skipping.")
                continue


            # Extract student name from file name
            student_name_parts = extract_student_name(file_name)
            if not student_name_parts:
                print(f"  - Could not parse name from: {file_name}, using placeholder.")
                student_name_parts = ["Student", "Name"]

            student_name = " ".join(student_name_parts)

            # Fetch file from Gemini if it already exists
            if file_name in gemini_files_map:
                print(f"  - File {file_name} already uploaded to Gemini, skipping.")
                gemini_file = gemini_files_map[file_name]
            else:

                print(f"  - Processing {file_name}...")
                request = drive_service.files().get_media(fileId=file_id)

                # Store the file in a temporary file
                temp_file = tempfile.NamedTemporaryFile(suffix=".pdf", mode='wb', delete=False)
                temp_file_path = temp_file.name  # Store the path

                # 2. Download the file data
                downloader = MediaIoBaseDownload(temp_file, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()

                temp_file.close()


                try:
                    print("Uploading to gemini")
                    gemini_file = gemini_client.files.upload(
                        file=temp_file_path,  # Use the path
                        config=UploadFileConfig(
                            display_name=file_name,
                            mime_type='application/pdf'
                        )
                    )
                    time.sleep(2)  # Pause to avoid rate limits

                finally:
                    os.remove(temp_file_path)

            # Store uploaded file info
            uploaded_pdfs.append({
                "file_id": file_id,
                "file_name": file_name,
                "student_name": student_name,
                "gemini_file": gemini_file
            })


        except HttpError as error:
            print(f"! Error processing {file_name}: {error}, skipped")
            if 'temp_file_path' in locals() and os.path.exists(temp_file_path):
                os.remove(temp_file_path)  # Clean up on error
            continue
        except Exception as e:
            print(f"! Unexpected error with {file_name}: {e}, skipped")
            if 'temp_file_path' in locals() and os.path.exists(temp_file_path):
                os.remove(temp_file_path)  # Clean up on error
            continue

    return uploaded_pdfs


def analyze_pdfs(gemini_client, prompt, uploaded_pdfs, gemini_model):
    """Analyzes all PDFs uploaded to Gemini"""
    all_responses = []
    for up in uploaded_pdfs:
        try:
            print(f"Analyzing {up['file_name']}...")
            result = gemini_client.models.generate_content(
                model=gemini_model,
                contents=[{"text": prompt}, {"file_data": {"file_uri": up["gemini_file"].uri}}],
            )
            print("  -Analysis Complete")

            all_responses.append(
                {"file_name": up['file_name'], "file_id": up['file_name'], "analysis": result.text})

            ## CLEANUP
            #gemini_client.files.delete(name=up['gemini_file'].name)
            #print(f"  - Cleaned up file {up['file_name']} from Gemini.")

            time.sleep(1)  # Avoid rate limits

        except exceptions.GoogleAPICallError as error:
            print(f"! Error analyzing {up['file_name']}: {error}, skipped")
            time.sleep(1)
            continue

        except exceptions.ResourceExhausted as error:
            print(f"! Resource error analyzing {up['file_name']}: {error}, skipped")
            time.sleep(1)
            continue

        except Exception as error:
            print(f"! Error analyzing {up['file_name']}: {error}, skipped")
            time.sleep(1)
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
            try:
                file = drive_service.files().get(fileId=file_id, fields="name").execute()
                name = file.get("name")

                copied_file = {
                    "name": name,
                    "parents": [folder_id]
                }
                drive_service.files().copy(fileId=file_id, body=copied_file).execute()
                print(f"Copied {name} to {folder_id}")
            except HttpError as error:
                print(f"An error occurred while copying file {file_id}: {error}")
                continue
            except Exception as error:
                print(f"An unexpected error occurred while copying file {file_id}: {error}")
                continue

    return folder_id


def get_sheet_data(sheets_service, spreadsheet_id, sheet_range):
    """Reads rows from a Google Sheets spreadsheet."""
    if not sheets_service:
        print("Failed to connect to Google Sheets.")
        return []

    try:
        result = sheets_service.spreadsheets().get(
            spreadsheetId=spreadsheet_id,
            ranges=sheet_range,
            includeGridData=True,
            fields="sheets/data/rowData/values/hyperlink"
        ).execute()

        links_list = []

        sheets = result.get("sheets", [])
        if not sheets:
            print("No sheets found in the spreadsheet.")
            return []

        data = sheets[0].get("data", [])
        if not data:
            print("No data found in sheet.")
            return []

        row_data = data[0].get("rowData", [])
        if not row_data:
            print("No row data found in sheet.")
            return []

        for row in row_data:
            cells = row.get("values", [])
            if cells:
                link = cells[0].get("hyperlink")
                if link:
                    links_list.append(link)
                else:
                    pass

        if not links_list:
            print("No hyperlinks found in the specified range.")
            return []

        print(f"Found {len(links_list)} links in the spreadsheet.")
        return links_list

    except HttpError as error:
        print(f"An error occurred: {error}")
        return []


def update_sheet(drive_service, sheets_service):
    """
    Reads links from the sheet, extracts first/last names, and overwrites the sheet
    with the data in the fortmat [firstname, lastname, link]
    """

    print("Reading data from spreadsheet...")
    links_list = get_sheet_data(sheets_service, SPREADSHEET_ID, SHEET_RANGE)

    if not links_list:
        print("No data found in the spreadsheet.")
        return

    updated_values = [["First Name", "Last Name", "Link"]]
    print("Processing rows...")
    for link in links_list:
        print(link)
        if not link:
            continue

        file_id = extract_file_id(link)
        if not file_id:
            print(f"Could not extract ID from link: {link}")
            updated_values.append(["ERROR", "Invalid link", link])
            continue
        try:
            # Call Drive API to get file metadata in order to extract the file name first
            file_metadata = drive_service.files().get(fileId=file_id, fields="name").execute()
            file_name = file_metadata.get("name")
            print(file_name)

            # Get student name from file name
            student_name = extract_student_name(file_name)
            if not student_name or len(student_name) < 2:
                print(f"Could not extract name from file name: {file_name}")
                updated_values.append(["ERROR", "Invalid name", link])
                continue

            print(student_name)

            first_name = student_name[0]
            last_name = student_name[1]

            updated_values.append([first_name, last_name, link])
            print(f"   + Processed: {first_name} {last_name}")

        except HttpError as error:
            print(f"An error occurred while processing link {link}: {error}")
            updated_values.append(["ERROR", "API error", link])
            continue
        except Exception as e:
            print(f"An unexpected error occurred while processing link {link}: {e}")
            updated_values.append(["ERROR", "Unexpected error", link])
            continue

    print("Updating spreadsheet with processed data...")
    try:
        # Clear existing data in the sheet in case of fewer rows
        sheets_service.spreadsheets().values().clear(
            spreadsheetId=SPREADSHEET_ID,
            range=SHEET_RANGE
        ).execute()

        # Write new data to the sheet
        result = sheets_service.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=SHEET_RANGE,
            valueInputOption="RAW",
            body={"values": updated_values}
        ).execute()
        print(f"Spreadsheet updated with {result.get('updatedRows')} rows.")
    except HttpError as error:
        print(f"An error occurred while updating the spreadsheet: {error}")



"""---------- Helper Functions ----------"""

def create_folder(drive_service, folder_name):
    folder_metadata = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder"
    }
    folder = drive_service.files().create(body=folder_metadata, fields="id").execute()
    return folder.get("id")


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

def clean_filename(filename):
    """Removes characters that are invalid in Windows/Mac/Linux filenames."""
    # Remove the extension and invalid characters
    name_without_ext = os.path.splitext(filename)[0]
    sanitized_name = re.sub(r'[\\/*?:"<>|]', "", name_without_ext)
    return f"{sanitized_name}.pdf"


def extract_file_id(link):
    """
    Extracts the Google Drive file ID from various link formats.
    """
    # This single regex checks for 'file/d/', 'open?id=', or 'uc?id='
    # and then captures the long ID string that follows.
    match = re.search(r"(?:file\/d\/|open\?id=|uc\?id=)([a-zA-Z0-9-_]+)", link)

    if match:
        return match.group(1)  # Return the captured ID
    else:
        print(f"  - Could not find ID in link: {link}")
        return None

def extract_student_name(text):
    try:
        #print("Original Text:" + text)

        # Replace all spaces with underscores for easier processing
        text = text.replace(" ", "_")

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


        name_parts = result.split("_")
        firstname = name_parts[0]
        lastname = " ".join(name_parts[1:])

        #print("Final Result:" + firstname + " " + lastname)
        return [firstname, lastname]
    except IndexError as error:
        print(f"Error extracting name from text: {error}")
        return None
    except Exception as e:
        print(f"Unexpected error extracting name: {e}")
        return None



if __name__ == "__main__":
    main()
