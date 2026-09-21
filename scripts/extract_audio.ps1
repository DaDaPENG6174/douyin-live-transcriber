param(
    [Parameter(Mandatory = $true)]
    [string]$InputVideo,

    [string]$OutputRoot = "output",

    [string]$FfmpegBin = ""
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $InputVideo -PathType Leaf)) {
    throw "Input video not found: $InputVideo"
}

$ffmpegPath = ""
$ffprobePath = ""
if ($FfmpegBin) {
    $ffmpegPath = Join-Path $FfmpegBin "ffmpeg.exe"
    $ffprobePath = Join-Path $FfmpegBin "ffprobe.exe"
} else {
    $ffmpeg = Get-Command ffmpeg -ErrorAction SilentlyContinue
    $ffprobe = Get-Command ffprobe -ErrorAction SilentlyContinue
    if ($ffmpeg) { $ffmpegPath = $ffmpeg.Source }
    if ($ffprobe) { $ffprobePath = $ffprobe.Source }
}

if (-not (Test-Path -LiteralPath $ffmpegPath -PathType Leaf)) {
    throw "ffmpeg.exe was not found. Use -FfmpegBin to provide the bin folder."
}
if (-not (Test-Path -LiteralPath $ffprobePath -PathType Leaf)) {
    throw "ffprobe.exe was not found. Use -FfmpegBin to provide the bin folder."
}

$inputFile = Get-Item -LiteralPath $InputVideo
$jobName = [IO.Path]::GetFileNameWithoutExtension($inputFile.Name)
$jobDir = Join-Path (Join-Path $PSScriptRoot "..\$OutputRoot") $jobName
$audioDir = Join-Path $jobDir "audio"
$metaDir = Join-Path $jobDir "metadata"

New-Item -ItemType Directory -Force -Path $audioDir, $metaDir | Out-Null

$audioPath = Join-Path $audioDir "normalized.wav"
$metadataPath = Join-Path $metaDir "media.json"

& $ffmpegPath -y -i $inputFile.FullName -vn -ac 1 -ar 16000 -c:a pcm_s16le $audioPath
if ($LASTEXITCODE -ne 0) {
    throw "Audio extraction failed. ffmpeg exit code: $LASTEXITCODE"
}

& $ffprobePath -v quiet -print_format json -show_format -show_streams $inputFile.FullName | Set-Content -Encoding UTF8 -LiteralPath $metadataPath
if ($LASTEXITCODE -ne 0) {
    throw "Media metadata extraction failed. The recording may be damaged."
}

Write-Host "Audio generated: $audioPath"
Write-Host "Metadata generated: $metadataPath"
