param(
  [string]$Video = ".\media\demo_draft\obol_demo_playwright_v16_final.mp4",
  [string]$Segments = ".\media\demo_draft\voiceover_v17_segments.json",
  [string]$Out = ".\media\demo_draft\obol_demo_v17_voiceover_draft.mp4"
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Speech

$root = Resolve-Path "."
$ffmpeg = (Resolve-Path ".\tools\video-tools\node_modules\ffmpeg-static\ffmpeg.exe").Path
$work = Join-Path $root "media\demo_draft\v17_voiceover_work"
New-Item -ItemType Directory -Force -Path $work | Out-Null

function Get-MediaDurationSeconds([string]$Path) {
  $output = & $ffmpeg -i $Path 2>&1 | Out-String
  $match = [regex]::Match($output, "Duration:\s*(\d+):(\d+):(\d+\.\d+)")
  if (-not $match.Success) {
    throw "Could not read duration for $Path"
  }
  return ([double]$match.Groups[1].Value * 3600) + ([double]$match.Groups[2].Value * 60) + [double]$match.Groups[3].Value
}

function Get-AtempoChain([double]$Tempo) {
  $parts = New-Object System.Collections.Generic.List[string]
  while ($Tempo -gt 2.0) {
    $parts.Add("atempo=2.0")
    $Tempo = $Tempo / 2.0
  }
  while ($Tempo -lt 0.5) {
    $parts.Add("atempo=0.5")
    $Tempo = $Tempo / 0.5
  }
  $parts.Add(("atempo={0:N5}" -f $Tempo).Replace(",", ""))
  return ($parts -join ",")
}

$synthProbe = New-Object System.Speech.Synthesis.SpeechSynthesizer
$englishVoice = $synthProbe.GetInstalledVoices() |
  Where-Object { $_.VoiceInfo.Culture.Name -like "en-*" } |
  Select-Object -First 1
$voiceName = $null
if ($englishVoice) {
  $voiceName = $englishVoice.VoiceInfo.Name
}
$synthProbe.Dispose()

$items = Get-Content $Segments -Raw -Encoding UTF8 | ConvertFrom-Json
$concatList = Join-Path $work "concat.txt"
Remove-Item $concatList -Force -ErrorAction SilentlyContinue

foreach ($seg in $items) {
  $raw = Join-Path $work ("raw_" + $seg.id + ".wav")
  $fit = Join-Path $work ("fit_" + $seg.id + ".wav")
  $target = [double]$seg.end - [double]$seg.start

  $synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
  if ($voiceName) {
    try {
      $synth.SelectVoice($voiceName)
    } catch {
      Write-Host "Could not select voice '$voiceName'; using default system voice."
    }
  }
  $synth.Rate = 1
  $synth.Volume = 100
  $synth.SetOutputToWaveFile($raw)
  $synth.Speak([string]$seg.text)
  $synth.Dispose()

  $sourceDuration = Get-MediaDurationSeconds $raw
  $tempo = $sourceDuration / $target
  $tempoChain = Get-AtempoChain $tempo
  $filter = "$tempoChain,apad,atrim=0:$target,loudnorm=I=-16:TP=-1.5:LRA=11"

  & $ffmpeg -y -i $raw -filter:a $filter -ar 48000 -ac 2 $fit 2> (Join-Path $work ("ffmpeg_" + $seg.id + ".log")) | Out-Null
  Add-Content -Path $concatList -Value ("file '" + ($fit.Replace("\", "/")) + "'") -Encoding ASCII
  Write-Host ("{0}: source {1:N2}s -> target {2:N2}s" -f $seg.id, $sourceDuration, $target)
}

$voiceWav = Join-Path $root "media\demo_draft\obol_v17_voiceover_draft.wav"
& $ffmpeg -y -f concat -safe 0 -i $concatList -c:a pcm_s16le -ar 48000 -ac 2 $voiceWav 2> (Join-Path $work "concat.log") | Out-Null

& $ffmpeg -y -i $Video -i $voiceWav -map 0:v:0 -map 1:a:0 -c:v copy -c:a aac -b:a 160k -movflags +faststart $Out 2> (Join-Path $work "mux.log") | Out-Null

Write-Host "voice: $voiceWav"
Write-Host "video: $Out"
