Add-Type -AssemblyName System.Speech

$root = Resolve-Path (Join-Path $PSScriptRoot "..\..\media\demo_draft")
$segments = Get-Content (Join-Path $root "segments_v5.json") -Raw | ConvertFrom-Json

foreach ($seg in $segments) {
  $out = Join-Path $root ($seg.id + ".wav")
  $synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
  $synth.Rate = -1
  $synth.Volume = 95
  $synth.SetOutputToWaveFile($out)
  $synth.Speak([string]$seg.voice)
  $synth.Dispose()
  Write-Host "wrote $out"
}
