Option Explicit
Dim shell, fs, folder, result
Set shell = CreateObject("WScript.Shell")
Set fs = CreateObject("Scripting.FileSystemObject")
folder = fs.GetParentFolderName(WScript.ScriptFullName)
result = shell.Run(Chr(34) & folder & "\calistir.cmd" & Chr(34) & " normal", 0, True)
If result = 9009 Then MsgBox "Python 3.10 veya uzeri ve Tcl/Tk gerekli. Python kurulumunda Add Python to PATH secenegini etkinlestirin.", 48, "Okan Durak"
If result <> 0 And result <> 9009 Then MsgBox "Uygulama baslatilamadi. Ayrintilar: %LOCALAPPDATA%\OkanDurak\launcher.log", 48, "Okan Durak"
