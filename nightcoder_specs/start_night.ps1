<#
  start_night.ps1 (v2) - start a NightCoder lane in one command, safely.

  Default: the Codex lane in C:\work\rra-codex with every spec from nightcoder_specs\ in backlog order.
    powershell -ExecutionPolicy Bypass -File C:\work\rra-codex\nightcoder_specs\start_night.ps1 -ScreenOff

  What it does (stops at the first problem, prints the cause and the fix):
    1. lane folder: exists, fetches main, puts the lane branch on top of main, clean tree
    2. tests: the full suite must be green (NightCoder re-runs it after every spec)
    3. coder CLI: finds the right sandbox flag for this Codex version (--full-auto was removed)
    4. lane config: built from the base config (your working codex_cmd) + this lane's paths
    5. SMOKE: a 1-2 minute spec (edit one file + commit) through NightCoder itself.
       Only if it produced a patch does the real queue start. (Catches missing config,
       wrong branch, removed CLI flags and "coder cannot commit" before the night starts.)
    6. queue: specs in backlog order, skipping specs whose report already exists on main
    7. start with --yes (remembered answers from the smoke run), sleep off, optional screen off

  Options: -DryRun (stop after step 4), -SkipSmoke, -Only "rra-c5*","rra-c6*", -StopAt 08:30,
           -Sandbox auto|workspace-write|full-auto (auto = detect), -ScreenOff
#>
param(
  [string]$Lane = "C:\work\rra-codex",
  [string]$Branch = "nc/rra-codex",
  [string]$NightCoder = "C:\myLectureWs\nightcoder-r9-stage\nc2.py",
  [string]$BaseConfig = "C:\Users\Codelab\tonight\nc2.refactor.json",
  [string]$Work = "C:\Users\Codelab\nc2-rra-codex",
  [string]$Python = "C:\myLectureWs\python-memvid-guardrail\.venv\Scripts\python.exe",
  [string]$SysPython = "python",
  [string[]]$Only = @(),
  [string]$StopAt = "08:30",
  [ValidateSet("auto","workspace-write","full-auto")][string]$Sandbox = "auto",
  [switch]$DryRun,
  [switch]$SkipSmoke,
  [switch]$ScreenOff,
  [switch]$NoStart,
  [switch]$Supervise,
  [int]$MaxRestarts = 12,
  [switch]$Relaunched
)
$SelfPath = $PSCommandPath
$SelfHash = if ($SelfPath) { (Get-FileHash $SelfPath -Algorithm SHA256).Hash } else { "" }
$ErrorActionPreference = "Continue"   # native tools write to stderr; we judge by exit codes only
$utf8 = New-Object System.Text.UTF8Encoding $false
function Step($n, $msg) { Write-Host "`n[$n] $msg" -ForegroundColor Cyan }
function Fail($msg, $fix) { Write-Host "STOP: $msg" -ForegroundColor Red; if ($fix) { Write-Host "FIX:  $fix" -ForegroundColor Yellow }; exit 1 }
function Ok($msg) { Write-Host "  ok  $msg" -ForegroundColor Green }

# backlog order (README table); smoke is separate
$Order = @("rra-p1-cli-inputs","rra-p3-lint","rra-p2-graph",
  "codex/rra-c1-causal-links","codex/rra-c2-golden-maker","codex/rra-c3-sentence-split","codex/rra-c4-embedding-relevance",
  "codex/rra-c5-store-stability","codex/rra-c6-library-incremental","codex/rra-c7-number-table","codex/rra-c8-wire-links-relevance",
  "codex/rra-c9-board-diff","codex/rra-c10-prediction-log","codex/rra-c11-cue-suggester","codex/rra-c12-real-embedders",
  "codex/rra-c13-embedder-compare","codex/rra-c14-kiwi-lab","codex/rra-c16-guard-adapter-research","codex/rra-c17-golden-v2-tooling",
  "codex/rra-p2b-graph-stages","codex/rra-e1-langchain-exits","codex/rra-e2-retry-loop","codex/rra-e3-langsmith-export",
  "codex/rra-f1-research-command","codex/rra-f2-memvid-writer","codex/rra-f3-dashboard-hub","codex/rra-f4-tune-workflow",
  "codex/rra-f5-auto-causal-class","codex/rra-f6-number-charts","codex/rra-f8-predict-from-brief")
# f7 (CI) touches .github, which NightCoder forbids: daytime Codex only
# c15 runs in the legal-intake repo, never in this lane

Step 1 "lane folder and branch"
if (-not (Test-Path "$Lane\.git")) {
  git clone https://github.com/ai-agent-orchestrator/langchain-rag-research-agent $Lane
  if ($LASTEXITCODE -ne 0) { Fail "clone failed" "check the network, then run again" }
}
Set-Location $Lane
$dirtyNow = git -C $Lane status --porcelain
if ($dirtyNow) { git -C $Lane status --short; Fail "lane folder has uncommitted changes" "git -C $Lane stash push -u -m before-night   (or delete the files listed above)" }
git fetch origin main --quiet
if ($LASTEXITCODE -ne 0) { Fail "git fetch failed" "check the network" }
$Stamp = Get-Date -Format "yyyyMMdd-HHmm"
# keep last night's work: archive the lane branch if it has commits that are not on main yet
$exists = git rev-parse --verify --quiet "refs/heads/$Branch"
if ($exists) {
  $ahead = git rev-list --count "origin/main..$Branch"
  if ([int]$ahead -gt 0) { git branch -f "nc/archive/$Stamp" $Branch | Out-Null; Ok "archived $ahead commit(s) of $Branch as nc/archive/$Stamp" }
}
git checkout -B $Branch origin/main --quiet
if ($LASTEXITCODE -ne 0) { Fail "could not put $Branch on origin/main" "" }
# self-update: if this run just pulled a newer version of this very script, restart with it
if (-not $Relaunched -and $SelfPath -and (Test-Path $SelfPath)) {
  $newHash = (Get-FileHash $SelfPath -Algorithm SHA256).Hash
  if ($newHash -ne $SelfHash) {
    Write-Host "  start script was updated on main; restarting with the new version..." -ForegroundColor Yellow
    $hostExe = (Get-Process -Id $PID).Path
    $argsList = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $SelfPath, "-Relaunched")
    foreach ($k in $PSBoundParameters.Keys) {
      $v = $PSBoundParameters[$k]
      if ($v -is [System.Management.Automation.SwitchParameter]) { if ($v.IsPresent) { $argsList += "-$k" } }
      elseif ($v -is [array]) { $argsList += "-$k"; $argsList += ($v -join ",") }
      else { $argsList += "-$k"; $argsList += "$v" }
    }
    if ($args.Count -gt 0) { $argsList += $args }   # options this older copy did not know (added in newer versions)
    & $hostExe @argsList
    exit $LASTEXITCODE
  }
}
# reaching here means no self-update restart: leftover arguments are typos, not newer options
if ($args.Count -gt 0) { Fail "unknown option(s): $($args -join ' ')" "check the spelling; options are listed at the top of start_night.ps1" }
Ok ("$Branch = " + (git log --oneline -1))

Step 2 "test baseline"
if (-not (Test-Path $Python)) { Fail "python not found: $Python" "pass -Python <path to a venv python with the test deps>" }
& $Python -m pytest -q -p no:cacheprovider
if ($LASTEXITCODE -ne 0) {
  Write-Host "  retrying once (Windows file locks cause rare one-off failures)..." -ForegroundColor Yellow
  & $Python -m pytest -q -p no:cacheprovider
  if ($LASTEXITCODE -ne 0) { Fail "tests are not green twice in a row" "send the output above to Claude; do not start the night" }
}
Ok "tests green"

Step 3 "coder CLI"
$codex = Get-Command codex -ErrorAction SilentlyContinue
if (-not $codex) { Fail "codex CLI not found" "install/login Codex CLI, then run again" }
$help = (& codex exec --help 2>&1 | Out-String)
$flags = @()
if ($Sandbox -eq "full-auto" -or ($Sandbox -eq "auto" -and $help -match "--full-auto")) { $flags = @("--full-auto") }
elseif ($help -match "--sandbox") { $flags = @("--sandbox","workspace-write") }
else { Fail "this codex exec has neither --full-auto nor --sandbox" "run 'codex exec --help' and send it to Claude" }
Ok ("sandbox flags: " + ($flags -join " "))

Step 4 "lane config"
if (-not (Test-Path $BaseConfig)) { Fail "base config not found: $BaseConfig" "pass -BaseConfig <a nc2 json whose codex_cmd works>" }
$cfg = Get-Content $BaseConfig -Raw -Encoding UTF8 | ConvertFrom-Json
$cmd = @()
foreach ($a in $cfg.codex_cmd) { if ($a -in @("--full-auto","--sandbox","workspace-write","danger-full-access","read-only")) { continue }; $cmd += $a }
# put the sandbox flags right after 'exec' (or after the program name)
$i = [Array]::IndexOf($cmd, "exec"); if ($i -lt 0) { $i = 0 }
$cmd = @($cmd[0..$i]) + $flags + $(if ($cmd.Count -gt $i + 1) { @($cmd[($i + 1)..($cmd.Count - 1)]) } else { @() })
$wrap = Join-Path $Lane "nightcoder_specs\codex_wrap.py"
if (-not (Test-Path $wrap)) { Fail "codex_wrap.py not found in the lane" "the lane is not on a recent main; run again after git fetch" }
$wrapLog = Join-Path $Work "wrap.log"
$wrapped = @($SysPython, ($wrap -replace '\\','/'), "--repo", ($Lane -replace '\\','/'), "--log", ($wrapLog -replace '\\','/'), "--") + $cmd
function LaneConfig($inbox, $outbox, $state, $maxTasks) {
  $c = $cfg | ConvertTo-Json -Depth 8 | ConvertFrom-Json
  $c | Add-Member -Force NoteProperty _note "RRA codex lane (generated by start_night.ps1 v2)"
  $c.workdir = ($Lane -replace '\\','/'); $c.branch = $Branch; $c.base = "main"
  $c.inbox = ($inbox -replace '\\','/'); $c.outbox = ($outbox -replace '\\','/'); $c.state_dir = ($state -replace '\\','/')
  $c.test_cmd = @(($Python -replace '\\','/'), "-m", "pytest", "-q", "-p", "no:cacheprovider")
  $c.codex_cmd = $wrapped; $c.max_tasks = $maxTasks
  if ($c.PSObject.Properties.Name -contains "codex_timeout_min") { $c.codex_timeout_min = 90 }
  return $c
}
# every run gets its own dated result folder: nothing is overwritten, nothing to name by hand
$Run = Join-Path (Join-Path $Work "runs") $Stamp
New-Item -ItemType Directory -Force "$Work\inbox","$Run\outbox","$Work\state","$Work\smoke\inbox","$Run\smoke-outbox" | Out-Null
$mainCfg = Join-Path $Run "nc2.lane.json"; $smokeCfg = Join-Path $Run "nc2.smoke.json"
[IO.File]::WriteAllText($mainCfg, ((LaneConfig "$Work\inbox" "$Run\outbox" "$Work\state" 30) | ConvertTo-Json -Depth 8), $utf8)
[IO.File]::WriteAllText($smokeCfg, ((LaneConfig "$Work\smoke\inbox" "$Run\smoke-outbox" "$Work\state" 1) | ConvertTo-Json -Depth 8), $utf8)
Ok "codex_cmd: $($wrapped -join ' ')"
Ok $mainCfg
if ($DryRun) { Write-Host "`nDry run: stopped before the smoke run." -ForegroundColor Yellow; exit 0 }

if (-not $SkipSmoke) {
  Step 5 "smoke run through NightCoder (1-2 min)"
  Get-ChildItem "$Work\smoke\inbox" -File -ErrorAction SilentlyContinue | Remove-Item -Force
  Copy-Item "$Lane\nightcoder_specs\smoke\rra-smoke.md" "$Work\smoke\inbox\000-rra-smoke.md"
  Write-Host "  NightCoder asks its start questions now (same state folder as the real run, so --yes can reuse them)." -ForegroundColor Yellow
  & $SysPython $NightCoder --config $smokeCfg --stop-at ((Get-Date).AddMinutes(20).ToString("HH:mm"))
  $patches = Get-ChildItem "$Run\smoke-outbox" -Recurse -Filter *.patch -ErrorAction SilentlyContinue
  if (-not $patches) {
    $report = Get-ChildItem "$Run\smoke-outbox" -Recurse -Filter REPORT.md -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($report) { Write-Host "---- smoke REPORT (last 25 lines) ----"; Get-Content $report.FullName -Encoding UTF8 -Tail 25 }
    if (Test-Path $wrapLog) { Write-Host "---- wrap.log (last 3) ----"; Get-Content $wrapLog -Tail 3 }
    $hint = "send the REPORT and wrap.log lines above to Claude (wrap.log shows the coder exit code and whether anything changed)"
    Fail "smoke run produced no patch" $hint
  }
  Ok "smoke passed: the coder edited, committed and NightCoder collected a patch"
  git -C $Lane checkout -B $Branch origin/main --quiet   # drop the smoke commit
}

Step 6 "queue"
$Only = @($Only | ForEach-Object { $_ -split ',' } | ForEach-Object { $_.Trim() } | Where-Object { $_ })   # "-Only a,b" arrives as one string via -File
Get-ChildItem "$Work\inbox" -File -Filter *.md -ErrorAction SilentlyContinue | Remove-Item -Force
$n = 0
foreach ($name in $Order) {
  if ($Only.Count -gt 0 -and -not ($Only | Where-Object { (Split-Path $name -Leaf) -like $_ })) { continue }
  $src = Join-Path "$Lane\nightcoder_specs" ($name + ".md")
  if (-not (Test-Path $src)) { Write-Host "  skip (missing) $name"; continue }
  $lines = Get-Content $src -Encoding UTF8
  $filesLine = ($lines | Where-Object { $_ -match '^files:' } | Select-Object -First 1)
  $report = if ($filesLine) { ($filesLine -replace '^files:\s*','').Split(',') | ForEach-Object { $_.Trim() } | Where-Object { $_ -match '_REPORT_' } | Select-Object -First 1 }
  if ($report -and (Test-Path (Join-Path $Lane $report))) { Write-Host "  skip (done on main) $name"; continue }
  $n++
  $dest = Join-Path "$Work\inbox" ("{0:D3}-{1}.md" -f $n, (Split-Path $name -Leaf))
  [IO.File]::WriteAllLines($dest, ($lines | Where-Object { $_ -notmatch '^after:' }), $utf8)
  Write-Host "  queued $(Split-Path $dest -Leaf)"
}
if ($n -eq 0) { Fail "nothing to queue" "all specs are done on main, or -Only matched nothing" }

Step 7 "start"
if (Get-Command powercfg -ErrorAction SilentlyContinue) {
  powercfg /change standby-timeout-ac 0
  powercfg /change hibernate-timeout-ac 0
}
if ($ScreenOff -and $IsWindows -ne $false) {
  Start-Job { Start-Sleep 30; (Add-Type '[DllImport("user32.dll")]public static extern int SendMessage(int hWnd,int hMsg,int wParam,int lParam);' -Name ScreenOff -Namespace Win32 -PassThru)::SendMessage(-1,0x0112,0xF170,2) } | Out-Null
  Write-Host "  display turns off in 30 seconds"
}
if ($NoStart) { Set-Content -Path (Join-Path $Work "LATEST.txt") -Value $Run -Encoding UTF8; Write-Host "`n-NoStart: queue ready, NightCoder not started. Run folder: $Run" -ForegroundColor Yellow; exit 0 }
Set-Content -Path (Join-Path $Work "LATEST.txt") -Value $Run -Encoding UTF8
Write-Host "  results: $Run\outbox   (also written to $Work\LATEST.txt; keep this window open)" -ForegroundColor Green
$summarize = Join-Path $Lane "nightcoder_specs\summarize_run.py"
$supLog = Join-Path $Run "supervise.log"
function Log($m) { $line = (Get-Date -Format "yyyy-MM-dd HH:mm") + "  " + $m; Add-Content -Path $supLog -Value $line -Encoding UTF8; Write-Host $line }
function Summarize { & $SysPython $summarize --run $Run --lane $Lane --work $Work | Out-Null; Write-Host "  summary: $Run\SUMMARY.html" -ForegroundColor Green }
# stop time as a DateTime (HH:mm = next occurrence; or full ISO date-time)
$stopTime = if ($StopAt -match '^\d{1,2}:\d{2}$') { $t = [datetime]::ParseExact($StopAt, "H:mm", $null); if ($t -le (Get-Date)) { $t.AddDays(1) } else { $t } } else { [datetime]::Parse($StopAt) }
Log "start: $n spec(s), stop at $($stopTime.ToString('yyyy-MM-dd HH:mm')), supervise=$($Supervise.IsPresent)"
$restarts = 0
while ($true) {
  $t0 = Get-Date
  & $SysPython $NightCoder --config $mainCfg --yes --stop-at $StopAt
  $rc = $LASTEXITCODE
  $left = @(Get-ChildItem "$Work\inbox" -File -Filter *.md -ErrorAction SilentlyContinue)
  Log "NightCoder exited rc=$rc after $([int]((Get-Date) - $t0).TotalMinutes) min; $($left.Count) spec(s) left in the inbox"
  Summarize
  if (-not $Supervise) { break }
  if ($left.Count -eq 0) { Log "queue empty: done"; break }
  if ((Get-Date) -ge $stopTime.AddMinutes(-20)) { Log "stop time reached: done"; break }
  if ($restarts -ge $MaxRestarts) { Log "restart limit $MaxRestarts reached: done"; break }
  if (((Get-Date) - $t0).TotalMinutes -lt 2 -and $restarts -gt 0) { Log "NightCoder stopped again within 2 minutes (likely needs fresh start answers or usage reset): done"; break }
  $restarts++
  Log "restart $restarts/$MaxRestarts with the remaining specs (a failed spec is not retried)"
  Start-Sleep -Seconds 30
}
Summarize
