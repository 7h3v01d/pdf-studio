cd src
pyinstaller --onefile --windowed --icon=icon.ico --name="PDF Reader Pro" --add-data "icon.ico;." --exclude-module tensorflow --exclude-module torch --exclude-module matplotlib --exclude-module scipy --exclude-module pandas --exclude-module numpy --exclude-module IPython --exclude-module pygame --exclude-module PIL pdf_reader.py
pause