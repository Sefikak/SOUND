Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
folder = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = folder
' SOUNDsetup.bat kendi Python ortamini (.venv) kurar; yoksa sistemdeki pythonw kullanilir
python = "pythonw"
If fso.FileExists(folder & "\.venv\Scripts\pythonw.exe") Then python = """" & folder & "\.venv\Scripts\pythonw.exe"""
shell.Run python & " main.py", 1, False
