Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
folder = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = folder
' SOUNDsetup.bat kendi Python ortamini (.venv) kurar; yoksa sistemdeki pythonw kullanilir
python = "pythonw"
If fso.FileExists(folder & "\.venv\Scripts\pythonw.exe") Then python = """" & folder & "\.venv\Scripts\pythonw.exe"""
args = ""
For Each a In WScript.Arguments
    args = args & " " & a
Next
' --startup: bilgisayar acilinca baslatildi, pencere kucultulmus acilir
shell.Run python & " main.py" & args, 1, False
