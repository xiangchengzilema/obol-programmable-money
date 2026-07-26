Add-Type -AssemblyName System.Drawing

$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$out = Join-Path $root "media\demo_draft"
$shots = Join-Path $out "shots_v5"
$profiles = Join-Path $out "edge-shot-profiles"
$edge = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
if (-not (Test-Path $edge)) {
  $edge = "C:\Program Files\Google\Chrome\Application\chrome.exe"
}

New-Item -ItemType Directory -Force -Path $shots | Out-Null
New-Item -ItemType Directory -Force -Path $profiles | Out-Null

Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win32Rect {
  [DllImport("user32.dll")]
  public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);
  public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
}
"@

$scenes = @(
  @("01_home", "home"),
  @("02_proof", "proof"),
  @("03_console_setup", "console-setup"),
  @("04_console_pending", "console-pending"),
  @("05_console_success", "console-success&run=4"),
  @("06_decision_log", "decision-log&run=4"),
  @("07_marketplace", "market"),
  @("08_creators", "creators"),
  @("09_x402", "x402"),
  @("10_traction", "traction"),
  @("11_close", "home")
)

foreach ($scene in $scenes) {
  $id = $scene[0]
  $sceneParam = $scene[1]
  $url = "http://localhost:5001/?scene=$sceneParam&shot=$id&v=20260624-31"
  $profile = Join-Path $profiles $id
  New-Item -ItemType Directory -Force -Path $profile | Out-Null
  Write-Host "capture $id $url"
  $args = @(
    "--app=$url",
    "--window-size=1600,900",
    "--window-position=0,0",
    "--force-device-scale-factor=1",
    "--no-first-run",
    "--no-default-browser-check",
    "--user-data-dir=$profile"
  )
  $p = Start-Process -FilePath $edge -ArgumentList $args -PassThru
  $handle = [IntPtr]::Zero
  for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Milliseconds 250
    $p.Refresh()
    if ($p.MainWindowHandle -ne 0) {
      $handle = $p.MainWindowHandle
      break
    }
  }
  Start-Sleep -Seconds 6
  $rect = New-Object Win32Rect+RECT
  [Win32Rect]::GetWindowRect($handle, [ref]$rect) | Out-Null
  $w = [Math]::Max(400, $rect.Right - $rect.Left)
  $h = [Math]::Max(300, $rect.Bottom - $rect.Top)
  $bmp = New-Object System.Drawing.Bitmap $w, $h
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.CopyFromScreen($rect.Left, $rect.Top, 0, 0, $bmp.Size)
  $file = Join-Path $shots "$id.jpg"
  $bmp.Save($file, [System.Drawing.Imaging.ImageFormat]::Jpeg)
  $g.Dispose()
  $bmp.Dispose()
  Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
}
