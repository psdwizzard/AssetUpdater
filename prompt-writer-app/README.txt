AssetUpdater Prompt Writer

Open `index.html` in a current Chrome or Edge browser.

What it does:
- Scans the folder you choose in the browser.
- Finds only leaf folders, meaning folders with no subfolders inside them.
- Counts PNG files in those leaf folders.
- Shows each folder's Start Index and End Index using AssetUpdater's sorted PNG scan order.
- Lets you edit the prompt label used for that folder.
- Writes `prompt.txt` into each leaf folder.
- Skips folders that already have `prompt.txt`.

How to use it:
- Click "Choose Root Folder" and pick the asset library root.
- Review the discovered leaf folders and image index ranges.
- Edit the "Prompt Label" values if the prompt should use a cleaner name than the real folder name.
- Edit the prompt template if needed.
- Click "Generate Prompt Files".

Prompt template token:
- Use `[folderName]` where you want the edited prompt label inserted.

Browser requirement:
- This app uses the File System Access API, so it should be opened in Chrome or Edge.
