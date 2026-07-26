$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$out = Join-Path $root "media\demo_draft"
$ffmpeg = Join-Path $root "tools\video-tools\node_modules\ffmpeg-static\ffmpeg.exe"
$video = Join-Path $out "obol_demo_recorded_v5.mp4"
$ffmpegLog = Join-Path $out "obol_demo_recorded_v5_ffmpeg.log"
$ffmpegOut = Join-Path $out "obol_demo_recorded_v5_ffmpeg.out.log"
$edge = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
if (-not (Test-Path $edge)) {
  $edge = "C:\Program Files\Google\Chrome\Application\chrome.exe"
}

$runId = "4"
$base = "http://localhost:5001/"
$scenes = @(
  @{ name = "Overview"; url = "$base?scene=home&v=20260624-31"; seconds = 12 },
  @{ name = "Agent setup"; url = "$base?scene=console-setup&v=20260624-31"; seconds = 10 },
  @{ name = "Agent pending"; url = "$base?scene=console-pending&v=20260624-31"; seconds = 10 },
  @{ name = "Agent success"; url = "$base?scene=console-success&run=$runId&v=20260624-31"; seconds = 12 },
  @{ name = "Agent decisions"; url = "$base?scene=decision-log&run=$runId&v=20260624-31"; seconds = 12 },
  @{ name = "Marketplace"; url = "$base?scene=market&v=20260624-31"; seconds = 12 },
  @{ name = "Creators"; url = "$base?scene=creators&v=20260624-31"; seconds = 12 },
  @{ name = "x402"; url = "$base?scene=x402&v=20260624-31"; seconds = 12 },
  @{ name = "Traction"; url = "$base?scene=traction&v=20260624-31"; seconds = 14 },
  @{ name = "Close"; url = "$base?scene=home&v=20260624-31"; seconds = 10 }
)

$profile = Join-Path $out "screen-record-profile"
New-Item -ItemType Directory -Force -Path $profile | Out-Null

Get-Process msedge,chrome -ErrorAction SilentlyContinue | Where-Object {
  $_.Path -eq $edge
} | Stop-Process -Force -ErrorAction SilentlyContinue

$firstUrl = $scenes[0].url
$browserArgs = @(
  "--app=$firstUrl",
  "--window-size=1600,900",
  "--window-position=0,0",
  "--force-device-scale-factor=1",
  "--disable-translate",
  "--disable-features=Translate,TranslateUI",
  "--lang=en-US",
  "--no-first-run",
  "--no-default-browser-check",
  "--user-data-dir=$profile"
)

$browser = Start-Process -FilePath $edge -ArgumentList $browserArgs -PassThru
Start-Sleep -Seconds 5

$duration = (($scenes | ForEach-Object { [int]$_['seconds'] }) | Measure-Object -Sum).Sum + 6
$ffmpegArgs = @(
  "-y",
  "-f", "gdigrab",
  "-framerate", "30",
  "-offset_x", "0",
  "-offset_y", "0",
  "-video_size", "1600x900",
  "-i", "desktop",
  "-t", "$duration",
  "-c:v", "libx264",
  "-preset", "veryfast",
  "-pix_fmt", "yuv420p",
  $video
)

if (Test-Path $ffmpegLog) { Remove-Item $ffmpegLog -Force }
if (Test-Path $ffmpegOut) { Remove-Item $ffmpegOut -Force }
$recorder = Start-Process -FilePath $ffmpeg -ArgumentList $ffmpegArgs -PassThru -RedirectStandardError $ffmpegLog -RedirectStandardOutput $ffmpegOut
Start-Sleep -Seconds 2

foreach ($scene in $scenes) {
  Write-Host ("scene: " + $scene.name)
  $args = @(
    "--app=$($scene.url)",
    "--window-size=1600,900",
    "--window-position=0,0",
    "--force-device-scale-factor=1",
    "--disable-translate",
    "--disable-features=Translate,TranslateUI",
    "--lang=en-US",
    "--no-first-run",
    "--no-default-browser-check",
    "--user-data-dir=$profile"
  )
  Start-Process -FilePath $edge -ArgumentList $args | Out-Null
  Start-Sleep -Seconds ([int]$scene.seconds)
}

Wait-Process -Id $recorder.Id -Timeout ($duration + 30)
Stop-Process -Id $browser.Id -Force -ErrorAction SilentlyContinue
Get-Process msedge,chrome -ErrorAction SilentlyContinue | Where-Object {
  $_.Path -eq $edge
} | Stop-Process -Force -ErrorAction SilentlyContinue
Write-Host "wrote $video"
