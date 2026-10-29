#requires -Version 5.1
param(
    [ValidateSet('start', 'stop', 'status', 'test', 'evaluate')]
    [string]$Action = 'start',
    [ValidateSet('mock', 'ollama')]
    [string]$Provider,
    [ValidateSet('qwen2.5-coder:7b', 'qwen2.5-coder:3b')]
    [string]$Model,
    [string]$Case
)

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$runtimeRoot = Join-Path $projectRoot '.runtime'
$statePath = Join-Path $runtimeRoot 'services.json'
$logRoot = Join-Path $runtimeRoot 'logs'
$pythonExecutable = Join-Path $projectRoot '.venv/Scripts/python.exe'
$apiUrl = 'http://127.0.0.1:8000'

function Read-JsonEndpoint([string]$Url) {
    try {
        if ($PSVersionTable.PSVersion.Major -ge 7) {
            Invoke-RestMethod -Uri $Url -TimeoutSec 2 -NoProxy -MaximumRedirection 0
        } else {
            Invoke-RestMethod -Uri $Url -TimeoutSec 2 -MaximumRedirection 0
        }
    }
    catch { return $null }
}

function Get-OwnedProcess($Record) {
    if ($null -eq $Record) { return $null }
    $running = Get-Process -Id $Record.pid -ErrorAction SilentlyContinue
    if ($running -and $running.ProcessName -eq $Record.name -and
        $running.StartTime.ToUniversalTime().Ticks.ToString() -eq $Record.started_ticks) {
        return $running
    }
    return $null
}

function Process-Record($Process) {
    return @{pid=$Process.Id; name=$Process.ProcessName;
        started_ticks=$Process.StartTime.ToUniversalTime().Ticks.ToString()}
}

function Save-State {
    $state | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $statePath -Encoding utf8
}

function Stop-Owned($Record) {
    $running = Get-OwnedProcess $Record
    if ($running) {
        Stop-Process -Id $running.Id
        $running.WaitForExit(5000) | Out-Null
    }
}

function Wait-Endpoint([string]$Url, $Process) {
    for ($attempt=0; $attempt -lt 20; $attempt++) {
        if ($Process.HasExited) { throw "Service exited. Inspect $logRoot" }
        if (Read-JsonEndpoint $Url) { return }
        Start-Sleep -Milliseconds 500
    }
    throw "Service did not become ready: $Url. Inspect $logRoot"
}

Push-Location $projectRoot
try {
    $state = @{project_root=$projectRoot; api=$null; api_launcher=$null; ollama=$null}
    if (Test-Path -LiteralPath $statePath) {
        $savedState = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
        foreach ($property in $savedState.PSObject.Properties) {
            $state[$property.Name] = $property.Value
        }
        if ($state.project_root -ne $projectRoot) { throw 'Service state belongs to another checkout.' }
    }
    if ($Action -eq 'stop') {
        Stop-Owned $state.api
        Stop-Owned $state.api_launcher
        Stop-Owned $state.ollama
        if (Test-Path -LiteralPath $statePath) { Remove-Item -LiteralPath $statePath }
        Write-Host 'Project services stopped. Models and other Ollama instances are retained.'
        exit 0
    }
    if (-not (Test-Path -LiteralPath $pythonExecutable)) {
        throw 'Create .venv and install .[dev] first; see README.md.'
    }
    if ($Action -eq 'test') {
        & $pythonExecutable -m pytest
        exit $LASTEXITCODE
    }
    if ($Provider) { $env:SECUREQUERY_PROVIDER = $Provider }
    if ($Model) { $env:SECUREQUERY_MODEL = $Model }
    $settingsJson = & $pythonExecutable -m app.cli_config
    if ($LASTEXITCODE -ne 0) { throw 'Invalid configuration; check .env against .env.example.' }
    $settings = $settingsJson | ConvertFrom-Json
    $ollamaUrl = $settings.ollama_url
    if ($Action -eq 'status') {
        $health = Read-JsonEndpoint "$apiUrl/api/v1/health"
        $version = Read-JsonEndpoint "$ollamaUrl/api/version"
        [PSCustomObject]@{
            ConfiguredProvider=$settings.provider; ConfiguredModel=$settings.model
            ConfiguredDemo=$settings.demo
            ApiUrl=$apiUrl; ApiOwned=[bool](Get-OwnedProcess $state.api)
            ApiStatus= $(if ($health) {$health.status} else {'stopped'})
            RunningModel= $(if ($health) {$health.provider.model} else {'-'})
            RunningDemo= $(if ($health) {$health.demo_mode} else {'-'})
            OllamaUrl=$ollamaUrl; OllamaOwned=[bool](Get-OwnedProcess $state.ollama)
            OllamaVersion= $(if ($version) {$version.version} else {'stopped'})
            ModelsDirectory=(Join-Path $runtimeRoot 'models'); LogsDirectory=$logRoot
            DatabaseGateway='not connected; candidate generation only'
        } | Format-List
        exit 0
    }
    if ($Action -eq 'evaluate') {
        $evaluationArgs = @('-m', 'scripts.evaluate', '--provider', $settings.provider, '--model', $settings.model)
        if ($Case) { $evaluationArgs += @('--case', $Case) }
        & $pythonExecutable @evaluationArgs
        exit $LASTEXITCODE
    }

    if ($settings.provider -eq 'ollama' -and ([Uri]$ollamaUrl).Port -eq 8000) {
        throw 'Ollama port must differ from the fixed API port 8000.'
    }
    New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
    $apiProcess = Get-OwnedProcess $state.api
    if ($apiProcess) {
        if ($state.config_hash -ne $settings.config_hash) {
            throw 'Configuration changed. Run: powershell -NoProfile -ExecutionPolicy Bypass -File ./run.ps1 stop, then start again.'
        }
        $health = Read-JsonEndpoint "$apiUrl/api/v1/health"
        if (-not $health) { throw 'Owned API is unresponsive; inspect logs, then stop/start.' }
        Write-Host "Already running: $apiUrl ($($health.provider.model), $($health.status))"
        exit 0
    }
    if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) {
        throw 'Port 8000 belongs to an unmanaged process; this command will not stop it.'
    }
    if ((Get-OwnedProcess $state.ollama) -and $state.ollama_url -ne $ollamaUrl) {
        throw 'Ollama address changed. Run: powershell -NoProfile -ExecutionPolicy Bypass -File ./run.ps1 stop, then start again.'
    }
    $state.provider = $settings.provider
    $state.model = $settings.model
    $state.ollama_url = $ollamaUrl
    $state.config_hash = $settings.config_hash
    if ($settings.provider -eq 'ollama') {
        $ollamaExecutable = Join-Path $env:LOCALAPPDATA 'Programs/Ollama/ollama.exe'
        if (-not (Test-Path -LiteralPath $ollamaExecutable)) {
            $ollamaExecutable = (Get-Command ollama -ErrorAction Stop).Source
        }
        $ollamaProcess = Get-OwnedProcess $state.ollama
        if (-not $ollamaProcess) {
            $port = ([Uri]$ollamaUrl).Port
            if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
                throw "Port $port belongs to an unmanaged Ollama. Choose a project port in .env."
            }
            $env:OLLAMA_HOST = $ollamaUrl
            $env:OLLAMA_MODELS = Join-Path $runtimeRoot 'models'
            $env:OLLAMA_NO_CLOUD = '1'
            $env:OLLAMA_NUM_PARALLEL = '1'
            $env:OLLAMA_MAX_LOADED_MODELS = '1'
            $env:OLLAMA_CONTEXT_LENGTH = '4096'
            $ollamaProcess = Start-Process -FilePath $ollamaExecutable -ArgumentList 'serve' -WindowStyle Hidden `
                -RedirectStandardOutput (Join-Path $logRoot 'ollama.stdout.log') `
                -RedirectStandardError (Join-Path $logRoot 'ollama.stderr.log') -PassThru
            $state.ollama = Process-Record $ollamaProcess
            Save-State
            Wait-Endpoint "$ollamaUrl/api/version" $ollamaProcess
        }
        $tags = Read-JsonEndpoint "$ollamaUrl/api/tags"
        if (-not $tags) { throw "Project Ollama did not respond. Inspect $logRoot, then stop/start." }
        if ($settings.model -notin @($tags.models.name)) {
            throw "Configured model $($settings.model) is missing. Project Ollama remains at $ollamaUrl; use the pull instructions in docs/usage-guide.md, then start again. No download or fallback was performed."
        }
    }
    $apiProcess = Start-Process -FilePath $pythonExecutable -ArgumentList '-m','app' -WorkingDirectory $projectRoot -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logRoot 'api.stdout.log') `
        -RedirectStandardError (Join-Path $logRoot 'api.stderr.log') -PassThru
    $state.api = Process-Record $apiProcess
    Save-State
    Wait-Endpoint "$apiUrl/api/v1/health" $apiProcess
    # A Windows venv python.exe launcher may spawn the actual listener as a child.
    # Track both so stop does not leave the API child behind.
    $apiListener = Get-NetTCPConnection -LocalPort 8000 -State Listen | Select-Object -First 1
    if ($apiListener.OwningProcess -ne $apiProcess.Id) {
        $child = Get-CimInstance Win32_Process -Filter "ProcessId=$($apiListener.OwningProcess)"
        if ($child.ParentProcessId -ne $apiProcess.Id) { throw 'API listener ownership could not be verified.' }
        $state.api_launcher = Process-Record $apiProcess
        $state.api = Process-Record (Get-Process -Id $apiListener.OwningProcess)
        Save-State
    }
    Write-Host "Ready: $apiUrl"
    Write-Host "Provider: $($settings.provider) | Model: $($settings.model) | Ollama: $ollamaUrl"
    Write-Host "Logs: $logRoot"
    Write-Host 'Use run.ps1 status / stop. Model files are never downloaded or deleted by this command.'
} finally {
    Pop-Location
}
