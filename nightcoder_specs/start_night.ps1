<#
  start_night.ps1 - one command to queue tonight's specs for NightCoder and start it.

  Usage (from anywhere):
    powershell -ExecutionPolicy Bypass -File C:\myLectureWs\python-memvid-guardrail\nightcoder_specs\start_night.ps1
  Options:
    -Specs "rra-p1-*.md","rra-p3-*.md"   which spec files from this folder (default: all rra-*.md, alphabetical)
    -StopAt 08:30                         when NightCoder must stop
    -DryRun                               check everything, start nothing
    -ScreenOff                            turn the display off after starting (the PC stays awake)

  What it does, in order (it stops at the first problem and tells you why):
    1. repo on main, clean, pulled           4. writes the lane config from nc2.rra.template.json
    2. full test suite: must be 0 failures   5. NightCoder dry run (shows the queue)
    3. copies specs to the inbox as 001-, 002-, ... (drops the after: line; order = number)
    6. asks once, then starts NightCoder (sleep is disabled while plugged in)
#>
param(
  [string]$Repo = "C:\myLectureWs\python-memvid-guardrail",
  [string]$NightCoder = "C:\myLectureWs\nightcoder-r9-stage\nc2.py",
  [string]$Work = "C:\Users\Codelab\nc2-rra",
  [string[]]$Specs = @("rra-*.md"),
  [string]$StopAt = "08:30",
  [switch]$DryRun,
  [switch]$ScreenOff
)
$ErrorActionPreference = "Stop"
function Step($n, $msg) { Write-Host "`n[$n] $msg" -ForegroundColor Cyan }
function Fail($msg) { Write-Host "STOP: $msg" -ForegroundColor Red; exit 1 }

Step 1 "repository: main, clean, up to date"
if (-not (Test-Path "$Repo\.git")) { Fail "no git repository at $Repo" }
Set-Location $Repo
git checkout main | Out-Null
git pull --ff-only
if ($LASTEXITCODE -ne 0) { Fail "git pull failed (local changes or diverged main)" }
$dirty = git status --porcelain
if ($dirty) { Write-Host $dirty; Fail "working tree is not clean. Commit or move these files first (or add them to .git\info\exclude)." }
Write-Host ("main = " + (git log --oneline -1))

Step 2 "test baseline (NightCoder re-runs this after every spec, so it must be green now)"
$py = "$Repo\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { Fail "virtual environment not found: $py" }
& $py -m pytest -q -p no:cacheprovider
if ($LASTEXITCODE -ne 0) { Fail "tests are not green. Do not start the night run; send the output to Claude." }

Step 3 "queue specs into $Work\inbox"
$inbox = Join-Path $Work "inbox"
New-Item -ItemType Directory -Force $inbox, (Join-Path $Work "outbox"), (Join-Path $Work "state") | Out-Null
$left = Get-ChildItem $inbox -Filter *.md -File
if ($left) { Write-Host "already queued:"; $left | ForEach-Object { Write-Host "  $($_.Name)" }
  $ans = Read-Host "replace them with tonight's specs? (y/N)"; if ($ans -ne "y") { Fail "kept the existing queue; nothing changed" }
  $left | Remove-Item -Force }
$files = foreach ($pattern in $Specs) { Get-ChildItem (Join-Path $PSScriptRoot $pattern) -File }
$files = $files | Sort-Object Name -Unique
if (-not $files) { Fail "no spec files match $($Specs -join ', ') in $PSScriptRoot" }
$utf8 = New-Object System.Text.UTF8Encoding $false
$i = 0
foreach ($f in $files) {
  $i++
  $name = "{0:D3}-{1}" -f $i, $f.Name
  $lines = Get-Content $f.FullName -Encoding UTF8 | Where-Object { $_ -notmatch '^after:' }
  [IO.File]::WriteAllLines((Join-Path $inbox $name), $lines, $utf8)
  Write-Host "  queued $name"
}

Step 4 "lane config"
$template = Join-Path $PSScriptRoot "nc2.rra.template.json"
$config = Join-Path $Work "nc2.rra.json"
$text = (Get-Content $template -Raw -Encoding UTF8).Replace("__REPO__", ($Repo -replace '\\','/')).Replace("__WORK__", ($Work -replace '\\','/'))
[IO.File]::WriteAllText($config, $text, $utf8)
Write-Host "  $config"

Step 5 "NightCoder dry run"
if (-not (Test-Path $NightCoder)) { Fail "nc2.py not found: $NightCoder (use -NightCoder <path>)" }
python $NightCoder --config $config --dry-run --stop-at $StopAt
if ($LASTEXITCODE -ne 0) { Fail "dry run failed" }
if ($DryRun) { Write-Host "`nDry run only. Nothing started." -ForegroundColor Yellow; exit 0 }

Step 6 "start"
$ans = Read-Host "Start NightCoder now until $StopAt? (y/N)"
if ($ans -ne "y") { Fail "not started" }
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
Write-Host "sleep disabled while plugged in. Restore later: powercfg /change standby-timeout-ac 30"
if ($ScreenOff) {
  Start-Job { Start-Sleep 20; (Add-Type '[DllImport("user32.dll")]public static extern int SendMessage(int hWnd,int hMsg,int wParam,int lParam);' -Name ScreenOff -Namespace Win32 -PassThru)::SendMessage(-1,0x0112,0xF170,2) } | Out-Null
  Write-Host "the display turns off in 20 seconds (any key or mouse move turns it back on)"
}
Write-Host "results: $Work\outbox\<task>\REPORT.md   - keep this window open" -ForegroundColor Green
python $NightCoder --config $config --stop-at $StopAt
