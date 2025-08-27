# gemini-batch-pdfs
## Description
This program leverages both the Google generative language API as well as the google drive API to access all files within a google drive folder and upload them to gemini along with a custom prompt. This allows for mass analysis of many files given just a drive folder ID.

## Setup
To begin, you will first need a Google Gemini API key, which you can obtain for free [here](https://aistudio.google.com/app/apikey) (note that your usage will be limited on the free tier as per Google's policy, but it should be more than enough for personal use).

Once you have your key, save it as an envoirnment variable named 'GEMINI_API_KEY' exactly. You can do that with this command in your terminal:

`$env:GEMINI_API_KEY:"your key here"`


After you have your API key set up, you'll need to configure an OAuth screen to verify your Google Drive account. First, go to [Google Cloud](console.cloud.google.com) and create a new project (or use the one that you created when getting your API key). Then, enable the Google Drive API under APIs and Services.

Then navigate to APIs & Services -> OAuth consent screen, and click 'get started.'

Set user type to 'external' and fill in the required fields.

Once you're done, go to APIs & Services -> Credentials and click 'Create Credentials', then 'OAuth client ID.' Select 'desktop app,' name it, and it'll give you a download button. Download that JSON file and save it as 'credentials.json' into the root folder of your cloned repo.

Before you can authenticate yourself, you need to go back to the OAuth consent screen section and click 'test users,' 'add users,' then add your own email adress. Click save and you're done.

The first time you run the script, you'll be taken to your browser and asked to authenticate your account. You won't have to do this again after that.

## Usage

In the script, edit the FOLDER_ID constant to be the ID of the folder you want to analyze (the string of numbers and letters at the end of a google drive link). Edit the prompt to be what you want, and then run through the terminal. Note that the script is set to only work on PDFs. The script is currently set to use gemini 2.5 pro, but this can be changed as well with the `GEMINI_MODEL` constant.

Gemini will proceed to process the files one by one, and once finished, save each response into a file called responses.json. The program can also have gemini turn each of its outputs into a PDF. This feature can be turned on/off using the CONVERT_TO_PDF constant (set to true by default). You can also specifiy the path to store output files to.
