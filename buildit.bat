cd src
pyinstaller --onefile --windowed --icon=icon.ico --name="PDF Reader Pro" --add-data "icon.ico;." pdf_reader.py
pause