"""
register_file_types.py
-----------------------
Associate PDF Studio with document types on Windows — per-user, no admin
rights required (everything lives under HKEY_CURRENT_USER).

What it does
------------
* Creates a ProgID ("PDFStudio.Document") whose shell\\open\\command launches
  PDF Studio with the file path.
* Adds that ProgID to each extension's OpenWithProgids list, so PDF Studio
  appears in Explorer's "Open with" menu and in Windows "Default apps".

What it deliberately does NOT do
--------------------------------
Windows 10/11 protect the *default* handler with an encrypted per-user choice
(UserChoice) specifically so apps can't silently hijack file types. So this
tool makes PDF Studio a valid, listed choice; the user then confirms it as the
default once — either via the "Open with" dialog ("Always use this app") or via
the Default apps settings page this tool opens for them.

Usage
-----
    python register_file_types.py                 # register .pdf + Word + Excel
    python register_file_types.py --pdf-only      # register .pdf only
    python register_file_types.py --unregister    # remove associations

(Or, with the built app:  "PDF Studio.exe" --register  /  --unregister)
"""
import os
import sys

PROGID = "PDFStudio.Document"
PDF_EXT = ".pdf"
WORD_EXTS = (".docx", ".doc", ".rtf", ".odt")
EXCEL_EXTS = (".xlsx", ".xls", ".ods")

_CLASSES = r"Software\Classes"


def _launch_command():
    """Return (command_string_with_%1, icon_path, icon_index)."""
    if getattr(sys, "frozen", False):
        exe = sys.executable
        return f'"{exe}" "%1"', exe, 0
    # Running from source: use pythonw.exe so no console window flashes.
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.exists(pyw):
        pyw = sys.executable
    here = os.path.dirname(os.path.abspath(__file__))
    script = os.path.join(here, "pdf_reader.py")
    icon = os.path.join(here, "icon.ico")
    return f'"{pyw}" "{script}" "%1"', icon, 0


def register(pdf_only: bool = False):
    """Register the ProgID and associate extensions. Returns the ext list."""
    import winreg

    cmd, icon_path, icon_idx = _launch_command()

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _CLASSES + "\\" + PROGID) as k:
        winreg.SetValueEx(k, "", 0, winreg.REG_SZ, "PDF Document")
        winreg.SetValueEx(k, "FriendlyTypeName", 0, winreg.REG_SZ, "PDF Document")
    with winreg.CreateKey(
        winreg.HKEY_CURRENT_USER, _CLASSES + "\\" + PROGID + r"\DefaultIcon"
    ) as k:
        winreg.SetValueEx(k, "", 0, winreg.REG_SZ, f'"{icon_path}",{icon_idx}')
    with winreg.CreateKey(
        winreg.HKEY_CURRENT_USER, _CLASSES + "\\" + PROGID + r"\shell\open\command"
    ) as k:
        winreg.SetValueEx(k, "", 0, winreg.REG_SZ, cmd)

    exts = [PDF_EXT] if pdf_only else [PDF_EXT, *WORD_EXTS, *EXCEL_EXTS]
    for ext in exts:
        with winreg.CreateKey(
            winreg.HKEY_CURRENT_USER, _CLASSES + "\\" + ext + r"\OpenWithProgids"
        ) as k:
            winreg.SetValueEx(k, PROGID, 0, winreg.REG_NONE, b"")

    _notify_shell()
    return exts


def unregister():
    """Remove the ProgID and all OpenWithProgids entries pointing at it."""
    import winreg

    for ext in [PDF_EXT, *WORD_EXTS, *EXCEL_EXTS]:
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                _CLASSES + "\\" + ext + r"\OpenWithProgids",
                0, winreg.KEY_SET_VALUE,
            ) as k:
                winreg.DeleteValue(k, PROGID)
        except FileNotFoundError:
            pass
    _delete_tree(winreg.HKEY_CURRENT_USER, _CLASSES + "\\" + PROGID)
    _notify_shell()


def _delete_tree(root, path):
    import winreg
    try:
        with winreg.OpenKey(root, path, 0, winreg.KEY_ALL_ACCESS) as k:
            while True:
                try:
                    sub = winreg.EnumKey(k, 0)
                except OSError:
                    break
                _delete_tree(root, path + "\\" + sub)
        winreg.DeleteKey(root, path)
    except FileNotFoundError:
        pass


def _notify_shell():
    """Tell Explorer that file associations changed."""
    try:
        import ctypes
        SHCNE_ASSOCCHANGED = 0x08000000
        SHCNF_IDLIST = 0x0000
        ctypes.windll.shell32.SHChangeNotify(
            SHCNE_ASSOCCHANGED, SHCNF_IDLIST, None, None)
    except Exception:
        pass


def open_default_apps_settings():
    """Open Windows 'Default apps' so the user can confirm PDF Studio."""
    try:
        os.startfile("ms-settings:defaultapps")
    except Exception:
        pass


if __name__ == "__main__":
    if sys.platform != "win32":
        print("This registration tool only runs on Windows.")
        sys.exit(1)
    if "--unregister" in sys.argv:
        unregister()
        print("PDF Studio file associations removed.")
    else:
        registered = register(pdf_only="--pdf-only" in sys.argv)
        print("Registered PDF Studio for:", ", ".join(registered))
        print("\nWindows requires you to confirm the default once — "
              "opening Default apps settings now.")
        open_default_apps_settings()
