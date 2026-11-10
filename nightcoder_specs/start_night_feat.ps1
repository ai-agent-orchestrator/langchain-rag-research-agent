<#
  start_night_feat.ps1 - start_night.ps1 (v2) adapted so nothing needs editing day to day:
    * base branch = the branch currently checked out in the repo this script lives in (-BaseBranch auto);
      it must be pushed (local HEAD == origin/<branch>), otherwise the script stops and says "git push".
    * queue = every spec under nightcoder_specs\ whose header has "status: ready", sorted by "order: <n>"
      (then file name). Specs with "repo: <other>" are skipped. Specs whose _REPORT_ file already exists on
      the base branch are skipped as done. Add a spec = drop a file with "status: ready"; no script edit.
    * test gate excludes memvid-marked tests (decision 2026-11-10); memvid tests run once for the record.

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
  [string]$BaseBranch = "auto",
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
  [switch]$NoStart
)
$ErrorActionPreference = "Continue"   # native tools write to stderr; we judge by exit codes only
$utf8 = New-Object System.Text.UTF8Encoding $false
function Step($n, $msg) { Write-Host "`n[$n] $msg" -ForegroundColor Cyan }
function Fail($msg, $fix) { Write-Host "STOP: $msg" -ForegroundColor Red; if ($fix) { Write-Host "FIX:  $fix" -ForegroundColor Yellow }; exit 1 }
function Ok($msg) { Write-Host "  ok  $msg" -ForegroundColor Green }

# backlog order (README table); smoke is separate
# queue is built from spec headers in step 6 (status: ready / order: / repo:)

Step 0 "base branch"
$Repo = Split-Path $PSScriptRoot -Parent
if ($BaseBranch -eq "auto") {
  $BaseBranch = (git -C $Repo rev-parse --abbrev-ref HEAD).Trim()
  if ($LASTEXITCODE -ne 0 -or -not $BaseBranch -or $BaseBranch -eq "HEAD") { Fail "could not read the current branch of $Repo" "git -C $Repo checkout <your day branch>" }
}
git -C $Repo fetch origin $BaseBranch --quiet
if ($LASTEXITCODE -ne 0) { Fail "origin/$BaseBranch not found (branch not pushed yet?)" "git -C $Repo push -u origin $BaseBranch" }
$localHead = (git -C $Repo rev-parse HEAD).Trim(); $remoteHead = (git -C $Repo rev-parse "origin/$BaseBranch").Trim()
if ($localHead -ne $remoteHead) {
  $ahead = (git -C $Repo rev-list --count "origin/$BaseBranch..HEAD").Trim()
  if ($ahead -ne "0") { Fail "$ahead local commit(s) on $BaseBranch are not pushed; the lane would not see them" "git -C $Repo push origin $BaseBranch" }
  Write-Host "  note: origin/$BaseBranch is ahead of your local copy; the lane uses origin (git pull later)" -ForegroundColor Yellow
}
Ok "base = origin/$BaseBranch ($($remoteHead.Substring(0,7)))"

Step 1 "lane folder and branch"
if (-not (Test-Path "$Lane\.git")) {
  git clone https://github.com/ai-agent-orchestrator/langchain-rag-research-agent $Lane
  if ($LASTEXITCODE -ne 0) { Fail "clone failed" "check the network, then run again" }
}
Set-Location $Lane
$dirtyNow = git -C $Lane status --porcelain
if ($dirtyNow) { git -C $Lane status --short; Fail "lane folder has uncommitted changes" "git -C $Lane stash push -u -m before-night   (or delete the files listed above)" }
git fetch origin $BaseBranch --quiet
if ($LASTEXITCODE -ne 0) { Fail "git fetch failed" "check the network" }
git checkout -B $Branch origin/$BaseBranch --quiet
if ($LASTEXITCODE -ne 0) { Fail "could not put $Branch on origin/$BaseBranch (is the branch pushed?)" "" }
# NightCoder fast-forwards the lane branch to config.base by NAME; a fresh clone only has origin/<base>, so create the local branch too
git branch -f $BaseBranch origin/$BaseBranch --quiet
if ($LASTEXITCODE -ne 0) { Fail "could not create local branch $BaseBranch" "git -C $Lane branch -f $BaseBranch origin/$BaseBranch" }
Ok ("$Branch = " + (git log --oneline -1))

Step 2 "test baseline"
if (-not (Test-Path $Python)) { Fail "python not found: $Python" "pass -Python <path to a venv python with the test deps>" }
# Gate = every test except the memvid-marked ones (decision 2026-11-10: development store is Chroma;
# memvid writes fail intermittently on this PC). memvid tests still run below, for the record only.
& $Python -m pytest -q -p no:cacheprovider -m "not memvid"
if ($LASTEXITCODE -ne 0) {
  Write-Host "  retrying once (Windows file locks cause rare one-off failures)..." -ForegroundColor Yellow
  & $Python -m pytest -q -p no:cacheprovider -m "not memvid"
  if ($LASTEXITCODE -ne 0) { Fail "tests (without memvid) are not green twice in a row" "send the output above to Claude; do not start the night" }
}
Ok "tests green (memvid excluded from the gate)"
New-Item -ItemType Directory -Force $Work | Out-Null
$memvidLog = Join-Path $Work "memvid-record.log"
& $Python -m pytest -q -p no:cacheprovider -m memvid *> $memvidLog
Write-Host ("  info memvid tests (record only, not a gate): exit " + $LASTEXITCODE + " -> " + $memvidLog)

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
  $c.workdir = ($Lane -replace '\\','/'); $c.branch = $Branch; $c.base = "origin/$BaseBranch"   # nc2 runs git merge --ff-only <base>; use the remote ref, which every fresh clone has
  $c.inbox = ($inbox -replace '\\','/'); $c.outbox = ($outbox -replace '\\','/'); $c.state_dir = ($state -replace '\\','/')
  $c.test_cmd = @(($Python -replace '\\','/'), "-m", "pytest", "-q", "-p", "no:cacheprovider", "-m", "not memvid")
  $c.codex_cmd = $wrapped; $c.max_tasks = $maxTasks
  if ($c.PSObject.Properties.Name -contains "codex_timeout_min") { $c.codex_timeout_min = 90 }
  return $c
}
New-Item -ItemType Directory -Force "$Work\inbox","$Work\outbox","$Work\state","$Work\smoke\inbox","$Work\smoke\outbox","$Work\smoke\state" | Out-Null
$mainCfg = Join-Path $Work "nc2.lane.json"; $smokeCfg = Join-Path $Work "nc2.smoke.json"
[IO.File]::WriteAllText($mainCfg, ((LaneConfig "$Work\inbox" "$Work\outbox" "$Work\state" 30) | ConvertTo-Json -Depth 8), $utf8)
[IO.File]::WriteAllText($smokeCfg, ((LaneConfig "$Work\smoke\inbox" "$Work\smoke\outbox" "$Work\state" 1) | ConvertTo-Json -Depth 8), $utf8)
Ok "codex_cmd: $($wrapped -join ' ')"
Ok $mainCfg
if ($DryRun) { Write-Host "`nDry run: stopped before the smoke run." -ForegroundColor Yellow; exit 0 }

if (-not $SkipSmoke) {
  Step 5 "smoke run through NightCoder (1-2 min)"
  Get-ChildItem "$Work\smoke\inbox" -File -ErrorAction SilentlyContinue | Remove-Item -Force
  Get-ChildItem "$Work\smoke\outbox" -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force
  Copy-Item "$Lane\nightcoder_specs\smoke\rra-smoke.md" "$Work\smoke\inbox\000-rra-smoke.md"
  Write-Host "  NightCoder asks its start questions now (same state folder as the real run, so --yes can reuse them)." -ForegroundColor Yellow
  & $SysPython $NightCoder --config $smokeCfg --stop-at ((Get-Date).AddMinutes(20).ToString("HH:mm"))
  $patches = Get-ChildItem "$Work\smoke\outbox" -Recurse -Filter *.patch -ErrorAction SilentlyContinue
  if (-not $patches) {
    $report = Get-ChildItem "$Work\smoke\outbox" -Recurse -Filter REPORT.md -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($report) { Write-Host "---- smoke REPORT (last 25 lines) ----"; Get-Content $report.FullName -Encoding UTF8 -Tail 25 }
    if (Test-Path $wrapLog) { Write-Host "---- wrap.log (last 3) ----"; Get-Content $wrapLog -Tail 3 }
    $hint = "send the REPORT and wrap.log lines above to Claude (wrap.log shows the coder exit code and whether anything changed)"
    Fail "smoke run produced no patch" $hint
  }
  Ok "smoke passed: the coder edited, committed and NightCoder collected a patch"
  git -C $Lane checkout -B $Branch origin/$BaseBranch --quiet   # drop the smoke commit
}

function HeaderValue([string[]]$lines, [string]$key) {
  foreach ($l in $lines) { if ($l -match ('^\s*' + $key + '\s*:\s*(.*)$')) { return ([string]$Matches[1]).Trim() } }
  return ""
}
Step 6 "queue"
$Only = @($Only | ForEach-Object { $_ -split ',' } | ForEach-Object { $_.Trim() } | Where-Object { $_ })   # "-Only a,b" arrives as one string via -File
Get-ChildItem "$Work\inbox" -File -Filter *.md -ErrorAction SilentlyContinue | Remove-Item -Force
$repoName = Split-Path $Lane -Leaf
$cands = @()
foreach ($f in (Get-ChildItem "$Lane\nightcoder_specs" -Recurse -File -Filter *.md | Where-Object { $_.FullName -notmatch '\\smoke\\' -and $_.Name -ne 'README.md' })) {
  $head = @(Get-Content $f.FullName -Encoding UTF8 -TotalCount 15)
  $status = HeaderValue $head 'status'
  if ($status -ne 'ready') { continue }   # no status / hold / done -> never queued
  $repoHdr = HeaderValue $head 'repo'
  if ($repoHdr -and $repoHdr -ne 'research') { Write-Host "  skip (repo: $repoHdr) $($f.Name)"; continue }
  $tmp = 0; $ordN = if ([int]::TryParse((HeaderValue $head 'order'), [ref]$tmp)) { $tmp } else { 9999 }
  $cands += [pscustomobject]@{ File = $f; Order = $ordN }
}
$n = 0
foreach ($c in ($cands | Sort-Object Order, @{ Expression = { $_.File.Name } })) {
  $name = $c.File.BaseName
  if ($Only.Count -gt 0 -and -not ($Only | Where-Object { $name -like $_ })) { continue }
  $lines = Get-Content $c.File.FullName -Encoding UTF8
  $filesLine = ($lines | Where-Object { $_ -match '^files:' } | Select-Object -First 1)
  $report = if ($filesLine) { ($filesLine -replace '^files:\s*','').Split(',') | ForEach-Object { $_.Trim() } | Where-Object { $_ -match '_REPORT_' } | Select-Object -First 1 }
  if (-not $report) { Write-Host "  warn (no _REPORT_ file in files:, cannot detect done) $name" -ForegroundColor Yellow }
  if ($report -and (Test-Path (Join-Path $Lane $report))) { Write-Host "  skip (done on $BaseBranch; set status: done) $name"; continue }
  $n++
  $dest = Join-Path "$Work\inbox" ("{0:D3}-{1}.md" -f $n, $name)
  [IO.File]::WriteAllLines($dest, ($lines | Where-Object { $_ -notmatch '^\s*(after|status|order|repo)\s*:' }), $utf8)
  Write-Host "  queued $(Split-Path $dest -Leaf)  (order $($c.Order))"
}
if ($n -eq 0) { Fail "nothing to queue" "no spec has status: ready (or all are done on $BaseBranch, or -Only matched nothing)" }

Step 7 "start"
if (Get-Command powercfg -ErrorAction SilentlyContinue) {
  powercfg /change standby-timeout-ac 0
  powercfg /change hibernate-timeout-ac 0
}
if ($ScreenOff -and $IsWindows -ne $false) {
  Start-Job { Start-Sleep 30; (Add-Type '[DllImport("user32.dll")]public static extern int SendMessage(int hWnd,int hMsg,int wParam,int lParam);' -Name ScreenOff -Namespace Win32 -PassThru)::SendMessage(-1,0x0112,0xF170,2) } | Out-Null
  Write-Host "  display turns off in 30 seconds"
}
if ($NoStart) { Write-Host "`n-NoStart: queue ready, NightCoder not started." -ForegroundColor Yellow; exit 0 }
Write-Host "  results: $Work\outbox   (keep this window open)" -ForegroundColor Green
& $SysPython $NightCoder --config $mainCfg --yes --stop-at $StopAt
