$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$out = Join-Path $root "media\demo_draft"
$frames = Join-Path $out "headless_v8_frames"
$ffmpeg = Join-Path $root "tools\video-tools\node_modules\ffmpeg-static\ffmpeg.exe"
$edge = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
if (-not (Test-Path $edge)) {
  $edge = "C:\Program Files\Google\Chrome\Application\chrome.exe"
}

New-Item -ItemType Directory -Force -Path $frames | Out-Null

$runId = "4"
$base = "http://localhost:5001/"
$shots = @(
  @{ name = "01_overview"; url = "${base}#home"; seconds = 10 },
  @{ name = "02_console_setup"; url = "${base}#console-setup"; seconds = 9 },
  @{ name = "03_console_pending"; url = "${base}#console-pending"; seconds = 9 },
  @{ name = "04_console_success"; url = "${base}#console-success/$runId"; seconds = 11 },
  @{ name = "05_decision_log"; url = "${base}#decision-log/$runId"; seconds = 10 },
  @{ name = "06_marketplace"; url = "${base}#market"; seconds = 10 },
  @{ name = "07_creators"; url = "${base}#creators"; seconds = 10 },
  @{ name = "08_x402"; url = "${base}#x402"; seconds = 10 },
  @{ name = "09_traction"; url = "${base}#traction"; seconds = 12 },
  @{ name = "10_proof_close"; url = "${base}#proof"; seconds = 8 }
)

$concat = Join-Path $out "headless_v8_concat.txt"
if (Test-Path $concat) { Remove-Item $concat -Force }

foreach ($shot in $shots) {
  $png = Join-Path $frames ($shot.name + ".png")
  if (Test-Path $png) { Remove-Item $png -Force }
  $edgeArgs = @(
    "--headless=new",
    "--disable-gpu",
    "--hide-scrollbars",
    "--window-size=1600,900",
    "--virtual-time-budget=3500",
    "--screenshot=$png",
    $shot.url
  )
  $edgeLog = Join-Path $frames ($shot.name + ".edge.log")
  Start-Process -FilePath $edge -ArgumentList $edgeArgs -Wait -NoNewWindow -RedirectStandardError $edgeLog | Out-Null

  if (-not (Test-Path $png)) {
    throw "Screenshot failed: $($shot.name)"
  }
  "file 'headless_v8_frames/$($shot.name).png'" | Add-Content -Path $concat -Encoding ASCII
  "duration $($shot.seconds)" | Add-Content -Path $concat -Encoding ASCII
}

$last = Join-Path $frames ($shots[$shots.Count - 1].name + ".png")
"file 'headless_v8_frames/$($shots[$shots.Count - 1].name).png'" | Add-Content -Path $concat -Encoding ASCII

$video = Join-Path $out "obol_demo_headless_v8.mp4"
$log = Join-Path $out "obol_demo_headless_v8_ffmpeg.log"
if (Test-Path $video) { Remove-Item $video -Force }
if (Test-Path $log) { Remove-Item $log -Force }

$ffmpegArgs = @(
  "-y",
  "-f", "concat",
  "-safe", "0",
  "-i", $concat,
  "-vf", "fps=30,format=yuv420p",
  "-c:v", "libx264",
  "-preset", "veryfast",
  "-pix_fmt", "yuv420p",
  $video
)
Start-Process -FilePath $ffmpeg -ArgumentList $ffmpegArgs -Wait -NoNewWindow -RedirectStandardError $log | Out-Null

Get-Item $video | Select-Object FullName, Length, LastWriteTime
