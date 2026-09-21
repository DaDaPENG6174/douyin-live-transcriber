Option Explicit

Dim shell, fso, projectDir, pythonw, gui, ffmpeg, ffprobe, command
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

projectDir = fso.GetParentFolderName(WScript.ScriptFullName)
pythonw = projectDir & "\.venv\Scripts\pythonw.exe"
gui = projectDir & "\scripts\watcher_gui.py"
ffmpeg = "C:\ffmpeg\ffmpeg-9.0.1-essentials_build\bin\ffmpeg.exe"
ffprobe = "C:\ffmpeg\ffmpeg-9.0.1-essentials_build\bin\ffprobe.exe"

If Not fso.FileExists(pythonw) Then
    MsgBox "Python environment not found:" & vbCrLf & pythonw, vbCritical, "Startup failed"
    WScript.Quit 1
End If

If Not fso.FileExists(gui) Then
    MsgBox "Dashboard script not found:" & vbCrLf & gui, vbCritical, "Startup failed"
    WScript.Quit 1
End If

If Not fso.FileExists(ffmpeg) Or Not fso.FileExists(ffprobe) Then
    MsgBox "FFmpeg tools not found:" & vbCrLf & ffmpeg & vbCrLf & ffprobe, vbCritical, "Startup failed"
    WScript.Quit 1
End If

shell.CurrentDirectory = projectDir
command = Chr(34) & pythonw & Chr(34) & " " & Chr(34) & gui & Chr(34) & " --device cuda:0 --ffmpeg " & Chr(34) & ffmpeg & Chr(34) & " --ffprobe " & Chr(34) & ffprobe & Chr(34) & " --track-labels " & Chr(34) & "主播,连线嘉宾" & Chr(34)
shell.Run command, 0, False
