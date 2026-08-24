param(
    [string]$Version = "1.0.0",
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$RootDir = Split-Path -Parent $ScriptDir
Set-Location -LiteralPath $RootDir

if ([string]::IsNullOrWhiteSpace($Version) -or $Version -match '[\\/]') {
    Write-Host "Error: Version must be a non-empty release name without path separators." -ForegroundColor Red
    exit 1
}

$StagingFolder = "Switch-Collector-Portable"
$StagingParent = Join-Path $RootDir "staging"
$StagingDir = Join-Path $StagingParent $StagingFolder
$ReleaseDir = Join-Path $RootDir "release"
$ZipName = "Switch-Collector-v$Version-portable.zip"
$ZipPath = Join-Path $ReleaseDir $ZipName

$DistDir = Join-Path $RootDir "dist\Switch-Collector"
$ExeName = "Switch-Collector.exe"
$InternalName = "_internal"

# Explicit allowlist of loose files shipped alongside the frozen bundle.
$AllowedFiles = @(
    "start_collector.bat",
    "setup.bat",
    "switch_collector.py",
    "requirements.txt",
    "switch.example.txt",
    "README.md"
)

# Never allowed anywhere in the release, including inside _internal.
$CredentialPatterns = @(
    '^switch\.txt$',
    '^\.git$'
)

# Applied to every staged/archived path. Build artefacts such as *.pyc are
# expected inside _internal (frozen bytecode), so those are skipped there.
$ForbiddenPatterns = @(
    '^switch\.txt$',
    '^\.git$',
    '^__pycache__$',
    '^\.pytest_cache$',
    '^logs$',
    '^outputs$',
    '^outputs_clean$',
    '^docs$',
    '^tests?$',
    '\.pyc$',
    '\.log$',
    '\.xlsx$',
    '\.csv$'
)

# Only these stay active for frozen runtime files under _internal.
$InternalSkippedPatterns = @(
    '^__pycache__$',
    '^tests?$',
    '\.pyc$'
)

function Stop-Packaging {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Message
    )

    Write-Host "Error: $Message" -ForegroundColor Red
    if (Test-Path -LiteralPath $StagingDir) {
        Remove-Item -LiteralPath $StagingDir -Recurse -Force -ErrorAction SilentlyContinue
    }
    exit 1
}

# Returns the matching pattern for one path segment, or $null.
function Get-ForbiddenMatch {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Segment,
        [switch]$InsideBundle
    )

    foreach ($Pattern in $ForbiddenPatterns) {
        if ($InsideBundle -and ($InternalSkippedPatterns -contains $Pattern)) {
            continue
        }
        if ($Segment -match $Pattern) {
            return $Pattern
        }
    }
    return $null
}

# True when a relative path lives under the frozen _internal directory.
function Test-InsideBundle {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RelativePath
    )

    $Segments = @($RelativePath -split '[\\/]' | Where-Object { $_ })
    return ($Segments.Count -ge 2 -and $Segments[0] -eq $InternalName)
}

if (Test-Path -LiteralPath $StagingDir) {
    if ($Force) {
        Write-Host "Force specified: removing existing staging directory." -ForegroundColor Yellow
        Remove-Item -LiteralPath $StagingDir -Recurse -Force
    } elseif (@(Get-ChildItem -LiteralPath $StagingDir -Force).Count -gt 0) {
        Stop-Packaging "Staging directory already contains files. Use -Force to replace it: $StagingDir"
    }
}

if (Test-Path -LiteralPath $ZipPath) {
    if ($Force) {
        Write-Host "Force specified: removing existing release archive." -ForegroundColor Yellow
        Remove-Item -LiteralPath $ZipPath -Force
    } else {
        Stop-Packaging "Release archive already exists. Use -Force to replace it: $ZipPath"
    }
}

# The frozen bundle is mandatory: a portable release that needs Python is not
# portable, so fail loudly rather than shipping a half-package.
$DistExe = Join-Path $DistDir $ExeName
if (-not (Test-Path -LiteralPath $DistExe)) {
    Stop-Packaging "Cannot find dist/Switch-Collector/Switch-Collector.exe. Run .\scripts\build_exe.ps1 first."
}
$DistInternal = Join-Path $DistDir $InternalName
if (-not (Test-Path -LiteralPath $DistInternal)) {
    Stop-Packaging "Cannot find dist/Switch-Collector/_internal. Run .\scripts\build_exe.ps1 first."
}

foreach ($Directory in @($StagingParent, $ReleaseDir)) {
    if (-not (Test-Path -LiteralPath $Directory)) {
        New-Item -ItemType Directory -Path $Directory | Out-Null
    }
}
if (-not (Test-Path -LiteralPath $StagingDir)) {
    New-Item -ItemType Directory -Path $StagingDir | Out-Null
}

Write-Host "Copying frozen distribution from $DistDir..." -ForegroundColor Cyan
$DistEntries = @(Get-ChildItem -LiteralPath $DistDir -Force)
Write-Host "Scanned $($DistEntries.Count) entries in dist bundle" -ForegroundColor Gray
foreach ($Entry in $DistEntries) {
    Copy-Item -LiteralPath $Entry.FullName -Destination $StagingDir -Recurse -Force
    Write-Host "  Bundled: $($Entry.Name)" -ForegroundColor Gray
}

# Verify the frozen runtime really landed in staging.
$StagedExe = Join-Path $StagingDir $ExeName
if (-not (Test-Path -LiteralPath $StagedExe)) {
    Stop-Packaging "Bundled executable is missing from staging: $StagedExe"
}
$StagedInternal = Join-Path $StagingDir $InternalName
if (-not (Test-Path -LiteralPath $StagedInternal)) {
    Stop-Packaging "Bundled runtime directory _internal is missing from staging."
}
$InternalFileCount = @(Get-ChildItem -LiteralPath $StagedInternal -Recurse -File -Force).Count
Write-Host "Frozen runtime verified: $ExeName + $InternalName ($InternalFileCount files)" -ForegroundColor Green

Write-Host "Populating clean staging directory from the explicit allowlist..." -ForegroundColor Cyan
$MissingFiles = @()
foreach ($RelativePath in $AllowedFiles) {
    $SourcePath = Join-Path $RootDir $RelativePath
    $DestinationPath = Join-Path $StagingDir $RelativePath

    if (-not (Test-Path -LiteralPath $SourcePath)) {
        $MissingFiles += $RelativePath
        continue
    }

    Copy-Item -LiteralPath $SourcePath -Destination $DestinationPath -Force
    Write-Host "  Copied: $RelativePath" -ForegroundColor Gray
}

if ($MissingFiles.Count -gt 0) {
    Stop-Packaging "Required allowlisted files are missing: $($MissingFiles -join ', ')"
}

Write-Host "Running forbidden-entry guard gate..." -ForegroundColor Cyan
$ForbiddenEntries = @()
foreach ($Item in Get-ChildItem -LiteralPath $StagingDir -Recurse -Force) {
    $RelativePath = $Item.FullName.Substring($StagingDir.Length).TrimStart('\', '/')
    $InsideBundle = Test-InsideBundle -RelativePath $RelativePath
    foreach ($Segment in @($RelativePath -split '[\\/]')) {
        if (-not $Segment) { continue }
        $Matched = Get-ForbiddenMatch -Segment $Segment -InsideBundle:$InsideBundle
        if ($Matched) {
            $ForbiddenEntries += "$RelativePath (matched $Matched on segment '$Segment')"
            break
        }
    }
}

if ($ForbiddenEntries.Count -gt 0) {
    Stop-Packaging "Forbidden entries found in staging:`n$($ForbiddenEntries -join "`n")"
}
Write-Host "Staging guard passed: 0 forbidden entries." -ForegroundColor Green

Write-Host "Creating portable ZIP with Compress-Archive..." -ForegroundColor Cyan
Compress-Archive -Path $StagingDir -DestinationPath $ZipPath -Force
if (-not (Test-Path -LiteralPath $ZipPath) -or (Get-Item -LiteralPath $ZipPath).Length -eq 0) {
    Stop-Packaging "Compress-Archive did not create a non-empty ZIP archive."
}

Write-Host "Validating ZIP table of contents..." -ForegroundColor Cyan
Add-Type -AssemblyName System.IO.Compression.FileSystem
$Archive = [System.IO.Compression.ZipFile]::OpenRead($ZipPath)
try {
    $Entries = @($Archive.Entries | ForEach-Object { $_.FullName.Replace('\', '/') })
} finally {
    $Archive.Dispose()
}

if ($Entries.Count -eq 0) {
    Stop-Packaging "The ZIP archive has no table-of-contents entries."
}

$TopLevelFolders = @()
foreach ($Entry in $Entries) {
    $Parts = @($Entry.TrimEnd('/').Split('/') | Where-Object { $_ })
    if ($Parts.Count -gt 0 -and $TopLevelFolders -notcontains $Parts[0]) {
        $TopLevelFolders += $Parts[0]
    }
}
if ($TopLevelFolders.Count -ne 1 -or $TopLevelFolders[0] -ne $StagingFolder) {
    Stop-Packaging "The archive must contain exactly one top-level folder: $StagingFolder"
}

$ArchiveForbiddenEntries = @()
foreach ($Entry in $Entries) {
    $InsideBundle = Test-InsideBundle -RelativePath $Entry
    foreach ($Segment in @($Entry -split '[\\/]')) {
        if (-not $Segment) { continue }
        $Matched = Get-ForbiddenMatch -Segment $Segment -InsideBundle:$InsideBundle
        if ($Matched) {
            $ArchiveForbiddenEntries += "$Entry (matched $Matched on segment '$Segment')"
            break
        }
    }
}
if ($ArchiveForbiddenEntries.Count -gt 0) {
    Remove-Item -LiteralPath $ZipPath -Force -ErrorAction SilentlyContinue
    Stop-Packaging "Forbidden entries found in ZIP:`n$($ArchiveForbiddenEntries -join "`n")"
}

# The frozen runtime must actually be inside the archive. Compress-Archive does
# not emit explicit directory entries, so _internal is proven by a file beneath it.
$RequiredEntries = @(
    "$StagingFolder/$ExeName"
)
foreach ($RelativePath in $AllowedFiles) {
    $RequiredEntries += "$StagingFolder/$RelativePath"
}
$MissingArchiveFiles = @()
foreach ($RequiredEntry in $RequiredEntries) {
    if ($Entries -notcontains $RequiredEntry) {
        $MissingArchiveFiles += $RequiredEntry
    }
}
if ($MissingArchiveFiles.Count -gt 0) {
    Remove-Item -LiteralPath $ZipPath -Force -ErrorAction SilentlyContinue
    Stop-Packaging "Required files are missing from the ZIP:`n$($MissingArchiveFiles -join "`n")"
}

$InternalEntries = @($Entries | Where-Object { $_.StartsWith("$StagingFolder/$InternalName/") })
if ($InternalEntries.Count -eq 0) {
    Remove-Item -LiteralPath $ZipPath -Force -ErrorAction SilentlyContinue
    Stop-Packaging "The frozen runtime directory $InternalName is missing from the ZIP."
}

# The example template must ship; the real credential file must not.
$TemplateEntry = "$StagingFolder/switch.example.txt"
if ($Entries -notcontains $TemplateEntry) {
    Stop-Packaging "switch.example.txt is required so operators get a safe credential template."
}
$CredentialEntry = "$StagingFolder/switch.txt"
if ($Entries -contains $CredentialEntry) {
    Remove-Item -LiteralPath $ZipPath -Force -ErrorAction SilentlyContinue
    Stop-Packaging "Credential file switch.txt must never be included in a release archive."
}

Write-Host "Removing staging directory..." -ForegroundColor Cyan
Remove-Item -LiteralPath $StagingDir -Recurse -Force -ErrorAction SilentlyContinue

$ArchiveSizeMB = [math]::Round((Get-Item -LiteralPath $ZipPath).Length / 1MB, 2)
$BundleFileCount = @($Entries | Where-Object { -not $_.EndsWith('/') }).Count
Write-Host ""
Write-Host "------------------------------------------------------------" -ForegroundColor Cyan
Write-Host "  Archive      : $ZipPath" -ForegroundColor Green
Write-Host "  Size         : $ArchiveSizeMB MB ($BundleFileCount files)" -ForegroundColor Green
Write-Host "  Runtime      : $ExeName + $InternalName ($InternalFileCount files, zero-install)" -ForegroundColor Green
Write-Host "  Forbidden    : 0 (staging and ZIP guards both passed)" -ForegroundColor Green
Write-Host "  Credentials  : switch.txt excluded, switch.example.txt included" -ForegroundColor Green
Write-Host "------------------------------------------------------------" -ForegroundColor Cyan
Write-Host "Success! Created $ZipPath" -ForegroundColor Green
